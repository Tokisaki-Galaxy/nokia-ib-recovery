"""Small codecs shared by the SMS and phonebook parsers."""

from __future__ import annotations

from typing import List

# GSM 03.38 default alphabet.
GSM7_BASIC = (
    "@\u00a3$\u00a5\u00e8\u00e9\u00f9\u00ec\u00f2\u00c7\n\u00d8\u00f8\r\u00c5\u00e5"
    "\u0394_\u03a6\u0393\u039b\u03a9\u03a0\u03a8\u03a3\u0398\u039e\u001b\u00c6\u00e6\u00df\u00c9"
    " !\"#\u00a4%&'()*+,-./0123456789:;<=>?"
    "\u00a1ABCDEFGHIJKLMNOPQRSTUVWXYZ\u00c4\u00d6\u00d1\u00dc\u00a7\u00bf"
    "abcdefghijklmnopqrstuvwxyz\u00e4\u00f6\u00f1\u00fc\u00e0"
)

GSM7_EXTENDED = {
    "\x0a": "\f",
    "\x14": "^",
    "\x28": "{",
    "\x29": "}",
    "\x2f": "\\",
    "\x3c": "[",
    "\x3d": "~",
    "\x3e": "]",
    "\x40": "|",
    "\x65": "\u20ac",
}


def bcd_digits(raw: bytes) -> str:
    """Decode nibble swapped BCD digits, dropping the 0xF filler."""
    digits = "".join(f"{byte & 0x0F:x}{byte >> 4:x}" for byte in raw)
    if "f" in digits:
        digits = digits[: digits.index("f")]
    return digits


def gsm7_unpack(raw: bytes, septets: int) -> str:
    """Unpack packed 7 bit septets into text."""
    accumulator = 0
    bits = 0
    values: List[int] = []
    for byte in raw:
        accumulator |= byte << bits
        bits += 8
        while bits >= 7 and len(values) < septets:
            values.append(accumulator & 0x7F)
            accumulator >>= 7
            bits -= 7

    out: List[str] = []
    i = 0
    while i < len(values):
        value = values[i]
        if value == 0x1B and i + 1 < len(values):
            out.append(GSM7_EXTENDED.get(chr(values[i + 1]), ""))
            i += 2
        else:
            out.append(GSM7_BASIC[value] if value < len(GSM7_BASIC) else "")
            i += 1
    return "".join(out)


def decode_address(toa: int, raw: bytes) -> str:
    """Decode an address field according to its type-of-address byte."""
    kind = toa & 0x70
    if kind == 0x50:
        if toa & 0x80:
            # Alphanumeric address, packed 7 bit septets.
            return gsm7_unpack(raw, len(raw) * 8 // 7).rstrip("\x00")
        return raw.decode("latin-1", "replace").rstrip("\x00")
    return bcd_digits(raw)


def encode_bcd(digits: str) -> bytes:
    """Encode digits as nibble swapped BCD with an F filler, for tests."""
    if len(digits) % 2:
        digits += "f"
    out = bytearray()
    for i in range(0, len(digits), 2):
        out.append(int(digits[i + 1], 16) << 4 | int(digits[i], 16))
    return bytes(out)
