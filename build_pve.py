"""PvE (Wolf Rush / boss) data and AI models -> client/ui/pve.json + assets/models/chars/ai/*.glb.

Sources (2016 client):
  wt_interface/attributes/map/mapattribute.txt  active PvE maps (PvETabType 1 normal / 2 hard / 3 boss,
      FM_AI_WOLFRUSH / GAME_MODE_WOLF_RUSH_BOSS, MapTagBGTexture colour = difficulty, BossAISetting).
  wt_attributes/pverounddata.dat  254-byte rows: u8 0, u8 2, u8 0x20, u8 boss, u32 MapIdentity, u32 round,
      11 x (u32 total, u32 at once) per AI wolf type, 18 flag bytes, 3 x 11 f32 (hp, damage, speed factors),
      f32 1.0, u32 reward tier.
  wt_attributes/aiwolfdata.dat  11 AI wolf types: model + skins (u16-length UTF-16), then f32 scale, f32 hp,
      u8 class, f32 walk / run / dash / turn / x, u8 u8, 3 bytes, u32 attack interval (ms), f32 damage,
      f32 attack range.
  wt_attributes/aibossdata.xml, aibossdata2.xml  Hound / Hell Hound bosses.
  wt_attributes/aipvescoregrade.dat  13-byte rows: u8 0, u8 2, u8 tab code, u8 difficulty, u8 grade (0 = S),
      u32 max, u32 min score.

AI wolf meshes use the shared wolf animation library (rig picked by bone set like convert_chars.py); the
bosses carry their own 29 clips and are converted with them.

  python tools/build_pve.py [--force]
"""
import json
import os
import re
import struct
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import convert_chars as cc  # noqa: E402
import ltb  # noqa: E402
import ltb2gltf  # noqa: E402

ROOT = cc.ROOT
ATTR = os.path.join(cc.EXT, "wt_attributes")
OUT_JSON = os.path.join(ROOT, "client", "ui", "pve.json")
OUT_AI = os.path.join(cc.OUT, "ai")
S = 0.01

MAP_NAMES = {"11045": "Bunker", "11043": "City Arena", "11046": "Ruins", "11021": "Junk Field",
             "11036": "Underworld", "11051": "Machu Picchu"}
# MapTagBGTexture colour -> difficulty
LEVELS = {"green": ("easy", "Kolay"), "blue": ("normal", "Normal"), "red": ("hard", "Zor"),
          "purple": ("hell", "Cehennem"), "gold": ("boss", "Boss")}
GRADES = ["S", "A", "B", "C", "D"]


def wstrings(b):
    """(start, end, text) of every u16-length UTF-16 string that looks like a file name."""
    out, p = [], 0
    while p < len(b) - 2:
        n = struct.unpack_from("<H", b, p)[0]
        if 3 < n < 200 and p + 2 + 2 * n <= len(b):
            try:
                s = b[p + 2:p + 2 + 2 * n].decode("utf-16-le")
                if s.isprintable() and "." in s[-5:]:
                    out.append((p, p + 2 + 2 * n, s))
                    p += 2 + 2 * n
                    continue
            except UnicodeDecodeError:
                pass
        p += 1
    return out


def read_ai_wolves():
    b = open(os.path.join(ATTR, "aiwolfdata.dat"), "rb").read()
    strs = wstrings(b)
    models = [i for i, s in enumerate(strs) if s[2].lower().endswith(".ltb")]
    wolves = []
    for k, mi in enumerate(models):
        stop = models[k + 1] if k + 1 < len(models) else len(strs)
        own = strs[mi:stop]
        end = strs[models[k + 1]][0] if k + 1 < len(models) else len(b)
        tail = b[max(e for _, e, _ in own):end]
        for o in range(0, max(0, len(tail) - 46)):
            sc, hp = struct.unpack_from("<2f", tail, o)
            if 0.5 <= sc <= 3 and 50 <= hp <= 20000:
                break
        else:
            continue
        t = tail[o:]
        sc, hp = struct.unpack_from("<2f", t, 0)
        walk, run, dash, turn = struct.unpack_from("<4f", t, 9)
        interval = struct.unpack_from("<I", t, 34)[0]
        dmg, reach = struct.unpack_from("<2f", t, 38)
        skins = [s for _, _, s in own[1:] if s.lower().endswith(".dtx") and "helmet" not in s.lower()]
        wolves.append({"model": own[0][2], "skins": skins, "scale": round(sc, 3), "hp": round(hp),
                       "class": t[8], "walk": walk, "run": run, "dash": dash, "turn": turn,
                       "interval": interval, "damage": round(dmg, 1), "reach": reach})
    return wolves


def read_rounds():
    b = open(os.path.join(ATTR, "pverounddata.dat"), "rb").read()
    rounds = {}
    for i in range(0, len(b) - 253, 254):
        r = b[i:i + 254]
        mid, n = struct.unpack_from("<2I", r, 4)
        pairs = struct.unpack_from("<22I", r, 12)
        f = struct.unpack_from("<33f", r, 118)
        rounds.setdefault(str(mid), []).append({
            "n": n, "boss": bool(r[3]),
            "wolves": [[pairs[2 * k], pairs[2 * k + 1]] for k in range(11)],
            "hp": [round(x, 2) for x in f[0:11]], "dmg": [round(x, 2) for x in f[11:22]],
            "speed": [round(x, 2) for x in f[22:33]], "tier": struct.unpack_from("<I", r, 250)[0]})
    for v in rounds.values():
        v.sort(key=lambda x: x["n"])
    return rounds


def read_grades():
    b = open(os.path.join(ATTR, "aipvescoregrade.dat"), "rb").read()
    out = {}
    for i in range(0, len(b) - 12, 13):
        r = b[i:i + 13]
        if r[1] != 2:
            continue
        hi, lo = struct.unpack_from("<2I", r, 5)
        out.setdefault(f"{r[2]:02x}-{r[3]}", []).append({"grade": GRADES[min(r[4], 4)], "min": lo, "max": hi})
    return out


def read_maps():
    t = open(os.path.join(cc.EXT, "wt_interface", "attributes", "map", "mapattribute.txt"), "rb").read().decode("utf-16-le", "replace")
    maps = []
    for blk in t.split("[START]"):
        d = {}
        for line in blk.splitlines():
            line = line.split("//")[0].strip()
            if line and not line.startswith("["):
                k, _, v = line.replace("\t", " ").partition(" ")
                d[k] = v.strip().strip('"')
        if "PvETabType" not in d or d.get("MapType") not in ("FM_AI_WOLFRUSH", "GAME_MODE_WOLF_RUSH_BOSS"):
            continue
        colour = re.search(r"band_(\w+)\.dtx", d.get("MapTagBGTexture", ""), re.I)
        level = LEVELS.get(colour.group(1).lower() if colour else "", ("normal", "Normal"))
        stem = os.path.splitext(d["MapFileName"].replace("\\\\", "\\").split("\\")[-1])[0]
        boss = d.get("BossAISetting", "").replace("\\\\", "\\").split("\\")[-1].lower()
        maps.append({"id": int(d["MapIdentity"]), "map": re.sub(r"[^a-z0-9_]+", "_", stem.lower()),
                     "title": MAP_NAMES.get(d.get("MapName"), stem), "tab": int(d["PvETabType"]),
                     "level": level[0], "levelLabel": level[1], "sort": int(d.get("MapSortID", 0)),
                     "boss": os.path.splitext(boss)[0] or None,
                     "music": d.get("BackgroundMusic", "").replace("\\\\", "/").replace("\\", "/").lower(),
                     "bossMusic": d.get("BackgroundMusicBoss", "").replace("\\\\", "/").replace("\\", "/").lower() or None})
    maps.sort(key=lambda m: (m["tab"], m["title"], m["sort"]))
    return maps


def num(v):
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return v if v not in ("", None) else None


def read_boss(name):
    t = open(os.path.join(ATTR, name + ".xml"), encoding="utf-8-sig").read()
    t = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;)", "&amp;", t)
    root = ET.fromstring(t)
    one = lambda tag: {k: num(v) for k, v in (root.find(tag).attrib if root.find(tag) is not None else {}).items()}
    model = one("Model")
    return {"name": root.find("BossName").get("Name"), "round": one("Appearance").get("Round"),
            "excite": one("Excitement"), "stats": one("Stats"), "regions": one("DamageByRegion"),
            "groups": one("AttackGroupInfo"), "model": model.get("WolfModel"),
            "skin": model.get("WolfSkin0"), "scale": model.get("WolfScale") or 1,
            "attacks": [{k: num(v) for k, v in a.attrib.items()} for a in root.findall("Attack")]}


def convert(src, dst, own_clips, force):
    if os.path.exists(dst) and not force:
        return
    m = ltb.parse(open(src, "rb").read())
    if own_clips:
        ltb2gltf.build(m, dst, [m], [], S, os.path.splitext(os.path.basename(src))[0], None)
    else:
        ltb2gltf.build(m, dst, [], [], S, os.path.splitext(os.path.basename(src))[0], None)


def find_model(name):
    """aiwolfdata / xml model paths -> extracted file (some live in other folders than the data says)."""
    p = cc.src_path(name)
    if os.path.exists(p):
        return p
    base = os.path.basename(name.replace("\\", "/")).lower()
    for d in ("wt_chars/models", "wt_chars/newchars/wolf_king", "wt_chars/newchars/ai_boss"):
        q = os.path.join(cc.EXT, d, base)
        if os.path.exists(q):
            return q
    return None


def main():
    force = "--force" in sys.argv
    os.makedirs(OUT_AI, exist_ok=True)
    rig_nodes = {rig: cc.node_names(cc.src_path(p)) for rig, p in cc.RIG_LIBS.items()}
    models, missing = {}, []

    def model_entry(path, skins, own_clips):
        src = find_model(path)
        if not src:
            missing.append(path)
            return None
        glb = "ai/" + cc.glb_name(path)
        convert(src, os.path.join(cc.OUT, glb), own_clips, force)
        names = cc.node_names(src)
        rig = None if own_clips else min(rig_nodes, key=lambda r: len(set(rig_nodes[r]) ^ set(names)))
        pngs = [cc.png_for(s) for s in skins]
        missing.extend(s for s, p in zip(skins, pngs) if s and not p)
        return {"glb": glb, "rig": rig, "skins": pngs, "alpha": []}

    wolves = read_ai_wolves()
    for i, w in enumerate(wolves):
        e = model_entry(w["model"], w["skins"], False)
        if e:
            models[f"w{i}"] = e
            w["body"] = f"w{i}"
    bosses = {}
    for name in ("aibossdata", "aibossdata2"):
        bo = read_boss(name)
        e = model_entry(bo["model"], [bo["skin"]], True)
        if e:
            models[name] = e
            bo["body"] = name
        bosses[name] = bo
    maps = read_maps()
    rounds = read_rounds()
    data = {"maps": maps, "rounds": {str(m["id"]): rounds.get(str(m["id"]), []) for m in maps},
            "wolves": wolves, "bosses": bosses, "grades": read_grades(), "models": models,
            "rigs": {r: f"anim_{r}.glb" for r in cc.RIG_LIBS}}
    json.dump(data, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"{len(maps)} PvE maps, {len(wolves)} AI wolf types, {len(bosses)} bosses, {len(models)} models")
    for m in maps:
        print(f"  {m['id']:3} {m['map']:24} tab {m['tab']} {m['level']:7} rounds {len(data['rounds'][str(m['id'])])} boss {m['boss']}")
    if missing:
        print("missing:", sorted(set(missing)))


if __name__ == "__main__":
    main()
