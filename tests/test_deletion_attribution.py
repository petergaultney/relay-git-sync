"""A change that only removes content must name the person who removed it.

Content attribution works from added characters, so it has nothing to say about
a pure deletion, and attributing one by authorship of the removed text would
name the victim instead of the actor. These tests pin the actor.
"""

import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch

import git

from attribution import AuthorResolver, GitAuthor
from persistence import PersistenceManager
from s3rn import S3RemoteFolder

RELAY_ID = "85a06712-af14-47bc-a859-e8106cc786e8"
FOLDER_ID = "3667fcda-755e-472b-abea-4b4fc96873a9"
REPO_KEY = f"{RELAY_ID}/{FOLDER_ID}"
PREFIX = "notes"

ADA = GitAuthor("Ada Lovelace", "ada@example.com")
BOB = GitAuthor("Bob Bobson", "bob@example.com")
CAROL = GitAuthor("Carol Carolson", "carol@example.com")

TEAM_LIST = "Team Members:\n  - Hillary Cansler\n  - Chris Hebert\n"
TEAM_LIST_TRIMMED = "Team Members:\n  - Chris Hebert\n"


def make_persistence(temp_dir):
    config_path = os.path.join(temp_dir, "git_connectors.toml")
    with open(config_path, "w") as f:
        f.write(
            f"""
[relay]
id = "{RELAY_ID}"
url = "https://auth.example.com"

[[git_connector]]
shared_folder_id = "{FOLDER_ID}"
branch = "main"
prefix = "{PREFIX}"

[authors]
user-ada = "{ADA.name} <{ADA.email}>"
user-bob = "{BOB.name} <{BOB.email}>"
"""
        )
    with patch.object(PersistenceManager, "_initialize_all_git_repos"):
        return PersistenceManager(temp_dir)


def make_repo(temp_dir, contents=TEAM_LIST):
    repo = git.Repo.init(os.path.join(temp_dir, "repo"), initial_branch="main")
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Sync Bot")
        cw.set_value("user", "email", "bot@example.com")
    notes = os.path.join(repo.working_dir, PREFIX)
    os.makedirs(notes)
    with open(os.path.join(notes, "frontmatter.md"), "w") as f:
        f.write(contents)
    repo.git.add(A=True)
    repo.index.commit("Initial commit")
    return repo


def setup(temp_dir, spans, contents=TEAM_LIST):
    """A repo with one committed file, wired for attribution."""
    persistence = make_persistence(temp_dir)
    repo = make_repo(temp_dir, contents)
    persistence.git_repos = {REPO_KEY: repo}
    persistence._push_to_remote = MagicMock()
    persistence._ensure_configured_branch = MagicMock()
    persistence.local_file_state = {
        RELAY_ID: {FOLDER_ID: {"/frontmatter.md": {"doc_id": "doc-1", "type": "markdown"}}}
    }
    persistence.author_resolver = AuthorResolver(
        lambda resource: spans, {"user-ada": ADA, "user-bob": BOB}
    )
    return persistence, repo


def authors_of(repo):
    return {c.author.email for c in list(repo.iter_commits("main"))[:-1]}


def test_deleting_someone_elses_line_is_attributed_to_the_deleter():
    """The regression this exists for: Bob removes a line Ada wrote."""
    temp_dir = tempfile.mkdtemp()
    try:
        # Every surviving character belongs to Ada; only Bob's removal is new.
        persistence, repo = setup(
            temp_dir, [{"text": TEAM_LIST_TRIMMED, "client_id": 1, "user": "user-ada"}]
        )
        persistence.note_doc_writer("doc-1", "user-bob")

        with open(os.path.join(repo.working_dir, PREFIX, "frontmatter.md"), "w") as f:
            f.write(TEAM_LIST_TRIMMED)

        assert persistence.commit_changes() is True
        assert authors_of(repo) == {BOB.email}, "the deleter, not the author of the deleted line"
    finally:
        shutil.rmtree(temp_dir)


def test_deletion_without_a_known_writer_falls_back_to_the_default_identity():
    temp_dir = tempfile.mkdtemp()
    try:
        persistence, repo = setup(
            temp_dir, [{"text": TEAM_LIST_TRIMMED, "client_id": 1, "user": "user-ada"}]
        )

        with open(os.path.join(repo.working_dir, PREFIX, "frontmatter.md"), "w") as f:
            f.write(TEAM_LIST_TRIMMED)

        assert persistence.commit_changes() is True
        assert authors_of(repo) == {"bot@example.com"}, "must not guess an author"
    finally:
        shutil.rmtree(temp_dir)


def test_added_content_still_beats_the_reported_writer():
    """A write that adds text is attributed from the text, as before."""
    temp_dir = tempfile.mkdtemp()
    try:
        added = TEAM_LIST + "  - Dillon Redding\n"
        persistence, repo = setup(
            temp_dir,
            [
                {"text": TEAM_LIST, "client_id": 1, "user": "user-ada"},
                {"text": "  - Dillon Redding\n", "client_id": 2, "user": "user-ada"},
            ],
        )
        # A stale writer must not override what the content itself proves.
        persistence.note_doc_writer("doc-1", "user-bob")

        with open(os.path.join(repo.working_dir, PREFIX, "frontmatter.md"), "w") as f:
            f.write(added)

        assert persistence.commit_changes() is True
        assert authors_of(repo) == {ADA.email}
    finally:
        shutil.rmtree(temp_dir)


def test_delete_file_captures_the_deleter_before_the_doc_mapping_goes():
    """delete_file drops the path's state entry, and with it the only route from
    that path to a doc_id. The deleter has to be captured before it goes."""
    temp_dir = tempfile.mkdtemp()
    try:
        persistence, _ = setup(temp_dir, [])
        persistence.note_doc_writer("doc-1", "user-bob")

        managed = persistence.get_folder_path_with_prefix(RELAY_ID, FOLDER_ID)
        os.makedirs(managed, exist_ok=True)
        with open(os.path.join(managed, "frontmatter.md"), "w") as f:
            f.write(TEAM_LIST)

        persistence.delete_file(S3RemoteFolder(RELAY_ID, FOLDER_ID), "/frontmatter.md")

        assert persistence._deleted_by[f"{REPO_KEY}:/frontmatter.md"] == "user-bob"
        assert persistence.local_file_state[RELAY_ID][FOLDER_ID] == {}
    finally:
        shutil.rmtree(temp_dir)


def test_whole_file_deletion_is_attributed_to_the_deleter():
    temp_dir = tempfile.mkdtemp()
    try:
        persistence, repo = setup(temp_dir, [])
        persistence.note_doc_writer("doc-1", "user-bob")

        os.remove(os.path.join(repo.working_dir, PREFIX, "frontmatter.md"))
        # what delete_file records as it drops the path's doc mapping
        persistence._deleted_by[f"{REPO_KEY}:/frontmatter.md"] = "user-bob"
        # past the pairing window, so it is a real removal and not half a rename
        persistence._deletion_first_seen[f"{REPO_KEY}:{PREFIX}/frontmatter.md"] = 0.0

        assert persistence.commit_changes() is True
        assert authors_of(repo) == {BOB.email}
        assert f"{PREFIX}/frontmatter.md" not in repo.head.commit.tree
    finally:
        shutil.rmtree(temp_dir)


def messages_of(repo):
    return {c.author.email: c.message for c in list(repo.iter_commits("main"))[:-1]}


def test_commit_names_whose_content_was_deleted():
    """git blame cannot answer this: the removed line is absent from the file,
    so it has no blame entry at all."""
    temp_dir = tempfile.mkdtemp()
    try:
        persistence, repo = setup(
            temp_dir, [{"text": TEAM_LIST_TRIMMED, "client_id": 1, "user": "user-ada"}]
        )
        persistence.note_doc_writer("doc-1", "user-bob", [("user-ada", 20)])

        with open(os.path.join(repo.working_dir, PREFIX, "frontmatter.md"), "w") as f:
            f.write(TEAM_LIST_TRIMMED)

        assert persistence.commit_changes() is True
        message = messages_of(repo)[BOB.email]
        assert f"Deleted-content-of: {ADA.name} <{ADA.email}>" in message
        # not Co-authored-by - Ada did not help write this commit
        assert "Co-authored-by" not in message
    finally:
        shutil.rmtree(temp_dir)


def test_deleting_your_own_content_names_no_victim():
    temp_dir = tempfile.mkdtemp()
    try:
        persistence, repo = setup(
            temp_dir, [{"text": TEAM_LIST_TRIMMED, "client_id": 1, "user": "user-bob"}]
        )
        persistence.note_doc_writer("doc-1", "user-bob", [("user-bob", 20)])

        with open(os.path.join(repo.working_dir, PREFIX, "frontmatter.md"), "w") as f:
            f.write(TEAM_LIST_TRIMMED)

        assert persistence.commit_changes() is True
        assert "Deleted-content-of" not in messages_of(repo)[BOB.email]
    finally:
        shutil.rmtree(temp_dir)


def test_a_line_with_multiple_editors_names_each_victim():
    """The multi-editor case: one removal can take several people's work."""
    temp_dir = tempfile.mkdtemp()
    try:
        persistence, repo = setup(
            temp_dir, [{"text": TEAM_LIST_TRIMMED, "client_id": 1, "user": "user-ada"}]
        )
        # server ranks victims by how much went; ada lost more than the bot user
        persistence.note_doc_writer("doc-1", "user-bob", [("user-ada", 18), ("user-carol", 4)])

        with open(os.path.join(repo.working_dir, PREFIX, "frontmatter.md"), "w") as f:
            f.write(TEAM_LIST_TRIMMED)

        assert persistence.commit_changes() is True
        message = messages_of(repo)[BOB.email]
        # user-carol has no configured git author, so only ada can be named
        assert f"Deleted-content-of: {ADA.name} <{ADA.email}>" in message
        assert message.count("Deleted-content-of") == 1
    finally:
        shutil.rmtree(temp_dir)


def test_whole_file_deletion_names_the_victim():
    temp_dir = tempfile.mkdtemp()
    try:
        persistence, repo = setup(temp_dir, [])
        os.remove(os.path.join(repo.working_dir, PREFIX, "frontmatter.md"))
        persistence._deleted_by[f"{REPO_KEY}:/frontmatter.md"] = "user-bob"
        persistence._deleted_victims[f"{REPO_KEY}:/frontmatter.md"] = ["user-ada"]
        persistence._deletion_first_seen[f"{REPO_KEY}:{PREFIX}/frontmatter.md"] = 0.0

        assert persistence.commit_changes() is True
        message = messages_of(repo)[BOB.email]
        assert f"Deleted-content-of: {ADA.name} <{ADA.email}>" in message
    finally:
        shutil.rmtree(temp_dir)


def test_deleting_several_peoples_content_names_them_all():
    """One removal can take several people's work - a paragraph they co-wrote,
    or a block someone edited after someone else. Every victim gets a trailer,
    ranked by how much of theirs went."""
    temp_dir = tempfile.mkdtemp()
    try:
        persistence, repo = setup(
            temp_dir, [{"text": TEAM_LIST_TRIMMED, "client_id": 1, "user": "user-ada"}]
        )
        # bob deletes content belonging to both ada and carol
        persistence.author_resolver.authors["user-carol"] = CAROL
        persistence.note_doc_writer(
            "doc-1", "user-bob", [("user-ada", 40), ("user-carol", 12)]
        )

        with open(os.path.join(repo.working_dir, PREFIX, "frontmatter.md"), "w") as f:
            f.write(TEAM_LIST_TRIMMED)

        assert persistence.commit_changes() is True
        message = messages_of(repo)[BOB.email]
        trailers = [l for l in message.splitlines() if l.startswith("Deleted-content-of:")]
        assert trailers == [
            f"Deleted-content-of: {ADA.name} <{ADA.email}>",
            f"Deleted-content-of: {CAROL.name} <{CAROL.email}>",
        ], "both victims, most-deleted first"
    finally:
        shutil.rmtree(temp_dir)
