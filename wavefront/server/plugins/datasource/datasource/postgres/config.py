from dataclasses import dataclass, field


@dataclass
class PostgresConfig:
    host: str
    port: int
    database: str
    user: str
    password: str
    schema: str = field(default='public')
