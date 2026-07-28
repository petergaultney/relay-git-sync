import hashlib
from datetime import timezone
from types import SimpleNamespace
from unittest.mock import Mock

from relay_client import RelayClient
from websocket_listener import WebsocketChangeListener

RELAY_ID = "85a06712-af14-47bc-a859-e8106cc786e8"
FOLDER_ID = "3667fcda-755e-472b-abea-4b4fc96873a9"
DOC_ID = "615bae6b-9ca2-4d73-8b63-1d8145276125"


def make_listener():
    persistence = SimpleNamespace(
        filemeta_folders={
            RELAY_ID: {
                FOLDER_ID: {
                    "/doc.md": {"id": DOC_ID, "type": "document"},
                    "/already-compound.md": {
                        "id": f"{RELAY_ID}-aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb",
                        "type": "document",
                    },
                }
            }
        },
        subdoc_heads={RELAY_ID: {}},
        load_persistent_data=Mock(),
    )
    queue = SimpleNamespace(enqueue_document_change=Mock())
    relay_client = RelayClient("https://relay.example", "SERVER")
    return WebsocketChangeListener(relay_client, queue, persistence), queue, persistence


def test_known_subdoc_guids_match_relay_provider_shape():
    listener, _queue, persistence = make_listener()

    guids = listener._known_subdoc_guids(RELAY_ID, FOLDER_ID)

    # Must not reload persisted state from listener threads: that would race with
    # the operations-queue worker, which owns load/mutate/save of this state.
    persistence.load_persistent_data.assert_not_called()
    assert guids == [
        f"{RELAY_ID}-{DOC_ID}",
        f"{RELAY_ID}-aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb",
    ]


def test_event_message_enqueues_only_changed_subdoc():
    listener, queue, _persistence = make_listener()
    subscription = SimpleNamespace(query=Mock())

    listener._handle_message(
        RELAY_ID,
        FOLDER_ID,
        {
            "type": "event",
            "data": {
                "event_type": "document.updated",
                "doc_id": f"{RELAY_ID}-{DOC_ID}",
                "timestamp": 1_719_000_000_123,
            },
        },
        subscription=subscription,
    )

    subscription.query.assert_not_called()
    change = queue.enqueue_document_change.call_args.args[0]
    assert change["relay_id"] == RELAY_ID
    assert change["resource_id"] == DOC_ID
    assert change["timestamp"].tzinfo == timezone.utc


def test_folder_event_enqueues_incremental_filemeta_sync_without_querying_all_subdocs():
    listener, queue, _persistence = make_listener()
    subscription = SimpleNamespace(query=Mock())

    listener._handle_message(
        RELAY_ID,
        FOLDER_ID,
        {
            "type": "event",
            "data": {
                "event_type": "document.updated",
                "doc_id": f"{RELAY_ID}-{FOLDER_ID}",
                "timestamp": 1_719_000_000_123,
            },
        },
        subscription=subscription,
    )

    subscription.query.assert_not_called()
    change = queue.enqueue_document_change.call_args.args[0]
    assert change["relay_id"] == RELAY_ID
    assert change["resource_id"] == FOLDER_ID


def test_initial_subdoc_index_baselines_heads_covered_by_startup_sync():
    listener, queue, _persistence = make_listener()
    listener._catchup_since_millis = 1_800_000_000_000

    listener._handle_message(
        RELAY_ID,
        FOLDER_ID,
        {
            "type": "subdocs",
            "snapshots": {
                f"{RELAY_ID}-{DOC_ID}": SimpleNamespace(
                    guid=f"{RELAY_ID}-{DOC_ID}",
                    snapshot=b"initial-head",
                    last_seen=1_719_000_000_123,
                )
            },
        },
        subscription=SimpleNamespace(query=Mock()),
    )

    change = queue.enqueue_document_change.call_args.args[0]
    assert change["resource_id"] == DOC_ID
    assert change["subdoc_snapshot"] == b"initial-head"
    assert change["baseline_only"] is True


def test_reconnect_subdoc_index_enqueues_only_advanced_heads():
    listener, queue, _persistence = make_listener()
    guid = f"{RELAY_ID}-{DOC_ID}"
    subscription = SimpleNamespace(query=Mock())

    listener._handle_message(
        RELAY_ID,
        FOLDER_ID,
        {
            "type": "subdocs",
            "snapshots": {
                guid: SimpleNamespace(
                    guid=guid,
                    snapshot=b"initial-head",
                    last_seen=1_719_000_000_123,
                )
            },
        },
        subscription=subscription,
    )
    listener._handle_message(
        RELAY_ID,
        FOLDER_ID,
        {
            "type": "subdocs",
            "snapshots": {
                guid: SimpleNamespace(
                    guid=guid,
                    snapshot=b"advanced-head",
                    last_seen=1_719_000_000_124,
                )
            },
        },
        subscription=subscription,
    )

    change = queue.enqueue_document_change.call_args.args[0]
    assert change["relay_id"] == RELAY_ID
    assert change["resource_id"] == DOC_ID


def test_persisted_subdoc_head_skips_unchanged_reconnect_snapshot():
    listener, queue, persistence = make_listener()
    snapshot = b"persisted-head"
    persistence.subdoc_heads[RELAY_ID][DOC_ID] = hashlib.sha256(snapshot).hexdigest()

    listener._handle_message(
        RELAY_ID,
        FOLDER_ID,
        {
            "type": "subdocs",
            "snapshots": {
                f"{RELAY_ID}-{DOC_ID}": SimpleNamespace(
                    guid=f"{RELAY_ID}-{DOC_ID}",
                    snapshot=snapshot,
                    last_seen=1_719_000_000_123,
                )
            },
        },
        subscription=SimpleNamespace(query=Mock()),
    )

    queue.enqueue_document_change.assert_not_called()
