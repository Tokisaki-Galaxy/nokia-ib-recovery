from __future__ import annotations

import datetime
import os
import tempfile
import unittest

from nokia_ib.codecs import bcd_digits, decode_address, encode_bcd, gsm7_unpack
from nokia_ib.exporters import (
    build_name_map,
    counts_by_number,
    write_chat_html,
    write_contacts_csv,
    write_contacts_html,
    write_contacts_txt,
    write_contacts_vcf,
    write_sms_csv,
    write_sms_html,
    write_sms_txt,
)
from nokia_ib.phonebook import compose_name, parse_phonebook
from nokia_ib.sms import load_messages, parse_sms, read_layout

from tests.fixtures import _gsm7_pack, build_phonebook, build_sms

WHEN = datetime.datetime(2023, 6, 1, 22, 48, 25)


class CodecTests(unittest.TestCase):
    def test_bcd_round_trip(self):
        self.assertEqual(bcd_digits(encode_bcd("8613800138000")), "8613800138000")

    def test_bcd_drops_filler(self):
        self.assertEqual(bcd_digits(bytes.fromhex("683108108300f0")), "8613800138000")

    def test_address_numeric(self):
        self.assertEqual(decode_address(0x91, encode_bcd("8613800138000")), "8613800138000")

    def test_address_alphanumeric(self):
        # "Ad" packed as 7 bit septets.
        self.assertEqual(decode_address(0xD0, bytes.fromhex("4132")).strip(), "Ad")

    def test_gsm7(self):
        raw, septets = _gsm7_pack("Hello")
        self.assertEqual(gsm7_unpack(raw, septets), "Hello")


class SmsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, data, name="sms.ib"):
        path = os.path.join(self.tmp.name, name)
        with open(path, "wb") as handle:
            handle.write(data)
        return path

    def test_single_records(self):
        path = self.write(
            build_sms(
                [
                    {
                        "direction": "in",
                        "address": "8613800138000",
                        "text": "hello from the past",
                        "time": WHEN,
                    },
                    {
                        "direction": "out",
                        "address": "8613800138000",
                        "text": "and a reply",
                        "time": WHEN + datetime.timedelta(minutes=2),
                    },
                ]
            )
        )
        records = parse_sms(path)
        self.assertEqual(len(records), 2)
        self.assertTrue(records[0].incoming)
        self.assertEqual(records[0].address, "8613800138000")
        self.assertEqual(records[0].text, "hello from the past")
        self.assertEqual(records[0].timestamp, WHEN)
        self.assertFalse(records[1].incoming)
        self.assertEqual(records[1].text, "and a reply")
        self.assertEqual(records[1].timestamp, WHEN + datetime.timedelta(minutes=2))

    def test_gsm7_record(self):
        path = self.write(
            build_sms(
                [
                    {
                        "direction": "out",
                        "address": "8613800138000",
                        "text": "Hello",
                        "time": WHEN,
                        "encoding": "gsm7",
                    }
                ]
            )
        )
        records = parse_sms(path)
        self.assertEqual(records[0].encoding, "gsm7")
        self.assertEqual(records[0].text, "Hello")

    def test_multipart_is_merged(self):
        base = {
            "direction": "in",
            "address": "8613800138000",
            "time": WHEN,
        }
        path = self.write(
            build_sms(
                [
                    dict(base, text="first half ", concat=(7, 2, 1)),
                    dict(base, text="second half", concat=(7, 2, 2)),
                ]
            )
        )
        messages = load_messages(path)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].text, "first half second half")
        self.assertEqual(messages[0].parts, 2)
        self.assertTrue(messages[0].complete)

    def test_layout_rejects_truncated_files(self):
        with self.assertRaises(ValueError):
            read_layout(b"\x00" * 32)

    def test_layout_comes_from_header(self):
        data = build_sms(
            [
                {
                    "direction": "out",
                    "address": "8613800138000",
                    "text": "x",
                    "time": WHEN,
                }
            ]
        )
        payload, count, stride = read_layout(data)
        self.assertEqual(payload, 860)
        self.assertEqual(count, 1)
        self.assertEqual(stride, 884)


class PhonebookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_contacts(self):
        data = build_phonebook(
            [
                {
                    "name_first": "\u5c0f\u660e",
                    "name_second": "\u738b",
                    "numbers": ["13700137000", "01012345678"],
                },
                {
                    "name_first": "",
                    "name_second": "\u5bb6\u4eba",
                    "numbers": ["13900139000", "6789"],
                    "extra": "2000-01-01",
                },
            ]
        )
        path = os.path.join(self.tmp.name, "phonebook.ib")
        with open(path, "wb") as handle:
            handle.write(data)

        contacts = parse_phonebook(path)
        self.assertEqual(len(contacts), 2)
        self.assertEqual(contacts[0].name, "\u738b\u5c0f\u660e")
        self.assertEqual([n.raw for n in contacts[0].numbers], ["13700137000", "01012345678"])
        self.assertEqual(contacts[1].name, "\u5bb6\u4eba")
        self.assertEqual(contacts[1].extra, "2000-01-01")

    def test_compose_name(self):
        self.assertEqual(compose_name("\u5c0f\u660e", "\u738b"), "\u738b\u5c0f\u660e")
        self.assertEqual(compose_name("\u5c0f\u674e", "\u8001\u5e08"), "\u5c0f\u674e\u8001\u5e08")
        self.assertEqual(compose_name("", "\u670b\u53cb"), "\u670b\u53cb")


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sms_path = os.path.join(self.tmp.name, "sms.ib")
        with open(self.sms_path, "wb") as handle:
            handle.write(
                build_sms(
                    [
                        {
                            "direction": "in",
                            "address": "8613800138000",
                            "text": "hello <world>",
                            "time": WHEN,
                        },
                        {
                            "direction": "out",
                            "address": "8613800138000",
                            "text": "reply",
                            "time": WHEN + datetime.timedelta(minutes=1),
                        },
                    ]
                )
            )
        self.messages = load_messages(self.sms_path)
        self.contacts = []
        self.names = build_name_map(self.contacts)

    def test_sms_outputs(self):
        csv_path = os.path.join(self.tmp.name, "sms.csv")
        txt_path = os.path.join(self.tmp.name, "sms.txt")
        html_path = os.path.join(self.tmp.name, "sms.html")
        write_sms_csv(csv_path, self.messages, self.names)
        write_sms_txt(txt_path, self.messages, self.names)
        write_sms_html(html_path, self.messages, self.names)
        with open(csv_path, encoding="utf-8-sig") as handle:
            body = handle.read()
        self.assertIn("Received", body)
        self.assertIn("hello <world>", body)
        with open(html_path, encoding="utf-8") as handle:
            page = handle.read()
        self.assertIn("&lt;world&gt;", page)
        self.assertIn("Search messages", page)

    def test_chat_output(self):
        path = os.path.join(self.tmp.name, "chat.html")
        write_chat_html(path, self.messages, self.names)
        with open(path, encoding="utf-8") as handle:
            page = handle.read()
        self.assertIn("Messages", page)
        self.assertIn("hello", page)

    def test_contact_outputs(self):
        data = build_phonebook(
            [
                {
                    "name_first": "\u5c0f\u660e",
                    "name_second": "\u738b",
                    "numbers": ["13700137000"],
                }
            ]
        )
        path = os.path.join(self.tmp.name, "phonebook.ib")
        with open(path, "wb") as handle:
            handle.write(data)
        contacts = parse_phonebook(path)
        counts = counts_by_number(self.messages)
        csv_path = os.path.join(self.tmp.name, "contacts.csv")
        txt_path = os.path.join(self.tmp.name, "contacts.txt")
        vcf_path = os.path.join(self.tmp.name, "contacts.vcf")
        html_path = os.path.join(self.tmp.name, "contacts.html")
        write_contacts_csv(csv_path, contacts, counts)
        write_contacts_txt(txt_path, contacts, counts)
        write_contacts_vcf(vcf_path, contacts)
        write_contacts_html(html_path, contacts, counts)
        with open(vcf_path, encoding="utf-8") as handle:
            vcf = handle.read()
        self.assertIn("FN:", vcf)
        self.assertIn("TEL;TYPE=CELL:+8613700137000", vcf)


if __name__ == "__main__":
    unittest.main()
