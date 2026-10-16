"""LithTech Jupiter world (.dat, version 85) reader - render geometry, lightmaps, objects.

Header: u32 version, u32 offsets[6] (objects, blind objects, light grid, collision,
particle blockers, render data), u32 reserved[8].

Render data:
  u32 block_count, RenderBlock[block_count]
  u32 world_model_count, { string name, u32 block_count, RenderBlock[], u32 unknown }[]

RenderBlock:
  vec3 center, vec3 half_dims
  u32 section_count, Section[]:
      string texture0, string texture1, u8 shader, u32 tri_count,
      string texture_effect, u32 lm_width, u32 lm_height, u32 lm_size, u8 lm_data[lm_size]
  u32 vertex_count, Vertex[]: vec3 pos, vec2 uv0, vec2 uv1, u8 rgba[4], vec3 normal,
                              vec3 tangent, vec3 binormal
  u32 tri_count, Tri[]: u32 i0, i1, i2, u32 poly_index
  u32 sky_portal_count, { u8 n, vec3[n], vec3 normal, f32 dist }[]
  u32 occluder_count, { u8 n, vec3[n], vec3 normal, f32 dist, u32 name_id }[]
  u32 light_group_count, { string name, vec3 color, u32 n, u8[n],
                           u32 section_count, { u32 n, { u32 l,t,w,h, u32 n, u8[n] }[] }[] }[]
  u8 child_flags, u32 children[2]
Triangles are assigned to sections in order (section i owns the next tri_count tris).
Strings are u16 length + bytes.
"""
import struct
import sys

VERTEX = struct.Struct('<3f2f2f4B3f3f3f')  # + tangent, binormal (68 bytes)


class R:
    def __init__(self, d, p=0):
        self.d, self.p = d, p

    def s(self, fmt):
        v = struct.unpack_from('<' + fmt, self.d, self.p)
        self.p += struct.calcsize('<' + fmt)
        return v

    def u8(self):
        self.p += 1
        return self.d[self.p - 1]

    def u16(self):
        return self.s('H')[0]

    def u32(self):
        return self.s('I')[0]

    def f32(self):
        return self.s('f')[0]

    def count(self, what, item_size=1):
        n = self.u32()
        if n * item_size > len(self.d) - self.p:
            raise ValueError(f'implausible {what} count {n} at {self.p - 4:#x}')
        return n

    def string(self):
        n = self.u16()
        v = self.d[self.p:self.p + n]
        self.p += n
        return v.decode('cp949', errors='replace')

    def raw(self, n):
        v = self.d[self.p:self.p + n]
        self.p += n
        return v


def decompress_lightmap(data, w, h):
    """Jupiter lightmap RLE: tag byte; tag & 0x80 -> run of (tag & 0x7f) + 1 copies of
    the following RGB triple, else (tag + 1) literal RGB triples."""
    out = bytearray()
    p = 0
    n = len(data)
    while p < n:
        tag = data[p]
        p += 1
        if tag & 0x80:
            out += data[p:p + 3] * ((tag & 0x7f) + 1)
            p += 3
        else:
            k = (tag + 1) * 3
            out += data[p:p + k]
            p += k
    if len(out) != w * h * 3:
        raise ValueError(f'lightmap size {len(out)} != {w}x{h}x3')
    return bytes(out)


class Section:
    __slots__ = ('texture', 'texture2', 'shader', 'tri_count', 'effect', 'lm_w', 'lm_h', 'lm_data')


class Block:
    pass


def read_block(r):
    b = Block()
    b.center = r.s('3f')
    b.half = r.s('3f')
    b.sections = []
    for _ in range(r.count('section')):
        s = Section()
        s.texture = r.string()
        s.texture2 = r.string()
        s.shader = r.u8()
        s.tri_count = r.u32()
        s.effect = r.string()
        s.lm_w, s.lm_h = r.s('2I')
        s.lm_data = r.raw(r.count('lightmap'))
        b.sections.append(s)
    nv = r.count('vertex', VERTEX.size)
    b.verts = r.raw(nv * VERTEX.size)
    b.vert_count = nv
    nt = r.count('triangle', 16)
    b.tris = r.raw(nt * 16)
    b.tri_count = nt
    b.sky_portals = []
    for _ in range(r.count('sky portal')):
        n = r.u8()
        b.sky_portals.append((r.s(f'{n * 3}f'), r.s('3f'), r.f32()))
    b.occluders = []
    for _ in range(r.count('occluder')):
        n = r.u8()
        b.occluders.append((r.s(f'{n * 3}f'), r.s('3f'), r.f32(), r.u32()))
    b.light_groups = []
    for _ in range(r.count('light group')):
        name = r.string()
        color = r.s('3f')
        intensities = r.raw(r.count('light group data'))
        subs = []
        for _ in range(r.count('light group section')):
            for _ in range(r.count('sub lightmap')):
                rect = r.s('4I')
                subs.append((rect, r.raw(r.count('sub lightmap data'))))
        b.light_groups.append((name, color, intensities, subs))
    b.child_flags = r.u8()
    b.children = r.s('2I')
    if sum(s.tri_count for s in b.sections) != nt:
        raise ValueError(f'section tri counts {sum(s.tri_count for s in b.sections)} != {nt}')
    return b


class ObjectDef:
    __slots__ = ('type', 'props')


def read_objects(r, end):
    objs = []
    for _ in range(r.count('object')):
        size = r.u16()
        start = r.p
        o = ObjectDef()
        o.type = r.string()
        o.props = {}
        for _ in range(r.u32()):
            name = r.string()
            ptype = r.u8()
            r.u32()  # property flags
            plen = r.u16()
            pstart = r.p
            if ptype == 0:      # string
                val = r.string()
            elif ptype in (1, 2):  # vector / color
                val = r.s('3f')
            elif ptype == 3:    # real
                val = r.f32()
            elif ptype == 4:    # flags
                val = r.u32()
            elif ptype == 5:    # bool
                val = bool(r.u8())
            elif ptype == 6:    # long int
                val = r.s('i')[0]
            elif ptype == 7:    # rotation (euler)
                val = r.s('3f')
            else:
                val = r.raw(plen)
            r.p = pstart + plen
            o.props[name] = val
        r.p = start + size
        objs.append(o)
    return objs


class World:
    pass


def load(data, objects=True):
    r = R(data)
    w = World()
    w.version = r.u32()
    if w.version != 85:
        raise ValueError(f'unsupported world version {w.version}')
    (w.obj_pos, w.blind_pos, w.lightgrid_pos, w.collision_pos,
     w.particle_pos, w.render_pos) = r.s('6I')

    r.p = w.render_pos
    w.blocks = [read_block(r) for _ in range(r.count('render block'))]
    w.world_models = []
    for _ in range(r.count('render world model')):
        name = r.string()
        w.world_models.append((name, [read_block(r) for _ in range(r.count('wm render block'))]))
        r.u32()  # unknown, always 0 so far
    w.trailing = len(data) - r.p

    w.objects = read_objects(R(data, w.obj_pos), w.blind_pos) if objects else []
    return w


def model_boxes(data, name):
    """Bounds of a brush object's brushes (Ladder volume, ...) from the world-model list before the objects
    section: u16 name length, name, u32 counts[10] (points, planes, surfaces, portals, polies, leafs, verts,
    vis, leaf lists, nodes), vec3 min, max, center (= (min + max) / 2, which checks the match), texture names
    (u32 length, u32 count, the strings), one vertex-count byte per poly, ... and the points (vec3 each).
    One object can hold several brushes far apart (arrival's Ladder0 = two ladders at the map's ends): the
    points come 8 per box brush, so those are returned box by box; else the whole bounds.
    Returns [(min, max), ...] in world units, [] when not found."""
    obj_pos = struct.unpack_from('<I', data, 4)[0]
    key = struct.pack('<H', len(name)) + name.encode('latin-1')
    i = data.find(key, 0, obj_pos)
    while i >= 0:
        k = i + len(key)
        if k + 76 <= obj_pos:
            counts = struct.unpack_from('<10I', data, k)
            mn = struct.unpack_from('<3f', data, k + 40)
            mx = struct.unpack_from('<3f', data, k + 52)
            c = struct.unpack_from('<3f', data, k + 64)
            if (all(a <= b for a, b in zip(mn, mx)) and any(b - a > 1 for a, b in zip(mn, mx))
                    and all(abs(x - (a + b) / 2) < 0.01 for a, b, x in zip(mn, mx, c))):
                boxes = _split_brushes(data, k + 76, counts, mn, mx)
                if boxes:
                    return boxes
                # not box brushes: the whole bounds only when it is ladder sized (else it would cover a
                # part of the map: sand_storm / secretlab / thesilo / w_district, 24-34 m wide)
                w = sorted((mx[0] - mn[0], mx[2] - mn[2]))
                return [(mn, mx)] if w[0] <= 450 and w[1] <= 600 else []
        i = data.find(key, i + 1, obj_pos)
    return []


def _split_brushes(data, k, counts, mn, mx):
    """Per-brush boxes from the points array (see model_boxes), or None when it is not 8-point boxes."""
    npts, npol = counts[0], counts[4]
    if not npts or npts % 8:
        return None
    nlen = struct.unpack_from('<I', data, k)[0]
    k += 8 + nlen + npol
    eps = 0.01
    inside = lambda p: all(mn[a] - eps <= p[a] <= mx[a] + eps for a in range(3))  # noqa: E731
    for s in range(k, min(len(data) - npts * 12, k + 20000)):
        first = struct.unpack_from('<3f', data, s)
        if not inside(first):
            continue
        f = struct.unpack_from('<%df' % (npts * 3), data, s)
        pts = [f[j:j + 3] for j in range(0, len(f), 3)]
        if not all(inside(p) for p in pts):
            continue
        if not all(abs(min(p[a] for p in pts) - mn[a]) < eps and abs(max(p[a] for p in pts) - mx[a]) < eps for a in range(3)):
            continue
        boxes = []
        for j in range(0, npts, 8):
            g = pts[j:j + 8]
            lo = tuple(min(p[a] for p in g) for a in range(3))
            hi = tuple(max(p[a] for p in g) for a in range(3))
            # a box brush: every point is a corner
            if not all(all(abs(p[a] - lo[a]) < eps or abs(p[a] - hi[a]) < eps for a in range(3)) for p in g):
                return None
            boxes.append((lo, hi))
        return boxes
    return None


def summary(w):
    nverts = sum(b.vert_count for b in w.blocks)
    ntris = sum(b.tri_count for b in w.blocks)
    tex = {}
    for b in w.blocks:
        for s in b.sections:
            tex[s.texture] = tex.get(s.texture, 0) + s.tri_count
    print(f'blocks {len(w.blocks)}  verts {nverts}  tris {ntris}  textures {len(tex)}  '
          f'world models {len(w.world_models)}  trailing {w.trailing}')
    for t, c in sorted(tex.items(), key=lambda x: -x[1])[:15]:
        print(f'  {c:7} {t}')
    from collections import Counter
    print('objects:', Counter(o.type for o in w.objects).most_common(25))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    with open(sys.argv[1], 'rb') as f:
        summary(load(f.read()))
