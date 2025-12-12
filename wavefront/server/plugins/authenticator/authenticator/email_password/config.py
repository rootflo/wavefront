from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class EmailPasswordConfig:
    password_policy: Dict[str, Any] = field(
        default_factory=lambda: {
            'min_length': 8,
            'require_uppercase': True,
            'require_lowercase': True,
            'require_numbers': True,
            'require_special_chars': False,
            'max_attempts': 5,
            'lockout_duration': 900,  # 15 minutes
        }
    )
    two_factor_enabled: bool = False
    password_reset_enabled: bool = True
    session_timeout: int = 3600  # 1 hour
    rate_limit_enabled: bool = True
