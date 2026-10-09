from dataclasses import dataclass


@dataclass(frozen=True)
class RedisSettings:
    host: str = 'localhost'
    port: int | str = 6379
    protocol: str = 'redis'
    password: str | None = None
    db: int | str = 0
    pool_size: int | str = 20
    pool_timeout: float | str = 2.0
    max_retries: int | str = 3
    initial_backoff: int | str = 1
    max_backoff: int | str = 10
    connection_timeout: int | str = 60
    socket_timeout: int | str = 60
    socket_keepalive: bool | str = True

    def __post_init__(self) -> None:
        if self.password == '':
            object.__setattr__(self, 'password', None)
        if isinstance(self.socket_keepalive, str):
            object.__setattr__(
                self,
                'socket_keepalive',
                self.socket_keepalive.strip().lower() in ('1', 'true', 'yes'),
            )
