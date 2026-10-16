"""Convert WolfTeam LTB models to binary glTF (.glb).

LithTech is left-handed (X right, Y up, Z forward); glTF is right-handed, so Z is
negated everywhere and triangle winding is reversed. Every mesh is exported as a
skinned mesh (rigid pieces get weight 1.0 on their bone), so animations from the
model itself or from animation-library models (--anims) drive all pieces.

Usage:
  python ltb2gltf.py model.ltb out.glb [--anims lib.ltb ...] [--skins a.png b.png ...]
                     [--scale 0.01] [--exclude REGEX]
Skins are listed in LTB texture-index order and embedded in the .glb.
Without --skins, a same-named texture next to the model is guessed for index 0.
"""
import argparse
import re
import json
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ltb  # noqa: E402

FLIP = np.diag([1.0, 1.0, -1.0, 1.0])


def conv_matrix(m16):
    """LithTech row-major (column-vector) matrix -> right-handed numpy 4x4."""
    return FLIP @ np.array(m16, dtype=np.float64).reshape(4, 4) @ FLIP


def conv_quat(q):
    x, y, z, w = q
    return (-x, -y, z, w)


def mat_to_trs(m):
    t = m[:3, 3].copy()
    rs = m[:3, :3]
    s = np.linalg.norm(rs, axis=0)
    s[s == 0] = 1.0
    r = rs / s
    if np.linalg.det(r) < 0:  # mirrored basis: fold the reflection into scale
        s[0] = -s[0]
        r[:, 0] = -r[:, 0]
    return t, quat_from_rot(r), s


def quat_from_rot(r):
    tr = r[0, 0] + r[1, 1] + r[2, 2]
    if tr > 0:
        k = np.sqrt(tr + 1.0) * 2
        q = ((r[2, 1] - r[1, 2]) / k, (r[0, 2] - r[2, 0]) / k, (r[1, 0] - r[0, 1]) / k, 0.25 * k)
    elif r[0, 0] > r[1, 1] and r[0, 0] > r[2, 2]:
        k = np.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2]) * 2
        q = (0.25 * k, (r[0, 1] + r[1, 0]) / k, (r[0, 2] + r[2, 0]) / k, (r[2, 1] - r[1, 2]) / k)
    elif r[1, 1] > r[2, 2]:
        k = np.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2]) * 2
        q = ((r[0, 1] + r[1, 0]) / k, 0.25 * k, (r[1, 2] + r[2, 1]) / k, (r[0, 2] - r[2, 0]) / k)
    else:
        k = np.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1]) * 2
        q = ((r[0, 2] + r[2, 0]) / k, (r[1, 2] + r[2, 1]) / k, 0.25 * k, (r[1, 0] - r[0, 1]) / k)
    q = np.array(q)
    return q / np.linalg.norm(q)


class GLB:
    def __init__(self):
        self.bin = bytearray()
        self.j = {'asset': {'version': '2.0', 'generator': 'wolfteam-webport ltb2gltf'},
                  'buffers': [], 'bufferViews': [], 'accessors': [], 'nodes': [], 'meshes': [],
                  'materials': [], 'textures': [], 'images': [], 'samplers': [], 'skins': [],
                  'animations': [], 'scenes': [{'nodes': []}], 'scene': 0}

    def view(self, data, target=None):
        while len(self.bin) % 4:
            self.bin.append(0)
        bv = {'buffer': 0, 'byteOffset': len(self.bin), 'byteLength': len(data)}
        if target:
            bv['target'] = target
        self.bin += data
        self.j['bufferViews'].append(bv)
        return len(self.j['bufferViews']) - 1

    def accessor(self, arr, gltype, comp, target=None, minmax=False):
        arr = np.ascontiguousarray(arr)
        acc = {'bufferView': self.view(arr.tobytes(), target), 'componentType': comp,
               'count': int(arr.shape[0]), 'type': gltype}
        if minmax:
            acc['min'] = arr.min(axis=0).tolist() if arr.ndim > 1 else [float(arr.min())]
            acc['max'] = arr.max(axis=0).tolist() if arr.ndim > 1 else [float(arr.max())]
        self.j['accessors'].append(acc)
        return len(self.j['accessors']) - 1

    def save(self, path):
        for k in [k for k, v in self.j.items() if v == []]:
            del self.j[k]
        while len(self.bin) % 4:
            self.bin.append(0)
        self.j['buffers'] = [{'byteLength': len(self.bin)}]
        js = json.dumps(self.j, separators=(',', ':')).encode()
        js += b' ' * (-len(js) % 4)
        with open(path, 'wb') as f:
            f.write(struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(self.bin)))
            f.write(struct.pack('<II', len(js), 0x4E4F534A) + js)
            f.write(struct.pack('<II', len(self.bin), 0x004E4942) + self.bin)


FLOAT, USHORT, UBYTE, UINT = 5126, 5123, 5121, 5125
ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER = 34962, 34963


def build(model, out, anim_models=(), skins=(), scale=0.01, name=None, exclude=None):
    g = GLB()
    nodes = model.nodes
    index_of = {id(n): i for i, n in enumerate(nodes)}
    # LithTech does not apply the root node's transform to its children (their
    # animation keys are already model-space), so the root is kept at identity.
    glob = []
    for n in nodes:
        m = conv_matrix(n.matrix) if n.parent else np.eye(4)
        m[:3, 3] *= scale
        glob.append(m)

    # skeleton nodes with rest pose
    for i, n in enumerate(nodes):
        if n.parent is None:
            # The root's bind transform (WolfTeam: a 180° turn about Y) is not part of the
            # children's model space or animation keys, but it is applied when the model
            # is drawn, so keep it as a static rotation on the glTF root joint.
            t, r, s = mat_to_trs(conv_matrix(n.matrix))
            t = t * scale
        else:
            parent = glob[index_of[id(n.parent)]]
            t, r, s = mat_to_trs(np.linalg.inv(parent) @ glob[i])
        node = {'name': n.name, 'translation': t.tolist(), 'rotation': r.tolist()}
        if not np.allclose(s, 1.0, atol=1e-4):
            node['scale'] = s.tolist()
        if n.children:
            node['children'] = [index_of[id(c)] for c in n.children]
        g.j['nodes'].append(node)
    g.j['scenes'][0]['nodes'].append(0)

    ibm = np.stack([np.linalg.inv(m).T for m in glob]).astype(np.float32)  # column-major
    g.j['skins'].append({'joints': list(range(len(nodes))), 'skeleton': 0,
                         'inverseBindMatrices': g.accessor(ibm.reshape(-1, 16), 'MAT4', FLOAT)})

    # materials
    mat_for_tex = {}

    def material(tex_index):
        if tex_index in mat_for_tex:
            return mat_for_tex[tex_index]
        mat = {'name': f'skin{tex_index}', 'pbrMetallicRoughness': {'metallicFactor': 0.0, 'roughnessFactor': 0.8}}
        if tex_index < len(skins) and skins[tex_index] and os.path.exists(skins[tex_index]):
            with open(skins[tex_index], 'rb') as f:
                img_view = g.view(f.read())
            g.j['images'].append({'bufferView': img_view, 'mimeType': 'image/png',
                                  'name': os.path.basename(skins[tex_index])})
            if not g.j['samplers']:
                g.j['samplers'].append({'magFilter': 9729, 'minFilter': 9987})
            g.j['textures'].append({'source': len(g.j['images']) - 1, 'sampler': 0})
            mat['pbrMetallicRoughness']['baseColorTexture'] = {'index': len(g.j['textures']) - 1}
        g.j['materials'].append(mat)
        mat_for_tex[tex_index] = len(g.j['materials']) - 1
        return mat_for_tex[tex_index]

    # meshes: one glTF mesh node per piece (LOD 0)
    for piece in model.pieces:
        lod = piece['lods'][0] if piece['lods'] else None
        if lod is None or lod.type == ltb.MESH_NULL or not lod.positions:
            continue
        if exclude and re.search(exclude, piece['name'], re.I):
            continue
        pos = np.array(lod.positions, dtype=np.float32) * np.float32(scale)
        pos[:, 2] *= -1
        attrs = {'POSITION': g.accessor(pos, 'VEC3', FLOAT, ARRAY_BUFFER, minmax=True)}
        if len(lod.normals) == len(pos):
            nrm = np.array(lod.normals, dtype=np.float32)
            nrm[:, 2] *= -1
            ln = np.linalg.norm(nrm, axis=1, keepdims=True)
            nrm = np.divide(nrm, ln, out=np.zeros_like(nrm), where=ln > 0)
            attrs['NORMAL'] = g.accessor(nrm, 'VEC3', FLOAT, ARRAY_BUFFER)
        if len(lod.uvs) == len(pos):
            attrs['TEXCOORD_0'] = g.accessor(np.array(lod.uvs, dtype=np.float32), 'VEC2', FLOAT, ARRAY_BUFFER)
        joints = np.zeros((len(pos), 4), dtype=np.uint8)
        weights = np.zeros((len(pos), 4), dtype=np.float32)
        for v, ws in enumerate(lod.weights):
            ws = sorted(ws or [(0, 1.0)], key=lambda x: -x[1])[:4]
            total = sum(w for _, w in ws) or 1.0
            for k, (b, w) in enumerate(ws):
                joints[v, k] = b if b < len(nodes) else 0
                weights[v, k] = w / total
        attrs['JOINTS_0'] = g.accessor(joints, 'VEC4', UBYTE, ARRAY_BUFFER)
        attrs['WEIGHTS_0'] = g.accessor(weights, 'VEC4', FLOAT, ARRAY_BUFFER)
        idx = np.array(lod.indices, dtype=np.uint16).reshape(-1, 3)[:, ::-1].reshape(-1)
        prim = {'attributes': attrs, 'indices': g.accessor(idx, 'SCALAR', USHORT, ELEMENT_ARRAY_BUFFER),
                'material': material(lod.textures[0] if lod.textures else 0)}
        g.j['meshes'].append({'name': piece['name'], 'primitives': [prim]})
        g.j['nodes'].append({'name': piece['name'], 'mesh': len(g.j['meshes']) - 1, 'skin': 0})
        g.j['scenes'][0]['nodes'].append(len(g.j['nodes']) - 1)

    # animations (model's own + libraries), matched to our skeleton by node name
    by_name = {n.name.lower(): i for i, n in enumerate(nodes)}
    seen = set()
    for src in (model,) + tuple(anim_models):
        for a in src.anims:
            if a['name'] in seen or not a['keys']:
                continue
            seen.add(a['name'])
            times = np.array([k[0] / 1000.0 for k in a['keys']], dtype=np.float32)
            if len(times) == 1:
                times = np.array([0.0], dtype=np.float32)
            t_acc = g.accessor(times, 'SCALAR', FLOAT, minmax=True)
            samplers, channels = [], []
            for src_node, (pos, rot) in zip(src.nodes, a['tracks']):
                dst = by_name.get(src_node.name.lower())
                if dst is None or src_node.parent is None:
                    continue
                if pos:
                    p = np.array(pos[:len(times)], dtype=np.float32) * np.float32(scale)
                    p[:, 2] *= -1
                    samplers.append({'input': t_acc, 'output': g.accessor(p, 'VEC3', FLOAT), 'interpolation': 'LINEAR'})
                    channels.append({'sampler': len(samplers) - 1, 'target': {'node': dst, 'path': 'translation'}})
                if rot:
                    q = np.array([conv_quat(x) for x in rot[:len(times)]], dtype=np.float32)
                    q /= np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-8)
                    samplers.append({'input': t_acc, 'output': g.accessor(q, 'VEC4', FLOAT), 'interpolation': 'LINEAR'})
                    channels.append({'sampler': len(samplers) - 1, 'target': {'node': dst, 'path': 'rotation'}})
            if channels:
                g.j['animations'].append({'name': a['name'], 'samplers': samplers, 'channels': channels})

    # sockets as empty child nodes (weapon / effect attachment points)
    for s in model.sockets:
        if s['node'] >= len(nodes):
            continue
        p = np.array(s['pos']) * scale
        node = {'name': 'socket_' + s['name'], 'translation': [p[0], p[1], -p[2]],
                'rotation': list(conv_quat(s['rot'])), 'extras': {'socket': True}}
        g.j['nodes'].append(node)
        g.j['nodes'][s['node']].setdefault('children', []).append(len(g.j['nodes']) - 1)

    g.j['scenes'][0]['name'] = name or 'model'
    g.save(out)
    return g


def guess_skins(ltb_path):
    """models/foo.ltb -> skins*/foo.png in the converted texture tree (index 0 only)."""
    here = os.path.dirname(os.path.abspath(ltb_path))
    base = os.path.splitext(os.path.basename(ltb_path))[0]
    tex_root = here.replace(os.sep + 'extracted' + os.sep, os.sep + os.path.join('assets', 'textures') + os.sep)
    parent = os.path.dirname(tex_root)
    if os.path.isdir(parent):
        for d in sorted(os.listdir(parent)):
            cand = os.path.join(parent, d, base + '.png')
            if d.lower().startswith('skin') and os.path.exists(cand):
                return [cand]
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ltb')
    ap.add_argument('out')
    ap.add_argument('--anims', nargs='*', default=[])
    ap.add_argument('--skins', nargs='*')
    ap.add_argument('--scale', type=float, default=0.01)
    ap.add_argument('--exclude', help='regex of piece names to skip')
    a = ap.parse_args()
    with open(a.ltb, 'rb') as f:
        model = ltb.parse(f.read())
    libs = []
    for p in a.anims:
        with open(p, 'rb') as f:
            libs.append(ltb.parse(f.read()))
    skins = a.skins if a.skins is not None else guess_skins(a.ltb)
    g = build(model, a.out, libs, skins, a.scale, os.path.splitext(os.path.basename(a.ltb))[0], a.exclude)
    print(f'{a.out}: {len(g.j.get("meshes", []))} meshes, {len(model.nodes)} bones, '
          f'{len(g.j.get("animations", []))} animations, {len(g.j.get("images", []))} textures, '
          f'{len(g.bin) / 1e6:.1f} MB')


if __name__ == '__main__':
    main()
