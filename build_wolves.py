"""Wolf system data -> client/ui/wolves.json (read by the client and by match_wolf.py).

Sources (2016 client):
  wt_attributes/wolfattr.dat   mutant wolf rows: wstr name + 26 bytes (4 x i16, 2 x u8, 6 x i16, i16, 2 x u8).
      Four groups of ten rows; the first (Conquest) is used. Row order = MUTANTS. Column meanings are our
      reading of the numbers (see docs/wolf.md "Mutant wolves"): c1 damage %, c2 speed %, c3 reach (units),
      c4 ghost (translucent), c5 can ride walls, c6 extra HP, c7..c10 armor head/body/arm/leg %, c14 extra HP
      drained per second. Armor is taken at half (45-55 % on every mutant reads too strong next to the
      extra HP; our choice).
  weapondata (assets/data/weapons_min.json)  per-type attacks: "<Type> Melee Attack (1st..3rd)", "falling".
  catalog.json   Medical Kit / Steam Pack numbers, Wolf Strengthening items, Skill Up items (from the texts).
  wt_attributes/abilityswingtrail.dat  u16 code, 5 bytes, wstr texture, 4 x wstr bone names (claw trail).
  wt_attributes/abilitytattoo.dat      u16 code, u16, wstr texture, 6 bytes, 2 x wstr render styles.

  python tools/build_wolves.py
"""
import json
import os
import re
import struct

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ATTR = os.path.join(ROOT, "extracted", "wt_attributes")
TEX = os.path.join(ROOT, "assets", "textures")
OUT = os.path.join(ROOT, "client", "ui", "wolves.json")

MUTANTS = ["basic", "power", "guardian", "ghost", "berserker", "smart", "ghost2", "ice", "psycho"]
# Turkish names: TR catalog 11001-11006 (Güçlü / Gardiyan / Çılgın / Buz / Deli / Zeki Kurt), stringtable 2505 / 2508
LABELS = {"basic": "Kurt", "power": "Güçlü Kurt", "guardian": "Gardiyan Kurt", "ghost": "Hayalet Kurt", "berserker": "Çılgın Kurt", "smart": "Zeki Kurt", "ghost2": "Hayalet Kurt-2", "ice": "Buz Kurt", "psycho": "Deli Kurt"}
# weapondata ids: 3-hit combo (Berserker / Smart have their own sets) and the falling attack
ATTACKS = {
    "basic": ([1, 16, 17], [18, 19]), "power": ([20, 21, 22], [23, 24]), "guardian": ([25, 26, 27], [18, 19]),
    "ghost": ([30, 31, 32], [33, 34]), "berserker": ([10], [18, 19]), "smart": ([14, 35], [18, 19]),
    "ghost2": ([36, 37, 38], [39, 40]), "ice": ([41, 42, 43], [44, 45]), "psycho": ([46, 47, 48], [49]),
}
SKILL_WEAPONS = {"berserker": 11, "smart": 15}   # Suicidal Explosion, Smart Wolf Assault
# hudmyteamforceinfo_wolf.txt Identity order; the first three come with the stations, the rest need
# "2nd Wolf Mutation" (10010). need = stations the team must hold (our choice, not in the data)
FORCES = [("power", 1, 1), ("guardian", 1, 3), ("ghost", 1, 2), ("smart", 2, 1),
          ("berserker", 2, 2), ("ghost2", 2, 3), ("ice", 2, 2), ("psycho", 2, 3)]
ICONS = {"ghost2": "ghost_2"}


def wstr(b, o):
    n = struct.unpack_from("<H", b, o)[0]
    return b[o + 2:o + 2 + 2 * n].decode("utf-16le", "replace"), o + 2 + 2 * n


def png(path):
    rel = os.path.splitext(path.replace("\\", "/").lower())[0] + ".png"
    return rel if os.path.exists(os.path.join(TEX, rel)) else None


def wolfattr():
    b = open(os.path.join(ATTR, "wolfattr.dat"), "rb").read()
    rows, o = [], 0
    while o < len(b):
        name, o = wstr(b, o)
        rows.append((name, struct.unpack_from("<4h2B6hh2B", b, o)))
        o += 26
    return rows


def types(weapons):
    rows = wolfattr()
    out = {}
    for i, name in enumerate(MUTANTS):
        v = rows[i][1]
        combo, falling = ATTACKS[name]
        t = {
            "label": LABELS[name], "dmg_pct": v[1], "speed_pct": v[2], "reach": v[3], "ghost": bool(v[4]),
            "wall": bool(v[5]), "xhp": max(0, v[6]), "armor": [a // 2 for a in v[7:11]], "drain": v[14],
            "combo": [c for c in combo if c in weapons], "falling": [c for c in falling if c in weapons],
        }
        if name in SKILL_WEAPONS:
            t["skill_weapon"] = SKILL_WEAPONS[name]
        out[name] = t
    out["basic"].update(xhp=0, drain=0, armor=[0, 0, 0, 0], dmg_pct=0, speed_pct=0, reach=0)
    return out


def num(desc, label):
    pat = r"\s+".join(re.escape(w) for w in label.split()) + r"(?:\([^)]*\))?[^\n+\-\d(]*\n?\s*([+\-]?\s*\d+)"
    m = re.search(pat, desc, re.I)
    return int(m.group(1).replace(" ", "")) if m else 0


def items(cat):
    medkit, steam, strength, skillup = {}, {}, {}, {}
    for it in cat.values():
        name, d = it["name"], it.get("desc") or ""
        if name.startswith("Medical Kit"):
            medkit[it["id"]] = {"heal": num(d, "Immediate reduction HP"), "regen": num(d, "HP Reduction per minute"),
                                "uses": num(d, "maximum number of use") or 1, "dur": num(d, "Duration") or 15}
        elif name.startswith("Steam Pack"):
            steam[it["id"]] = {"armor": num(d, "Wolf head AP"), "speed": num(d, "Speed Up"),
                               "hp_cut": abs(num(d, "Immediate reduction HP")), "drain": abs(num(d, "HP Reduction per Sec")),
                               "dur": num(d, "Duration") or 10, "dmg": num(d, "Basic power")}
        m = re.match(r"Wolf Strengthening item\s*\((\w+)\)", name)
        if m and m.group(1).lower() in MUTANTS:
            strength[it["id"]] = m.group(1).lower()
        m = re.match(r"(\w+) Wolf Skill Up", name)
        if m and m.group(1).lower() in MUTANTS:
            skillup[it["id"]] = {"type": m.group(1).lower(), "regen": num(d, "HP feedback system"),
                                 "attack": num(d, "Attack"),
                                 "keep": abs(num(d, "Additional HP"))}
    return medkit, steam, strength, skillup


def trails():
    b = open(os.path.join(ATTR, "abilityswingtrail.dat"), "rb").read()
    out, o = {}, 0
    while o < len(b) - 4:
        code = struct.unpack_from("<H", b, o)[0]
        o += 7
        tex, o = wstr(b, o)
        for _ in range(4):
            _, o = wstr(b, o)
        p = png(tex)
        if p:
            out[str(code)] = p
    return out


def tattoos(cat):
    b = open(os.path.join(ATTR, "abilitytattoo.dat"), "rb").read()
    out, o = {}, 0
    while o < len(b) - 4:
        code = struct.unpack_from("<H", b, o)[0]
        tex, o = wstr(b, o + 4)
        o += 6
        _, o = wstr(b, o)
        _, o = wstr(b, o)
        it = cat.get(code)
        p = png(tex)
        if not it or not p:
            continue
        m = re.search(r"Tattoo\s*\(?\s*([BLR])\b", it["name"])
        side = m.group(1) if m else "B"
        out[str(code)] = {"tex": p, "slot": {"B": 10, "L": 14, "R": 18}[side]}
    return out


def main():
    weapons = {w["id"]: w for w in json.load(open(os.path.join(ROOT, "assets", "data", "weapons_min.json"), encoding="utf-8"))}
    cat = json.load(open(os.path.join(ROOT, "client", "ui", "catalog.json"), encoding="utf-8"))["items"]
    cat = {int(k): v for k, v in cat.items()} if isinstance(cat, dict) else {x["id"]: x for x in cat}
    medkit, steam, strength, skillup = items(cat)
    data = {
        "types": types(weapons),
        "forces": [{"type": t, "set": s, "need": n, "icon": ICONS.get(t, t)} for t, s, n in FORCES],
        "mutation2": 10010,
        "medkit": medkit, "steam": steam, "strength": strength, "skillup": skillup,
        "trails": trails(), "tattoos": tattoos(cat),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(data['types'])} types, medkit {list(medkit)}, steam {list(steam)}, strength {strength}, "
          f"skillup {len(skillup)}, trails {len(data['trails'])}, tattoos {len(data['tattoos'])}")


if __name__ == "__main__":
    main()
