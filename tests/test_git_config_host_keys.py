import os
import shutil
import tempfile

import pytest

from git_config import GitConnectorConfig
from git_host_keys import KnownHostKeyFetchError


class TestGitConfigHostKeys:
    relay_id = "85a06712-af14-47bc-a859-e8106cc786e8"
    folder_id = "3667fcda-755e-472b-abea-4b4fc96873a9"

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)

    def _write_config(self, body: str):
        config_path = os.path.join(self.temp_dir, "git_connectors.toml")
        with open(config_path, "w") as f:
            f.write(body)
        return config_path

    @pytest.mark.parametrize(
        ("url", "host"),
        [
            ("git@github.com:example/repository.git", "github.com"),
            ("git@gitlab.com:example/repository.git", "gitlab.com"),
            ("ssh://git@bitbucket.org/example/repository.git", "bitbucket.org"),
        ],
    )
    def test_hosted_provider_ssh_url_fetches_known_hosts(self, url, host, monkeypatch):
        def fake_fetch_known_hosts(fetch_host):
            assert fetch_host == host
            return [
                f"{host} ssh-ed25519 AAAATestEd25519",
                f"{host} ecdsa-sha2-nistp256 AAAATestEcdsa",
                f"{host} ssh-rsa AAAATestRsa",
            ]

        monkeypatch.setattr("git_config.fetch_known_hosts_for_host", fake_fetch_known_hosts)
        config_path = self._write_config(
            f"""
[relay]
id = "{self.relay_id}"
url = "https://auth.system3.dev"

[[git_connector]]
shared_folder_id = "{self.folder_id}"
url = "{url}"
"""
        )

        config = GitConnectorConfig(config_path)

        assert config.validate_config() == []
        assert any(entry.startswith(f"{host} ssh-ed25519 ") for entry in config.known_hosts)
        assert any(entry.startswith(f"{host} ecdsa-sha2-nistp256 ") for entry in config.known_hosts)
        assert any(entry.startswith(f"{host} ssh-rsa ") for entry in config.known_hosts)

    def test_explicit_known_hosts_for_hosted_provider_skips_fetch(self, monkeypatch):
        def fail_fetch_known_hosts(host):
            raise AssertionError(f"fetch should not be called for {host}")

        monkeypatch.setattr("git_config.fetch_known_hosts_for_host", fail_fetch_known_hosts)
        known_host = "github.com ssh-ed25519 AAAATestHostKey"
        config_path = self._write_config(
            f"""
known_hosts = ["{known_host}"]

[relay]
id = "{self.relay_id}"
url = "https://auth.system3.dev"

[[git_connector]]
shared_folder_id = "{self.folder_id}"
url = "git@github.com:example/repository.git"
"""
        )

        config = GitConnectorConfig(config_path)

        assert config.validate_config() == []
        assert config.known_hosts == [known_host]

    def test_hosted_provider_fetch_failure_is_validation_error(self, monkeypatch):
        def fail_fetch_known_hosts(host):
            raise KnownHostKeyFetchError("provider endpoint unavailable")

        monkeypatch.setattr("git_config.fetch_known_hosts_for_host", fail_fetch_known_hosts)
        monkeypatch.setattr("git_config.bundled_known_hosts_for_host", lambda host: [])
        config_path = self._write_config(
            f"""
[relay]
id = "{self.relay_id}"
url = "https://auth.system3.dev"

[[git_connector]]
shared_folder_id = "{self.folder_id}"
url = "git@github.com:example/repository.git"
"""
        )

        config = GitConnectorConfig(config_path)

        assert config.validate_config() == [
            "Unable to fetch known_hosts for SSH host in git_connector[0]: "
            "github.com: provider endpoint unavailable"
        ]

    def test_hosted_provider_fetch_failure_falls_back_to_bundled_known_hosts(self, monkeypatch):
        bundled_entry = "github.com ssh-ed25519 AAAABundledHostKey"

        def fail_fetch_known_hosts(host):
            raise KnownHostKeyFetchError("provider endpoint unavailable")

        monkeypatch.setattr("git_config.fetch_known_hosts_for_host", fail_fetch_known_hosts)
        monkeypatch.setattr("git_config.bundled_known_hosts_for_host", lambda host: [bundled_entry])
        config_path = self._write_config(
            f"""
[relay]
id = "{self.relay_id}"
url = "https://auth.system3.dev"

[[git_connector]]
shared_folder_id = "{self.folder_id}"
url = "git@github.com:example/repository.git"
"""
        )

        config = GitConnectorConfig(config_path)

        assert config.validate_config() == []
        assert config.known_hosts == [bundled_entry]

    def test_hosted_provider_fetch_failure_falls_back_to_cached_known_hosts(self, monkeypatch):
        cached_entry = "github.com ssh-ed25519 AAAACachedHostKey"
        config_body = f"""
[relay]
id = "{self.relay_id}"
url = "https://auth.system3.dev"

[[git_connector]]
shared_folder_id = "{self.folder_id}"
url = "git@github.com:example/repository.git"
"""

        # First load succeeds and populates the on-disk cache.
        monkeypatch.setattr("git_config.fetch_known_hosts_for_host", lambda host: [cached_entry])
        config_path = self._write_config(config_body)
        assert GitConnectorConfig(config_path).validate_config() == []

        # Second load fails to fetch but recovers from the cache.
        def fail_fetch_known_hosts(host):
            raise KnownHostKeyFetchError("provider endpoint unavailable")

        monkeypatch.setattr("git_config.fetch_known_hosts_for_host", fail_fetch_known_hosts)
        config = GitConnectorConfig(config_path)

        assert config.validate_config() == []
        assert config.known_hosts == [cached_entry]

    def test_https_and_local_connectors_do_not_add_known_hosts(self):
        config_path = self._write_config(
            f"""
[relay]
id = "{self.relay_id}"
url = "https://auth.system3.dev"

[[git_connector]]
shared_folder_id = "{self.folder_id}"
url = "https://github.com/example/repository.git"

[[git_connector]]
shared_folder_id = "bcb3e341-6ddf-4a3d-9e8f-8fc3773cd49f"
prefix = "snapshots"
"""
        )

        config = GitConnectorConfig(config_path)

        assert config.validate_config() == []
        assert config.known_hosts == []

    def test_custom_ssh_host_requires_explicit_known_hosts_entry(self):
        config_path = self._write_config(
            f"""
[relay]
id = "{self.relay_id}"
url = "https://auth.system3.dev"

[[git_connector]]
shared_folder_id = "{self.folder_id}"
url = "git@git.example.com:example/repository.git"
"""
        )

        config = GitConnectorConfig(config_path)

        assert config.validate_config() == [
            "Missing known_hosts entry for SSH host in git_connector[0]: git.example.com"
        ]

    def test_custom_ssh_host_accepts_explicit_known_hosts_entry(self):
        known_host = "git.example.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestHostKey"
        config_path = self._write_config(
            f"""
known_hosts = ["{known_host}"]

[relay]
id = "{self.relay_id}"
url = "https://auth.system3.dev"

[[git_connector]]
shared_folder_id = "{self.folder_id}"
url = "git@git.example.com:example/repository.git"
"""
        )

        config = GitConnectorConfig(config_path)

        assert config.validate_config() == []
        assert config.known_hosts == [known_host]
