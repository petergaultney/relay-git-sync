from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple

MSG_SYNC = 0
MSG_AWARENESS = 1
MSG_AUTH = 2
MSG_QUERY_AWARENESS = 3
MSG_EVENT = 4
MSG_EVENT_SUBSCRIBE = 5
MSG_EVENT_UNSUBSCRIBE = 6
MSG_QUERY_SUBDOCS = 7
MSG_SUBDOCS = 8

MAX_QUERY_SUBDOCS_PER_REQUEST = 100


@dataclass(frozen=True)
class SubdocSnapshot:
    guid: str
    snapshot: bytes
    last_seen: int


def encode_varuint(value: int) -> bytes:
    if value < 0:
        raise ValueError("varuint cannot encode negative values")

    out = bytearray()
    while value > 0x7F:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def decode_varuint(data: bytes, offset: int = 0) -> Tuple[int, int]:
    shift = 0
    value = 0

    while True:
        if offset >= len(data):
            raise ValueError("truncated varuint")
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
        shift += 7
        if shift > 63:
            raise ValueError("varuint is too large")


def encode_string(value: str) -> bytes:
    raw = value.encode("utf-8")
    return encode_varuint(len(raw)) + raw


def decode_string(data: bytes, offset: int = 0) -> Tuple[str, int]:
    raw, offset = decode_bytes(data, offset)
    return raw.decode("utf-8"), offset


def encode_bytes(value: bytes) -> bytes:
    return encode_varuint(len(value)) + value


def decode_bytes(data: bytes, offset: int = 0) -> Tuple[bytes, int]:
    length, offset = decode_varuint(data, offset)
    end = offset + length
    if end > len(data):
        raise ValueError("truncated byte buffer")
    return data[offset:end], end


def encode_event_subscription(event_types: Sequence[str]) -> bytes:
    return _encode_string_list_message(MSG_EVENT_SUBSCRIBE, event_types)


def encode_event_unsubscription(event_types: Sequence[str]) -> bytes:
    return _encode_string_list_message(MSG_EVENT_UNSUBSCRIBE, event_types)


def encode_query_subdocs(guids: Sequence[str]) -> bytes:
    if not guids:
        raise ValueError("MSG_QUERY_SUBDOCS requires at least one GUID")
    if len(guids) > MAX_QUERY_SUBDOCS_PER_REQUEST:
        raise ValueError(f"MSG_QUERY_SUBDOCS accepts at most {MAX_QUERY_SUBDOCS_PER_REQUEST} GUIDs")
    return _encode_string_list_message(MSG_QUERY_SUBDOCS, guids)


def _encode_string_list_message(tag: int, values: Sequence[str]) -> bytes:
    out = bytearray(encode_varuint(tag))
    out.extend(encode_varuint(len(values)))
    for value in values:
        out.extend(encode_string(value))
    return bytes(out)


def decode_subdocs_frame(frame: bytes) -> Dict[str, SubdocSnapshot]:
    tag, offset = decode_varuint(frame)
    if tag != MSG_SUBDOCS:
        raise ValueError(f"expected MSG_SUBDOCS ({MSG_SUBDOCS}), got {tag}")

    cbor_payload, offset = decode_bytes(frame, offset)
    if offset != len(frame):
        raise ValueError("unexpected trailing bytes after MSG_SUBDOCS")
    return decode_subdocs_payload(cbor_payload)


def decode_subdocs_payload(cbor_payload: bytes) -> Dict[str, SubdocSnapshot]:
    payload = _cbor_loads(cbor_payload)
    raw_data = payload.get("data", {}) if isinstance(payload, dict) else {}

    snapshots: Dict[str, SubdocSnapshot] = {}
    for guid, value in raw_data.items():
        if not isinstance(value, dict):
            continue
        snapshot = value.get("snapshot")
        last_seen = value.get("last_seen")
        if isinstance(snapshot, bytes) and last_seen is not None:
            snapshots[str(guid)] = SubdocSnapshot(
                guid=str(guid),
                snapshot=snapshot,
                last_seen=int(last_seen),
            )
    return snapshots


def decode_message(frame: bytes) -> Dict[str, Any]:
    tag, offset = decode_varuint(frame)

    if tag == MSG_SUBDOCS:
        cbor_payload, offset = decode_bytes(frame, offset)
        _ensure_consumed(frame, offset)
        return {
            "type": "subdocs",
            "tag": tag,
            "snapshots": decode_subdocs_payload(cbor_payload),
            "cbor": cbor_payload,
        }

    if tag == MSG_EVENT:
        cbor_payload, offset = decode_bytes(frame, offset)
        _ensure_consumed(frame, offset)
        return {
            "type": "event",
            "tag": tag,
            "data": _try_cbor_loads(cbor_payload),
            "cbor": cbor_payload,
        }

    if tag in (MSG_EVENT_SUBSCRIBE, MSG_EVENT_UNSUBSCRIBE, MSG_QUERY_SUBDOCS):
        values, offset = _decode_string_list(frame, offset)
        _ensure_consumed(frame, offset)
        return {"type": _message_type_name(tag), "tag": tag, "values": values}

    payload = frame[offset:]
    return {"type": _message_type_name(tag), "tag": tag, "payload": payload}


def _decode_string_list(frame: bytes, offset: int) -> Tuple[list[str], int]:
    count, offset = decode_varuint(frame, offset)
    values = []
    for _ in range(count):
        value, offset = decode_string(frame, offset)
        values.append(value)
    return values, offset


def _ensure_consumed(frame: bytes, offset: int) -> None:
    if offset != len(frame):
        raise ValueError("unexpected trailing bytes")


def _message_type_name(tag: int) -> str:
    names = {
        MSG_SYNC: "sync",
        MSG_AWARENESS: "awareness",
        MSG_AUTH: "auth",
        MSG_QUERY_AWARENESS: "query_awareness",
        MSG_EVENT: "event",
        MSG_EVENT_SUBSCRIBE: "event_subscribe",
        MSG_EVENT_UNSUBSCRIBE: "event_unsubscribe",
        MSG_QUERY_SUBDOCS: "query_subdocs",
        MSG_SUBDOCS: "subdocs",
    }
    return names.get(tag, "custom")


def _cbor_loads(payload: bytes) -> Any:
    try:
        import cbor2
    except ImportError as exc:
        raise RuntimeError("cbor2 is required to decode CBOR websocket payloads") from exc
    return cbor2.loads(payload)


def _try_cbor_loads(payload: bytes) -> Optional[Any]:
    try:
        return _cbor_loads(payload)
    except RuntimeError:
        return None
