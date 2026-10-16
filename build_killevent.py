"""Kill event missions of the TR client (wt_interface/attributes/stringtable/killeventstringtable.txt, UTF-16:
id <tab> "title" <tab> "text") -> client/ui/killevent.json, read by client/js/notices.js."""

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "extracted_tr", "wt_interface", "attributes", "stringtable", "killeventstringtable.txt")
OUT = os.path.join(ROOT, "client", "ui", "killevent.json")


def main():
    rows = []
    with open(SRC, encoding="utf-16") as f:
        for line in f:
            m = re.match(r'\s*(\d+)\s+"([^"]*)"\s+"([^"]*)"', line)
            if m:
                rows.append({"id": int(m.group(1)), "title": m.group(2).strip(),
                             "text": m.group(3).replace("\\n", "\n").strip()})
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    print(len(rows), "missions ->", OUT)


if __name__ == "__main__":
    main()
