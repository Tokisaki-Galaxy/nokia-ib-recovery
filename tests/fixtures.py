"""Build small synthetic .ib files for the test suite."""

from __future__ import annotations

import datetime
import struct

from nokia_ib.codecs import encode_bcd

HEADER_SIZE = 0x244
NODE_SIZE = 24


def _header(data_size: int, count: int) -> bytearray:
    data = bytearray(HEADER_SIZE + count * (data_size // count + NODE_SIZE))
    struct.pack_into("<I", data, 0x20, 1)
    struct.pack_into("<I", data, 0x24, 1)
    struct.pack_into("<II", data, 0x28, data_size, count)
    struct.pack_into("<I", data, 0x30, count)
    return data


def _scts(value: datetime.datetime) -> bytes:
    digits = value.strftime("%y%m%d%H%M%S") + "32"
    out = bytearray()
    for i in range(0, len(digits), 2):
        out.append(int(digits[i + 1], 16) << 4 | int(digits[i], 16))
    return bytes(out)


def _sent_time(value: datetime.datetime) -> bytes:
    return bytes(
        [value.year - 1980, value.month, value.day, value.hour, value.minute, value.second, 0]
    )


def _gsm7_pack(text: str):
    values = [ord(char) for char in text]
    accumulator = 0
    bits = 0
    out = bytearray()
    for value in values:
        accumulator |= value << bits
        bits += 7
        while bits >= 8:
            out.append(accumulator & 0xFF)
            accumulator >>= 8
            bits -= 8
    if bits:
        out.append(accumulator & 0xFF)
    return bytes(out), len(values)


def build_sms(records):
    """Build a synthetic sms.ib.

    Each record is a dict with keys: direction, address, text, time, encoding,
    and optionally concat=(ref, total, seq).
    """
    payload = 860
    data = _header(payload * len(records), len(records))
    stride = payload + NODE_SIZE

    for index, spec in enumerate(records):
        start = HEADER_SIZE + index * stride
        body = bytearray(stride)

        incoming = spec["direction"] == "in"
        address = spec["address"]
        address_bytes = encode_bcd(address)
        body[0x18] = len(address_bytes)
        body[0x19] = 0x91 if len(address) > 11 else 0x81
        body[0x1A : 0x1A + len(address_bytes)] = address_bytes
        body[0x44] = 0x02 if incoming else 0x05

        concat = spec.get("concat")
        udh = b""
        if concat:
            ref, total, seq = concat
            udh = bytes([0x05, 0x00, 0x03, ref, total, seq])

        text = spec["text"]
        if spec.get("encoding") == "gsm7":
            raw, septets = _gsm7_pack(text)
            length = len(udh) + len(raw)
            octets = len(udh) + septets
        else:
            raw = text.encode("utf-16-be")
            length = len(udh) + len(raw)
            octets = length + 1

        if incoming:
            body[0x1DF] = octets
            body[0x1E0] = length
            body[0x1E1 : 0x1E1 + len(udh) + len(raw)] = udh + raw

            first_octet = 0x04 | (0x40 if concat else 0x00)
            body[0x270] = first_octet
            body[0x271] = len(address)
            body[0x272] = 0x91
            body[0x273 : 0x273 + len(address_bytes)] = address_bytes
            pdu_pos = 0x273 + len(address_bytes)
            body[pdu_pos] = 0x00
            body[pdu_pos + 1] = 0x08
            body[pdu_pos + 2 : pdu_pos + 9] = _scts(spec["time"])
        else:
            body[0x1F0] = octets
            body[0x1F1] = length
            body[0x1F2 : 0x1F2 + len(raw)] = raw
            body[0x27E : 0x27E + 7] = _sent_time(spec["time"])

        struct.pack_into("<I", body, 0, payload)
        data[start : start + stride] = body

    return bytes(data)


def build_phonebook(contacts):
    """Build a synthetic phonebook.ib.

    Each contact is a dict with name_first, name_second, numbers, extra.
    """
    payload = 568
    data = _header(payload * len(contacts), len(contacts))
    stride = payload + NODE_SIZE

    for index, spec in enumerate(contacts):
        start = HEADER_SIZE + index * stride
        body = bytearray(stride)

        for position, number in zip((0x1E, 0x34, 0x4A), spec.get("numbers", [])):
            raw = encode_bcd(number)
            body[position] = len(raw)
            body[position + 1] = 0x11 if len(number) > 11 else 0x01
            body[position + 2 : position + 2 + len(raw)] = raw

        for offset, value in (
            (0x60, spec.get("name_first", "")),
            (0xB4, spec.get("name_second", "")),
        ):
            encoded = value.encode("utf-16-le")
            struct.pack_into("<H", body, offset, len(value))
            body[offset + 2 : offset + 2 + len(encoded)] = encoded

        extra = spec.get("extra", "")
        if extra:
            encoded = extra.encode("utf-16-le")
            struct.pack_into("<H", body, 0x10A, len(extra))
            body[0x10C : 0x10C + len(encoded)] = encoded

        struct.pack_into("<I", body, 0, payload)
        data[start : start + stride] = body

    return bytes(data)
