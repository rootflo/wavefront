import base64
import os


def load_test_key(filename: str) -> str:
    """Load and base64 encode a test key file."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    key_path = os.path.join(current_dir, 'keys', filename)

    with open(key_path, 'rb') as key_file:
        key_data = key_file.read()
        return base64.b64encode(key_data).decode()


def get_test_keys():
    """Get both test keys encoded in base64."""
    return {
        'private_key': load_test_key('private_key.pem'),
        'public_key': load_test_key('public_key.pem'),
    }
