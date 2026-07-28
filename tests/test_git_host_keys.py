import base64
import hashlib

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


@pytest.mark.parametrize(
    ("provider", "fingerprints"),
    [
        (
            github,
            {
                "ssh-ed25519": "SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU",
                "ecdsa-sha2-nistp256": "SHA256:p2QAMXNIC1TJYWeIOttrVc98/R1BUFWu3/LiyKgUfQM",
                "ssh-rsa": "SHA256:uNiVztksCsDhcc0u9e8BujQXVUpKZIDTMczCvj3tD2s",
            },
        ),
        (
            gitlab,
            {
                "ssh-ed25519": "SHA256:eUXGGm1YGsMAS7vkcx6JOJdOGHPem5gQp4taiCfCLB8",
                "ecdsa-sha2-nistp256": "SHA256:HbW3g8zUjNSksFbqTiUWPWg2Bq1x8xdGUrliXFzSnUw",
                "ssh-rsa": "SHA256:ROQFvPThGrW4RuWLoL9tq9I9zJ42fK4XywyRtbOz/EQ",
            },
        ),
        (
            bitbucket,
            {
                "ssh-ed25519": "SHA256:ybgmFkzwOSotHTHLJgHO0QN8L0xErw6vd0VhFA9m3SM",
                "ecdsa-sha2-nistp256": "SHA256:FC73VB6C4OQLSCrjEayhMp9UMxS97caD/Yyi2bhW/J0",
                "ssh-rsa": "SHA256:46OSHA1Rmj8E8ERTC6xkNcmGOw9oFxYr0WF6zWW8l1E",
            },
        ),
    ],
)
def test_bundled_provider_keys_match_published_fingerprints(provider, fingerprints):
    actual = {}
    for entry in provider.BUILTIN_KNOWN_HOSTS:
        host, key_type, encoded_key = entry.split()
        assert host == provider.HOST
        digest = hashlib.sha256(base64.b64decode(encoded_key)).digest()
        actual[key_type] = "SHA256:" + base64.b64encode(digest).decode().rstrip("=")

    assert actual == fingerprints


def test_registry_returns_validated_bundled_keys():
    assert registry.bundled_known_hosts_for_host("github.com") == github.BUILTIN_KNOWN_HOSTS
    assert registry.bundled_known_hosts_for_host("unknown.example.com") == []
