"""Parser for ``sms.ib`` files produced by Nokia Series 30+ backups.

The file is a flat array of fixed size records.  Each record starts with a
24 byte filesystem node header followed by the record payload.  The payload
contains the address, a direction flag, the message body and, for incoming
messages, a copy of the raw SMS PDU.

Only the fields needed to recover messages are decoded here.  See
``docs/format.md`` for the full layout.
"""

from __future__ import annotations

import datetime
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .codecs import decode_address, gsm7_unpack

FILE_HEADER_SIZE = 0x244
NODE_HEADER_SIZE = 24

# Offsets inside a record payload, i.e. after the 24 byte node header.
OFF_ADDRESS_LEN = 0x18
OFF_ADDRESS_TOA = 0x19
OFF_ADDRESS = 0x1A
OFF_DIRECTION = 0x44

OFF_TEXT_IN_HDR = 0x1DF
OFF_TEXT_IN_BODY = 0x1E1
OFF_TEXT_OUT_HDR = 0x1F0
OFF_TEXT_OUT_BODY = 0x1F2

OFF_PDU = 0x270
OFF_SENT_TIME = 0x27E

DIRECTION_INCOMING = 0x02


@dataclass
class SmsRecord:
    """One message read from ``sms.ib``."""

    index: int
    offset: int
    incoming: bool
    address: str
    timestamp: Optional[datetime.datetime]
    text: str
    encoding: str
    direction_byte: int
    parts: int = 1
    complete: bool = True
    udh: Dict[str, int] = field(default_factory=dict)


def _decode_scts(raw: bytes) -> Optional[datetime.datetime]:
    """Decode the 7 byte SMS centre timestamp of an incoming message."""
    digits = "".join(f"{byte & 0x0F:x}{byte >> 4:x}" for byte in raw)
    try:
        return datetime.datetime(
            2000 + int(digits[0:2]),
            int(digits[2:4]),
            int(digits[4:6]),
            int(digits[6:8]),
            int(digits[8:10]),
            int(digits[10:12]),
        )
    except (ValueError, IndexError):
        return None


def _decode_sent_time(raw: bytes) -> Optional[datetime.datetime]:
    """Decode the 7 byte timestamp of an outgoing message.

    The first byte is the year offset from 1980, the rest are plain binary
    month, day, hour, minute and second values.
    """
    try:
        return datetime.datetime(
            1980 + raw[0], raw[1], raw[2], raw[3], raw[4], raw[5]
        )
    except (ValueError, IndexError):
        return None


def parse_udh(raw: bytes) -> Dict[str, int]:
    """Parse a concatenation UDH and return ref, total and seq when present."""
    if not raw:
        return {}
    length = min(1 + raw[0], len(raw))
    i = 1
    while i + 1 < length:
        iei = raw[i]
        size = raw[i + 1]
        data = raw[i + 2 : i + 2 + size]
        if iei == 0x00 and size >= 3:
            return {"ref": data[0], "total": data[1], "seq": data[2]}
        if iei == 0x08 and size >= 4:
            return {
                "ref": (data[0] << 8) | data[1],
                "total": data[2],
                "seq": data[3],
            }
        i += 2 + size
    return {}


def read_layout(data: bytes, header_size: int = FILE_HEADER_SIZE) -> Tuple[int, int, int]:
    """Return record payload size, record count and stride from the file header."""
    if len(data) < header_size + 8:
        raise ValueError("file is too small to be a Nokia .ib backup")
    data_size, count = struct.unpack_from("<II", data, 0x28)
    if count == 0 or data_size == 0 or data_size % count != 0:
        raise ValueError(
            "unexpected header: data size %d, record count %d" % (data_size, count)
        )
    payload = data_size // count
    stride = payload + NODE_HEADER_SIZE
    if header_size + count * stride > len(data):
        raise ValueError("file is shorter than the record table declared in the header")
    return payload, count, stride


def _read_text(
    record: bytes, incoming: bool, first_octet: int
) -> Tuple[str, str, Dict[str, int]]:
    """Decode the message body and return text, encoding name and UDH info."""
    if incoming:
        header, body_off = OFF_TEXT_IN_HDR, OFF_TEXT_IN_BODY
    else:
        header, body_off = OFF_TEXT_OUT_HDR, OFF_TEXT_OUT_BODY

    octets = record[header]
    length = record[header + 1]

    udh: Dict[str, int] = {}
    udh_len = 0
    if incoming and length > 2 and first_octet & 0x40:
        udhl = record[body_off]
        if 0 < udhl < length - 1:
            udh_len = 1 + udhl
            udh = parse_udh(record[body_off : body_off + udh_len])

    # In UCS2 bodies the first length byte is always one more than the second,
    # which holds the byte count.  In GSM 7 bit bodies the two bytes are the
    # octet count and the septet count.
    if octets == length + 1:
        size = length - udh_len
        raw = record[body_off + udh_len : body_off + udh_len + size]
        return raw.decode("utf-16-be", "replace"), "ucs2", udh

    size = octets - udh_len
    septets = length - udh_len
    raw = record[body_off + udh_len : body_off + udh_len + size]
    return gsm7_unpack(raw, septets), "gsm7", udh


def _parse_record(record: bytes, index: int, offset: int) -> SmsRecord:
    direction = record[OFF_DIRECTION]
    incoming = direction == DIRECTION_INCOMING

    address_len = record[OFF_ADDRESS_LEN]
    toa = record[OFF_ADDRESS_TOA]
    address = decode_address(toa, record[OFF_ADDRESS : OFF_ADDRESS + address_len])

    first_octet = 0
    if incoming:
        first_octet = record[OFF_PDU]
        pdu_len = record[OFF_PDU + 1]
        pdu_toa = record[OFF_PDU + 2]
        pdu_bytes = (pdu_len + 1) // 2
        pdu_addr = record[OFF_PDU + 3 : OFF_PDU + 3 + pdu_bytes]
        resolved = decode_address(pdu_toa, pdu_addr)
        if resolved.strip("0"):
            address = resolved
        scts_at = OFF_PDU + 3 + pdu_bytes + 2
        timestamp = _decode_scts(record[scts_at : scts_at + 7])
    else:
        timestamp = _decode_sent_time(record[OFF_SENT_TIME : OFF_SENT_TIME + 7])

    text, encoding, udh = _read_text(record, incoming, first_octet)

    return SmsRecord(
        index=index,
        offset=offset,
        incoming=incoming,
        address=address,
        timestamp=timestamp,
        text=text,
        encoding=encoding,
        direction_byte=direction,
        parts=udh.get("total", 1) if udh else 1,
        complete=not udh,
        udh=udh,
    )


def parse_sms(path: str, header_size: int = FILE_HEADER_SIZE) -> List[SmsRecord]:
    """Read every record of an ``sms.ib`` file."""
    with open(path, "rb") as handle:
        data = handle.read()

    _payload, count, stride = read_layout(data, header_size)
    records: List[SmsRecord] = []
    for index in range(count):
        start = header_size + index * stride
        raw = data[start : start + stride]
        if len(raw) < 0x285:
            continue
        records.append(_parse_record(raw, index, start))
    return records


def load_messages(path: str, header_size: int = FILE_HEADER_SIZE) -> List[SmsRecord]:
    """Parse ``sms.ib``, drop duplicated records and merge multipart messages."""
    records = parse_sms(path, header_size)

    unique: List[SmsRecord] = []
    seen = set()
    for record in records:
        key = (record.incoming, record.address, record.timestamp, record.text)
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)

    groups: Dict[tuple, List[SmsRecord]] = {}
    singles: List[SmsRecord] = []
    for record in unique:
        if record.udh and record.udh.get("total", 1) > 1:
            day = record.timestamp.strftime("%Y%m%d") if record.timestamp else ""
            key = (record.address, record.udh["ref"], record.udh["total"], day)
            groups.setdefault(key, []).append(record)
        else:
            singles.append(record)

    merged: List[SmsRecord] = []
    for parts in groups.values():
        parts.sort(key=lambda item: item.udh["seq"])
        first = parts[0]
        seqs = {item.udh["seq"] for item in parts}
        first.text = "".join(item.text for item in parts)
        first.parts = first.udh["total"]
        first.complete = len(seqs) == first.parts
        merged.append(first)

    messages = singles + merged
    messages.sort(
        key=lambda item: (item.timestamp or datetime.datetime(1900, 1, 1), item.index)
    )
    return messages
