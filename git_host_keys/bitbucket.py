from typing import List

from .provider import get_text, parse_known_hosts_entries

HOST = "bitbucket.org"
SOURCE_URL = "https://bitbucket.org/site/ssh"


def fetch_known_hosts() -> List[str]:
    return parse_known_hosts_entries(HOST, get_text(SOURCE_URL))
