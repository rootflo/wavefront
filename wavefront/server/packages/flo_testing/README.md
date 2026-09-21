# flo-testing

Shared pytest harness for the wavefront server workspace.

Registers itself as a pytest plugin, so adding `flo-testing` to a module's dev
dependency group is enough to get every fixture below. See
[`server/TESTING.md`](../../TESTING.md) for the full guide.
