"""Convert a WolfTeam world (.dat v85) to glTF + lightmap atlases + object list.

Output (in <out_dir>/<name>/):
  <name>.glb          render geometry; textures referenced as external PNGs
  lightmap_N.png      packed lightmap atlas pages
  objects.json        world objects (spawn points, ladders, lights, ...)

Geometry rules (see world.py for the format):
  shader 2 'LightAnim_BASE' sections are lightmap-only twins of textured triangles;
  they are not exported, their lightmap UVs are copied onto the textured twin as
  TEXCOORD_1. Textured triangles without a twin are vertex lit (COLOR_0).
  'colwall', 'blocker' and untextured sections are invisible collision -> node 'collision'.
  DemoSkyWorldModel* world models are the skybox -> node 'sky'.
Coordinates: Z negated (left- to right-handed), winding reversed, scaled by --scale.

Usage: python world2gltf.py <world.dat> <out_dir> [--textures assets/textures] [--scale 0.01]
"""
import argparse
import json
import os
import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import world  # noqa: E402
from ltb2gltf import GLB, FLOAT, USHORT, UINT, UBYTE, ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER  # noqa: E402

PAGE = 2048
PAD = 1
SHADER_LIGHTMAP = 2


class Atlas:
    """Shelf packer for lightmap rectangles."""

    def __init__(self):
        self.pages = []
        self.x = self.y = self.shelf_h = 0

    def add(self, rgb, w, h):
        bw, bh = w + 2 * PAD, h + 2 * PAD
        if not self.pages or self.x + bw > PAGE:
            self.x, self.y, self.shelf_h = 0, self.y + self.shelf_h, 0
        if not self.pages or self.y + bh > PAGE:
            self.pages.append(Image.new('RGB', (PAGE, PAGE)))
            self.x = self.y = self.shelf_h = 0
        img = Image.frombytes('RGB', (w, h), rgb)
        padded = img.resize((bw, bh), Image.NEAREST) if (w, h) == (1, 1) else _edge_pad(img)
        page = len(self.pages) - 1
        self.pages[page].paste(padded, (self.x, self.y))
        rect = (page, self.x + PAD, self.y + PAD, w, h)
        self.x += bw
        self.shelf_h = max(self.shelf_h, bh)
        return rect


def _edge_pad(img):
    a = np.asarray(img)
    return Image.fromarray(np.pad(a, ((PAD, PAD), (PAD, PAD), (0, 0)), mode='edge'))


def tri_key(p):
    return tuple(np.round(np.sort(p, axis=0).ravel(), 2))


def block_triangles(b):
    """Yield (section, tri_indices[3], verts) per triangle, plus vertex arrays."""
    T = np.frombuffer(b.tris, dtype='<u4').reshape(-1, 4)
    V = np.frombuffer(b.verts, dtype=np.uint8).reshape(-1, 68)
    f = V[:, :56].copy().view('<f4').reshape(-1, 14)  # pos3 uv2 uv2 | rgba as float garbage | normal3
    pos = f[:, 0:3]
    uv0 = f[:, 3:5]
    rgba = V[:, 28:32]
    normal = V[:, 32:44].copy().view('<f4').reshape(-1, 3)
    return T, pos, uv0, rgba, normal


class Group:
    def __init__(self):
        self.pos, self.nrm, self.uv0, self.uv1, self.col = [], [], [], [], []


def ladder_boxes(data, name, scale):
    """A Ladder volume's brushes in glTF coordinates, [[[min xyz], [max xyz]], ...] (Z negated); the client
    climbs inside them (world.js / player.js ladderStep)."""
    return [[[mn[0] * scale, mn[1] * scale, -mx[2] * scale], [mx[0] * scale, mx[1] * scale, -mn[2] * scale]]
            for mn, mx in (world.model_boxes(data, name) if name else [])]


def convert(path, out_dir, tex_root, scale, name=None):
    with open(path, 'rb') as f:
        data = f.read()
    w = world.load(data)
    name = name or os.path.splitext(os.path.basename(path))[0]
    dst = os.path.join(out_dir, name)
    os.makedirs(dst, exist_ok=True)
    tex_index = {}
    idx_path = os.path.join(tex_root, 'textures.json')
    if os.path.exists(idx_path):
        with open(idx_path, encoding='utf-8') as f:
            tex_index = {k.lower(): v for k, v in json.load(f).items()}

    atlas = Atlas()
    lm_rect_cache = {}

    def collect(blocks, groups):
        for b in blocks:
            T, pos, uv0, rgba, nrm = block_triangles(b)
            # lightmap twins: key -> (rect, {vertex position -> lightmap uv})
            twins = {}
            t = 0
            for s in b.sections:
                if s.shader == SHADER_LIGHTMAP and s.lm_w:
                    key = id(s)
                    if key not in lm_rect_cache:
                        lm_rect_cache[key] = atlas.add(world.decompress_lightmap(s.lm_data, s.lm_w, s.lm_h), s.lm_w, s.lm_h)
                    page, x, y, lw, lh = lm_rect_cache[key]
                    for ti in range(t, t + s.tri_count):
                        vi = T[ti, :3]
                        lm = {}
                        for v in vi:
                            u, vv = uv0[v]
                            lm[tuple(np.round(pos[v], 2))] = (page, (x + u * lw) / PAGE, (y + vv * lh) / PAGE)
                        twins[tri_key(pos[vi])] = lm
                t += s.tri_count
            t = 0
            for s in b.sections:
                n = s.tri_count
                if s.shader == SHADER_LIGHTMAP:
                    t += n
                    continue
                tex = s.texture.replace('\\', '/').lower()
                kind = 'collision' if (not tex or 'colwall' in tex or tex.endswith('/blocker.dtx')) else 'render'
                for ti in range(t, t + n):
                    vi = T[ti, :3]
                    lm = twins.get(tri_key(pos[vi])) if kind == 'render' else None
                    page = None
                    if lm:
                        uvs = [lm.get(tuple(np.round(pos[v], 2))) for v in vi]
                        if all(uvs):
                            page = uvs[0][0]
                        else:
                            lm = None
                    g = groups.setdefault((kind, tex, s.shader, page), Group())
                    for k, v in enumerate(vi[::-1]):  # reversed winding
                        g.pos.append(pos[v])
                        g.nrm.append(nrm[v])
                        g.uv0.append(uv0[v])
                        g.col.append(rgba[v])
                        if page is not None:
                            u = uvs[2 - k]
                            g.uv1.append((u[1], u[2]))
                t += n

    main_groups = {}
    collect(w.blocks, main_groups)
    wm_groups = []
    for wm_name, blocks in w.world_models:
        gs = {}
        collect(blocks, gs)
        wm_groups.append((wm_name, gs))

    for i, page in enumerate(atlas.pages):
        page.save(os.path.join(dst, f'lightmap_{i}.png'))

    g = GLB()
    g.j['samplers'].append({'magFilter': 9729, 'minFilter': 9987, 'wrapS': 10497, 'wrapT': 10497})
    images = {}
    materials = {}

    def image(uri):
        if uri not in images:
            g.j['images'].append({'uri': uri})
            g.j['textures'].append({'source': len(g.j['images']) - 1, 'sampler': 0})
            images[uri] = len(g.j['textures']) - 1
        return images[uri]

    def material(tex, shader, page):
        key = (tex, shader, page)
        if key in materials:
            return materials[key]
        m = {'name': tex, 'pbrMetallicRoughness': {'metallicFactor': 0.0, 'roughnessFactor': 1.0},
             'extras': {'shader': shader}}
        png = os.path.splitext(tex)[0] + '.png'
        meta = tex_index.get(tex)
        if os.path.exists(os.path.join(tex_root, png)):
            rel = os.path.relpath(os.path.join(tex_root, png), dst).replace('\\', '/')
            m['pbrMetallicRoughness']['baseColorTexture'] = {'index': image(rel)}
            if meta and 'alpharef' in meta.get('command', '').lower():
                m['alphaMode'] = 'MASK'
                m['alphaCutoff'] = 0.5
        else:
            m['extras']['missing_texture'] = True
        if page is not None:
            m['extras']['lightmap'] = f'lightmap_{page}.png'
        g.j['materials'].append(m)
        materials[key] = len(g.j['materials']) - 1
        return materials[key]

    def mesh(groups, mesh_name, kinds):
        prims = []
        for (kind, tex, shader, page), grp in sorted(groups.items(), key=lambda x: str(x[0])):
            if kind not in kinds or not grp.pos:
                continue
            P = np.array(grp.pos, dtype=np.float32) * np.float32(scale)
            P[:, 2] *= -1
            cols = [P, np.array(grp.uv0, dtype=np.float32)]
            N = np.array(grp.nrm, dtype=np.float32)
            N[:, 2] *= -1
            cols.append(N)
            if grp.uv1:
                cols.append(np.array(grp.uv1, dtype=np.float32))
            C = np.array(grp.col, dtype=np.uint8)
            # dedupe identical vertices
            rows = np.concatenate([c.view(np.uint8).reshape(len(P), -1) for c in cols] + [C], axis=1)
            uniq, inv = np.unique(rows, axis=0, return_inverse=True)
            inv = inv.reshape(-1)
            sel = np.zeros(len(uniq), dtype=np.int64)
            sel[inv] = np.arange(len(inv))
            attrs = {'POSITION': g.accessor(P[sel], 'VEC3', FLOAT, ARRAY_BUFFER, minmax=True)}
            if kind == 'render':
                attrs['TEXCOORD_0'] = g.accessor(cols[1][sel], 'VEC2', FLOAT, ARRAY_BUFFER)
                n = N[sel]
                ln = np.linalg.norm(n, axis=1, keepdims=True)
                attrs['NORMAL'] = g.accessor(np.divide(n, ln, out=np.tile([0, 1, 0], (len(n), 1)).astype(np.float32), where=ln > 1e-6), 'VEC3', FLOAT, ARRAY_BUFFER)
                if grp.uv1:
                    attrs['TEXCOORD_1'] = g.accessor(cols[3][sel], 'VEC2', FLOAT, ARRAY_BUFFER)
                else:
                    attrs['COLOR_0'] = g.accessor(C[sel], 'VEC4', UBYTE, ARRAY_BUFFER)
                    g.j['accessors'][-1]['normalized'] = True
            big = len(uniq) > 65535
            idx = inv.astype(np.uint32 if big else np.uint16)
            prim = {'attributes': attrs,
                    'indices': g.accessor(idx, 'SCALAR', UINT if big else USHORT, ELEMENT_ARRAY_BUFFER)}
            if kind == 'render':
                prim['material'] = material(tex, shader, page)
            prims.append(prim)
        if not prims:
            return None
        g.j['meshes'].append({'name': mesh_name, 'primitives': prims})
        return len(g.j['meshes']) - 1

    root_children = []

    def node(nname, mesh_index, extras=None):
        if mesh_index is None:
            return
        n = {'name': nname, 'mesh': mesh_index}
        if extras:
            n['extras'] = extras
        g.j['nodes'].append(n)
        root_children.append(len(g.j['nodes']) - 1)

    node('world', mesh(main_groups, 'world', {'render'}))
    node('collision', mesh(main_groups, 'collision', {'collision'}), {'collision': True})
    for wm_name, gs in wm_groups:
        is_sky = wm_name.lower().startswith('demosky')
        node(wm_name, mesh(gs, wm_name, {'render'}), {'sky': True} if is_sky else {'world_model': True})
        node(wm_name + '_collision', mesh(gs, wm_name + '_collision', {'collision'}), {'collision': True})
    g.j['nodes'].append({'name': name, 'children': root_children})
    g.j['scenes'][0]['nodes'] = [len(g.j['nodes']) - 1]
    for k in ('skins', 'animations'):
        g.j.pop(k, None)
    g.save(os.path.join(dst, name + '.glb'))

    # objects
    def conv(v):
        if isinstance(v, tuple) and len(v) == 3:
            return [v[0], v[1], v[2]]
        if isinstance(v, bytes):
            return v.hex()
        return v

    objs = []
    for o in w.objects:
        props = {k: conv(v) for k, v in o.props.items()}
        if isinstance(props.get('Pos'), list):
            x, y, z = props['Pos']
            props['position'] = [x * scale, y * scale, -z * scale]
        if o.type == 'Ladder':
            props['boxes'] = ladder_boxes(data, props.get('Name', ''), scale)
        objs.append({'type': o.type, 'props': props})
    with open(os.path.join(dst, 'objects.json'), 'w', encoding='utf-8') as f:
        json.dump({'name': name, 'scale': scale, 'objects': objs}, f, ensure_ascii=False, indent=1)

    ntri = sum(len(gr.pos) // 3 for gr in main_groups.values())
    print(f'{name}: {ntri} tris, {len(g.j.get("materials", []))} materials, {len(atlas.pages)} lightmap pages, '
          f'{len(w.world_models)} world models, {len(objs)} objects, glb {len(g.bin) / 1e6:.1f} MB')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('world')
    ap.add_argument('out_dir')
    ap.add_argument('--textures', default=os.path.join(os.path.dirname(__file__), '..', 'assets', 'textures'))
    ap.add_argument('--scale', type=float, default=0.01)
    a = ap.parse_args()
    convert(a.world, a.out_dir, os.path.abspath(a.textures), a.scale)


if __name__ == '__main__':
    main()
