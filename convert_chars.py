"""Convert the playable characters (catalog codes 30xxx) to assets/models/chars/*.glb.

Data path (2016 client):
  wt_attributes/characterdata.dat  21-byte rows, two per character code: the human row
      (u16 code, u16 0xffff, ...) and the wolf row (u16 code, u16 0x09c6, ...); u16 at +9 is
      the [ModelN] index in attributes/modelbutes.txt, byte +8 the team (0 blue, 1 red).
  attributes/modelbutes.txt  [ModelN] ModelFile + Skin0..9 (LTB texture-index order) +
      RenderStyle0..6.

Meshes are converted WITHOUT textures or animations: materials are named skinN by LTB texture
index and the client assigns Skin N, and the animations come from one shared library per
skeleton (rig): wt_new_man_ch / wt_new_woman_ch / wt_new_wolf_ch, converted to anim_<rig>.glb.
A piece whose texture index has no skin (empty Skin, tattoo slots 10+) is hidden by the client.

Writes assets/models/chars/index.json:
  {"rigs": {rig: glb}, "chars": {code: {"name", "team", "human": model, "wolf": model}},
   "mutants": {type: {"red": model, "blue": model}},
   "models": {model: {"name", "glb", "rig", "skins": [png or null], "alpha": [tex indices]}},
   "parts": {code: {"fit": model, "cat": helmet|vest|elbow|knee|gloves|boots,
                    "pieces": [{"glb", "skin", "socket"}] | "swap": {"slot", "skin"}}}}
Accessory pieces (wt_attributes/charcustomize.dat) go to parts/*.glb and hang on the body's
socket nodes; a 30xxx record there is the character's own default head piece.

  python tools/convert_chars.py [--force]
"""
import collections
import json
import os
import re
import struct
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ltb  # noqa: E402
import ltb2gltf  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXT = os.path.join(ROOT, "extracted")
OUT = os.path.join(ROOT, "assets", "models", "chars")
TEX = os.path.join(ROOT, "assets", "textures")
RIG_LIBS = {
    "man": "wt_chars/models/wt_new_man_ch.ltb",
    "woman": "wt_chars/models/wt_new_woman_ch.ltb",
    "wolf": "wt_chars/models/wt_new_wolf_ch.ltb",
}
# mutant wolves (wolfattr.dat row order): [ModelN] 2 + 2 * type is red, 3 + 2 * type blue
MUTANTS = ["basic", "power", "guardian", "ghost", "berserker", "smart", "ghost2", "ice", "psycho"]
# extra wolf clips: the Wolf King's T_Dash / T_Dash_JJ / JT / JL (the gallop of the dash, item 19601 / 19610) and
# T_BITE_Skill; same skeleton as the wolf minus two ponytail bones. Every mutant gets its own library: its _ch
# model's clips (berserker T_DBM / T_Fi1, ice / psycho UMTF ...) over the basic wolf's, then these.
WOLF_EXTRA = "wt_chars/newchars/wolf_king/wolf_king_ch.ltb"


def src_path(p):
    return os.path.join(EXT, p.replace("\\", "/").lower())


def read_modelbutes():
    with open(os.path.join(EXT, "attributes", "modelbutes.txt"), "rb") as f:
        t = re.sub(r"//[^\n]*", "", f.read().decode("latin1"))
    models = {}
    for m in re.finditer(r"\[Model(\d+)\](.*?)(?=\n\s*\[|\Z)", t, re.S):
        kv = {k.lower(): v.strip().strip('"') for k, v in re.findall(r"^\s*(\w+)\s*=\s*([^\n\r]*)", m.group(2), re.M)}
        models[int(m.group(1))] = kv
    return models


def read_characterdata():
    with open(os.path.join(EXT, "wt_attributes", "characterdata.dat"), "rb") as f:
        b = f.read()
    chars = collections.defaultdict(dict)
    for o in range(0, len(b) - 20, 21):
        code, kind = struct.unpack_from("<HH", b, o)
        model = struct.unpack_from("<H", b, o + 9)[0]
        if kind == 0xFFFF:
            chars[code]["human"] = model
            chars[code]["team"] = "red" if b[o + 8] == 1 else "blue"
        elif kind == 0x09C6:
            chars[code]["wolf"] = model
    return chars


def read_charcustomize():
    """Accessories (wt_attributes/charcustomize.dat). Each record: u16 code, u16 fit (the
    [ModelN] of the character it is made for), u8 kind, u16 slot, u16 ?, then u16-length
    UTF-16 strings. kind 0: per piece model + skins, render styles, then one socket name per
    piece (s_helmet, s_Vest, s_Elbow_L/R, s_Knee_L/R). kind 1: a skin swap of the body's
    texture index `slot` (4 boots, 5 gloves). Records are not length-prefixed, so they are
    found by their header pattern."""
    with open(os.path.join(EXT, "wt_attributes", "charcustomize.dat"), "rb") as f:
        b = f.read()
    wt = "WT_".encode("utf-16le")

    def is_str(p, n):
        return 0 < n < 300 and p + 2 + 2 * n <= len(b) and all(
            0x20 <= b[p + 2 + 2 * i] < 0x7F and b[p + 3 + 2 * i] == 0 for i in range(n))

    def is_header(p):
        if p + 13 > len(b):
            return False
        code, fit = struct.unpack_from("<HH", b, p)
        if not (30000 <= code < 35000 and fit < 2000 and b[p + 4] in (0, 1)):
            return False
        q = p + 9
        if b[p + 4] == 1 and struct.unpack_from("<H", b, q)[0] == 0:
            q += 2
        n = struct.unpack_from("<H", b, q)[0]
        return is_str(q, n) and b[q + 2:q + 8] == wt

    recs, cur, p = [], None, 0
    while p < len(b) - 1:
        if is_header(p):
            code, fit = struct.unpack_from("<HH", b, p)
            cur = {"code": code, "fit": fit, "kind": b[p + 4], "slot": struct.unpack_from("<H", b, p + 5)[0], "strs": []}
            recs.append(cur)
            p += 9
            continue
        n = struct.unpack_from("<H", b, p)[0]
        if n == 0:
            if cur:
                cur["strs"].append("")
            p += 2
        elif is_str(p, n):
            if cur:
                cur["strs"].append(b[p + 2:p + 2 + 2 * n].decode("utf-16le"))
            p += 2 + 2 * n
        else:
            p += 1

    parts = {}
    for r in recs:
        s = r["strs"]
        if r["kind"] == 1:
            skin = next((x for x in s if x.lower().endswith(".dtx")), None)
            if skin and r["slot"] in (4, 5):
                parts.setdefault(r["code"], {"fit": r["fit"], "cat": "boots" if r["slot"] == 4 else "gloves",
                                             "swap": {"slot": r["slot"], "skin": skin}})
            continue
        models = [(i, x) for i, x in enumerate(s) if x.lower().endswith(".ltb") and "\\rs_" not in x.lower()]
        sockets = [x for x in s if x.lower().startswith("s_")]
        pieces = []
        for k, (i, model) in enumerate(models):
            skin = s[i + 1] if i + 1 < len(s) and s[i + 1].lower().endswith(".dtx") else ""
            socket = sockets[k] if k < len(sockets) else (sockets[-1] if sockets else None)
            if socket:
                pieces.append({"model": model, "skin": skin, "socket": socket})
        if not pieces:
            continue
        sock = pieces[0]["socket"].lower()
        cat = ("helmet" if "helmet" in sock else "vest" if "vest" in sock else "elbow" if "elbow" in sock
               else "knee" if "knee" in sock else "etc")
        parts.setdefault(r["code"], {"fit": r["fit"], "cat": cat, "pieces": pieces})
    return parts


def glb_name(model_file):
    parts = model_file.replace("\\", "/").lower().split("/")
    stem = os.path.splitext(parts[-1])[0]
    folder = parts[-2] if len(parts) > 1 else ""
    name = stem if folder in ("models", stem) else f"{folder}__{stem}"
    return re.sub(r"[^a-z0-9_]+", "_", name) + ".glb"


def png_for(skin):
    if not skin:
        return None
    rel = os.path.splitext(skin.replace("\\", "/").lower())[0] + ".png"
    return rel if os.path.exists(os.path.join(TEX, rel)) else None


def node_names(path):
    with open(path, "rb") as f:
        return [n.name for n in ltb.parse(f.read()).nodes]


def own_anim_lib(path):
    """The model's own animation library (its LTB child model, e.g. the SE fire wolves' WT_SE_FIREWOLF_CH.ltb with
    their own T_CRY etc.) as an extracted path, or None when it is one of RIG_LIBS / missing."""
    with open(path, "rb") as f:
        children = ltb.parse(f.read()).child_models or []
    std = {os.path.basename(p).lower() for p in RIG_LIBS.values()}
    for ch in children:
        name = os.path.basename(ch.replace("\\", "/")).lower()
        lib = src_path("wt_chars/models/" + name)
        if name not in std and os.path.exists(lib):
            return lib
    return None


def convert(job):
    src, dst, libs, force = job
    if os.path.exists(dst) and not force:
        return dst, "skip", None
    try:
        with open(src, "rb") as f:
            m = ltb.parse(f.read())
        anim_models = []
        for lib in libs:
            with open(lib, "rb") as f:
                anim_models.append(ltb.parse(f.read()))
        exclude = ".*" if libs else None   # animation libraries: skeleton + clips only
        ltb2gltf.build(m, dst, anim_models, [], 0.01, os.path.splitext(os.path.basename(src))[0], exclude)
        tex_rs = {}
        for p in m.pieces:
            lod = p["lods"][0] if p["lods"] else None
            if lod is not None and lod.textures:
                tex_rs[lod.textures[0]] = lod.render_style
        return dst, "ok", tex_rs
    except Exception:
        return dst, "ERR " + traceback.format_exc(limit=1).strip().splitlines()[-1], None


def main():
    force = "--force" in sys.argv
    os.makedirs(OUT, exist_ok=True)
    cat = json.load(open(os.path.join(ROOT, "client", "ui", "catalog.json"), encoding="utf-8"))["items"]
    butes = read_modelbutes()
    cdata = read_characterdata()

    rig_nodes = {rig: node_names(src_path(p)) for rig, p in RIG_LIBS.items()}
    chars, used = {}, set()
    for code, c in sorted(cdata.items()):
        it = cat.get(str(code))
        if not it or it["cat"] != "char" or "human" not in c:
            continue
        chars[str(code)] = {"name": it["name"], "team": c.get("team"), "human": c["human"], "wolf": c.get("wolf")}
        used.update(x for x in (c["human"], c.get("wolf")) if x is not None)
    used.update(range(2, 2 + 2 * len(MUTANTS)))

    models, jobs, by_glb = {}, [], {}
    for idx in sorted(used):
        mb = butes.get(idx)
        if not mb or not mb.get("modelfile") or not os.path.exists(src_path(mb["modelfile"])):
            continue
        names = node_names(src_path(mb["modelfile"]))
        rig = next((r for r, n in rig_nodes.items() if n == names), None)
        if rig is None:   # same bone set in another order / extra finger bones: closest library
            rig = min(rig_nodes, key=lambda r: len(set(rig_nodes[r]) ^ set(names)))
        glb = glb_name(mb["modelfile"])
        skins = [png_for(mb.get(f"skin{i}", "")) for i in range(max(10, 1 + max(
            [int(k[4:]) for k in mb if re.fullmatch(r"skin\d+", k)] or [0])))]
        while skins and skins[-1] is None:
            skins.pop()
        rs = {i: mb.get(f"renderstyle{i}", "") for i in range(8)}
        models[str(idx)] = {"name": mb.get("name", ""), "glb": glb, "rig": rig, "skins": skins, "_rs": rs,
                            "_lib": own_anim_lib(src_path(mb["modelfile"]))}
        if glb not in by_glb:
            by_glb[glb] = str(idx)
            jobs.append((src_path(mb["modelfile"]), os.path.join(OUT, glb), [], force))
    # accessories: rigid models attached to the character's sockets, or body skin swaps
    parts = {}
    os.makedirs(os.path.join(OUT, "parts"), exist_ok=True)
    part_glbs = set()
    for code, pt in sorted(read_charcustomize().items()):
        if str(code) not in cat:
            continue
        entry = {"fit": pt["fit"], "cat": pt["cat"]}
        if "swap" in pt:
            png = png_for(pt["swap"]["skin"])
            if not png:
                continue
            entry["swap"] = {"slot": pt["swap"]["slot"], "skin": png}
        else:
            pieces = []
            for pc in pt["pieces"]:
                if not os.path.exists(src_path(pc["model"])):
                    continue
                glb = "parts/" + glb_name(pc["model"])
                pieces.append({"glb": glb, "skin": png_for(pc["skin"]), "socket": pc["socket"]})
                if glb not in part_glbs:
                    part_glbs.add(glb)
                    jobs.append((src_path(pc["model"]), os.path.join(OUT, glb), [], force))
            if not pieces:
                continue
            entry["pieces"] = pieces
        parts[str(code)] = entry

    rigs = {}
    rig_force = force or "--rigs" in sys.argv   # --rigs: rebuild only the animation libraries
    extra = [src_path(WOLF_EXTRA)] if os.path.exists(src_path(WOLF_EXTRA)) else []
    for rig, p in RIG_LIBS.items():
        rigs[rig] = f"anim_{rig}.glb"
        jobs.append((src_path(p), os.path.join(OUT, rigs[rig]), [src_path(p)] + (extra if rig == "wolf" else []), rig_force))
    for t in MUTANTS[1:]:
        p = src_path(f"wt_chars/models/wt_wolf_{t}_ch.ltb")
        if os.path.exists(p):
            rigs[f"wolf_{t}"] = f"anim_wolf_{t}.glb"
            jobs.append((p, os.path.join(OUT, rigs[f"wolf_{t}"]), [p, src_path(RIG_LIBS["wolf"])] + extra, rig_force))
    # characters with their own clip library (SE fire / ice / radiation / lightning wolves, the woman wolves, RE,
    # Ramadan ...): its clips over the rig's standard ones, like the mutants (rig "lib_<file>")
    own_rig = {}
    for m in models.values():
        lib = m.get("_lib")
        stem = os.path.splitext(os.path.basename(lib))[0].lower() if lib else None
        if not lib or any(f"wt_wolf_{t}_ch" == stem for t in MUTANTS):
            continue
        key = f"lib_{stem}"
        if key not in rigs:
            rigs[key] = f"anim_{stem}.glb"
            jobs.append((lib, os.path.join(OUT, rigs[key]), [lib, src_path(RIG_LIBS[m["rig"]])] + (extra if m["rig"] == "wolf" else []), rig_force))
        own_rig[id(m)] = key

    tex_rs, errors = {}, []
    with ProcessPoolExecutor() as pool:
        for dst, status, rs in pool.map(convert, jobs):
            if status.startswith("ERR"):
                errors.append((dst, status))
            if rs is not None:
                tex_rs[os.path.basename(dst)] = rs
    if os.path.exists(os.path.join(OUT, "index.json")) and not force:   # keep alpha info of skipped models
        old = json.load(open(os.path.join(OUT, "index.json"), encoding="utf-8"))
        for m in old.get("models", {}).values():
            if m["glb"] not in tex_rs and "alpha" in m:
                tex_rs[m["glb"]] = {t: 5 for t in m["alpha"]}
                tex_rs[m["glb"]]["_cached"] = True
    bad = {os.path.basename(d) for d, _ in errors}
    for k in list(models):
        m = models[k]
        if m["glb"] in bad or not os.path.exists(os.path.join(OUT, m["glb"])):
            del models[k]
            continue
        rs = m.pop("_rs")
        m.pop("_lib", None)
        own = own_rig.get(id(m))
        if own and os.path.exists(os.path.join(OUT, rigs[own])):
            m["rig"] = own
        per_tex = tex_rs.get(m["glb"], {})
        if per_tex.pop("_cached", False):
            m["alpha"] = sorted(int(t) for t in per_tex)
        else:
            m["alpha"] = sorted(int(t) for t, s in per_tex.items() if "alpha" in rs.get(s, "").lower())
    for code in list(chars):
        c = chars[code]
        if str(c["human"]) not in models:
            del chars[code]
        elif c["wolf"] is not None and str(c["wolf"]) not in models:
            c["wolf"] = None
    for code in list(parts):
        pt = parts[code]
        if "pieces" in pt:
            pt["pieces"] = [pc for pc in pt["pieces"] if os.path.basename(pc["glb"]) not in bad
                            and os.path.exists(os.path.join(OUT, pc["glb"]))]
            if not pt["pieces"]:
                del parts[code]
    mutants = {name: {"red": str(2 + 2 * i), "blue": str(3 + 2 * i)} for i, name in enumerate(MUTANTS)
               if str(2 + 2 * i) in models and str(3 + 2 * i) in models}
    for name, sides in mutants.items():   # the mutant's own clip library
        if f"wolf_{name}" in rigs and os.path.exists(os.path.join(OUT, rigs[f"wolf_{name}"])):
            for idx in sides.values():
                models[idx]["rig"] = f"wolf_{name}"
    json.dump({"rigs": rigs, "chars": chars, "models": models, "parts": parts, "mutants": mutants},
              open(os.path.join(OUT, "index.json"), "w", encoding="utf-8"), indent=0, ensure_ascii=False)
    size = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT))
    size += sum(os.path.getsize(os.path.join(OUT, "parts", f)) for f in os.listdir(os.path.join(OUT, "parts")))
    print(f"{len(chars)} characters, {len(models)} models ({len(by_glb)} files), {len(parts)} accessories "
          f"({len(part_glbs)} part files), {len(errors)} errors, {size / 1e6:.0f} MB")
    for d, e in errors[:15]:
        print("  ", os.path.basename(d), e)


if __name__ == "__main__":
    main()
