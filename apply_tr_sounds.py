"""Turkish voices: copy every wt_snd file of the TR 2016 client (extracted_tr/wt_snd_tr) that differs from the US 2016
one, or exists only in TR, to assets/sound/tr/wt_snd/<lower-case path> and list them in client/ui/tr_sounds.json.
client/js/trsound.js sends those paths there instead of extracted/ (announcer, radio messages, Ceyda / Esra voices).

Run: python tools/apply_tr_sounds.py
"""
import hashlib
import json
import os
import shutil

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
US = os.path.join(ROOT, "extracted", "wt_snd")
TR = os.path.join(ROOT, "extracted_tr", "wt_snd_tr", "wt_snd")
OUT = os.path.join(ROOT, "assets", "sound", "tr", "wt_snd")
LIST = os.path.join(ROOT, "client", "ui", "tr_sounds.json")


def digest(path):
    return hashlib.md5(open(path, "rb").read()).digest()


def main():
    out = []
    for root, _, names in os.walk(TR):
        for n in names:
            if not n.lower().endswith((".wav", ".ogg")):
                continue
            src = os.path.join(root, n)
            rel = os.path.relpath(src, TR)
            us = os.path.join(US, rel)
            if os.path.isfile(us) and os.path.getsize(us) == os.path.getsize(src) and digest(us) == digest(src):
                continue
            key = "wt_snd/" + rel.replace(os.sep, "/").lower()
            dst = os.path.join(OUT, *key.split("/")[1:])
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
            out.append(key)
    out.sort()
    with open(LIST, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"{len(out)} Turkish sounds -> {OUT}, list {LIST}")


if __name__ == "__main__":
    main()
