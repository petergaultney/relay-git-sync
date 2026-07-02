from typing import List

from .provider import get_text, parse_known_hosts_entries


HOST = "gitlab.com"
SOURCE_URL = "https://docs.gitlab.com/user/gitlab_com/"


def fetch_known_hosts() -> List[str]:
    return parse_known_hosts_entries(HOST, get_text(SOURCE_URL))
