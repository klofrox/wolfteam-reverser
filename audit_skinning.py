"""Pose every PV weapon .glb (assets/models/pv) through its clips like three.js does and find stretched / exploded triangles.

glTF skinning in numpy: node TRS hierarchy, LINEAR sampling (slerp for rotations), joint matrix =
global * inverseBind. Per clip a few frames; a triangle edge longer than 4x its bind length and
over 5% of the model size is "stretched". (alone: python tools/audit_skinning.py [name.glb ...], no args = all).
"""
import json
import os
import struct
import sys

import numpy as np

CT = {5126: np.float32, 5121: np.uint8, 5123: np.uint16, 5125: np.uint32}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def load(path):
    b = open(path, "rb").read()
    n = struct.unpack_from("<I", b, 12)[0]
    j = json.loads(b[20:20 + n])
    bin_ = b[20 + n + 8:]

    def acc(i):
        a = j["accessors"][i]
        v = j["bufferViews"][a["bufferView"]]
        dt = CT[a["componentType"]]
        nc = NC[a["type"]]
        off = v.get("byteOffset", 0) + a.get("byteOffset", 0)
        arr = np.frombuffer(bin_, dtype=dt, count=a["count"] * nc, offset=off)
        return arr.reshape(a["count"], nc) if nc > 1 else arr
    return j, acc


def quat_mat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def slerp(a, b, t):
    d = np.dot(a, b)
    if d < 0:
        b, d = -b, -d
    if d > 0.9995:
        r = a + t * (b - a)
        return r / np.linalg.norm(r)
    th = np.arccos(d)
    return (np.sin((1 - t) * th) * a + np.sin(t * th) * b) / np.sin(th)


def sample(times, vals, t, rot):
    if t <= times[0]:
        return vals[0]
    if t >= times[-1]:
        return vals[-1]
    i = int(np.searchsorted(times, t)) - 1
    f = (t - times[i]) / max(times[i + 1] - times[i], 1e-9)
    return slerp(vals[i], vals[i + 1], f) if rot else vals[i] + f * (vals[i + 1] - vals[i])


def check(path, frames=12):
    j, acc = load(path)
    nodes = j["nodes"]
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i
    skin = j["skins"][0]
    joints = skin["joints"]
    ibm = acc(skin["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1)
    meshes = []
    for i, n in enumerate(nodes):
        if "mesh" not in n:
            continue
        p = j["meshes"][n["mesh"]]["primitives"][0]
        a = p["attributes"]
        pos = acc(a["POSITION"]).astype(np.float64)
        jt = acc(a["JOINTS_0"]).astype(np.int64)
        wt = acc(a["WEIGHTS_0"]).astype(np.float64)
        tri = acc(p["indices"]).astype(np.int64).reshape(-1, 3)
        edges = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]])
        meshes.append((n["name"], pos, jt, wt, edges))

    def globals_for(over):
        g = [None] * len(nodes)

        def get(i):
            if g[i] is not None:
                return g[i]
            n = nodes[i]
            t = over.get((i, "translation"), n.get("translation", [0, 0, 0]))
            r = over.get((i, "rotation"), n.get("rotation", [0, 0, 0, 1]))
            s = n.get("scale", [1, 1, 1])
            m = np.eye(4)
            m[:3, :3] = quat_mat(np.asarray(r, dtype=np.float64)) * np.asarray(s)
            m[:3, 3] = t
            g[i] = get(parent[i]) @ m if i in parent else m
            return g[i]
        for i in range(len(nodes)):
            get(i)
        return g

    def skinned(g):
        jm = np.stack([g[jn] for jn in joints]) @ ibm
        out = []
        for name, pos, jt, wt, edges in meshes:
            hp = np.concatenate([pos, np.ones((len(pos), 1))], 1)
            v = np.zeros((len(pos), 3))
            for k in range(4):
                v += wt[:, k:k + 1] * np.einsum("nij,nj->ni", jm[jt[:, k]], hp)[:, :3]
            out.append(v)
        return out

    # true bind = the stored POSITIONs (inverseBindMatrices undo the joints' bind globals)
    bind_len = [np.linalg.norm(p[e[:, 0]] - p[e[:, 1]], axis=1) for _, p, _, _, e in meshes]
    allp = np.concatenate([m[1] for m in meshes])
    min_len = 0.05 * float(np.linalg.norm(allp.max(0) - allp.min(0)))   # 5% of the model's size
    res = {}
    for an in j.get("animations", []):
        ch = []
        tmax = 0
        for c in an["channels"]:
            s = an["samplers"][c["sampler"]]
            tm = acc(s["input"]).astype(np.float64)
            vv = acc(s["output"]).astype(np.float64)
            tmax = max(tmax, tm[-1])
            ch.append((c["target"]["node"], c["target"]["path"], tm, vv))
        worst = None
        for f in range(frames + 1):
            t = tmax * f / frames
            over = {(nd, pth): sample(tm, vv, t, pth == "rotation") for nd, pth, tm, vv in ch}
            for (name, _, _, _, e), v, bl in zip(meshes, skinned(globals_for(over)), bind_len):
                ln = np.linalg.norm(v[e[:, 0]] - v[e[:, 1]], axis=1)
                ratio = ln / np.maximum(bl, 1e-4)
                bad = (ratio > 4) & (ln > min_len)
                if bad.any():
                    k = int(np.argmax(np.where(bad, ratio, 0)))
                    if worst is None or ratio[k] > worst[2]:
                        worst = (name, round(t * 1000), float(ratio[k]), float(ln[k]), int(bad.sum()))
        if worst:
            res[an["name"]] = worst
    return res


if __name__ == "__main__":
    pv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "models", "pv")
    for p in sys.argv[1:] or sorted(f for f in os.listdir(pv) if f.endswith(".glb")):
        print(p, check(p if os.path.exists(p) else os.path.join(os.path.dirname(__file__), "..", "assets", "models", "pv", p)))
