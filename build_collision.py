"""Shot collision of every map for the hub (collision.py): assets/maps/<map>/<map>.glb -> assets/maps/<map>/shots.wtc.

The triangles are the ones the client's bullets stop at (client/js/world.js shotCollider): every mesh except the
sky, the invisible collision hulls (node extras collision), ladder brushes and WorldModels with Solid false or
Rayhit false (objects.json). Each triangle keeps its surface (material = dtx path -> client/ui/surfaces.json
textures), and the surfaces' shoot-through rules come from the 2016 attributes/surface.txt (CanShootThrough,
MaxShootThroughThickness, BulletDamageDampen; object.lto FUN_6cf2bd60).

File (gzip): b"WTC1", u32 header length, header JSON {cell, origin, dims, ntris, ncells, surfaces: [{id, name,
through, thick, dmg}]}, then f32[ntris * 9] (v0, v1 - v0, v2 - v0: what a Moller-Trumbore test needs),
u8[ntris] surface index, cells u32[ncells * 3] (key = ix + nx * (iy + ny * iz), start, count) sorted by key,
u32 triangle indices. Units: three.js metres (the glb's).

  python tools/build_collision.py            (all maps)
  python tools/build_collision.py 03gate     (some)
"""
import gzip
import json
import math
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_surfaces  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MAPS = os.path.join(ROOT, "assets", "maps")
CELL = 2.0   # grid cell (m): a ~40 m shot walks ~60 cells of a few triangles each


def sanitize(name):
    """three.js PropertyBinding.sanitizeNodeName (GLTFLoader names nodes with it)."""
    return re.sub(r"[\[\]\.:/]", "", re.sub(r"\s", "_", name or ""))


def mat_mul(a, b):
    return [sum(a[r + 4 * k] * b[k + 4 * c] for k in range(4)) for c in range(4) for r in range(4)]


def node_matrix(n):
    """column-major 4x4 of a glTF node"""
    if "matrix" in n:
        return list(n["matrix"])
    tx, ty, tz = n.get("translation", (0, 0, 0))
    qx, qy, qz, qw = n.get("rotation", (0, 0, 0, 1))
    sx, sy, sz = n.get("scale", (1, 1, 1))
    r = [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy + qz * qw), 2 * (qx * qz - qy * qw),
         2 * (qx * qy - qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz + qx * qw),
         2 * (qx * qz + qy * qw), 2 * (qy * qz - qx * qw), 1 - 2 * (qx * qx + qy * qy)]
    return [r[0] * sx, r[1] * sx, r[2] * sx, 0, r[3] * sy, r[4] * sy, r[5] * sy, 0,
            r[6] * sz, r[7] * sz, r[8] * sz, 0, tx, ty, tz, 1]


def read_glb(path):
    b = open(path, "rb").read()
    n = struct.unpack_from("<I", b, 12)[0]
    j = json.loads(b[20:20 + n])
    o = 20 + n
    ln = struct.unpack_from("<I", b, o)[0]
    return j, b[o + 8:o + 8 + ln]


def accessor(j, binb, i):
    a = j["accessors"][i]
    bv = j["bufferViews"][a["bufferView"]]
    comps = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
    fmt, size = {5126: ("f", 4), 5125: ("I", 4), 5123: ("H", 2), 5121: ("B", 1)}[a["componentType"]]
    stride = bv.get("byteStride") or size * comps
    base = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    if stride == size * comps:
        flat = struct.unpack_from(f"<{a['count'] * comps}{fmt}", binb, base)
        return [flat[k:k + comps] for k in range(0, len(flat), comps)] if comps > 1 else list(flat)
    return [struct.unpack_from(f"<{comps}{fmt}", binb, base + k * stride) for k in range(a["count"])]


def pen_rules():
    """{surface id: (name, through, thick, dmg)} from the 2016 surface.txt (None when it is not there)."""
    build_surfaces.EXT = os.path.join(ROOT, "extracted_2016")
    try:
        sec = build_surfaces.butes("surface.txt")
    except OSError:
        return None

    def num(v, d):
        try:
            return float(str(v).split()[0])
        except (TypeError, ValueError, IndexError):
            return d
    out = {}
    for v in sec.values():
        if "Id" in v:
            out[int(num(v["Id"], 0))] = (v.get("Name", ""), num(v.get("CanShootThrough"), 0) > 0,
                                         num(v.get("MaxShootThroughThickness"), 0), num(v.get("BulletDamageDampen"), 1))
    return out


def shot_triangles(name, textures):
    j, binb = read_glb(os.path.join(MAPS, name, name + ".glb"))
    try:
        objs = json.load(open(os.path.join(MAPS, name, "objects.json"), encoding="utf-8")).get("objects") or []
    except OSError:
        objs = []
    wms = {sanitize(x["props"]["Name"]): x["props"] for x in objs
           if re.search("WorldModel", x.get("type") or "") and (x.get("props") or {}).get("Name")}
    ladders = {sanitize(x["props"]["Name"]) for x in objs if x.get("type") == "Ladder" and (x.get("props") or {}).get("Name")}
    mats = [(m.get("name") or "").lower() for m in j.get("materials", [])]
    tris, surf = [], []

    def walk(ni, parent_m, chain):
        n = j["nodes"][ni]
        m = mat_mul(parent_m, node_matrix(n))
        ex = n.get("extras") or {}
        nm = sanitize(n.get("name", ""))
        chain = chain + [(nm, ex)]
        if "mesh" in n:
            mesh = j["meshes"][n["mesh"]]
            skip = any(e.get("sky") for _, e in chain) or any(e.get("collision") for _, e in chain[-2:])
            skip = skip or (ladders and any(re.sub(r"_collision$", "", c) in ladders for c, _ in chain))
            wp = next((wms[c] for c, _ in reversed(chain) if c in wms), None)
            if wp and (wp.get("Solid") is False or wp.get("Rayhit") is False):
                skip = True
            if not skip:
                for pr in mesh["primitives"]:
                    if pr.get("mode", 4) != 4:
                        continue
                    pos = accessor(j, binb, pr["attributes"]["POSITION"])
                    idx = accessor(j, binb, pr["indices"]) if "indices" in pr else range(len(pos))
                    sid = textures.get(mats[pr["material"]], 0) if "material" in pr else 0
                    w = [(m[0] * x + m[4] * y + m[8] * z + m[12], m[1] * x + m[5] * y + m[9] * z + m[13],
                          m[2] * x + m[6] * y + m[10] * z + m[14]) for x, y, z in pos]
                    for k in range(0, len(idx) - 2, 3):
                        a, b, c = w[idx[k]], w[idx[k + 1]], w[idx[k + 2]]
                        e1 = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
                        e2 = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
                        nx_ = e1[1] * e2[2] - e1[2] * e2[1]
                        ny_ = e1[2] * e2[0] - e1[0] * e2[2]
                        nz_ = e1[0] * e2[1] - e1[1] * e2[0]
                        if nx_ * nx_ + ny_ * ny_ + nz_ * nz_ < 1e-12:   # degenerate
                            continue
                        tris.append((a, b, c))
                        surf.append(sid)
        for c in n.get("children", ()):
            walk(c, m, chain)

    ident = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    for r in j["scenes"][j.get("scene", 0)]["nodes"]:
        walk(r, ident, [])
    return tris, surf


def tri_box(a, b, c, lo, hi):
    """Conservative triangle / box overlap: the box straddles the triangle's plane (the bounds overlap already)."""
    e1 = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    e2 = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
    ctr = [(lo[i] + hi[i]) / 2 for i in range(3)]
    h = [(hi[i] - lo[i]) / 2 for i in range(3)]
    d = sum(n[i] * (ctr[i] - a[i]) for i in range(3))
    r = sum(abs(n[i]) * h[i] for i in range(3))
    return abs(d) <= r


def build(name, textures, rules):
    tris, surf = shot_triangles(name, textures)
    if not tris:
        return None
    lo = [min(min(t[k][i] for k in range(3)) for t in tris) - 0.01 for i in range(3)]
    hi = [max(max(t[k][i] for k in range(3)) for t in tris) + 0.01 for i in range(3)]
    dims = [max(1, int(math.ceil((hi[i] - lo[i]) / CELL))) for i in range(3)]
    cells = {}
    for ti, (a, b, c) in enumerate(tris):
        r0 = [max(0, int((min(a[i], b[i], c[i]) - lo[i]) / CELL)) for i in range(3)]
        r1 = [min(dims[i] - 1, int((max(a[i], b[i], c[i]) - lo[i]) / CELL)) for i in range(3)]
        many = (r1[0] - r0[0] + 1) * (r1[1] - r0[1] + 1) * (r1[2] - r0[2] + 1) > 1
        for iz in range(r0[2], r1[2] + 1):
            for iy in range(r0[1], r1[1] + 1):
                for ix in range(r0[0], r1[0] + 1):
                    if many:
                        clo = (lo[0] + ix * CELL, lo[1] + iy * CELL, lo[2] + iz * CELL)
                        if not tri_box(a, b, c, clo, (clo[0] + CELL, clo[1] + CELL, clo[2] + CELL)):
                            continue
                    cells.setdefault(ix + dims[0] * (iy + dims[1] * iz), []).append(ti)
    ids = sorted(set(surf))
    sidx = {s: i for i, s in enumerate(ids)}
    rules = rules or {}
    sdesc = []
    for s in ids:
        nm, through, thick, dmg = rules.get(s, ("", False, 0.0, 1.0))
        sdesc.append({"id": s, "name": nm, "through": through, "thick": thick, "dmg": dmg})
    keys = sorted(cells)
    header = json.dumps({"cell": CELL, "origin": lo, "dims": dims, "ntris": len(tris), "ncells": len(keys),
                         "surfaces": sdesc}).encode()
    out = [b"WTC1", struct.pack("<I", len(header)), header]
    flat = []
    for a, b, c in tris:
        flat += [a[0], a[1], a[2], b[0] - a[0], b[1] - a[1], b[2] - a[2], c[0] - a[0], c[1] - a[1], c[2] - a[2]]
    out.append(struct.pack(f"<{len(flat)}f", *flat))
    out.append(bytes(sidx[s] for s in surf))
    table, lst = [], []
    for k in keys:
        table += [k, len(lst), len(cells[k])]
        lst += cells[k]
    out.append(struct.pack(f"<{len(table)}I", *table))
    out.append(struct.pack(f"<{len(lst)}I", *lst))
    data = gzip.compress(b"".join(out), 9)
    with open(os.path.join(MAPS, name, "shots.wtc"), "wb") as f:
        f.write(data)
    return len(tris), len(keys), len(lst), len(data)


def main():
    textures = json.load(open(os.path.join(ROOT, "client", "ui", "surfaces.json"), encoding="utf-8")).get("textures", {})
    textures = {k.lower(): v for k, v in textures.items()}
    rules = pen_rules()
    if rules is None:
        print("warning: extracted_2016/attributes/surface.txt missing, no shoot-through surfaces")
    names = sys.argv[1:] or sorted(d for d in os.listdir(MAPS) if os.path.exists(os.path.join(MAPS, d, d + ".glb")))
    for name in names:
        r = build(name, textures, rules)
        print(name, "empty" if r is None else "tris %d cells %d refs %d bytes %d" % r, flush=True)


if __name__ == "__main__":
    main()
