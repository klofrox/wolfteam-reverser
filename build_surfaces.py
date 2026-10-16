"""Surfaces, impacts and map sounds -> client/ui/surfaces.json.

Sources (2016 client, LithTech "butes" text files):
  attributes/surface.txt   [SurfaceN] Id, foot sounds (human / wolf), bullet / melee / shell / grenade impact
                           sounds, bullet hole sprite, ImpactFXName (clientfx group per surface).
  attributes/fx.txt        [ImpactFXN] Name (= ammo ImpactFXName), FXName (clientfx group), DoSurfaceFX, Mark.
  attributes/weapons.txt   [AmmoN] Name, ImpactFXName, FireFXName.
  DTX headers              user_flags of a world texture = its surface Id (wt_tex/castle/cs_rock.dtx -> 102).
  assets/maps/*/objects.json  SoundFX objects (map ambience): sound, position, inner / outer radius, loop.

Output: {"surfaces": {id: {...}}, "textures": {dtx path: id}, "impacts": {weapondata bullet_fx (lower case): {fx, surfaceFx, mark}},
         "maps": {map: [{snd, pos, inner, outer, volume, loop}]}}
Radii and positions are in three.js metres (x 0.01, z flipped like the world).

  python tools/build_surfaces.py
"""
import glob
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dtx  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXT = os.path.join(ROOT, "extracted")
OUT = os.path.join(ROOT, "client", "ui", "surfaces.json")
S = 0.01


def butes(name):
    """{section: {key: value}} of a LithTech attribute file (comments removed, quotes stripped)."""
    t = open(os.path.join(EXT, "attributes", name), "rb").read().decode("latin1").replace("\r", "")
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    t = re.sub(r"//[^\n]*", "", t)
    out, cur = {}, None
    for line in t.split("\n"):
        line = line.strip()
        m = re.match(r"^\[([^\]]+)\]", line)
        if m:
            cur = out.setdefault(m.group(1), {})
            continue
        m = re.match(r"^(\w+)\s*=\s*(.*)$", line)
        if m and cur is not None:
            v = m.group(2).strip()
            if v.startswith('"'):
                v = v[1:v.find('"', 1)] if '"' in v[1:] else v[1:]
            cur[m.group(1)] = v
    return out


def snd(v):
    """sound path as the client's audio loader wants it (wt_snd/..., lower case), or None"""
    v = (v or "").strip().replace("\\", "/").lower()
    return v if v and os.path.exists(os.path.join(EXT, v)) else None


def spr_frames(path):
    """frames (png paths under assets/textures) of a .spr: 5 x u32 header, then u16-length strings"""
    p = os.path.join(EXT, path.replace("\\", "/").lower())
    if not os.path.exists(p):
        return None
    b = open(p, "rb").read()
    n = struct.unpack_from("<I", b, 0)[0]
    o, frames = 20, []
    for _ in range(n):
        ln = struct.unpack_from("<H", b, o)[0]
        f = b[o + 2:o + 2 + ln].decode("latin1").replace("\\", "/").lower()
        o += 2 + ln
        frames.append(os.path.splitext(f)[0] + ".png")
    return frames


def surfaces():
    out = {}
    for sec, v in butes("surface.txt").items():
        if not sec.lower().startswith("surface") or "Id" not in v:
            continue
        sid = int(v["Id"])
        hole = spr_frames(v.get("BulletHoleSpr", "")) if v.get("BulletHoleSpr") else None
        e = {
            "name": v.get("Name", ""),
            "foot": [x for x in (snd(v.get("RtFootSnd1")), snd(v.get("LtFootSnd1"))) if x],
            "footWolf": [x for x in (snd(v.get("RtFootSndWolf1")), snd(v.get("LtFootSndWolf1"))) if x],
            "bullet": [x for x in (snd(v.get("BulletImpactSnd1")), snd(v.get("BulletImpactSnd2"))) if x],
            "melee": [x for x in (snd(v.get("MeleeImpactSnd1")), snd(v.get("MeleeImpactSnd2"))) if x],
            "shell": snd(v.get("ShellImpactSnd1")), "grenade": snd(v.get("GrenadeImpactSnd")),
            "fall": snd(v.get("BodyFallSnd")),
            "fx": v.get("ImpactFXName") or None,
            # object.lto CGrenade touch (FUN_10138b10): a bounce keeps this share of the speed
            "hardness": float(v["Hardness"].split()[0]) if v.get("Hardness") else None,
        }
        if hole:
            e["hole"] = {"frames": hole, "min": float(v.get("BulletHoleMinScale", 1)), "max": float(v.get("BulletHoleMaxScale", 1))}
        out[str(sid)] = {k: x for k, x in e.items() if x not in (None, [], "")}
    return out


def impacts():
    fx = butes("fx.txt")
    # [PusherFXN]: knock-back of an explosion (radius / strength in units, delay / duration in s)
    pushers = {v["Name"]: {"radius": float(v.get("Radius", 0)), "delay": float(v.get("StartDelay", 0)),
                           "duration": float(v.get("Duration", 0)), "strength": float(v.get("Strength", 0))}
               for sec, v in fx.items() if sec.startswith("PusherFX") and v.get("Name")}
    impacts = {}
    for sec, v in fx.items():
        if sec.startswith("ImpactFX") and v.get("Name"):
            s = snd(v.get("Sound"))
            imp = {"fx": v.get("FXName") or None, "surfaceFx": v.get("DoSurfaceFX") == "1",
                   "mark": v.get("CreateMark") == "1",
                   # explosions: their own sound (grenades: MK-5G / Mass / Stick / ElecBomb ...) and knock-back
                   "sound": s, "soundRadius": float(v["SoundRadius"]) if s and v.get("SoundRadius") else None,
                   "pusher": pushers.get(v.get("PusherName") or "")}
            impacts[v["Name"].lower()] = {k: x for k, x in imp.items() if x not in (None, False)}
    return impacts   # weapondata bullet_fx names these directly (BulletFmj, handgrenade, ...)


def textures():
    """surface id of every texture used by a converted map (DTX user flags)"""
    out = {}
    for f in glob.glob(os.path.join(ROOT, "assets", "maps", "*", "*.glb")):
        b = open(f, "rb").read()
        n = struct.unpack_from("<I", b, 12)[0]
        for m in json.loads(b[20:20 + n]).get("materials", []):
            name = (m.get("name") or "").lower()
            if not name.endswith(".dtx") or name in out:
                continue
            p = os.path.join(EXT, name)
            if os.path.exists(p):
                with open(p, "rb") as fh:
                    out[name] = dtx.read_header(fh.read(164))["user_flags"] & 0xFF
    return out


def f32(v):
    """some float properties come through as raw bits (Volume 1120403456 = 100.0)"""
    if isinstance(v, int) and v > 1e6:
        return struct.unpack("<f", struct.pack("<I", v & 0xFFFFFFFF))[0]
    return float(v)


def map_sounds():
    out = {}
    for f in glob.glob(os.path.join(ROOT, "assets", "maps", "*", "objects.json")):
        name = os.path.basename(os.path.dirname(f))
        lst = []
        for o in json.load(open(f, encoding="utf-8"))["objects"]:
            p = o["props"]
            if o["type"] != "SoundFX" or not p.get("StartOn", True) or not p.get("position"):
                continue
            s = snd(p.get("Sound"))
            if not s:
                continue
            lst.append({"snd": s, "pos": [round(x, 3) for x in p["position"]],
                        "inner": round(float(p.get("InnerRadius", 300)) * S, 2),
                        "outer": round(float(p.get("OuterRadius", 1000)) * S, 2),
                        "volume": round(min(100.0, f32(p.get("Volume", 100))) / 100, 2),
                        "loop": bool(p.get("Loop", True)), "ambient": bool(p.get("Ambient", False))})
        if lst:
            out[name] = lst
    return out


def main():
    data = {"surfaces": surfaces(), "textures": textures(), "impacts": impacts(), "maps": map_sounds()}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"{len(data['surfaces'])} surfaces, {len(data['textures'])} textures, {len(data["impacts"])} impacts, "
          f"{sum(len(v) for v in data['maps'].values())} map sounds in {len(data['maps'])} maps")


if __name__ == "__main__":
    main()
