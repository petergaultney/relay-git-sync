import re
from typing import Any, Dict, List

import requests


DEFAULT_TIMEOUT_SECONDS = 10
KNOWN_HOST_KEY_TYPES = ("ssh-ed25519", "ecdsa-sha2-nistp256", "ssh-rsa")


class KnownHostKeyFetchError(RuntimeError):
    """Raised when a trusted provider's known_hosts entries cannot be fetched."""


def get_json(url: str) -> Dict[str, Any]:
    response = requests.get(url, timeout=DEFAULT_TIMEOUT_SECONDS)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise KnownHostKeyFetchError(f"{url} did not return a JSON object")
    return data


def get_text(url: str) -> str:
    response = requests.get(url, timeout=DEFAULT_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.text


def dedupe_preserving_order(entries: List[str]) -> List[str]:
    seen = set()
    deduped = []
    for entry in entries:
        if entry not in seen:
            seen.add(entry)
            deduped.append(entry)
    return deduped


def parse_known_hosts_entries(host: str, text: str) -> List[str]:
    key_types = "|".join(re.escape(key_type) for key_type in KNOWN_HOST_KEY_TYPES)
    pattern = re.compile(
        rf"(?:^|[>\s])({re.escape(host)}\s+(?:{key_types})\s+[A-Za-z0-9+/=]+)(?=\s|<|$)",
        re.MULTILINE,
    )
    return dedupe_preserving_order([match.group(1).strip() for match in pattern.finditer(text)])


def known_hosts_entry_matches_host(entry: str, host: str) -> bool:
    stripped = entry.strip()
    if not stripped or stripped.startswith("#"):
        return False

    parts = stripped.split()
    if not parts:
        return False

    hosts_field = parts[1] if parts[0].startswith("@") and len(parts) > 1 else parts[0]
    for known_host in hosts_field.split(","):
        if known_host == host:
            return True
        bracket_match = re.match(r"^\[([^\]]+)\]:(\d+)$", known_host)
        if bracket_match and bracket_match.group(1) == host:
            return True

    return False


def known_hosts_cover_host(entries: List[str], host: str) -> bool:
    return any(known_hosts_entry_matches_host(entry, host) for entry in entries)


def validate_provider_entries(host: str, source_url: str, entries: List[str]) -> List[str]:
    if not entries:
        raise KnownHostKeyFetchError(f"{source_url} returned no known_hosts entries")
    if not known_hosts_cover_host(entries, host):
        raise KnownHostKeyFetchError(f"{source_url} did not return a known_hosts entry for {host}")
    return dedupe_preserving_order(entries)
