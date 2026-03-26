from dataclasses import dataclass


@dataclass
class SynapseConfig:
    host: str
    port: int
    database: str
    user: str
    password: str
    schema: str = 'dbo'
