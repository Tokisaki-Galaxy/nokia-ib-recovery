"""Exporters that turn parsed records into human friendly files."""

from __future__ import annotations

import csv
import datetime
import html
import json
import os
from typing import Dict, Iterable, List, Optional

from .phonebook import Contact
from .sms import SmsRecord


def format_address(address: str) -> str:
    """Return a readable form of a phone number or alphanumeric sender."""
    if address.startswith("86") and len(address) == 13:
        return "+" + address
    if len(address) == 11 and address[0] == "1":
        return "+86 " + address
    return address


def normalise_number(address: str) -> str:
    if address.startswith("86") and len(address) == 13:
        return address[2:]
    return address


def build_name_map(
    contacts: Optional[Iterable[Contact]], aliases: Optional[Dict[str, str]] = None
) -> Dict[str, str]:
    """Build a lookup from raw numbers to display names."""
    names: Dict[str, str] = {}
    for contact in contacts or []:
        if not contact.name:
            continue
        for number in contact.numbers:
            names[number.raw] = contact.name
            if number.raw.startswith("86") and len(number.raw) == 13:
                names[number.raw[2:]] = contact.name
    for key, value in (aliases or {}).items():
        names[key] = value
        names[normalise_number(key)] = value
    return names


def lookup_name(address: str, names: Dict[str, str]) -> str:
    if address in names:
        return names[address]
    key = normalise_number(address)
    return names.get(key, "")


def _time_text(value: Optional[datetime.datetime]) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


def write_sms_csv(
    path: str, messages: List[SmsRecord], names: Optional[Dict[str, str]] = None
) -> None:
    names = names or {}
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["Time", "Direction", "Address", "Name", "Text", "Parts", "Complete", "Offset"]
        )
        for message in messages:
            writer.writerow(
                [
                    _time_text(message.timestamp),
                    "Received" if message.incoming else "Sent",
                    format_address(message.address),
                    lookup_name(message.address, names),
                    message.text,
                    message.parts,
                    "yes" if message.complete else "no",
                    hex(message.offset),
                ]
            )


def write_sms_txt(
    path: str, messages: List[SmsRecord], names: Optional[Dict[str, str]] = None
) -> None:
    names = names or {}
    with open(path, "w", encoding="utf-8") as handle:
        received = sum(1 for item in messages if item.incoming)
        handle.write(
            "Recovered SMS: %d messages, %d received, %d sent\n"
            % (len(messages), received, len(messages) - received)
        )
        handle.write("=" * 60 + "\n\n")
        current_day = None
        for message in messages:
            day = message.timestamp.strftime("%Y-%m-%d") if message.timestamp else "unknown"
            if day != current_day:
                handle.write("\n" + "-" * 20 + " " + day + " " + "-" * 20 + "\n\n")
                current_day = day
            who = lookup_name(message.address, names) or format_address(message.address)
            direction = "Received" if message.incoming else "Sent"
            stamp = message.timestamp.strftime("%H:%M:%S") if message.timestamp else "--:--:--"
            handle.write("[%s] %s %s:\n" % (stamp, direction, who))
            for line in message.text.split("\n"):
                handle.write("    " + line + "\n")
            handle.write("\n")


def _page(title: str, subtitle: str, body: str, script: str = "") -> str:
    return (
        "<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
        "<link rel=\"icon\" href=\"data:,\">\n"
        "<title>" + html.escape(title) + "</title>\n<style>\n"
        "*{box-sizing:border-box}\n"
        "body{margin:0;font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;background:#eef2f5;color:#1f2937}\n"
        "header{position:sticky;top:0;background:#1f2937;color:#fff;padding:14px 20px;z-index:9;box-shadow:0 2px 8px rgba(0,0,0,.2)}\n"
        "header h1{margin:0 0 6px;font-size:18px;font-weight:600}\n"
        "header .stat{font-size:12px;opacity:.85}\n"
        "input.search{margin-top:10px;width:100%;max-width:420px;padding:8px 10px;border:0;border-radius:6px;font-size:14px;outline:none}\n"
        "main{max-width:900px;margin:0 auto;padding:18px 12px 60px}\n"
        "</style></head><body>\n<header><h1>" + html.escape(title) + "</h1>\n"
        "<div class=\"stat\">" + subtitle + "</div>\n</header>\n<main>\n" + body + "\n</main>\n" + script + "\n</body></html>"
    )


def write_sms_html(
    path: str, messages: List[SmsRecord], names: Optional[Dict[str, str]] = None
) -> None:
    names = names or {}
    rows: List[str] = []
    current_day = None
    for message in messages:
        day = message.timestamp.strftime("%Y-%m-%d") if message.timestamp else "unknown"
        if day != current_day:
            label = day
            if message.timestamp:
                label += " " + message.timestamp.strftime("%A")
            rows.append('<div class="day"><span>%s</span></div>' % html.escape(label))
            current_day = day
        direction = "in" if message.incoming else "out"
        who = lookup_name(message.address, names) or format_address(message.address)
        stamp = message.timestamp.strftime("%H:%M") if message.timestamp else ""
        tag = ""
        if message.parts > 1:
            tag = '<div class="tag">multipart %d parts%s</div>' % (
                message.parts,
                "" if message.complete else ", incomplete",
            )
        rows.append(
            '<div class="msg %s"><div class="meta"><span>%s</span><span>%s</span></div>'
            '<div class="bubble">%s</div>%s</div>'
            % (direction, html.escape(who), stamp, html.escape(message.text).replace("\n", "<br>"), tag)
        )

    received = sum(1 for item in messages if item.incoming)
    subtitle = "Total %d &nbsp; received %d &nbsp; sent %d" % (
        len(messages),
        received,
        len(messages) - received,
    )
    style = (
        "<style>\n"
        ".day{text-align:center;margin:22px 0 12px}\n"
        ".day span{background:#cbd5e1;color:#334155;font-size:12px;padding:3px 10px;border-radius:10px}\n"
        ".msg{display:flex;flex-direction:column;margin:8px 0;align-items:flex-start}\n"
        ".msg.out{align-items:flex-end}\n"
        ".meta{font-size:11px;color:#64748b;margin:0 8px 3px;display:flex;gap:8px}\n"
        ".bubble{max-width:78%;background:#fff;padding:9px 12px;border-radius:10px;line-height:1.6;font-size:14px;white-space:pre-wrap;word-wrap:break-word;box-shadow:0 1px 2px rgba(0,0,0,.08)}\n"
        ".msg.out .bubble{background:#95ec69}\n"
        ".tag{font-size:10px;color:#94a3b8;margin:2px 8px 0}\n"
        "</style>\n"
    )
    script = (
        "<script>\n"
        "document.getElementById('q').addEventListener('input',function(e){\n"
        "var k=e.target.value.trim().toLowerCase();\n"
        "[].forEach.call(document.querySelectorAll('.msg'),function(m){\n"
        "m.style.display=!k||m.textContent.toLowerCase().indexOf(k)>=0?'':'none';});});\n"
        "</script>"
    )
    body = '<input id="q" class="search" placeholder="Search messages">\n' + "\n".join(rows)
    page = _page("SMS archive", subtitle, body, script).replace("</style>", style + "</style>", 1)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(page)


def write_contacts_csv(
    path: str, contacts: List[Contact], counts: Optional[Dict[str, int]] = None
) -> None:
    counts = counts or {}
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["Name", "Name field 1", "Name field 2", "Numbers", "SMS count", "Extra", "Index"]
        )
        for contact in contacts:
            primary = contact.numbers[0].formatted if contact.numbers else ""
            all_numbers = " / ".join(number.formatted for number in contact.numbers)
            sms_count = sum(
                counts.get(normalise_number(number.raw), 0)
                for number in contact.numbers
            )
            writer.writerow(
                [
                    contact.name,
                    contact.name_first,
                    contact.name_second,
                    all_numbers or primary,
                    sms_count,
                    contact.extra,
                    contact.index,
                ]
            )


def write_contacts_txt(
    path: str, contacts: List[Contact], counts: Optional[Dict[str, int]] = None
) -> None:
    counts = counts or {}
    with open(path, "w", encoding="utf-8") as handle:
        total_numbers = sum(len(contact.numbers) for contact in contacts)
        handle.write(
            "Recovered contacts: %d entries, %d numbers\n" % (len(contacts), total_numbers)
        )
        handle.write("=" * 60 + "\n\n")
        for contact in contacts:
            handle.write(contact.name + "\n")
            for number in contact.numbers:
                handle.write("    " + number.formatted + "\n")
            if contact.extra:
                handle.write("    note: " + contact.extra + "\n")
            count = sum(
                counts.get(normalise_number(number.raw), 0)
                for number in contact.numbers
            )
            if count:
                handle.write("    matching messages: %d\n" % count)
            handle.write("\n")


def _vcard_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace(";", "\\;")
        .replace("\n", "\\n")
    )


def write_contacts_vcf(path: str, contacts: List[Contact]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        for contact in contacts:
            handle.write("BEGIN:VCARD\r\nVERSION:3.0\r\n")
            handle.write("FN:%s\r\n" % _vcard_escape(contact.name))
            if len(contact.name_second) == 1:
                handle.write(
                    "N:%s;%s;;;\r\n"
                    % (_vcard_escape(contact.name_second), _vcard_escape(contact.name_first))
                )
            else:
                handle.write("N:;%s;;;\r\n" % _vcard_escape(contact.name))
            for number in contact.numbers:
                handle.write("TEL;TYPE=CELL:%s\r\n" % _vcard_escape(number.vcard))
            if contact.extra and "-" in contact.extra:
                handle.write("NOTE:%s\r\n" % _vcard_escape(contact.extra))
            handle.write("END:VCARD\r\n")


def write_contacts_html(
    path: str, contacts: List[Contact], counts: Optional[Dict[str, int]] = None
) -> None:
    counts = counts or {}
    rows = []
    for contact in contacts:
        numbers = "<br>".join(html.escape(number.formatted) for number in contact.numbers)
        count = sum(
            counts.get(normalise_number(number.raw), 0)
            for number in contact.numbers
        )
        rows.append(
            "<tr><td class=\"n\">%s</td><td>%s</td><td>%s</td><td class=\"m\">%s</td></tr>"
            % (
                html.escape(contact.name),
                numbers,
                count or "",
                html.escape(contact.extra),
            )
        )
    total_numbers = sum(len(contact.numbers) for contact in contacts)
    subtitle = "Total %d contacts &nbsp; %d numbers" % (len(contacts), total_numbers)
    style = (
        "<style>\n"
        "table{width:100%;border-collapse:collapse;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.08);border-radius:8px;overflow:hidden}\n"
        "th,td{padding:10px 12px;text-align:left;font-size:14px;border-bottom:1px solid #e2e8f0;vertical-align:top}\n"
        "th{background:#e2e8f0;font-size:12px;color:#475569}\n"
        "td.n{font-weight:600;white-space:nowrap}\n"
        "td.m{color:#64748b;font-size:12px}\n"
        "tr:hover td{background:#f8fafc}\n"
        "</style>\n"
    )
    script = (
        "<script>\n"
        "document.getElementById('q').addEventListener('input',function(e){\n"
        "var k=e.target.value.trim().toLowerCase();\n"
        "[].forEach.call(document.querySelectorAll('tbody tr'),function(r){\n"
        "r.style.display=!k||r.textContent.toLowerCase().indexOf(k)>=0?'':'none';});});\n"
        "</script>"
    )
    body = (
        '<input id="q" class="search" placeholder="Search contacts">\n'
        "<table><thead><tr><th>Name</th><th>Numbers</th><th>SMS</th><th>Note</th></tr></thead><tbody>\n"
        + "\n".join(rows)
        + "\n</tbody></table>"
    )
    page = _page("Contacts", subtitle, body, script).replace("</style>", style + "</style>", 1)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(page)


def _json_for_script(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def write_chat_html(
    path: str,
    messages: List[SmsRecord],
    names: Optional[Dict[str, str]] = None,
) -> None:
    """Write a phone style conversation browser grouped by contact."""
    names = names or {}

    conversations: Dict[str, dict] = {}
    for message in messages:
        if not message.timestamp:
            continue
        label = lookup_name(message.address, names) or format_address(message.address)
        entry = conversations.setdefault(label, {"name": label, "nums": set(), "msgs": []})
        entry["nums"].add(normalise_number(message.address))
        entry["msgs"].append(
            {
                "t": message.timestamp.isoformat(),
                "d": 0 if message.incoming else 1,
                "x": message.text,
            }
        )

    ordered = []
    for entry in conversations.values():
        entry["msgs"].sort(key=lambda item: item["t"])
        entry["nums"] = sorted(entry["nums"])
        entry["last"] = entry["msgs"][-1]["t"]
        ordered.append(entry)
    ordered.sort(key=lambda item: item["last"], reverse=True)

    data = _json_for_script(ordered)

    template = r'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<link rel="icon" href="data:,">
<title>Conversations</title>
<style>
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{height:100%}
body{margin:0;font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;background:#ededed;color:#111;overflow:hidden}
#app{display:flex;height:100%}
#sidebar{width:320px;min-width:280px;background:#fff;border-right:1px solid #dcdcdc;display:flex;flex-direction:column}
#sidebar header{padding:16px 16px 10px;background:#f7f7f7;border-bottom:1px solid #e5e5e5}
#sidebar h1{margin:0 0 10px;font-size:18px;font-weight:600}
#search{width:100%;padding:8px 12px;border:0;border-radius:8px;background:#e9e9e9;font-size:14px;outline:none}
#convs{flex:1;overflow-y:auto;margin:0;padding:0;list-style:none}
.conv{display:flex;gap:12px;padding:12px 14px;border-bottom:1px solid #f0f0f0;cursor:pointer;align-items:center}
.conv:hover{background:#f5f5f5}
.conv.active{background:#e8f4e2}
.ava{width:44px;height:44px;border-radius:50%;background:#cfd8dc;color:#37474f;display:flex;align-items:center;justify-content:center;font-size:18px;flex:0 0 44px}
.conv-main{flex:1;min-width:0}
.conv-top{display:flex;justify-content:space-between;gap:8px}
.conv-name{font-size:15px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.conv-time{font-size:11px;color:#999;flex:0 0 auto}
.conv-prev{font-size:12px;color:#888;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:3px}
#chat{flex:1;display:flex;flex-direction:column;min-width:0;background:#ededed}
#chat>header{height:56px;display:flex;align-items:center;gap:10px;padding:0 14px;background:#f7f7f7;border-bottom:1px solid #ddd;flex:0 0 56px}
#back{display:none;border:0;background:none;font-size:26px;line-height:1;color:#2e7d32;cursor:pointer;padding:0 4px}
#chatName{font-size:16px;font-weight:600}
#chatSub{font-size:11px;color:#999;margin-top:2px}
#msgs{flex:1;overflow-y:auto;padding:16px 14px 40px}
.day{text-align:center;margin:16px 0 10px}
.day span{font-size:11px;color:#999;background:#e0e0e0;padding:2px 8px;border-radius:9px}
.msg{display:flex;margin:6px 0}
.msg.out{justify-content:flex-end}
.b{max-width:76%;padding:8px 11px;border-radius:10px;background:#fff;font-size:14px;line-height:1.6;white-space:pre-wrap;word-wrap:break-word;box-shadow:0 1px 1px rgba(0,0,0,.06);position:relative}
.msg.out .b{background:#95ec69}
.t{font-size:9px;color:#999;margin:2px 4px 0;text-align:right}
.empty{color:#999;text-align:center;margin-top:80px;font-size:14px}
@media (max-width:720px){
  #sidebar{width:100%;border-right:0}
  #chat{display:none}
  #app.open #sidebar{display:none}
  #app.open #chat{display:flex}
  #back{display:block}
}
</style></head><body>
<div id="app">
  <aside id="sidebar">
    <header><h1>Messages</h1><input id="search" placeholder="Search name or text"></header>
    <ul id="convs"></ul>
  </aside>
  <section id="chat">
    <header><button id="back">&#8249;</button><div><div id="chatName"></div><div id="chatSub"></div></div></header>
    <div id="msgs"><div class="empty">Select a conversation</div></div>
  </section>
</div>
<script>
const DATA = __DATA__;
const app=document.getElementById('app'), list=document.getElementById('convs'),
      msgs=document.getElementById('msgs'), chatName=document.getElementById('chatName'),
      chatSub=document.getElementById('chatSub'), q=document.getElementById('search');
function pad(n){return n<10?'0'+n:''+n}
function d(v){return new Date(v)}
function fmtList(v){
  const t=d(v), now=new Date();
  if(t.toDateString()===now.toDateString()) return pad(t.getHours())+':'+pad(t.getMinutes());
  if(t.getFullYear()===now.getFullYear()) return (t.getMonth()+1)+'/'+t.getDate();
  return t.getFullYear()+'/'+pad(t.getMonth()+1)+'/'+pad(t.getDate());
}
function fmtDay(v){
  const t=d(v);
  return t.getFullYear()+'-'+pad(t.getMonth()+1)+'-'+pad(t.getDate())+' '+['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][t.getDay()];
}
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function renderList(){
  const k=q.value.trim().toLowerCase();
  list.innerHTML='';
  DATA.forEach(function(c,i){
    const hay=(c.name+' '+c.msgs.map(function(m){return m.x}).join(' ')).toLowerCase();
    if(k && hay.indexOf(k)<0) return;
    const li=document.createElement('li');
    li.className='conv'; li.dataset.i=i;
    const last=c.msgs[c.msgs.length-1];
    const prev=(last.d?'Me: ':'')+last.x.replace(/\n/g,' ');
    li.innerHTML='<div class="ava">'+esc(Array.from(c.name)[0]||'?')+'</div>'+
      '<div class="conv-main"><div class="conv-top"><span class="conv-name">'+esc(c.name)+
      '</span><span class="conv-time">'+fmtList(last.t)+'</span></div>'+
      '<div class="conv-prev">'+esc(prev)+'</div></div>';
    li.onclick=function(){openChat(i)};
    list.appendChild(li);
  });
}
function openChat(i){
  const c=DATA[i];
  chatName.textContent=c.name;
  chatSub.textContent='Total '+c.msgs.length+(c.nums.length?' - '+c.nums.join('  '):'');
  let out='', day='';
  c.msgs.forEach(function(m){
    const t=d(m.t), ds=t.toDateString();
    if(ds!==day){day=ds; out+='<div class="day"><span>'+fmtDay(m.t)+'</span></div>';}
    out+='<div class="msg '+(m.d?'out':'in')+'"><div class="b">'+esc(m.x)+
         '<div class="t">'+pad(t.getHours())+':'+pad(t.getMinutes())+'</div></div></div>';
  });
  msgs.innerHTML=out;
  app.classList.add('open');
  msgs.scrollTop=msgs.scrollHeight;
  Array.prototype.forEach.call(document.querySelectorAll('.conv'),function(el){
    el.classList.toggle('active', +el.dataset.i===i);
  });
}
document.getElementById('back').onclick=function(){app.classList.remove('open')};
q.oninput=renderList;
renderList();
</script></body></html>'''
    page = template.replace("__DATA__", data)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(page)


def counts_by_number(messages: Iterable[SmsRecord]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for message in messages:
        key = normalise_number(message.address)
        counts[key] = counts.get(key, 0) + 1
    return counts


def export_everything(
    messages: List[SmsRecord],
    contacts: List[Contact],
    outdir: str,
    names: Optional[Dict[str, str]] = None,
    aliases: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Write every supported output file and return the paths."""
    os.makedirs(outdir, exist_ok=True)
    names = names if names is not None else build_name_map(contacts, aliases)
    counts = counts_by_number(messages)

    written = []
    files = [
        ("sms.csv", lambda p: write_sms_csv(p, messages, names)),
        ("sms.txt", lambda p: write_sms_txt(p, messages, names)),
        ("sms.html", lambda p: write_sms_html(p, messages, names)),
        ("contacts.csv", lambda p: write_contacts_csv(p, contacts, counts)),
        ("contacts.txt", lambda p: write_contacts_txt(p, contacts, counts)),
        ("contacts.vcf", lambda p: write_contacts_vcf(p, contacts)),
        ("contacts.html", lambda p: write_contacts_html(p, contacts, counts)),
        ("chat.html", lambda p: write_chat_html(p, messages, names)),
    ]
    for name, writer in files:
        path = os.path.join(outdir, name)
        writer(path)
        written.append(path)
    return written
