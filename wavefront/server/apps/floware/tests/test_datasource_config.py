"""The [datasource] section of config.ini matches the limits the plugins read."""

import configparser
import dataclasses
import re
from pathlib import Path

from datasource.executor import DatasourceLimits

CONFIG_INI = Path(__file__).resolve().parent.parent / 'floware' / 'config.ini'


def _datasource_section() -> dict:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(CONFIG_INI)
    return dict(parser.items('datasource'))


def test_every_limit_has_a_config_key_and_no_key_is_unknown():
    fields = {field.name for field in dataclasses.fields(DatasourceLimits)}

    assert set(_datasource_section()) == fields


def test_config_defaults_match_the_code_defaults():
    # Each value is '${ENV_VAR:default}'; with the variable unset, the default
    # in config.ini should be the same as the one in code.
    defaults = {
        key: re.fullmatch(r'\$\{[A-Z_]+:(.*)\}', value).group(1)
        for key, value in _datasource_section().items()
    }

    for field in dataclasses.fields(DatasourceLimits):
        assert float(defaults[field.name]) == float(field.default), field.name
