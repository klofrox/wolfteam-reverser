"""Lobby web links (top bar Web icon) from wt_attributes/webdata.dat -> client/ui/web.json.

Record: u16 id (1000.. group 0, 2000.. group 1), u8 group, wstr button texture (141x52 x 4 frames: normal / over /
down / disabled), wstr URL. The TR 2016 client (Joygame) is preferred: YouTube, Facebook, Ceza Sistemi, Forum, Haberler.
Run: python tools/build_webdata.py
"""
import json
import os
import struct

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = [os.path.join(ROOT, "extracted_tr", "wt_attributes", "webdata.dat"),
       os.path.join(ROOT, "extracted", "wt_attributes", "webdata.dat")]
DST = os.path.join(ROOT, "client", "ui", "web.json")


def wstr(b, o):
    n = struct.unpack_from("<H", b, o)[0]
    return b[o + 2:o + 2 + 2 * n].decode("utf-16-le"), o + 2 + 2 * n


def main():
    src = next(p for p in SRC if os.path.isfile(p))
    b = open(src, "rb").read()
    out, o = [], 0
    while o + 3 <= len(b):
        rid, group = struct.unpack_from("<HB", b, o)
        if not rid:
            break
        tex, o = wstr(b, o + 3)
        url, o = wstr(b, o)
        rel = tex.replace("\\", "/").lower().split("wt_interface/", 1)[-1].rsplit(".", 1)[0] + ".png"
        out.append({"id": rid, "group": group, "tex": rel, "url": url.replace("\\", "/")})
    json.dump(out, open(DST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(len(out), "links from", os.path.relpath(src, ROOT), "->", DST)


if __name__ == "__main__":
    main()
