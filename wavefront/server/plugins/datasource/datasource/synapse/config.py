from dataclasses import dataclass


@dataclass
class SynapseConfig:
    host: str
    database: str
    user: str
    password: str
    port: int = 1433
    schema: str = 'dbo'
