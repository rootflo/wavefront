"""Feature flags from ``[feature_flags]`` in the app's config.ini.

Built once as ``CommonContainer.feature_flags`` and injected. There is no
process-wide copy: tests override the provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from common_module.config_loader import is_truthy

ALLOW_NON_ADMIN_ALL_DATA_ACCESS_FLAG = 'ALLOW_NON_ADMIN_ALL_DATA_ACCESS_FLAG'
DATASOURCE_AUDIT_ENABLED_FLAG = 'DATASOURCE_AUDIT_ENABLED_FLAG'
DATASOURCE_CHANGE_NOTIFICATION_FLAG = 'DATASOURCE_CHANGE_NOTIFICATION_FLAG'
INACTIVE_ACCOUNT_DISABLE_FLAG = 'INACTIVE_ACCOUNT_DISABLE_FLAG'
SUPERSET_FLAG = 'SUPERSET_FLAG'

_ALL_FLAGS = (
    ALLOW_NON_ADMIN_ALL_DATA_ACCESS_FLAG,
    DATASOURCE_AUDIT_ENABLED_FLAG,
    DATASOURCE_CHANGE_NOTIFICATION_FLAG,
    INACTIVE_ACCOUNT_DISABLE_FLAG,
    SUPERSET_FLAG,
)


def _section_value(section: Mapping[str, Any], name: str) -> Any:
    """Config parsers may lowercase keys; match the flag constants case-insensitively."""
    for key, value in section.items():
        if str(key).upper() == name:
            return value
    return None


@dataclass(frozen=True)
class FeatureFlags:
    allow_non_admin_all_data_access: bool = False
    datasource_audit_enabled: bool = False
    datasource_change_notification: bool = False
    inactive_account_disable: bool = False
    superset: bool = False

    def enabled(self, feature: str) -> bool:
        return {
            ALLOW_NON_ADMIN_ALL_DATA_ACCESS_FLAG: self.allow_non_admin_all_data_access,
            DATASOURCE_AUDIT_ENABLED_FLAG: self.datasource_audit_enabled,
            DATASOURCE_CHANGE_NOTIFICATION_FLAG: self.datasource_change_notification,
            INACTIVE_ACCOUNT_DISABLE_FLAG: self.inactive_account_disable,
            SUPERSET_FLAG: self.superset,
        }[feature]

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> FeatureFlags:
        section = config.get('feature_flags') or {}
        values = {name: is_truthy(_section_value(section, name)) for name in _ALL_FLAGS}
        return cls(
            allow_non_admin_all_data_access=values[
                ALLOW_NON_ADMIN_ALL_DATA_ACCESS_FLAG
            ],
            datasource_audit_enabled=values[DATASOURCE_AUDIT_ENABLED_FLAG],
            datasource_change_notification=values[DATASOURCE_CHANGE_NOTIFICATION_FLAG],
            inactive_account_disable=values[INACTIVE_ACCOUNT_DISABLE_FLAG],
            superset=values[SUPERSET_FLAG],
        )
