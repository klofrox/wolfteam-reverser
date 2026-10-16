r"""Radio messages (Z / X / C in a match): client/ui/radio.json from wt_attributes/radiomsgsound.dat + the stringtable.

radiomsgsound.dat: records of u16 model index (modelbutes [ModelN]) + 3 wstrs (u16 count + UTF-16):
the Reply / Request / Tactics sound prefixes of that character's voice; "<prefix><n>.wav", n = 1..9
(WT_Snd\RadioMessage\Reply -> reply1.wav, ...\Angela_RE\Reply -> angela_re/reply1.wav).
Texts: stringtable 1700-1708 reply, 1710-1718 tactics, 1720-1728 request.
Keys (Profiles/Default.prf RadioMessage1..3 = Z X C): Z tactics, X request, C reply (our reading).

  python tools/build_radio.py
"""
import json
import os
import struct

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def main():
    b = open(os.path.join(ROOT, "extracted", "wt_attributes", "radiomsgsound.dat"), "rb").read()
    i, voices = 0, {}

    def wstr(i):
        n = struct.unpack_from("<H", b, i)[0]
        return b[i + 2:i + 2 + 2 * n].decode("utf-16le"), i + 2 + 2 * n

    while i + 2 <= len(b):
        key = struct.unpack_from("<H", b, i)[0]
        i += 2
        reply, i = wstr(i)
        _, i = wstr(i)
        _, i = wstr(i)
        folder = reply.replace("\\", "/").lower().rsplit("/", 1)[0]   # wt_snd/radiomessage[/angela_re]
        voices[str(key)] = folder
    strings = json.load(open(os.path.join(ROOT, "client", "ui", "layouts", "strings.json"), encoding="utf-8"))["stringtable"]
    groups = {g: [strings.get(str(base + k), f"{g} {k + 1}") for k in range(9)]
              for g, base in (("tactics", 1710), ("request", 1720), ("reply", 1700))}
    out = {"keys": {"KeyZ": "tactics", "KeyX": "request", "KeyC": "reply"},
           "titles": {"tactics": "Taktik", "request": "İstek", "reply": "Cevap"},
           "groups": groups, "default": "wt_snd/radiomessage", "voices": voices}
    json.dump(out, open(os.path.join(ROOT, "client", "ui", "radio.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("radio.json:", len(voices), "voices")


if __name__ == "__main__":
    main()
