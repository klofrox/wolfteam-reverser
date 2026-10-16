"""Audit every catalog weapon's first-person (PV) model for broken skins, meshes and animations.

Reads the source LTB (extracted/), the converted .glb (assets/models/pv) and the weapondata skin
list (pv_model_and_skins) the client uses (weapon.js load(): material skinN <- skins[N + 1]) and
reports what would show up wrong in game: white / ghost hands, missing textures, vertices bound
to nothing, popping or missing Reload clips, Reload played much faster / slower than its clip.

  python tools/audit_weapons.py            -> docs/weapon_audit.txt + docs/weapon_audit.json
"""
import json
import math
import re
import os
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ltb  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TEX = os.path.join(ROOT, "assets", "textures")
PV = os.path.join(ROOT, "assets", "models", "pv")
HH = os.path.join(ROOT, "assets", "models", "hh")
HAND_BONE = re.compile(r"finger|hand|forearm|upperarm|clavicle", re.I)
NO_RELOAD = ("knife", "grenade", "bomb", "mine")


def glb_name(model):
    return os.path.splitext(os.path.basename(model.replace("\\", "/")))[0].lower().replace(" ", "_") + ".glb"


# weapon.js SKIN_FIX: data typos / a sprite -> the texture meant
SKIN_FIX = {"wt_guns/skins_pv/wt_pv_kei_2_hologramglasst.dtx": "wt_guns/skins_pv/wt_pv_kei_2_hologramglass.dtx",
            "wt_fx/torch/torchfire.spr": "wt_fx/torch/10006.dtx"}


def tex_png(entry):
    p = entry.replace("\\", "/").lower()
    p = SKIN_FIX.get(p) or re.sub(r"([^.])dtx$", r"\1.dtx", p)
    return os.path.join(TEX, p.replace(".dtx", ".png"))


def kind(s):
    """weapon.js weaponKind()"""
    model = (s.get("pv_model_and_skins") or [""])[0] or ""
    cls = s["id"] // 1000
    if s["id"] == 3:
        return "bomb"
    if cls == 8 and (s.get("explosion_damage") or 0) > 0:
        return "launcher"
    if s["id"] in (8507, 8508):
        return "minigun"
    if cls == 8 and s["id"] < 8500:
        return "mg"
    if cls == 9 and "mine" in model.lower():
        return "mine"
    if s.get("weapon_class") == 6 or s.get("projectile_type") == "Melee":
        return "knife"
    if s.get("weapon_class") in (2, 3) or cls == 9:
        return "grenade"
    return "gun"


def qangle(a, b):
    d = abs(sum(x * y for x, y in zip(a, b)))
    return 2 * math.degrees(math.acos(min(1.0, d)))


def bad(v):
    return any(math.isnan(x) or math.isinf(x) for x in v)


def scan_model(model):
    """per LTB model: pieces (texture index, weights), animation health"""
    src = os.path.join(ROOT, "extracted", model.replace("\\", "/").lower())
    out = {"model": model, "issues": [], "pieces": [], "anims": {}}
    if not os.path.exists(src):
        out["issues"].append(("LTB_MISSING", src))
        return out
    try:
        with open(src, "rb") as f:
            m = ltb.parse(f.read())
    except Exception as e:  # noqa: BLE001
        out["issues"].append(("LTB_PARSE", repr(e)))
        return out
    nn = len(m.nodes)
    if m.child_models:
        out["issues"].append(("CHILD_MODELS", ", ".join(m.child_models)))
    for p in m.pieces:
        lod = p["lods"][0] if p["lods"] else None
        if lod is None or lod.type == ltb.MESH_NULL or not lod.positions:
            continue
        none_w = sum(1 for w in lod.weights if not w)
        oob = sum(1 for w in lod.weights if w and any(b >= nn for b, _ in w))
        far = max((max(abs(c) for c in v) for v in lod.positions), default=0)
        nan = sum(1 for v in lod.positions if bad(v))
        # a hand / arm piece: most vertices hang on finger / hand / arm bones (names like Box01 say nothing)
        top = [max(w, key=lambda x: x[1])[0] for w in lod.weights if w]
        handish = sum(1 for b in top if b < nn and HAND_BONE.search(m.nodes[b].name))
        out["pieces"].append({"name": p["name"], "tex": list(lod.textures), "verts": len(lod.positions),
                              "unweighted": none_w, "bone_oob": oob, "far": far, "nan": nan,
                              "style": lod.render_style, "type": lod.type,
                              "hand": bool(top) and handish > 0.6 * len(top)})
    # animations: per clip length, missing tracks vs idle, key pops, NaN, far bone translations
    def tracks_of(a):
        return {m.nodes[i].name: t for i, t in enumerate(a["tracks"]) if m.nodes[i].parent is not None}
    idle = next((a for a in m.anims if a["name"].lower() in ("idle0", "idle")), None)
    idle_t = tracks_of(idle) if idle else {}
    for a in m.anims:
        info = {"ms": a["keys"][-1][0] if a["keys"] else 0, "keys": len(a["keys"]), "cmp": a["compression"],
                "no_track": [], "pop": [], "nan": 0, "far_move": []}
        for name, (pos, rot) in tracks_of(a).items():
            ip, ir = idle_t.get(name, ([], []))
            if (ir and not rot) or (ip and not pos):
                info["no_track"].append(name)
            if any(bad(x) for x in pos) or any(bad(x) for x in rot):
                info["nan"] += 1
            for i in range(1, len(rot)):
                ang = qangle(rot[i - 1], rot[i])
                dt = (a["keys"][i][0] - a["keys"][i - 1][0]) if i < len(a["keys"]) else 33
                # > 120 deg between neighbouring keys (and fast) = a bone flipping, not a motion
                if ang > 120 and dt <= 100:
                    info["pop"].append(f"{name}@{a['keys'][i][0] if i < len(a['keys']) else i}ms {ang:.0f}deg")
                    break
            if pos and ip:
                ref = ip[0]
                d = max(math.dist(x, ref) for x in pos)
                if d > 60:   # LTB units (cm): a bone 60 cm away from its idle place in a first-person clip
                    info["far_move"].append(f"{name} {d:.0f}")
        out["anims"][a["name"]] = info
    return out


def main():
    cat = json.load(open(os.path.join(ROOT, "client", "ui", "catalog.json"), encoding="utf-8"))["items"]
    stats = {w["id"]: w for w in json.load(open(os.path.join(ROOT, "assets", "data", "weapons_min.json"), encoding="utf-8"))}
    ids = sorted({int(k) for k, v in cat.items() if v["cat"] == "weapon"} | {3})
    models = sorted({stats[i]["pv_model_and_skins"][0] for i in ids if stats.get(i) and stats[i]["pv_model_and_skins"][0]})
    with ProcessPoolExecutor(max_workers=6) as pool:
        scans = {r["model"]: r for r in pool.map(scan_model, models, chunksize=4)}

    hand_png = [os.path.join(TEX, "wt_guns", "skins_pv", "humanhands", f"wt_pv_hand_{t}.png") for t in "rb"]
    report = []        # (weapon id, name, model, [issue (code, detail)])
    for i in ids:
        s = stats.get(i)
        name = (cat.get(str(i)) or {}).get("name") or s and s.get("name") or "?"
        if not s:
            report.append((i, name, "", [("NO_STATS", "")]))
            continue
        skins = s["pv_model_and_skins"]
        model = skins[0]
        k = kind(s)
        iss = []
        if not model:
            report.append((i, name, "", [("NO_PV_MODEL", "")]))
            continue
        if not os.path.exists(os.path.join(PV, glb_name(model))):
            iss.append(("GLB_MISSING", glb_name(model)))
        sc = scans[model]
        iss += sc["issues"]
        for p in sc["pieces"]:
            is_hand = p["hand"]
            t = p["tex"][0] if p["tex"] else 0
            entry = skins[t + 1] if t + 1 < len(skins) else None
            where = f"{p['name']} (tex{t})"
            if entry == "FirstHand":
                if not all(os.path.exists(os.path.join(TEX, "wt_guns", "skins_pv", f"firsthand_{t}.png")) for t in "rb"):
                    iss.append(("HAND_PNG_MISSING", f"{where} -> FirstHand"))
            elif entry == "HumanHands":
                if not is_hand:
                    iss.append(("HANDSKIN_ON_GUN", where))
                if not all(os.path.exists(h) for h in hand_png):
                    iss.append(("HAND_PNG_MISSING", where))
            elif is_hand:
                # hands wearing a gun skin, an env pass or nothing -> white / see-through hands
                iss.append(("HAND_WRONG_SKIN", f"{where} -> {entry or 'BOS'}"))
            elif not entry:
                iss.append(("SKIN_EMPTY", f"{where} (client: %25 saydam)"))
            elif "renderstyles" in entry.lower().replace("\\", "/") and "/env" in entry.lower().replace("\\", "/"):
                if not re.search(r"glass|lens|dot|sight|scope", p["name"], re.I) and not os.path.exists(tex_png(entry)):
                    iss.append(("SKIN_ENV_MISSING", f"{where} -> {entry}"))   # client: matcap with the env map
            elif not os.path.exists(tex_png(entry)):
                iss.append(("SKIN_PNG_MISSING", f"{where} -> {entry} (beyaz)"))
            if p["unweighted"]:
                iss.append(("MESH_UNWEIGHTED", f"{p['name']}: {p['unweighted']}/{p['verts']} vertex koke bagli (gerilme)"))
            if p["bone_oob"]:
                iss.append(("MESH_BONE_OOB", f"{p['name']}: {p['bone_oob']} vertex gecersiz kemik"))
            if p["nan"]:
                iss.append(("MESH_NAN", f"{p['name']}: {p['nan']} NaN vertex"))
            if p["far"] > 300:
                iss.append(("MESH_FAR", f"{p['name']}: {p['far']:.0f} birim uzakta vertex"))
        an = {n.lower(): v for n, v in sc["anims"].items()}
        if k not in NO_RELOAD and k != "minigun":
            r = an.get("reload")
            if not r:
                iss.append(("RELOAD_MISSING", ", ".join(sc["anims"])))
            else:
                rs = (s.get("reload_ms") or 0) / 1000
                if r["ms"] <= 0:
                    iss.append(("RELOAD_ZERO_LEN", f"{r['keys']} key"))
                elif rs > 0:
                    ts = (r["ms"] / 1000) / rs
                    shell = "reload2" in an and r["ms"] < 1200
                    # weapon.js: shell reloads loop Reload + Reload2, clips > 1.6x reload_ms play at their own speed
                    if not shell and ts < 0.5:
                        iss.append(("RELOAD_SPEED", f"klip {r['ms']} ms, reload_ms {s.get('reload_ms')} -> x{ts:.2f} hiz"))
        for n, v in sc["anims"].items():
            tag = "RELOAD" if n.lower() == "reload" else "ANIM"
            # POP: > 120 deg in one 33 ms key; uncompressed source data (spinning cylinders, snapped hands),
            # the original plays the same keys -> info only
            if v["no_track"]:
                iss.append((f"{tag}_NO_TRACK", f"{n}: {len(v['no_track'])} kemik bind pozuna doner ({', '.join(v['no_track'][:4])})"))
            if v["pop"]:
                iss.append((f"{tag}_POP", f"{n}: {'; '.join(v['pop'][:3])}"))
            if v["nan"]:
                iss.append((f"{tag}_NAN", f"{n}: {v['nan']} track"))
            if v["far_move"]:
                iss.append((f"{tag}_FAR", f"{n}: {'; '.join(v['far_move'][:3])}"))
        for want in ("select", "idle0") + (("fire",) if k == "gun" else ()):
            if want not in an:
                iss.append(("ANIM_MISSING", want))
        # third-person model + skin
        if s.get("hh_model") and not os.path.exists(os.path.join(HH, glb_name(s["hh_model"]))):
            iss.append(("HH_GLB_MISSING", s["hh_model"]))
        if s.get("hh_skin") and not os.path.exists(tex_png(s["hh_skin"])):
            iss.append(("HH_SKIN_MISSING", s["hh_skin"]))
        if iss:
            report.append((i, name, model, iss))

    by_code = defaultdict(list)
    for i, name, model, iss in report:
        for code, _ in iss:
            by_code[code].append(i)
    lines = [f"Silah denetimi: {len(ids)} silah, {len(models)} PV model, {len(report)} silahta sorun", ""]
    for code, w in sorted(by_code.items(), key=lambda x: -len(set(x[1]))):
        lines.append(f"{code:20s} {len(set(w)):4d} silah")
    lines.append("")
    for i, name, model, iss in report:
        lines.append(f"[{i}] {name}  ({os.path.basename(model.replace(chr(92), '/'))})")
        seen = set()
        for code, d in iss:
            if (code, d) in seen:
                continue
            seen.add((code, d))
            lines.append(f"    {code}: {d}")
    out = os.path.join(ROOT, "docs", "weapon_audit.txt")
    open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    json.dump([{"id": i, "name": n, "model": m, "issues": iss} for i, n, m, iss in report],
              open(os.path.join(ROOT, "docs", "weapon_audit.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n".join(lines[:40]))


if __name__ == "__main__":
    main()
