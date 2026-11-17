from dataclasses import dataclass, fields


@dataclass(frozen=True)
class RedisSettings:
    host: str = 'localhost'
    port: int | str = 6379
    protocol: str = 'redis'
    password: str | None = None
    db: int | str = 0
    pool_size: int | str = 20
    pool_timeout: float | str = 2.0
    # Total attempts per call (first try included), and the exponential wait
    # between attempts in seconds: initial_backoff, doubling, capped at max_backoff.
    max_retries: int | str = 3
    initial_backoff: float | str = 1
    max_backoff: float | str = 10
    connection_timeout: float | str = 60
    socket_timeout: float | str = 60
    socket_keepalive: bool | str = True

    def __post_init__(self) -> None:
        # A key missing from config.ini arrives as None: use the field default.
        for field in fields(self):
            if field.name != 'password' and getattr(self, field.name) is None:
                object.__setattr__(self, field.name, field.default)
        if self.password == '':
            object.__setattr__(self, 'password', None)
        if isinstance(self.socket_keepalive, str):
            object.__setattr__(
                self,
                'socket_keepalive',
                self.socket_keepalive.strip().lower() in ('1', 'true', 'yes'),
            )
