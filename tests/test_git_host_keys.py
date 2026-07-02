import pytest

from git_host_keys import bitbucket, github, gitlab, registry
from git_host_keys.provider import KnownHostKeyFetchError


@pytest.fixture(autouse=True)
def clear_provider_cache():
    registry.fetch_known_hosts_for_host.cache_clear()
    yield
    registry.fetch_known_hosts_for_host.cache_clear()


def test_github_fetches_known_hosts_from_meta(monkeypatch):
    def fake_get_json(url):
        assert url == github.SOURCE_URL
        return {
            "ssh_keys": [
                "ssh-ed25519 AAAATestEd25519",
                "ecdsa-sha2-nistp256 AAAATestEcdsa",
                "ssh-rsa AAAATestRsa",
            ]
        }

    monkeypatch.setattr(github, "get_json", fake_get_json)

    assert github.fetch_known_hosts() == [
        "github.com ssh-ed25519 AAAATestEd25519",
        "github.com ecdsa-sha2-nistp256 AAAATestEcdsa",
        "github.com ssh-rsa AAAATestRsa",
    ]


def test_bitbucket_fetches_known_hosts_text(monkeypatch):
    def fake_get_text(url):
        assert url == bitbucket.SOURCE_URL
        return """
bitbucket.org ssh-ed25519 AAAATestEd25519
ignored.example.com ssh-ed25519 AAAAIgnored
bitbucket.org ssh-rsa AAAATestRsa
"""

    monkeypatch.setattr(bitbucket, "get_text", fake_get_text)

    assert bitbucket.fetch_known_hosts() == [
        "bitbucket.org ssh-ed25519 AAAATestEd25519",
        "bitbucket.org ssh-rsa AAAATestRsa",
    ]


def test_gitlab_fetches_known_hosts_from_docs_page(monkeypatch):
    def fake_get_text(url):
        assert url == gitlab.SOURCE_URL
        return """
<span class=line><span class=cl>gitlab.com ssh-ed25519 AAAATestEd25519
</span></span><span class=line><span class=cl>gitlab.com ssh-rsa AAAATestRsa
</span></span>
"""

    monkeypatch.setattr(gitlab, "get_text", fake_get_text)

    assert gitlab.fetch_known_hosts() == [
        "gitlab.com ssh-ed25519 AAAATestEd25519",
        "gitlab.com ssh-rsa AAAATestRsa",
    ]


def test_registry_validates_provider_response_covers_host(monkeypatch):
    monkeypatch.setattr(github, "fetch_known_hosts", lambda: ["example.com ssh-ed25519 AAAA"])

    with pytest.raises(KnownHostKeyFetchError, match="did not return a known_hosts entry"):
        registry.fetch_known_hosts_for_host("github.com")
