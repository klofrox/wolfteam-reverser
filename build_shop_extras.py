"""Shop extras data: weapon upgrades (upgradedata.dat / upgradetext.dat) -> client/ui/upgrades.json and the 70x70
EDS (item forge) icons of forge.dat -> client/ui/forge.json. Run from webport/: python tools/build_shop_extras.py

upgrades.json  weapons: {weapon id: [4 upgrade ids]} (weapondata raw o486)
               upgrades: {id: {name, short, info, desc, icon, price[5], d: {named stat: delta}, acc: {accuracy: delta},
                         fire_sound}}  price = Gold by the weapon's remaining time (permanent / >30 / >7 / >1 / 1 day,
                         the 100/60/40/10/2 ratio of o114). Deltas are added to the weapon (cshell FUN_34135f60).
forge.json     icons: {item code: item/forge/*.png}
"""
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamedata  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "assets", "data")
TEX = os.path.join(ROOT, "assets", "textures")
ATTR_TR = os.path.join(ROOT, "extracted_tr", "wt_attributes")
ATTR_US = os.path.join(ROOT, "extracted", "wt_attributes")
OUT = os.path.join(ROOT, "client", "ui")

SIGNED_U8 = {"p3", "o450", "o460"}            # weight / wolf stun / stopping power: 254 = -2
SKIP = {"weapon_class", "burst_limit"}        # o490 = 1 on every record (a flag, not a delta)
ICONS = [   # upgrade name keyword -> item/upicon*.png (the client picks one per upgrade kind)
    (r"sil[ei]n?c", "upicon11_silencer"), (r"suppress", "upicon02_suppressor"),
    (r"flash|compens|muzzle|choke", "upicon01_muzzle"), (r"front|rear|iron", "upicon03_ironsight"),
    (r"dot|holo|aiming", "upicon04_dotsight"), (r"scope", "upicon05_scope"), (r"barrel", "upicon06_barrel"),
    (r"hand ?guard|grip|stock|cheek|frame|plate", "upicon07_handguard"), (r"laser", "upicon08_laser"),
    (r"magazine|feed|tube|\d+r ", "upicon10_magazine"),
]


def icon_for(name):
    n = name.lower()
    return "item/" + next((f for pat, f in ICONS if re.search(pat, n)), "upicon09_ect") + ".png"


def signed(k, v):
    return v - 256 if k in SIGNED_U8 and isinstance(v, int) and v > 127 else v


def upgrades():
    data = json.load(open(os.path.join(DATA, "upgradedata.json"), encoding="utf-8"))
    us = json.load(open(os.path.join(DATA, "upgradetext.json"), encoding="utf-8"))
    text = dict(us)
    tr_path = os.path.join(ATTR_TR, "upgradetext.dat")
    if os.path.isfile(tr_path):
        for k, v in gamedata.read_text_table(open(tr_path, "rb").read(), 4).items():
            text[str(k)] = v
    out = {}
    for uid, r in data.items():
        d = {}
        for k, v in r.items():
            name = gamedata.NAMES.get(k, (None,))[0]
            if name and name not in SKIP and isinstance(v, (int, float)) and not isinstance(v, bool) and v:
                d[name] = signed(k, v)
        acc = {gamedata.ACCURACY_NAMES.get(k, (k,))[0]: v for k, v in (r.get("o34") or {}).items() if v}
        t = text.get(uid) or ["?", "", "", ""]
        wp = d.get("weapon_points", 0)
        rec = {"name": re.sub(r"\(완료\)", "", t[0]).strip() or "?", "short": t[1].strip(), "info": t[2].replace("%d", str(wp)).strip(),
               # the icon keywords are English: picked from the US name
               "desc": t[3].strip(), "icon": icon_for((us.get(uid) or t)[0]),
               "price": list(r.get("o114") or [0] * 5), "d": d}
        if acc:
            rec["acc"] = acc
        if r.get("o37c"):
            rec["fire_sound"] = r["o37c"]
        pv = r.get("o580") or []   # the part the upgrade shows on the gun (silencer / scope / grip ltb + its skin)
        if pv and pv[0]:
            rec["pv"] = [pv[0], "", pv[2] if len(pv) > 2 else "", pv[3] if len(pv) > 3 else ""]
        out[uid] = rec
    out = {k: v for k, v in out.items() if v["name"] != "?"}
    weapons = {}
    for w in json.load(open(os.path.join(DATA, "weapons.json"), encoding="utf-8")):
        # records with no text in either client are unused slots
        raw = w["modes"][0].get("raw", {}).get("o486") or []
        ids = [i for i in raw if out.get(str(i), {}).get("name", "?") != "?"]
        if ids:
            weapons[str(w["id"])] = ids
            for n, i in enumerate(raw):   # the part sits on the model's socket_WeaponAttach<n + 1>
                if str(i) in out and "pv" in out[str(i)]:
                    out[str(i)]["sock"] = n
    return {"weapons": weapons, "upgrades": out}


def wstr(b, o):
    n = struct.unpack_from("<H", b, o)[0]
    return b[o + 2:o + 2 + 2 * n].decode("utf-16-le", "replace"), o + 2 + 2 * n


def forge_icons():
    """forge.dat: u32 code, wstr name, wstr icon (WT_Interface\\Item\\Forge\\*.dtx), u16 w, u16 h (70 x 70)."""
    icons = {}
    for attr in (ATTR_US, ATTR_TR):   # TR over US
        p = os.path.join(attr, "forge.dat")
        if not os.path.isfile(p):
            continue
        b, o = open(p, "rb").read(), 0
        while o + 4 <= len(b):
            code = struct.unpack_from("<I", b, o)[0]
            _, o = wstr(b, o + 4)
            icon, o = wstr(b, o)
            o += 4
            # some records repeat the folder ("WT_Interface\Item\Forge\WT_Interface\Item\Forge\PI-90.dtx")
            rel = "item/forge/" + os.path.splitext(icon.replace("\\", "/").split("/")[-1].lower())[0] + ".png"
            if os.path.isfile(os.path.join(TEX, "wt_interface", rel)):
                icons[str(code)] = rel
    return {"icons": icons}


def main():
    up = upgrades()
    with open(os.path.join(OUT, "upgrades.json"), "w", encoding="utf-8") as f:
        json.dump(up, f, ensure_ascii=False, separators=(",", ":"))
    fg = forge_icons()
    with open(os.path.join(OUT, "forge.json"), "w", encoding="utf-8") as f:
        json.dump(fg, f, ensure_ascii=False, separators=(",", ":"))
    print(f"upgrades.json: {len(up['upgrades'])} upgrades, {len(up['weapons'])} weapons; forge.json: {len(fg['icons'])} icons")


if __name__ == "__main__":
    main()
