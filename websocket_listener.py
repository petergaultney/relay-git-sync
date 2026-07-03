#!/usr/bin/env python3

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List

from git_config import GitConnector
from operations_queue import OperationsQueue
from persistence import PersistenceManager
from relay_client import RelayClient

logger = logging.getLogger(__name__)


class WebsocketChangeListener:
    """Subscribe to Relay folder sockets and enqueue document changes."""

    def __init__(
        self,
        relay_client: RelayClient,
        operations_queue: OperationsQueue,
        persistence_manager: PersistenceManager,
        reconnect_delay: float = 5.0,
    ):
        self.relay_client = relay_client
        self.operations_queue = operations_queue
        self.persistence_manager = persistence_manager
        self.reconnect_delay = reconnect_delay
        self._stop_event = threading.Event()
        self._threads: List[threading.Thread] = []
        self._subscriptions = []
        self._subscriptions_lock = threading.Lock()

    def start(self) -> int:
        connectors = self.persistence_manager.git_config.connectors
        if not connectors:
            logger.info("No git connectors configured; websocket listener not started")
            return 0

        for connector in connectors:
            thread = threading.Thread(
                target=self._listen_connector,
                args=(connector,),
                daemon=True,
                name=f"relay-ws-{connector.relay_id[:8]}-{connector.shared_folder_id[:8]}",
            )
            thread.start()
            self._threads.append(thread)

        logger.info("Started %d websocket folder listener(s)", len(self._threads))
        return len(self._threads)

    def stop(self) -> None:
        self._stop_event.set()
        with self._subscriptions_lock:
            subscriptions = list(self._subscriptions)
            self._subscriptions.clear()

        for subscription in subscriptions:
            try:
                subscription.close()
            except Exception:
                logger.debug("Error closing websocket subscription", exc_info=True)

    def _listen_connector(self, connector: GitConnector) -> None:
        relay_id = connector.relay_id
        folder_id = connector.shared_folder_id

        while not self._stop_event.is_set():
            subscription = None
            try:
                folder = self.relay_client.dm.shared_folder(relay_id, folder_id)
                guids = self._known_subdoc_guids(relay_id, folder_id)
                subscription = folder.open_subdoc_subscription(guids, timeout=30)
                self._register_subscription(subscription)

                logger.info(
                    "Subscribed to Relay websocket for relay=%s folder=%s (%d known subdocs)",
                    relay_id,
                    folder_id,
                    len(guids),
                )

                self._enqueue_change(relay_id, folder_id, datetime.now(timezone.utc))

                while not self._stop_event.is_set():
                    try:
                        message = subscription.recv()
                    except Exception as exc:
                        if self._is_timeout(exc):
                            continue
                        raise

                    self._handle_message(relay_id, folder_id, message, subscription)

            except Exception as exc:
                if not self._stop_event.is_set():
                    logger.warning(
                        "Relay websocket listener failed for relay=%s folder=%s: %s",
                        relay_id,
                        folder_id,
                        exc,
                    )
                    logger.debug("Relay websocket listener traceback", exc_info=True)
                    self._stop_event.wait(self.reconnect_delay)
            finally:
                if subscription is not None:
                    self._unregister_subscription(subscription)
                    try:
                        subscription.close()
                    except Exception:
                        logger.debug("Error closing websocket subscription", exc_info=True)

    def _handle_message(
        self,
        relay_id: str,
        folder_id: str,
        message: Dict[str, Any],
        subscription,
    ) -> None:
        message_type = message.get("type")

        if message_type == "event":
            event = message.get("data") or {}
            doc_id = event.get("doc_id")
            timestamp = self._event_timestamp(event)

            if doc_id:
                self._enqueue_doc_id(relay_id, folder_id, doc_id, timestamp)
                if doc_id == f"{relay_id}-{folder_id}":
                    self._refresh_subdoc_query(relay_id, folder_id, subscription)
            else:
                self._enqueue_change(relay_id, folder_id, timestamp)

        elif message_type == "subdocs":
            for snapshot in message.get("snapshots", {}).values():
                timestamp = self._millis_to_datetime(snapshot.last_seen)
                self._enqueue_doc_id(relay_id, folder_id, snapshot.guid, timestamp)

    def _refresh_subdoc_query(self, relay_id: str, folder_id: str, subscription) -> None:
        guids = self._known_subdoc_guids(relay_id, folder_id)
        if not guids:
            return
        try:
            subscription.query(guids)
        except Exception:
            logger.debug("Failed to refresh subdoc query for folder=%s", folder_id, exc_info=True)

    def _known_subdoc_guids(self, relay_id: str, folder_id: str) -> List[str]:
        # Read in-memory state only: reloading from disk here would race with the
        # operations-queue worker, which owns load/mutate/save of this state.
        # Copy the folder dict so iteration is safe while the worker updates it.
        filemeta = dict(
            self.persistence_manager.filemeta_folders.get(relay_id, {}).get(folder_id, {})
        )
        guids: List[str] = []
        prefix = f"{relay_id}-"

        for metadata in filemeta.values():
            if not isinstance(metadata, dict):
                continue
            resource_id = metadata.get("id")
            if not resource_id:
                continue
            guid = resource_id if str(resource_id).startswith(prefix) else f"{prefix}{resource_id}"
            guids.append(guid)

        return sorted(set(guids))

    def _enqueue_doc_id(
        self,
        expected_relay_id: str,
        fallback_folder_id: str,
        doc_id: str,
        timestamp: datetime,
    ) -> None:
        try:
            relay_id = self.relay_client.extract_relay_id(doc_id)
            resource_id = self.relay_client.extract_document_id(doc_id)
        except Exception:
            relay_id = expected_relay_id
            resource_id = fallback_folder_id

        self._enqueue_change(relay_id, resource_id, timestamp)

    def _enqueue_change(self, relay_id: str, resource_id: str, timestamp: datetime) -> None:
        self.operations_queue.enqueue_document_change(
            {
                "relay_id": relay_id,
                "resource_id": resource_id,
                "timestamp": timestamp,
            }
        )

    def _event_timestamp(self, event: Dict[str, Any]) -> datetime:
        timestamp = event.get("timestamp")
        if timestamp is None:
            return datetime.now(timezone.utc)

        try:
            timestamp_value = float(timestamp)
        except (TypeError, ValueError):
            return datetime.now(timezone.utc)

        if timestamp_value > 10_000_000_000:
            timestamp_value = timestamp_value / 1000.0

        return datetime.fromtimestamp(timestamp_value, tz=timezone.utc)

    def _millis_to_datetime(self, timestamp_millis: int) -> datetime:
        return datetime.fromtimestamp(timestamp_millis / 1000.0, tz=timezone.utc)

    def _register_subscription(self, subscription) -> None:
        with self._subscriptions_lock:
            self._subscriptions.append(subscription)

    def _unregister_subscription(self, subscription) -> None:
        with self._subscriptions_lock:
            if subscription in self._subscriptions:
                self._subscriptions.remove(subscription)

    def _is_timeout(self, exc: Exception) -> bool:
        name = exc.__class__.__name__.lower()
        return "timeout" in name or "timed out" in str(exc).lower()
