from typing import List

from .provider import KnownHostKeyFetchError, get_json

HOST = "github.com"
SOURCE_URL = "https://api.github.com/meta"


def fetch_known_hosts() -> List[str]:
    data = get_json(SOURCE_URL)
    ssh_keys = data.get("ssh_keys")
    if not isinstance(ssh_keys, list) or not all(isinstance(key, str) for key in ssh_keys):
        raise KnownHostKeyFetchError(f"{SOURCE_URL} did not return ssh_keys")
    return [f"{HOST} {key.strip()}" for key in ssh_keys if key.strip()]
