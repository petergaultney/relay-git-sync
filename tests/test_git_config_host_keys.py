import os
import shutil
import tempfile

from git_config import GitConnectorConfig


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

    def test_github_ssh_url_adds_builtin_known_hosts(self):
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
        assert any(entry.startswith("github.com ssh-ed25519 ") for entry in config.known_hosts)
        assert any(
            entry.startswith("github.com ecdsa-sha2-nistp256 ") for entry in config.known_hosts
        )
        assert any(entry.startswith("github.com ssh-rsa ") for entry in config.known_hosts)

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
