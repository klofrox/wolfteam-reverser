"""Pride / crest data -> client/ui/social.json (read by the client and by social.py).

Sources (wt_attributes):
  crestdata.dat     crest challenges: u16 id, u8 kind (0 kill, 1 mode, 2 etc), u16 group, u8 tier, u16 value,
                    wstr icon, u16 count, u16 WC price, 20 bytes; the first record is the "none" icon.
  cresttext.dat     u16 id, wstr name, wstr text ("Headshot %d times accomplished (%dWC)").
  pridemarkdata.dat Pride mark parts: u32 id, u32 type (high word = category, low word = layer 0 background,
                    1 frame, 2 ribbon, 3 arms), wstr file number; layer files in wt_pride/step1_64 (background),
                    step2_64 (frame), step3_64 (ribbon). Arms (layer 3) has no complete folder in the 2016
                    archive and is left out.
  prideladdermark.dat  ladder tiers: u8 id, wstr name, u16 string id, u16, wstr texture, 2 bytes.

  python tools/build_social.py
"""
import json
import os
import re
import struct

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ATTR = os.path.join(ROOT, "extracted", "wt_attributes")
TEX = os.path.join(ROOT, "assets", "textures")
OUT = os.path.join(ROOT, "client", "ui", "social.json")
# what each crest group counts (match_end / item events in social.py); "none" = no counter in this port yet
CREST_EVENTS = {1000: "headshot", 1001: "knife", 1002: "plant", 1003: "wolfking", 1004: "discard",
                1005: "gift", 1006: "box"}
LAYERS = {0: "step1_64", 1: "step2_64", 2: "step3_64"}


def wstr(b, o):
    n = struct.unpack_from("<H", b, o)[0]
    return b[o + 2:o + 2 + 2 * n].decode("utf-16le", "replace"), o + 2 + 2 * n


def png(path):
    rel = os.path.splitext(path.replace("\\", "/").lower())[0] + ".png"
    return rel if os.path.exists(os.path.join(TEX, rel)) else None


def crests():
    text = {}
    t = open(os.path.join(ATTR, "cresttext.dat"), "rb").read()
    o = 0
    while o < len(t):
        cid = struct.unpack_from("<H", t, o)[0]
        name, o = wstr(t, o + 2)
        desc, o = wstr(t, o)
        text[cid] = (name, desc)
    b = open(os.path.join(ATTR, "crestdata.dat"), "rb").read()
    out, o = [], 0
    while o + 8 < len(b):
        cid, kind, group, tier, value = struct.unpack_from("<HBHBH", b, o)
        icon, o = wstr(b, o + 8)
        count, price = struct.unpack_from("<HH", b, o)
        o += 4 + 20
        if cid == 0:
            continue
        name, desc = text.get(cid, ("", ""))
        out.append({"id": cid, "kind": kind, "group": group, "tier": tier + 1, "value": value, "icon": png(icon),
                    "count": count, "price": price, "name": name,
                    "text": desc.replace("%d", str(count), 1).replace("%d", str(price), 1),
                    "event": CREST_EVENTS.get(group)})
    return out


def marks():
    b = open(os.path.join(ATTR, "pridemarkdata.dat"), "rb").read()
    out, o = {"background": [], "frame": [], "ribbon": []}, 0
    names = ["background", "frame", "ribbon"]
    while o < len(b):
        mid, typ = struct.unpack_from("<II", b, o)
        num, o = wstr(b, o + 8)
        layer, cat = typ & 0xFFFF, typ >> 16
        if layer not in LAYERS:
            continue
        p = png(f"wt_pride/{LAYERS[layer]}/{num}")
        if p:
            out[names[layer]].append({"id": mid, "cat": cat, "tex": p})
    return out


def tiers():
    b = open(os.path.join(ATTR, "prideladdermark.dat"), "rb").read()
    out, o = [], 0
    while o + 3 < len(b):
        tid = b[o]
        name, o = wstr(b, o + 1)
        o += 4
        tex, o = wstr(b, o)
        o += 2
        out.append({"id": tid, "name": name, "tex": png(tex)})
    return out


def main():
    data = {"crests": crests(), "marks": marks(), "tiers": tiers()}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(data['crests'])} crests, marks {[len(v) for v in data['marks'].values()]}, tiers {[t['name'] for t in data['tiers']]}")


if __name__ == "__main__":
    main()
