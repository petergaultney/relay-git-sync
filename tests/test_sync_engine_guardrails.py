from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from models import SyncRequest
from s3rn import S3RemoteFolder
from sync_engine import SyncEngine


def make_engine():
    relay_client = Mock()
    persistence = Mock()
    persistence.filemeta_folders = {}
    persistence.load_persistent_data.return_value = None
    persistence.save_persistent_data.return_value = None
    persistence.init_git_repo.return_value = None
    return SyncEngine("/tmp/git-sync-test", relay_client, persistence)


def test_process_document_change_skips_unconfigured_folder_event():
    engine = make_engine()
    engine.persistence_manager.filemeta_folders = {"relay": {"stale-folder": {}}}
    engine.persistence_manager.should_sync_folder.return_value = False

    result = engine.process_document_change(
        "relay", "stale-folder", datetime.now(timezone.utc)
    )

    assert result.success is True
    assert result.operations == []
    engine.relay_client.get_doc_object.assert_not_called()
    engine.persistence_manager.init_git_repo.assert_not_called()


def test_process_sync_request_skips_unconfigured_folder():
    engine = make_engine()
    engine.relay_client.get_document_structure.return_value = (
        {"filemeta_v0": object()},
        {"type": "folder", "filemeta": {}},
    )
    engine.persistence_manager.should_sync_folder.return_value = False
    folder = S3RemoteFolder("relay", "stale-folder")

    result = engine.process_sync_request(
        SyncRequest(resource=folder, timestamp=datetime.now(timezone.utc))
    )

    assert result.success is True
    assert result.operations == []
    engine.persistence_manager.init_git_repo.assert_not_called()


def test_sync_relay_all_folders_uses_configured_connectors():
    engine = make_engine()
    engine.persistence_manager.git_config.get_connectors_for_relay.return_value = [
        SimpleNamespace(shared_folder_id="configured-folder")
    ]
    engine.process_sync_request = Mock(return_value=object())

    results = engine.sync_relay_all_folders("relay")

    assert results == [engine.process_sync_request.return_value]
    request = engine.process_sync_request.call_args.args[0]
    assert request.resource.relay_id == "relay"
    assert request.resource.folder_id == "configured-folder"
