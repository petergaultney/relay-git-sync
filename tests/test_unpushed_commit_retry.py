import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch

from persistence import PersistenceManager


class TestUnpushedCommitRetry:
    relay_id = "85a06712-af14-47bc-a859-e8106cc786e8"
    configured_folder_id = "3667fcda-755e-472b-abea-4b4fc96873a9"

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        config_path = os.path.join(self.temp_dir, "git_connectors.toml")
        with open(config_path, "w") as f:
            f.write(
                f"""
[relay]
id = "{self.relay_id}"
url = "https://auth.system3.dev"

[[git_connector]]
shared_folder_id = "{self.configured_folder_id}"
url = "git@github.com:No-Instructions/git-sync-test.git"
branch = "main"
remote_name = "origin"
prefix = "notes"
"""
            )
        with patch.object(PersistenceManager, "_initialize_all_git_repos"):
            self.persistence = PersistenceManager(self.temp_dir)

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)

    def test_commit_changes_retries_clean_configured_repo_with_unpushed_commits(self):
        configured_repo = MagicMock()
        configured_repo.is_dirty.return_value = False
        configured_repo.untracked_files = []
        configured_repo.remotes = [MagicMock(name="origin")]

        self.persistence.git_repos = {
            f"{self.relay_id}/{self.configured_folder_id}": configured_repo
        }
        self.persistence._has_unpushed_commits = MagicMock(return_value=True)
        self.persistence._push_to_remote = MagicMock()

        assert self.persistence.commit_changes() is False

        configured_repo.git.add.assert_not_called()
        configured_repo.index.commit.assert_not_called()
        self.persistence._push_to_remote.assert_called_once_with(
            f"{self.relay_id}/{self.configured_folder_id}", configured_repo
        )
