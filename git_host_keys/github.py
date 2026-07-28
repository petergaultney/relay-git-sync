from typing import List

from .provider import KnownHostKeyFetchError, get_json

HOST = "github.com"
SOURCE_URL = "https://api.github.com/meta"
BUILTIN_KNOWN_HOSTS = [
    (
        "github.com ssh-ed25519 "
        "AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"
    ),
    (
        "github.com ecdsa-sha2-nistp256 "
        "AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEmKSENjQEezOmxkZMy7opKgw"
        "FB9nkt5YRrYMjNuG5N87uRgg6CLrbo5wAdT/y6v0mKV0U2w0WZ2YB/++Tpockg="
    ),
    (
        "github.com ssh-rsa "
        "AAAAB3NzaC1yc2EAAAADAQABAAABgQCj7ndNxQowgcQnjshcLrqPEiiphnt+VTTvDP6mHBL9j1aNU"
        "kY4Ue1gvwnGLVlOhGeYrnZaMgRK6+PKCUXaDbC7qtbW8gIkhL7aGCsOr/C56SJMy/BCZfxd1nWzA"
        "OxSDPgVsmerOBYfNqltV9/hWCqBywINIR+5dIg6JTJ72pcEpEjcYgXkE2YEFXV1JHnsKgbLWNlhS"
        "cqb2UmyRkQyytRLtL+38TGxkxCflmO+5Z8CSSNY7GidjMIZ7Q4zMjA2n1nGrlTDkzwDCsw+wqFPG"
        "QA179cnfGWOWRVruj16z6XyvxvjJwbz0wQZ75XK5tKSb7FNyeIEs4TT4jk+S4dhPeAUC5y+bDYir"
        "YgM4GC7uEnztnZyaVWQ7B381AK4Qdrwt51ZqExKbQpTUNn+EjqoTwvqNj4kqx5QUCI0ThS/YkOxJ"
        "CXmPUWZbhjpCg56i+2aB6CmK2JGhn57K5mj0MNdBXA4/WnwH6XoPWJzK5Nyu2zB3nAZp+S5hpQs"
        "+p1vN1/wsjk="
    ),
]


def fetch_known_hosts() -> List[str]:
    data = get_json(SOURCE_URL)
    ssh_keys = data.get("ssh_keys")
    if not isinstance(ssh_keys, list) or not all(isinstance(key, str) for key in ssh_keys):
        raise KnownHostKeyFetchError(f"{SOURCE_URL} did not return ssh_keys")
    return [f"{HOST} {key.strip()}" for key in ssh_keys if key.strip()]
