from functools import lru_cache
from types import ModuleType
from typing import Dict, List

from . import bitbucket, github, gitlab
from .provider import KnownHostKeyFetchError, validate_provider_entries

PROVIDERS: Dict[str, ModuleType] = {
    provider.HOST: provider
    for provider in (
        github,
        gitlab,
        bitbucket,
    )
}


def is_known_provider_host(host: str) -> bool:
    return host in PROVIDERS


def bundled_known_hosts_for_host(host: str) -> List[str]:
    provider = PROVIDERS.get(host)
    if provider is None:
        return []

    entries = list(getattr(provider, "BUILTIN_KNOWN_HOSTS", []))
    if not entries:
        return []
    return validate_provider_entries(host, provider.SOURCE_URL, entries)


@lru_cache(maxsize=None)
def fetch_known_hosts_for_host(host: str) -> List[str]:
    provider = PROVIDERS.get(host)
    if provider is None:
        return []

    try:
        entries = provider.fetch_known_hosts()
    except KnownHostKeyFetchError:
        raise
    except Exception as e:
        raise KnownHostKeyFetchError(
            f"Unable to fetch known_hosts for {host} from {provider.SOURCE_URL}: {e}"
        ) from e

    return validate_provider_entries(host, provider.SOURCE_URL, entries)
