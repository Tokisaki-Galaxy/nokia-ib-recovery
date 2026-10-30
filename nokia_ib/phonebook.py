"""Parser for ``phonebook.ib`` files produced by Nokia Series 30+ backups.

Each record holds up to three phone numbers and two name fields.  Numbers are
nibble swapped BCD, names are length prefixed UTF-16LE strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .codecs import bcd_digits
from .sms import FILE_HEADER_SIZE, read_layout

OFF_NUMBERS = (0x1E, 0x34, 0x4A)
OFF_NAME_FIRST = 0x60
OFF_NAME_SECOND = 0xB4
OFF_EXTRA = 0x10A


@dataclass
class PhoneNumber:
    """One number stored on a contact."""

    raw: str
    flag: int
    international: bool = False

    @property
    def formatted(self) -> str:
        if self.raw.startswith("86") and len(self.raw) == 13:
            return "+" + self.raw
        if len(self.raw) == 11 and self.raw[0] == "1":
            return "+86 " + self.raw
        return self.raw

    @property
    def vcard(self) -> str:
        if self.raw.startswith("86") and len(self.raw) == 13:
            return "+" + self.raw
        if len(self.raw) == 11 and self.raw[0] == "1":
            return "+86" + self.raw
        return self.raw


@dataclass
class Contact:
    """A contact recovered from the phonebook."""

    index: int
    offset: int
    name: str
    name_first: str
    name_second: str
    numbers: List[PhoneNumber] = field(default_factory=list)
    extra: str = ""


def _utf16le(raw: bytes) -> str:
    return raw.decode("utf-16-le", "replace")


def _name_at(record: bytes, offset: int) -> str:
    length = record[offset] | (record[offset + 1] << 8)
    if not 0 < length < 30:
        return ""
    start = offset + 2
    return _utf16le(record[start : start + length * 2])


def compose_name(first: str, second: str) -> str:
    """Combine the two name fields into a display name.

    Many Chinese contacts store a single character family name in one field
    and the given name in the other.  A few contacts store a two character
    title instead, in which case the two fields are simply joined.
    """
    if first and second:
        if len(second) == 1:
            return second + first
        if len(first) == 1:
            return first + second
        return first + second
    return first or second


def _parse_number(record: bytes, offset: int) -> Optional[PhoneNumber]:
    length = record[offset]
    flag = record[offset + 1]
    if not 0 < length < 20:
        return None
    digits = bcd_digits(record[offset + 2 : offset + 2 + length])
    if not digits.isdigit() or len(digits) < 3:
        return None
    return PhoneNumber(raw=digits, flag=flag, international=bool(flag & 0x80))


def _parse_contact(record: bytes, index: int, offset: int) -> Contact:
    name_first = _name_at(record, OFF_NAME_FIRST)
    name_second = _name_at(record, OFF_NAME_SECOND)

    extra = ""
    extra_length = record[OFF_EXTRA] | (record[OFF_EXTRA + 1] << 8)
    if 0 < extra_length < 30:
        start = OFF_EXTRA + 2
        extra = _utf16le(record[start : start + extra_length * 2])

    numbers = []
    for position in OFF_NUMBERS:
        number = _parse_number(record, position)
        if number is not None:
            numbers.append(number)

    return Contact(
        index=index,
        offset=offset,
        name=compose_name(name_first, name_second),
        name_first=name_first,
        name_second=name_second,
        numbers=numbers,
        extra=extra,
    )


def parse_phonebook(path: str, header_size: int = FILE_HEADER_SIZE) -> List[Contact]:
    """Read every contact of a ``phonebook.ib`` file."""
    with open(path, "rb") as handle:
        data = handle.read()

    payload, count, stride = read_layout(data, header_size)
    contacts: List[Contact] = []
    for index in range(count):
        start = header_size + index * stride
        raw = data[start : start + stride]
        if len(raw) < OFF_EXTRA + 2:
            continue
        contacts.append(_parse_contact(raw, index, start))
    return contacts
