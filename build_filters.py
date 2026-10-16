"""Chat / call-sign word filters of the TR 2016 client -> assets/data/chat_filter.json (read by chatfilter.py).

wt_attributes/filterabusestring.txt (1142 Turkish + English words, chat), filterabusecallsign.txt (146, nicknames,
quoted, incl. "GM" / "[" style reserved bits). UTF-16 LE, one entry per line. US 2016 has only the English 146.
Run: python tools/build_filters.py
"""
import json
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "extracted_tr", "wt_attributes")
DST = os.path.join(ROOT, "assets", "data", "chat_filter.json")


def words(name):
    raw = open(os.path.join(SRC, name), "rb").read()
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("cp1254")
    out = []
    for line in text.splitlines():
        w = line.strip().strip('"').strip()
        if w and w not in out:
            out.append(w)
    return out


def main():
    data = {"chat": words("filterabusestring.txt"), "callsign": words("filterabusecallsign.txt")}
    with open(DST, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"chat {len(data['chat'])}, callsign {len(data['callsign'])} -> {DST}")


if __name__ == "__main__":
    main()
