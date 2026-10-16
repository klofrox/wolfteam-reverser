# Mode objective lines per team (stringtable/mapmodecommentstringtable.txt, TR client) -> client/ui/modecomments.json.
# Shown above the equipment set picker: "Ölüm Oyunu : Kırmızı takım bu bölgedeki düşmanı yok eder."
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from export_ui_layouts import read_text  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = [os.path.join(ROOT, d, "wt_interface", "attributes", "stringtable", "mapmodecommentstringtable.txt")
       for d in ("extracted_tr", "extracted")]
OUT = os.path.join(ROOT, "client", "ui", "modecomments.json")


def parse(path):
    out = {}
    if not os.path.isfile(path):
        return out
    for block in re.findall(r"\[START\](.*?)\[END\]", read_text(path), re.S):
        f = dict(re.findall(r'^\s*(\w+)\s+"?([^"\r\n]*?)"?\s*$', block, re.M))
        mode, team = f.get("ModeType", "").strip(), f.get("TeamType", "").strip().lower()
        if mode and team:
            out.setdefault(mode, {})[team] = {"name": f.get("ModeName", "").strip(), "comment": f.get("Comment", "").strip()}
    return out


def main():
    data = parse(SRC[1])
    for mode, teams in parse(SRC[0]).items():   # Turkish over US
        data.setdefault(mode, {}).update(teams)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"{len(data)} modes -> {OUT}")


if __name__ == "__main__":
    main()
