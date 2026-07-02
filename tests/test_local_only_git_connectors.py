import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch

from git_config import GitConnectorConfig
from persistence import PersistenceManager


class TestLocalOnlyGitConnectors:
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

    def test_config_allows_connector_without_remote_url(self):
        config_path = self._write_config(
            f"""
known_hosts = ["git.example.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestHostKey"]

[relay]
id = "{self.relay_id}"
url = "https://auth.system3.dev"

[[git_connector]]
shared_folder_id = "{self.folder_id}"
prefix = "snapshots"
"""
        )

        config = GitConnectorConfig(config_path)

        assert len(config.connectors) == 1
        connector = config.connectors[0]
        assert connector.shared_folder_id == self.folder_id
        assert connector.url == ""
        assert connector.prefix == "snapshots"
        assert config.known_hosts == [
            "git.example.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestHostKey"
        ]
        assert config.validate_config() == []

    def test_toml_initialization_skips_remote_configuration_without_url(self):
        self._write_config(
            f"""
[relay]
id = "{self.relay_id}"
url = "https://auth.system3.dev"

[[git_connector]]
shared_folder_id = "{self.folder_id}"
prefix = "snapshots"
"""
        )

        with patch.object(PersistenceManager, "_initialize_all_git_repos"):
            persistence = PersistenceManager(self.temp_dir)

        persistence.init_git_repo = MagicMock(return_value=MagicMock())
        persistence.configure_git_remote = MagicMock()

        assert persistence._initialize_git_repos_from_toml() == 1
        persistence.init_git_repo.assert_called_once_with(self.relay_id, self.folder_id)
        persistence.configure_git_remote.assert_not_called()
        assert persistence.filemeta_folders[self.relay_id][self.folder_id] == {}
