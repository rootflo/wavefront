import requests


class NetworkUtils:
    def http_get(url: str, headers: dict):
        response = requests.get(url=url, headers=headers)
        return response.json()
