"""Command line interface for the Nokia backup parsers."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional

from .exporters import (
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
from .phonebook import Contact, parse_phonebook
from .sms import FILE_HEADER_SIZE, load_messages


def _resolve(target: str, filename: str) -> str:
    if os.path.isdir(target):
        return os.path.join(target, filename)
    return target


def _load_aliases(path: Optional[str]) -> Dict[str, str]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise SystemExit("aliases file must contain a JSON object of number to name")
    return {str(key): str(value) for key, value in data.items()}


def _contacts(target: str, header_size: int) -> List[Contact]:
    path = _resolve(target, "phonebook.ib")
    if not os.path.exists(path):
        return []
    return parse_phonebook(path, header_size)


def _messages(target: str, header_size: int):
    path = _resolve(target, "sms.ib")
    if not os.path.exists(path):
        raise SystemExit("sms.ib not found in %s" % target)
    return load_messages(path, header_size)


def _summary(messages, contacts) -> None:
    if messages:
        received = sum(1 for item in messages if item.incoming)
        print(
            "messages: %d, received: %d, sent: %d"
            % (len(messages), received, len(messages) - received)
        )
        times = [item.timestamp for item in messages if item.timestamp]
        if times:
            print("range: %s to %s" % (min(times).date(), max(times).date()))
    if contacts:
        print(
            "contacts: %d, numbers: %d"
            % (len(contacts), sum(len(item.numbers) for item in contacts))
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nokia-ib",
        description="Recover SMS and contacts from Nokia Series 30+ .ib backups.",
    )
    parser.add_argument(
        "command",
        choices=["all", "sms", "contacts", "chat"],
        help="what to export",
    )
    parser.add_argument(
        "backup",
        help="backup folder containing sms.ib and phonebook.ib, or a single .ib file",
    )
    parser.add_argument(
        "-o",
        "--out",
        default="output",
        help="output directory, or output file for the chat command",
    )
    parser.add_argument(
        "--header-size",
        type=lambda value: int(value, 0),
        default=FILE_HEADER_SIZE,
        help="size of the file header in bytes (default: 0x244)",
    )
    parser.add_argument(
        "--aliases",
        help="optional JSON file mapping phone numbers to display names",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    aliases = _load_aliases(args.aliases)
    header_size = args.header_size

    if args.command == "contacts":
        contacts = _contacts(args.backup, header_size)
        if not contacts:
            raise SystemExit("phonebook.ib not found in %s" % args.backup)
        os.makedirs(args.out, exist_ok=True)
        counts = {}
        sms_path = _resolve(args.backup, "sms.ib")
        if os.path.exists(sms_path):
            counts = counts_by_number(load_messages(sms_path, header_size))
        write_contacts_csv(os.path.join(args.out, "contacts.csv"), contacts, counts)
        write_contacts_txt(os.path.join(args.out, "contacts.txt"), contacts, counts)
        write_contacts_vcf(os.path.join(args.out, "contacts.vcf"), contacts)
        write_contacts_html(os.path.join(args.out, "contacts.html"), contacts, counts)
        _summary([], contacts)
        print("written to %s" % args.out)
        return 0

    messages = _messages(args.backup, header_size)
    contacts = _contacts(args.backup, header_size)
    names = build_name_map(contacts, aliases)
    counts = counts_by_number(messages)

    if args.command == "sms":
        os.makedirs(args.out, exist_ok=True)
        write_sms_csv(os.path.join(args.out, "sms.csv"), messages, names)
        write_sms_txt(os.path.join(args.out, "sms.txt"), messages, names)
        write_sms_html(os.path.join(args.out, "sms.html"), messages, names)
        _summary(messages, contacts)
        print("written to %s" % args.out)
        return 0

    if args.command == "chat":
        path = args.out
        if os.path.isdir(path) or not os.path.splitext(path)[1]:
            os.makedirs(path, exist_ok=True)
            path = os.path.join(path, "chat.html")
        else:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        write_chat_html(path, messages, names)
        _summary(messages, contacts)
        print("written to %s" % path)
        return 0

    os.makedirs(args.out, exist_ok=True)
    write_sms_csv(os.path.join(args.out, "sms.csv"), messages, names)
    write_sms_txt(os.path.join(args.out, "sms.txt"), messages, names)
    write_sms_html(os.path.join(args.out, "sms.html"), messages, names)
    if contacts:
        write_contacts_csv(os.path.join(args.out, "contacts.csv"), contacts, counts)
        write_contacts_txt(os.path.join(args.out, "contacts.txt"), contacts, counts)
        write_contacts_vcf(os.path.join(args.out, "contacts.vcf"), contacts)
        write_contacts_html(os.path.join(args.out, "contacts.html"), contacts, counts)
    write_chat_html(os.path.join(args.out, "chat.html"), messages, names)
    _summary(messages, contacts)
    print("written to %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
