import base64
import json
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding

TOKEN_EXPIRY = 5 * 60  # 5 minutes in seconds


class ClientTokenService:
    def __init__(self, private_key_pem: str, client_id: str, product_id: str):
        self.client_id = client_id
        self.product_id = product_id
        # Look for alternate way to load private key
        private_key_pem = base64.b64decode(private_key_pem).decode('utf-8')
        self.private_key = serialization.load_pem_private_key(
            private_key_pem.encode(), password=None
        )

    def generate_token(self) -> str:
        payload = {
            'client_id': self.client_id,
            'product_id': self.product_id,
            'timestamp': int(time.time()),
            'exp': int(time.time() + TOKEN_EXPIRY),
        }

        payload_str = json.dumps(payload, sort_keys=True)
        payload_bytes = payload_str.encode()

        signature = self.private_key.sign(
            payload_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256(),
        )

        signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip('=')
        payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode().rstrip('=')

        return f'{payload_b64}.{signature_b64}'
