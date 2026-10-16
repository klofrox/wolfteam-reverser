"""Convert the client's UI definition files (wt_interface/attributes/{section,interface}/*.txt,
UTF-16 "[Start] key value ... [End]" blocks) to JSON the web client draws from.

Output: client/ui/layouts/<section|interface>/<name>.json
  [{"name", "type", "id", "parent", "size": [w,h], "pos": [x,y], "tex": ["wt_interface/...png"],
    "rects": {"def": [l,t,r,b], ...}, "font": {...}, "caption", "tip", "raw": {other keys}}]
Texture paths are rewritten to the PNGs under assets/textures (lower case, .png); a texture
that was not converted keeps its path with "missing": true on the control.
Layouts and strings come from the TR 2016 client (extracted_tr) where it has the file, else US 2016.
Strings: client/ui/layouts/strings.json  (stringtable.txt + tooltipstringtable.txt, id -> text)
"""
import json
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "extracted", "wt_interface", "attributes")
TEX = os.path.join(ROOT, "assets", "textures")
OUT = os.path.join(ROOT, "client", "ui", "layouts")

RECTS = {
    "ButtonDefaultRect": "def", "ButtonOverRect": "over", "ButtonClickRect": "down",
    "ButtonSelectRect": "sel", "ButtonDisableRect": "dis",
}
FONT = ("FontSize", "FontRect", "FontAlign", "CaptionStyle", "CaptionColor", "FontName",
        "CaptionOverColor", "CaptionClickColor", "CaptionDisableColor", "CaptionSelectColor")


def read_text(path):
    raw = open(path, "rb").read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw[: len(raw) // 2 * 2].decode("utf-16", errors="replace")
    for enc in ("utf-8", "cp949", "latin1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("latin1")


def strip_comment(line):
    out, quoted, i = [], False, 0
    while i < len(line):
        c = line[i]
        if c == '"':
            quoted = not quoted
        if not quoted and line.startswith("//", i):
            break
        out.append(c)
        i += 1
    return "".join(out).strip()


def value(text):
    text = text.strip()
    m = re.match(r'^"(.*)"', text)
    if m:
        return m.group(1).replace("\\\\", "\\")
    if text.startswith("("):  # e.g. "CaptionStyle 1 ( NORMAL = 0 ... )" already cut; keep raw
        return text
    parts = [p for p in re.split(r"[,\s]+", text) if p]
    nums = []
    for p in parts:
        try:
            nums.append(int(p))
        except ValueError:
            try:
                nums.append(float(p))
            except ValueError:
                return text
    return nums[0] if len(nums) == 1 else nums


def texture(path):
    rel = re.sub(r"(?i)^.*?(wt_interface[\\/])", r"\1", path).replace("\\", "/").lower()
    rel = re.sub(r"/+", "/", os.path.splitext(rel)[0] + ".png")
    return rel, os.path.isfile(os.path.join(TEX, rel))


def parse(path):
    controls = []
    cur = None
    for line in read_text(path).splitlines():
        line = strip_comment(line)
        if not line:
            continue
        if line.lower() == "[start]":
            cur = {"raw": {}}
            continue
        if line.lower() == "[end]":
            if cur is not None:
                controls.append(finish(cur))
            cur = None
            continue
        if cur is None:
            continue
        m = re.match(r"^(\w+)\s*(.*)$", line)
        if not m:
            continue
        key, rest = m.group(1), m.group(2)
        cur["raw"].setdefault(key, []).append(value(rest))
    return controls


def finish(c):
    raw = c.pop("raw")
    one = lambda k: raw.pop(k)[0] if k in raw else None
    out = {"name": one("Name"), "type": one("Type")}
    for k, dst in (("Identity", "id"), ("Parent", "parent")):
        v = one(k)
        if v is not None:
            out[dst] = v
    if "Size" in raw:
        out["size"] = one("Size")
    pos = None
    for k in ("RealPosition", "Position"):
        if k in raw:
            pos = raw.pop(k)[0]
    raw.pop("StartPosition", None)
    raw.pop("EndPosition", None)
    if pos is not None:
        out["pos"] = pos
    if "Texture" in raw:
        texs, missing = [], False
        for t in raw.pop("Texture"):
            rel, ok = texture(str(t))
            texs.append(rel)
            missing |= not ok
        out["tex"] = texs
        if missing:
            out["missing"] = True
    rects = {dst: raw.pop(k)[0] for k, dst in RECTS.items() if k in raw}
    if rects:
        out["rects"] = rects
    font = {k[0].lower() + k[1:]: raw.pop(k)[0] for k in FONT if k in raw}
    if font:
        out["font"] = font
    for k, dst in (("Caption", "caption"), ("ToolTipIndex", "tip"), ("ButtonType", "buttonType")):
        v = one(k)
        if v is not None:
            out[dst] = v
    if raw:
        out["raw"] = {k: (v[0] if len(v) == 1 else v) for k, v in raw.items()}
    return out


# Texts in Turkish: the Joygame TR 2016 client (extracted_tr, same ids); US 2016 fills ids TR lacks
SRC_TR = os.path.join(ROOT, "extracted_tr", "wt_interface", "attributes")
STRING_TABLES = ("stringtable.txt", "tooltipstringtable.txt", "gametipstringtable.txt",
                 "killeventstringtable.txt", "mapmodeinfostringtable.txt", "mapmodecommentstringtable.txt")
# The TR client's wt_interface stringtable.txt is still the English one (2156 / 2156 ids equal to US); its Turkish
# game strings are in extracted_tr/attributes/stringtable/stringtable.txt (1327 ids, laid over the table last).
TR_GAME_STRINGS = os.path.join(ROOT, "extracted_tr", "attributes", "stringtable", "stringtable.txt")


def read_table(path):
    table = {}
    if not os.path.isfile(path):
        return table
    for line in read_text(path).splitlines():
        # gametip rows are: id "title" "text"; the others: id "text"
        m = re.match(r'^\s*(\d+)\s+"(.*?)"(?:\s+"(.*)")?\s*(?://.*)?$', line)
        if m:
            table[m.group(1)] = (m.group(3) if m.group(3) is not None else m.group(2)).replace("\\n", "\n")
    return table


def load_strings():
    out = {}
    for name in STRING_TABLES:
        table = read_table(os.path.join(SRC, "stringtable", name))
        table.update({k: v for k, v in read_table(os.path.join(SRC_TR, "stringtable", name)).items() if v.strip()})
        if name == "stringtable.txt":
            table.update({k: v for k, v in read_table(TR_GAME_STRINGS).items() if v.strip()})
        if table:
            out[os.path.splitext(name)[0]] = table
    return out


def load_ranks():
    """class/class.txt: SerialNumber 61 (Recruit) .. 1 (G of the Army), 62 = GM.
    Returns ranks ordered from the lowest (level 1 = serial 61) to the highest."""
    out = []
    tr = os.path.join(SRC_TR, "class", "class.txt")   # Turkish rank names (same blocks / textures)
    text = read_text(tr if os.path.isfile(tr) else os.path.join(SRC, "class", "class.txt"))
    for block in re.findall(r"\[START\](.*?)\[END\]", text, re.S | re.I):
        f = lambda k: (re.search(rf'^\s*{k}\s+"?([^"\r\n]*)"?', block, re.M) or [None, ""])[1].strip()
        try:
            serial = int(f("SerialNumber"))
        except ValueError:
            continue
        out.append({"serial": serial, "name": f("ClassName"),
                    "back": texture(f("BackGround"))[0] if f("BackGround") else None,
                    "emblem": texture(f("Class"))[0] if f("Class") else None})
    ranks = sorted((r for r in out if r["serial"] <= 61), key=lambda r: -r["serial"])
    gm = [r for r in out if r["serial"] == 62]
    return {"ranks": ranks, "gm": gm[0] if gm else None}


def main():
    total = missing = 0
    for group in ("section", "interface"):
        os.makedirs(os.path.join(OUT, group), exist_ok=True)
        tr_dir = os.path.join(SRC_TR, group)
        names = set(os.listdir(os.path.join(SRC, group))) | set(os.listdir(tr_dir) if os.path.isdir(tr_dir) else [])
        for name in sorted(names):
            if not name.lower().endswith(".txt"):
                continue
            # the TR client's layout when it has one (Joygame web shop button, TR-only windows), else US
            src = os.path.join(tr_dir, name)
            controls = parse(src if os.path.isfile(src) else os.path.join(SRC, group, name))
            total += len(controls)
            missing += sum(1 for c in controls if c.get("missing"))
            dst = os.path.join(OUT, group, os.path.splitext(name)[0].lower() + ".json")
            json.dump(controls, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    json.dump(load_strings(), open(os.path.join(OUT, "strings.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(load_ranks(), open(os.path.join(OUT, "ranks.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(f"{total} controls, {missing} with a missing texture")


if __name__ == "__main__":
    main()
