from dataclasses import dataclass


@dataclass
class RedshiftConfig:
    host: str
    port: int
    database: str
    user: str
    password: str
