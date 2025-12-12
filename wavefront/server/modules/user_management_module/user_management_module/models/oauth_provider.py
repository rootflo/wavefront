from pydantic import BaseModel


class OAuthProviderConfig(BaseModel):
    name: str
    client_id: str
    client_secret: str
    redirect_uri: str
    client_kwargs: dict
    server_metadata_url: str
