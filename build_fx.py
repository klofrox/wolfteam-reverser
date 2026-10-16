"""ClientFX groups (clientfx/clientfx.fxf, LithTech FxED text) -> client/ui/fx.json for client/js/clientfx.js.

The .fxf lists "Groups: N", each "GroupName" with "FxInGroup" effects; an effect has FxName ("Type;label"),
StartTime / EndTime / Repeat and typed properties (Type 0 STRING, 1 INTEGER, 2 FLOAT, 3 COMBO "index,choices",
4 VECTOR, 5 VECTOR4 scale key "Sk", 6 CLRKEY colour key "Ck", 7 PATH "kind|file").

Kept types: ParticleSystem, Sprite, DynaLight, PlaySound, CamJitter, CreateFX (LTBModel / PolyTrail / LightningFX
and the rest are dropped). Paths become what the client loads: sprites -> png frame lists (.spr: 5 x u32 header
+ u16-length frame names), textures -> png under assets/textures, sounds -> wt_snd/... when the file exists.
Vectors stay in LithTech units (the client converts).

  python tools/build_fx.py
"""
import json
import os
import re
import struct

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXT = os.path.join(ROOT, "extracted")
TEX = os.path.join(ROOT, "assets", "textures")
OUT = os.path.join(ROOT, "client", "ui", "fx.json")
TYPES = {"ParticleSystem", "Sprite", "DynaLight", "PlaySound", "CamJitter", "CreateFX"}
SKIP = {"MenuLayer", "DisableAtDist", "DetailLevel", "RandomizeStartOffset", "StartOffsetInterval",
        "MaxStartOffset", "EffectShaderID", "SmoothShutDown", "IsGore", "Priority", "UseMarkers",
        "MultiPlaySound", "CastVisibleRay", "SplatPercent", "KillOnSplat", "SplatEffect", "AttachName",
        "LightParticles", "CollideModels", "FlipRenderingOrder", "DisableLight", "ForceLightWorld"}
_spr = {}


def png(path):
    rel = os.path.splitext(path.replace("\\", "/").lower())[0] + ".png"
    return rel if os.path.exists(os.path.join(TEX, rel)) else None


def spr(path):
    path = path.replace("\\", "/").lower()
    if path in _spr:
        return _spr[path]
    out = None
    p = os.path.join(EXT, path)
    if os.path.exists(p):
        b = open(p, "rb").read()
        n, rate = struct.unpack_from("<II", b, 0)
        o, frames = 20, []
        for _ in range(n):
            ln = struct.unpack_from("<H", b, o)[0]
            f = png(b[o + 2:o + 2 + ln].decode("latin1"))
            o += 2 + ln
            if f:
                frames.append(f)
        if frames:
            out = {"frames": frames, "rate": rate}
    _spr[path] = out
    return out


def path_value(v):
    kind, _, f = v.partition("|")
    if not f or f == "...":
        return None
    if kind == "spr":
        return spr(f)
    if kind == "dtx":
        p = png(f)
        return {"frames": [p], "rate": 1} if p else None
    if kind == "wav":
        p = f.replace("\\", "/").lower()
        return p if os.path.exists(os.path.join(EXT, p)) else None
    return None


def parse():
    t = open(os.path.join(EXT, "clientfx", "clientfx.fxf"), "rb").read().decode("latin1").replace("\r", "")
    lines = [l.strip() for l in t.split("\n")]
    groups, i = {}, 0
    cur = fx = None
    while i < len(lines):
        l = lines[i]
        if l.startswith("GroupName:"):
            cur = groups.setdefault(l.split(":", 1)[1].strip(), [])
            fx = None
        elif l.startswith("FxName:") and cur is not None:
            kind = l.split(":", 1)[1].strip().split(";")[0]
            fx = {"type": kind, "props": {}, "ck": [], "sk": []}
            cur.append(fx)
        elif fx is not None and l.startswith(("StartTime:", "EndTime:", "Repeat:")):
            k, v = l.split(":", 1)
            fx[{"StartTime": "start", "EndTime": "end", "Repeat": "repeat"}[k]] = float(v)
        elif fx is not None and l.startswith("PropName:"):
            name = l.split(":", 1)[1].strip()
            kind, _, val = lines[i + 2].partition(":")
            val = val.strip()
            i += 2
            if name == "Ck":
                fx["ck"].append([round(float(x), 4) for x in val.split()[:5]])
            elif name == "Sk":
                fx["sk"].append([round(float(x), 4) for x in val.split()[:2]])
            elif name not in SKIP:
                if kind == "COMBO":
                    v = int(val.split(",")[0])
                elif kind == "VECTOR":
                    v = [round(float(x), 3) for x in val.split()[:3]]
                elif kind == "FLOAT":
                    v = round(float(val), 4)
                elif kind == "INTEGER":
                    v = int(float(val))
                elif kind == "PATH":
                    v = path_value(val)
                else:
                    v = val
                if v not in (None, ""):
                    fx["props"][name] = v
        i += 1
    return groups


def main():
    groups = parse()
    out = {}
    for name, fxs in groups.items():
        keep = []
        for f in fxs:
            if f["type"] not in TYPES:
                continue
            p = f["props"]
            if f["type"] in ("ParticleSystem", "Sprite") and not (p.get("Sprite") or p.get("Texture")):
                continue
            if f["type"] == "PlaySound" and not p.get("Sound"):
                continue
            e = {"type": f["type"], "start": f.get("start", 0), "end": f.get("end", 1), "p": p}
            if f.get("repeat"):
                e["repeat"] = 1
            if len(f["ck"]) > 0:
                e["ck"] = f["ck"]
            if len(f["sk"]) > 0:
                e["sk"] = f["sk"]
            keep.append(e)
        if keep:
            out[name.lower()] = keep
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print(f"{len(out)} of {len(groups)} groups kept, {sum(len(v) for v in out.values())} effects, "
          f"{os.path.getsize(OUT) // 1024} KB")


if __name__ == "__main__":
    main()
