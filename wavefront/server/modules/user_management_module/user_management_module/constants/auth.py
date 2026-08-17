"""Authentication constants."""


class RootfloHeaders:
    CLIENT_KEY = 'X-Rootflo-Key'
    SIGNATURE = 'X-Rootflo-Signature'
    TIMESTAMP = 'X-Rootflo-Timestamp'
    NONCE = 'X-Rootflo-Nonce'
    PASSTHROUGH = 'X-Passthrough'


SERVICE_AUTH_ROLE_ID = 'floconsole-service'

ADMIN_ROLE_NAME = 'admin'
