"""CI guard against blocking the FastAPI event loop and unowned concurrency.

Blocking work must go through ``run_in_pool(pool, fn, *args)`` (see
``common_module/blocking_io.py``) or async Redis (``CacheManager.a*`` /
``try_a*``). This AST scan flags the patterns that reintroduce the problem.

To silence a deliberate hit, add ``# concurrency: allowed`` (with a reason) on
a line of the call, or add an entry to ``event_loop_guard_allowlist.txt``.
"""

import ast
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pytest

SERVER_ROOT = Path(__file__).resolve().parents[3]
ALLOWLIST_PATH = Path(__file__).resolve().parent / 'event_loop_guard_allowlist.txt'

EXCLUDED_SEGMENTS = {
    'tests',
    'test',
    'alembic',
    'background_jobs',
    'scripts',
    'venv',
    'test_venv',
    '.venv',
    '__pycache__',
    'node_modules',
    'build',
    'dist',
}
PRAGMA = '# concurrency: allowed'

SYNC_CACHE_METHODS = {
    'add',
    'get_str',
    'get_int',
    'pop_str',
    'incr_with_expiry',
    'remove',
    'invalidate_query',
    'publish',
    'subscribe',
    'xadd',
    'xgroup_create',
    'xread_group',
    'xack',
    'xpending_range',
    'xautoclaim',
}
REDIS_CONSTRUCTORS = {
    'redis.Redis',
    'redis.StrictRedis',
    'redis.from_url',
    'redis.Redis.from_url',
    'redis.StrictRedis.from_url',
}
SYNC_HTTP_CALLS = {
    'httpx.get',
    'httpx.post',
    'httpx.put',
    'httpx.patch',
    'httpx.delete',
    'httpx.head',
    'httpx.options',
    'httpx.request',
    'httpx.stream',
    'httpx.Client',
    'urllib.request.urlopen',
}
SUBPROCESS_CALLS = {
    'subprocess.run',
    'subprocess.call',
    'subprocess.check_call',
    'subprocess.check_output',
    'subprocess.getoutput',
    'subprocess.getstatusoutput',
    'subprocess.Popen',
    'os.system',
    'os.popen',
}


@dataclass(frozen=True)
class Violation:
    relpath: str
    qualname: str
    rule: str
    lineno: int


def _collect_aliases(tree: ast.AST) -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    aliases[a.asname] = a.name
                else:
                    top = a.name.split('.')[0]
                    aliases[top] = top
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for a in node.names:
                if a.name != '*':
                    aliases[a.asname or a.name] = f'{node.module}.{a.name}'
    return aliases


def _dotted(node: ast.AST, aliases: Dict[str, str]) -> Optional[str]:
    """Resolve a Name/Attribute chain to a dotted name, applying import aliases."""
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value, aliases)
        return f'{base}.{node.attr}' if base else None
    return None


def _final_name(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


class _Scanner(ast.NodeVisitor):
    def __init__(self, lines: List[str], aliases: Dict[str, str], relpath: str):
        self.lines = lines
        self.aliases = aliases
        self.relpath = relpath
        self.scope: List[str] = []
        self.in_async = False
        self.found: List[Violation] = []

    # -- helpers
    def _qualname(self) -> str:
        return '.'.join(self.scope) or '<module>'

    def _report(self, node: ast.AST, rule: str) -> None:
        start = node.lineno
        end = getattr(node, 'end_lineno', None) or start
        if any(PRAGMA in self.lines[i - 1] for i in range(start, end + 1)):
            return
        self.found.append(Violation(self.relpath, self._qualname(), rule, start))

    # -- scope handling
    def _visit_function(self, node) -> None:
        for d in node.decorator_list:
            self.visit(d)
        args = node.args
        for d in args.defaults + [d for d in args.kw_defaults if d is not None]:
            self.visit(d)
        self.scope.append(node.name)
        prev = self.in_async
        self.in_async = isinstance(node, ast.AsyncFunctionDef)
        for stmt in node.body:
            self.visit(stmt)
        self.in_async = prev
        self.scope.pop()

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def visit_Lambda(self, node: ast.Lambda) -> None:
        prev = self.in_async
        self.in_async = False
        self.visit(node.body)
        self.in_async = prev

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for d in node.decorator_list + node.bases:
            self.visit(d)
        self.scope.append(node.name)
        prev = self.in_async
        self.in_async = False
        for stmt in node.body:
            self.visit(stmt)
        self.in_async = prev
        self.scope.pop()

    # -- rules
    def visit_Await(self, node: ast.Await) -> None:
        v = node.value
        if (
            isinstance(v, ast.Call)
            and isinstance(v.func, ast.Attribute)
            and v.func.attr == 'cancel'
            and not v.args  # `await super().cancel(frame)` is an async method
            and not (
                isinstance(v.func.value, ast.Call)
                and _final_name(v.func.value.func) == 'super'
            )
        ):
            self._report(node, 'await-cancel')
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        dotted = _dotted(func, self.aliases)
        final = _final_name(func)

        if dotted in ('asyncio.create_task', 'asyncio.ensure_future'):
            self._report(node, 'create-task')
        elif isinstance(func, ast.Attribute) and func.attr == 'create_task':
            recv = func.value
            name = _final_name(recv)
            is_loop = name is not None and 'loop' in name.lower()
            if isinstance(recv, ast.Call):
                is_loop = is_loop or _final_name(recv.func) in (
                    'get_event_loop',
                    'get_running_loop',
                )
            if is_loop:
                self._report(node, 'create-task')

        if dotted == 'asyncio.to_thread' or (
            isinstance(func, ast.Attribute) and func.attr == 'run_in_executor'
        ):
            self._report(node, 'to-thread')

        if (
            dotted == 'threading.Thread'
            or final == 'ThreadPoolExecutor'
            or (dotted or '').endswith('.ThreadPoolExecutor')
        ):
            self._report(node, 'thread')

        if self.in_async:
            self._check_blocking(node, func, dotted)
        self.generic_visit(node)

    def _check_blocking(self, node: ast.Call, func: ast.AST, dotted: Optional[str]):
        blocking = False
        if dotted == 'time.sleep':
            blocking = True
        elif dotted and dotted.startswith('requests.'):
            blocking = True
        elif (
            isinstance(func, ast.Name)
            and func.id == 'open'
            and 'open' not in self.aliases
        ):
            blocking = True
        elif dotted in REDIS_CONSTRUCTORS:
            blocking = True
        elif dotted in SYNC_HTTP_CALLS or dotted in SUBPROCESS_CALLS:
            blocking = True
        elif isinstance(func, ast.Attribute) and func.attr in SYNC_CACHE_METHODS:
            recv = _final_name(func.value)
            if recv is not None and 'cache' in recv.lower():
                blocking = True
        if blocking:
            self._report(node, 'blocking-in-async')


def find_violations(source: str, relpath: str) -> List[Violation]:
    tree = ast.parse(source)
    scanner = _Scanner(source.splitlines(), _collect_aliases(tree), relpath)
    scanner.visit(tree)
    return scanner.found


def iter_server_files(root: Path = SERVER_ROOT):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_SEGMENTS)
        for fn in sorted(filenames):
            if not fn.endswith('.py'):
                continue
            if fn.startswith('test_') or fn.endswith('_test.py') or fn == 'conftest.py':
                continue
            yield Path(dirpath) / fn


def scan_repo(root: Path = SERVER_ROOT) -> List[Violation]:
    out: List[Violation] = []
    for path in iter_server_files(root):
        rel = path.relative_to(root).as_posix()
        # No try/except: a file the guard can't parse must fail loudly, not
        # silently escape the check.
        out.extend(find_violations(path.read_text(encoding='utf-8'), rel))
    return out


_ENTRY_RE = re.compile(
    r'^[^:\s][^\s]*::[^\s:]+(?:\.[^\s:]+)*::[a-z-]+$|^[^\s]+::<module>::[a-z-]+$'
)


def parse_allowlist(path: Path = ALLOWLIST_PATH) -> List[Tuple[str, str, str]]:
    entries = []
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        parts = line.split('::')
        if len(parts) != 3 or not all(parts) or not _ENTRY_RE.match(line):
            raise ValueError(f'bad allowlist line: {raw!r}')
        entries.append((parts[0], parts[1], parts[2]))
    return entries


# --------------------------------------------------------------------------
# Scanner unit tests
# --------------------------------------------------------------------------


def _rules(src: str) -> List[str]:
    return [v.rule for v in find_violations(src, 'x.py')]


@pytest.mark.parametrize(
    'src',
    [
        'import asyncio\nasync def f():\n    asyncio.create_task(g())\n',
        'from asyncio import create_task as ct\ndef f():\n    ct(g())\n',
        'from asyncio import create_task\ndef f():\n    create_task(g())\n',
        'import asyncio as aio\ndef f():\n    aio.ensure_future(g())\n',
        'def f(loop):\n    loop.create_task(g())\n',
        'def f(self):\n    self._event_loop.create_task(g())\n',
        'import asyncio\ndef f():\n    asyncio.get_event_loop().create_task(g())\n',
        'import asyncio\ndef f():\n    asyncio.get_running_loop().create_task(g())\n',
    ],
)
def test_create_task_positive(src):
    assert _rules(src) == ['create-task']


@pytest.mark.parametrize(
    'src',
    [
        'import asyncio\nasync def f():\n    await asyncio.to_thread(g)\n',
        'from asyncio import to_thread as tt\nasync def f():\n    await tt(g)\n',
        'async def f(loop):\n    await loop.run_in_executor(None, g)\n',
        'async def f(self):\n    await self.x.run_in_executor(None, g)\n',
    ],
)
def test_to_thread_positive(src):
    assert _rules(src) == ['to-thread']


@pytest.mark.parametrize(
    'src',
    [
        'import threading\ndef f():\n    threading.Thread(target=g)\n',
        'from threading import Thread\ndef f():\n    Thread(target=g)\n',
        'import threading as t\ndef f():\n    t.Thread(target=g)\n',
        'import concurrent.futures\ndef f():\n    concurrent.futures.ThreadPoolExecutor(2)\n',
        'import concurrent.futures as cf\ndef f():\n    cf.ThreadPoolExecutor(2)\n',
        'from concurrent.futures import ThreadPoolExecutor\ndef f():\n    ThreadPoolExecutor(2)\n',
        'from concurrent.futures import ThreadPoolExecutor as TPE\ndef f():\n    TPE(2)\n',
    ],
)
def test_thread_positive(src):
    assert 'thread' in _rules(src)


def test_await_cancel_positive():
    assert _rules('async def f(t):\n    await t.cancel()\n') == ['await-cancel']
    assert _rules('async def f(t):\n    t.cancel()\n') == []
    assert _rules('async def f(self, fr):\n    await super().cancel(fr)\n') == []


@pytest.mark.parametrize(
    'src',
    [
        'import time\nasync def f():\n    time.sleep(1)\n',
        'from time import sleep\nasync def f():\n    sleep(1)\n',
        'import time as t\nasync def f():\n    t.sleep(1)\n',
        'import requests\nasync def f():\n    requests.get("u")\n',
        'import requests as r\nasync def f():\n    r.post("u")\n',
        'from requests import get\nasync def f():\n    get("u")\n',
        'async def f():\n    open("p")\n',
        'import redis\nasync def f():\n    redis.Redis()\n',
        'import redis\nasync def f():\n    redis.StrictRedis()\n',
        'from redis import Redis\nasync def f():\n    Redis.from_url("u")\n',
        'import redis\nasync def f():\n    redis.from_url("u")\n',
        'async def f(self):\n    self.cache_manager.get_str("k")\n',
        'async def f(cache):\n    cache.add("k", "v")\n',
        'async def f(self):\n    self.cache.xadd("s", {})\n',
        'import httpx\nasync def f():\n    httpx.get("u")\n',
        'import httpx\nasync def f():\n    httpx.Client()\n',
        'import httpx as h\nasync def f():\n    h.post("u")\n',
        'import urllib.request\nasync def f():\n    urllib.request.urlopen("u")\n',
        'from urllib.request import urlopen\nasync def f():\n    urlopen("u")\n',
        'import subprocess\nasync def f():\n    subprocess.run(["ls"])\n',
        'from subprocess import run as r\nasync def f():\n    r(["ls"])\n',
        'import subprocess\nasync def f():\n    subprocess.Popen(["ls"])\n',
        'import os\nasync def f():\n    os.system("ls")\n',
        'import os\nasync def f():\n    os.popen("ls")\n',
    ],
)
def test_blocking_in_async_positive(src):
    assert _rules(src) == ['blocking-in-async']


@pytest.mark.parametrize(
    'src',
    [
        # TaskGroup receiver
        'async def f(tg):\n    tg.create_task(g())\n',
        # sync nested def / lambda / class inside async def
        'import time\nasync def f():\n    def inner():\n        time.sleep(1)\n',
        'import time\nasync def f():\n    x = lambda: time.sleep(1)\n',
        'import time\nasync def f():\n    class C:\n        def m(self):\n            time.sleep(1)\n',
        # sync def
        'def f():\n    open("p")\n',
        'import time\ndef f():\n    time.sleep(1)\n',
        # references, not calls
        'import time\nfrom common_module.blocking_io import Pool, run_in_pool\n'
        'async def f():\n    await run_in_pool(Pool.CPU, time.sleep, 1)\n',
        # async cache API
        'async def f(cache):\n    await cache.aget_str("k")\n',
        # open rebound by import
        'from os import open\nasync def f():\n    open("p", 0)\n',
        # async redis constructors
        'import redis.asyncio as aioredis\nasync def f():\n    aioredis.Redis()\n',
        'from redis.asyncio import Redis\nasync def f():\n    Redis.from_url("u")\n',
        # async http / subprocess APIs, sync subprocess in a sync def
        'import httpx\nasync def f():\n    httpx.AsyncClient()\n',
        'import asyncio\nasync def f():\n    await asyncio.create_subprocess_exec("ls")\n',
        'import subprocess\ndef f():\n    subprocess.run(["ls"])\n',
        # non-cache receiver with a cache-like method name
        'async def f(s):\n    s.add(1)\n',
        # unrelated receiver for create_task
        'async def f(self):\n    self.scheduler.create_task(g())\n',
    ],
)
def test_negatives(src):
    assert _rules(src) == []


def test_pragma_single_line():
    src = 'import asyncio\ndef f():\n    asyncio.create_task(g())  # concurrency: allowed\n'
    assert _rules(src) == []


def test_pragma_multi_line_any_line():
    src = (
        'import asyncio\n'
        'def f():\n'
        '    asyncio.create_task(\n'
        '        g(),  # concurrency: allowed - owned by caller\n'
        '    )\n'
    )
    assert _rules(src) == []
    src2 = src.replace('  # concurrency: allowed - owned by caller', '')
    assert _rules(src2) == ['create-task']


def test_pragma_does_not_leak_to_other_calls():
    src = (
        'import asyncio\n'
        'def f():\n'
        '    asyncio.create_task(a())  # concurrency: allowed\n'
        '    asyncio.create_task(b())\n'
    )
    vs = find_violations(src, 'x.py')
    assert [v.lineno for v in vs] == [4]


def test_qualname_nested_class_method():
    src = (
        'import time\n'
        'class Outer:\n'
        '    class Inner:\n'
        '        async def m(self):\n'
        '            time.sleep(1)\n'
    )
    (v,) = find_violations(src, 'pkg/mod.py')
    assert v == Violation('pkg/mod.py', 'Outer.Inner.m', 'blocking-in-async', 5)


def test_qualname_module_level_and_nested_function():
    src = (
        'import asyncio\n'
        'asyncio.create_task(g())\n'
        'def outer():\n'
        '    def inner():\n'
        '        asyncio.create_task(g())\n'
    )
    got = [(v.qualname, v.lineno) for v in find_violations(src, 'x.py')]
    assert got == [('<module>', 2), ('outer.inner', 5)]


# --------------------------------------------------------------------------
# Repo-wide guard
# --------------------------------------------------------------------------


def test_server_root_is_sane():
    assert (SERVER_ROOT / 'pyproject.toml').exists(), SERVER_ROOT


def test_allowlist_format():
    seen: Set[Tuple[str, str, str]] = set()
    for entry in parse_allowlist():
        assert entry not in seen, f'duplicate allowlist entry: {"::".join(entry)}'
        seen.add(entry)


def test_no_new_event_loop_violations():
    assert (SERVER_ROOT / 'pyproject.toml').exists(), SERVER_ROOT
    allowed = set(parse_allowlist())
    violations = scan_repo()

    new = [v for v in violations if (v.relpath, v.qualname, v.rule) not in allowed]
    hit = {(v.relpath, v.qualname, v.rule) for v in violations}
    stale = sorted(e for e in allowed if e not in hit)

    problems = []
    if new:
        lines = '\n'.join(
            f'  {v.relpath}:{v.lineno} {v.qualname} {v.rule}'
            for v in sorted(new, key=lambda v: (v.relpath, v.lineno))
        )
        problems.append(
            'New event-loop / concurrency violations. Use run_in_pool(...) or the '
            'async CacheManager API, or add a justified "# concurrency: allowed" '
            f'pragma:\n{lines}'
        )
    if stale:
        lines = '\n'.join(f'  {"::".join(e)}' for e in stale)
        problems.append(
            'Stale allowlist entries match nothing; delete them from '
            f'event_loop_guard_allowlist.txt:\n{lines}'
        )
    assert not problems, '\n\n'.join(problems)
