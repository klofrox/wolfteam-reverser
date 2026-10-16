"""LithTech Jupiter LTB (PC, D3D, model versions 23-25) parser - WolfTeam variant.

Written from the binary layout of WolfTeam's .ltb files, cross-checked against
their .lta (text) twins. The layout matches NOLF2-era PC LTB files.

Usage:
  python ltb.py <file.ltb>            dump a summary
  python ltb.py --scan <dir>          parse every .ltb under dir, report failures
"""
import os
import struct
import sys

MESH_RIGID, MESH_SKEL, MESH_VA, MESH_NULL = 4, 5, 6, 7

VTX_POS, VTX_NORMAL, VTX_COLOR = 0x1, 0x2, 0x4
VTX_UV = (0x10, 0x20, 0x40, 0x80)
VTX_BASIS = 0x100

CMP_NONE, CMP_RELEVANT, CMP_RELEVANT16, CMP_RELEVANT_ROT16 = 0, 1, 2, 3
INVALID_BONE = 255


class Reader:
    def __init__(self, data):
        self.d = data
        self.p = 0

    def u8(self):
        v = self.d[self.p]
        self.p += 1
        return v

    def s(self, fmt):
        v = struct.unpack_from('<' + fmt, self.d, self.p)
        self.p += struct.calcsize('<' + fmt)
        return v

    def u16(self):
        return self.s('H')[0]

    def u32(self):
        return self.s('I')[0]

    def count(self, what='count'):
        n = self.u32()
        if n > len(self.d) - self.p:
            raise ValueError(f'implausible {what} {n} at {self.p - 4:#x}')
        return n

    def i32(self):
        return self.s('i')[0]

    def f32(self):
        return self.s('f')[0]

    def vec3(self):
        return self.s('3f')

    def quat(self):  # x y z w
        return self.s('4f')

    def string(self):
        n = self.u16()
        v = self.d[self.p:self.p + n].decode('cp949', errors='replace')
        self.p += n
        return v

    def floats(self, n):
        return self.s(f'{n}f') if n else ()


class Mesh:
    def __init__(self):
        self.type = None
        self.positions = []
        self.normals = []
        self.colors = []
        self.uvs = []          # uv set 1 only
        self.indices = []
        self.weights = []      # per vertex: [(bone, weight), ...]
        self.textures = []
        self.render_style = 0
        self.nodes_used = []


def _read_streams(r, flags, nverts, mesh, skel_blends, palette):
    """Vertex data is stored as up to 4 consecutive streams, each with its own flags."""
    blends = [None] * nverts
    for mask in flags:
        if not mask:
            continue
        for v in range(nverts):
            if mask & VTX_POS:
                if palette:
                    # matrix palette: position + (bones-1) blends + packed bone indices
                    mesh.positions.append(r.vec3())
                    blends[v] = (r.floats(skel_blends), r.u32())
                else:
                    mesh.positions.append(r.vec3())
                    blends[v] = (r.floats(skel_blends), None)
            if mask & VTX_NORMAL:
                mesh.normals.append(r.vec3())
            if mask & VTX_COLOR:
                mesh.colors.append(r.u32())
            for i, uvbit in enumerate(VTX_UV):
                if mask & uvbit:
                    uv = r.s('2f')
                    if i == 0:
                        mesh.uvs.append(uv)
            if mask & VTX_BASIS:
                r.vec3()
                r.vec3()
    return blends


def read_lod(r, model):
    m = Mesh()
    ntex = r.u32()
    m.textures = list(r.s('4I'))[:ntex]
    m.render_style = r.u32()
    m.render_priority = r.u8()
    m.type = r.u32()
    if m.type == MESH_NULL:
        r.u32()
    else:
        obj_size = r.u32()
        start = r.p
        nverts, nfaces, max_bones_face, max_bones_vert = r.s('4I')
        m.max_bones_vert = max_bones_vert
        m.max_bones_face = max_bones_face
        if m.type == MESH_RIGID:
            flags = r.s('4I')
            bone = r.u32()
            _read_streams(r, flags, nverts, m, 0, False)
            m.indices = list(r.s(f'{nfaces * 3}H'))
            m.weights = [[(bone, 1.0)]] * nverts
        elif m.type == MESH_SKEL:
            reindexed = r.u8()
            flags = r.s('4I')
            palette = r.u8()
            if palette:
                min_bone, max_bone = r.s('2I')
                remap = list(r.s(f'{r.count("remap")}I')) if reindexed else None
                nb = max(0, max_bones_vert - 1)
                blends = _read_streams(r, flags, nverts, m, nb, True)
                m.indices = list(r.s(f'{nfaces * 3}H'))
                for b, packed in blends:
                    bones = [(packed >> (8 * i)) & 0xff for i in range(4)]
                    if remap:
                        bones = [remap[x] if x < len(remap) else x for x in bones]
                    m.weights.append(_blend_weights(bones, b))
            else:
                nb = max(0, max_bones_face - 1)
                blends = _read_streams(r, flags, nverts, m, nb, False)
                m.indices = list(r.s(f'{nfaces * 3}H'))
                m.weights = [None] * nverts
                for _ in range(r.count('bone sets')):
                    first, count = r.s('2H')
                    bones = r.s('4B')
                    r.u32()  # index buffer index
                    for v in range(first, first + count):
                        m.weights[v] = _blend_weights(bones, blends[v][0])
        elif m.type == MESH_VA:
            raise NotImplementedError('vertex animated mesh')
        else:
            raise ValueError(f'unknown mesh type {m.type}')
        if r.p - start != obj_size:
            raise ValueError(f'mesh size mismatch: read {r.p - start}, obj_size {obj_size}')
    m.nodes_used = list(r.s(f'{r.u8()}B'))
    return m


def _blend_weights(bones, blends):
    ws = list(blends) + [1.0 - sum(blends)]
    # the implicit last weight belongs to the last used bone slot
    out = []
    for i, w in enumerate(ws):
        if i < len(bones) and bones[i] != INVALID_BONE and w > 1e-6:
            out.append((bones[i], w))
    return out or [(bones[0], 1.0)]


class Node:
    __slots__ = ('name', 'index', 'flags', 'matrix', 'children', 'parent')


class Model:
    pass


def _read_anim_transforms(r, cmp, nkeys, nnodes):
    tracks = []
    for _ in range(nnodes):
        if cmp == CMP_NONE:
            is_vertex = r.u8()
            if is_vertex:
                raise NotImplementedError('vertex animation')
            pos = [r.vec3() for _ in range(nkeys)]
            rot = [r.quat() for _ in range(nkeys)]
        else:
            n = r.count('pos keys')
            if cmp == CMP_RELEVANT16:
                pos = [tuple(c / 16.0 for c in r.s('3h')) for _ in range(n)]
            else:
                pos = [r.vec3() for _ in range(n)]
            n = r.count('rot keys')
            if cmp == CMP_RELEVANT:
                rot = [r.quat() for _ in range(n)]
            else:
                rot = [tuple(c / 0x7fff for c in r.s('4h')) for _ in range(n)]
        # fewer keys than frames means "hold the last value"
        if pos and len(pos) < nkeys:
            pos += [pos[-1]] * (nkeys - len(pos))
        if rot and len(rot) < nkeys:
            rot += [rot[-1]] * (nkeys - len(rot))
        tracks.append((pos, rot))
    return tracks


def parse(data):
    r = Reader(data)
    file_type, file_version = r.s('2H')
    if file_type != 1 or file_version != 9:
        raise ValueError(f'not a D3D LTB ({file_type}, {file_version})')
    r.s('4I')
    m = Model()
    m.version = r.i32()
    if m.version not in (23, 24, 25):
        raise ValueError(f'unsupported model version {m.version}')
    (m.n_keyframes, m.n_anims, m.n_nodes, m.n_pieces, m.n_child_models, m.n_faces,
     m.n_verts, m.n_vert_weights, m.n_lods, m.n_sockets, m.n_weight_sets,
     m.n_strings, m.string_len, m.va_data_size, m.anim_data_size) = r.s('15i')
    m.command = r.string()
    m.radius = r.f32()
    n_obb = r.count('obb')
    m.obbs = [r.s('17f' if m.version > 23 else '16f') for _ in range(n_obb)]

    m.pieces = []
    for _ in range(r.count('pieces')):
        name = r.string()
        nlod = r.count('lods')
        dists = r.floats(nlod)
        lod_min, lod_max = r.s('2I')
        lods = [read_lod(r, m) for _ in range(nlod)]
        m.pieces.append({'name': name, 'lod_dists': dists, 'lods': lods})

    # node tree, pre-order
    m.nodes = []

    def read_node(parent):
        n = Node()
        n.name = r.string()
        n.index = r.u16()
        n.flags = r.u8()
        n.matrix = r.s('16f')  # row-major 4x4
        n.parent = parent
        n.children = []
        m.nodes.append(n)
        for _ in range(r.count('children')):
            n.children.append(read_node(n))
        return n

    read_node(None)

    m.weight_sets = []
    for _ in range(r.count('weight sets')):
        name = r.string()
        m.weight_sets.append((name, r.floats(r.count('weights'))))

    n_child = r.count('child models')
    m.child_models = [r.string() for _ in range(max(0, n_child - 1))]

    m.anims = []
    for _ in range(r.count('anims')):
        a = {'dims': r.vec3(), 'name': r.string()}
        a['compression'] = r.i32()
        a['interp_ms'] = r.u32()
        nkeys = r.count('keyframes')
        a['keys'] = [(r.u32(), r.string()) for _ in range(nkeys)]
        a['tracks'] = _read_anim_transforms(r, a['compression'], nkeys, len(m.nodes))
        m.anims.append(a)

    m.sockets = []
    for _ in range(r.count('sockets')):
        node = r.u32()
        name = r.string()
        m.sockets.append({'node': node, 'name': name, 'rot': r.quat(), 'pos': r.vec3(), 'scale': r.vec3()})

    m.anim_bindings = []
    for _ in range(max(1, m.n_child_models)):
        if r.p >= len(data):
            break
        for _ in range(r.count('anim bindings')):
            name = r.string()
            m.anim_bindings.append({'name': name, 'dims': r.vec3(), 'origin': r.vec3()})
    m.trailing = len(data) - r.p
    return m


def summary(m):
    print(f'version {m.version}  radius {m.radius:.1f}  cmd {m.command!r}')
    print(f'nodes {len(m.nodes)}  anims {len(m.anims)}  sockets {len(m.sockets)}  child models {m.child_models}')
    for p in m.pieces:
        for i, l in enumerate(p['lods']):
            print(f'  piece {p["name"]!r} lod{i}: type {l.type} verts {len(l.positions)} tris {len(l.indices) // 3} '
                  f'tex {l.textures} style {l.render_style} bones/vert {getattr(l, "max_bones_vert", 0)}')
    for a in m.anims[:10]:
        print(f'  anim {a["name"]!r} cmp {a["compression"]} keys {len(a["keys"])} last {a["keys"][-1][0] if a["keys"] else 0}ms')
    print(f'trailing bytes: {m.trailing}')


def scan(root):
    ok, fails = 0, []
    for dp, _, names in os.walk(root):
        for n in names:
            if n.lower().endswith('.ltb'):
                p = os.path.join(dp, n)
                try:
                    with open(p, 'rb') as f:
                        m = parse(f.read())
                    if m.trailing:
                        raise ValueError(f'{m.trailing} trailing bytes')
                    ok += 1
                except Exception as ex:
                    fails.append((os.path.relpath(p, root), f'{type(ex).__name__}: {ex}'))
    print(f'ok {ok}, failed {len(fails)}')
    from collections import Counter
    for msg, c in Counter(f[1] for f in fails).most_common(15):
        ex = next(f[0] for f in fails if f[1] == msg)
        print(f'  {c:5}  {msg}   e.g. {ex}')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if sys.argv[1] == '--scan':
        scan(sys.argv[2])
    else:
        with open(sys.argv[1], 'rb') as f:
            summary(parse(f.read()))
