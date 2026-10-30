# Backup format notes

These notes describe what was observed in a Nokia TA-127B backup. All offsets are relative to the start of a record, which includes its 24 byte node header. Values are little endian unless stated otherwise.

Nothing here comes from a vendor document. Verify against your own file before trusting an offset.

## Container

Both `sms.ib` and `phonebook.ib` share the same outer structure.

| Offset | Type | Meaning |
| --- | --- | --- |
| 0x00 | UTF-16LE string | File name, for example `sms.ib`, zero padded |
| 0x20 | u32 | Unknown, observed value 1 |
| 0x24 | u32 | Unknown, observed value 1 |
| 0x28 | u32 | Total payload bytes of all records |
| 0x2C | u32 | Record count |
| 0x30 | u32 | Record count again |
| 0x244 | - | First record |

Each record has a 24 byte node header at the front. The payload size is `0x28 / 0x2C`, and the stride is payload size plus 24.

For the tested files:

| File | Payload | Records | Stride | File size |
| --- | --- | --- | --- | --- |
| `sms.ib` | 860 | 776 | 884 | 686564 |
| `phonebook.ib` | 568 | 29 | 592 | 17748 |

The file size is always `0x244 + records * stride` on the tested firmware.

The 24 byte node header starts with the payload size as u32, followed by flags and two link pointers that are mostly `0xFFFFFFFF`. The exporter does not use these fields.

## sms.ib records

| Offset | Type | Meaning |
| --- | --- | --- |
| 0x00 | u32 | Payload size, 860 |
| 0x18 | u8 | Address length in bytes |
| 0x19 | u8 | Type of address |
| 0x1A | bytes | Address, BCD nibble swapped |
| 0x44 | u8 | Direction, 0x02 incoming, 0x05 outgoing |
| 0x1DF | u8 | Incoming body octet count |
| 0x1E0 | u8 | Incoming body length |
| 0x1E1 | bytes | Incoming body |
| 0x1F0 | u8 | Outgoing body octet count |
| 0x1F1 | u8 | Outgoing body length |
| 0x1F2 | bytes | Outgoing body |
| 0x270 | bytes | Incoming SMS PDU copy |
| 0x27E | 7 bytes | Outgoing timestamp |

### Address

The type of address byte follows the usual GSM layout.

- `0x91` or `0x81`: numeric address, digits are stored as BCD with the nibbles swapped, low nibble first. A trailing `0xF` is filler.
- `0x50`: alphanumeric address stored as plain ASCII.
- `0xD0`: alphanumeric address stored as packed 7 bit septets.

Incoming records keep a second copy of the address inside the PDU at `0x270`. It is used when the record level address is empty or all zeroes, which happens for some senders.

### Body encoding

The two length bytes decide the encoding.

- If `octets == length + 1`, the body is UTF-16BE and `length` is the byte count. The first value is one more than the second.
- Otherwise the body is GSM 03.38. `octets` is the byte count and `length` is the septet count. The packed septets are unpacked least significant bit first, and the `0x1B` escape maps to the extension table.

Bodies are not terminated by a null byte. Use the length fields, not a string scan.

### Multipart messages

The first octet of the incoming PDU at `0x270` carries the TP-UDHI bit, `0x40`. When it is set, the body begins with a user data header. The first byte of the body is the header length, so skip `1 + header_length` bytes and subtract that from the body length.

Two concatenation information elements are handled.

- `00 03 ref total seq`: 8 bit reference.
- `08 04 ref_hi ref_lo total seq`: 16 bit reference.

Parts are grouped by address, reference, total and day, then sorted by sequence number and joined.

### Timestamps

Incoming messages use the SMS centre timestamp inside the PDU. The PDU starts at `0x270`:

```
first_octet  address_len  toa  address...  pid  dcs  scts[7]
```

The address length is in digits, and the byte count is `ceil(address_len / 2)`. The seven timestamp bytes are BCD with swapped nibbles: year, month, day, hour, minute, second, time zone in quarter hours. The year is added to 2000.

Outgoing messages store seven plain bytes at `0x27E`: year minus 1980, month, day, hour, minute, second, and a time zone byte.

A 32 bit Unix style timestamp also exists near the start of each record. On the tested firmware it is ten years early, so it is ignored. See the note in the README.

## phonebook.ib records

| Offset | Type | Meaning |
| --- | --- | --- |
| 0x00 | u32 | Payload size, 568 |
| 0x1E | slot | First number |
| 0x34 | slot | Second number |
| 0x4A | slot | Third number |
| 0x60 | string | First name field |
| 0xB4 | string | Second name field |
| 0x10A | string | Extra field, sometimes a date |

### Number slot

```
length u8 | flag u8 | digits
```

`length` is the number of bytes, not digits. Digits are BCD with swapped nibbles. Flag `0x11` was seen on numbers stored with the country code, flag `0x01` on national numbers.

### Name fields

Each name field is a u16 little endian character count followed by UTF-16LE text. Many contacts store a one character family name in the second field and the given name in the first. The tool joins them as `second + first`, and falls back to plain concatenation when the second field is longer than one character.

### Extra field

A u16 length followed by UTF-16LE text. In the tested file two contacts store a date string here and the rest are empty.

## Caveats

- The offsets for the name fields are specific to 568 byte payload records. A backup with a different payload size will need the name and number offsets re-derived.
- The number slot offsets are 0x16 bytes apart, but the tool reads each slot from its fixed offset instead of scanning.
- Direction values other than `0x02` and `0x05` are treated as outgoing.
- Records that contain binary payloads, such as WAP pushes, are decoded as text and will contain garbage.
