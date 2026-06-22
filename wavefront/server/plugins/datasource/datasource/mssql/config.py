from dataclasses import dataclass, field


@dataclass
class MSSQLConfig:
    host: str
    port: int
    database: str
    user: str
    password: str
    schema: str = field(default='dbo')
    encrypt: bool = field(default=True)
    trust_server_certificate: bool = field(default=False)
