import queue
import threading

from operations_queue import DOCUMENT_CHANGE, OperationsQueue


def make_queue_without_workers():
    operations_queue = OperationsQueue.__new__(OperationsQueue)
    operations_queue.request_queue = queue.Queue()
    operations_queue._document_changes = {}
    operations_queue._document_changes_lock = threading.Lock()
    return operations_queue


def test_duplicate_document_notifications_are_coalesced_to_latest():
    operations_queue = make_queue_without_workers()
    first = {"relay_id": "relay", "resource_id": "doc", "timestamp": 1}
    latest = {"relay_id": "relay", "resource_id": "doc", "timestamp": 2}

    operations_queue.enqueue_document_change(first)
    operations_queue.enqueue_document_change(latest)

    assert operations_queue.request_queue.qsize() == 1
    message_type, key = operations_queue.request_queue.get_nowait()
    assert message_type == DOCUMENT_CHANGE
    assert operations_queue._take_document_change(key) == latest
