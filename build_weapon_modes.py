"""Weapon alt modes (right click: zoom / scope / burst) from wt_attributes/weaponmode.dat -> assets/data/weapon_modes.json.

Format (cshell loads it in FUN_34073a90; layout read from the data, 1173 records end exactly at the file end):
  per record (FUN_34063930): u32 weapon id, u8 mode index (0-2), wstr name ("x1.2", "x4.0", "3 burst", "empty"),
  u32, accuracy block (102 bytes, same layout as weapondata, FUN_34135440), u8, u16, u32, u8,
  wstr sprite (.spr -> one .dtx), u8 flags (0x08 overlay sprite, 0x02 hide the first-person gun: snipers 0x0a),
  u8 burst count, u16 burst interval ms, f32 x3 first-person gun offset in that mode, 3 empty wstrs.
  The accuracy block is a delta ADDED to the weapon while that mode is on (FUN_34136520; ESA-80 x1.2: spread -8,
  crosshair max -40; snipers: spread -3000 = no unscoped penalty).
Output: { "<id>": [ {"name", "zoom", "burst", "burstMs", "flags", "overlay": "<texture png path>", "pv": [x,y,z],
                     "acc": {named non-zero accuracy deltas}} ] }
"""
import gzip
import json
import os
import re
import struct

from gamedata import ACCURACY_NAMES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACC_KEYS = ['a0', 'o34_00', 'a1', 'a2', 'a3', 'a4', 'o34_c8', 'a5', 'o34_70_u8', 'a6', 'o34_50', 'a7', 'a8', 'a9', 'a10',
            'o34_6c', 'a11', 'a12', 'a13', 'a14', 'a15', 'o34_68_u8', 'a16', 'a17', 'a18', 'a19', 'a20']
SRC = os.path.join(ROOT, 'extracted', 'wt_attributes', 'weaponmode.dat')


def wstr(d, o):
    n = struct.unpack_from('<H', d, o)[0]
    return d[o + 2:o + 2 + 2 * n].decode('utf-16le'), o + 2 + 2 * n


def sprite_texture(spr):
    """.spr (LithTech sprite) -> its first frame's texture as our png path (assets/textures/...)"""
    if not spr:
        return None
    p = os.path.join(ROOT, 'extracted', spr.replace('\\', os.sep).lower())
    if not os.path.exists(p):
        return None
    m = re.findall(rb'[\x20-\x7e]{4,}', open(p, 'rb').read())
    if not m:
        return None
    return m[0].decode().replace('\\', '/').lower().rsplit('.', 1)[0] + '.png'


def main():
    d = open(SRC, 'rb').read()
    out = {}
    o = 0
    while o < len(d) - 8:
        wid, mode = struct.unpack_from('<IB', d, o)
        name, p = wstr(d, o + 5)
        acc = {}
        q = p + 4
        for k in ACC_KEYS:
            if k.endswith('_u8'):
                v, q = d[q], q + 1
            else:
                v, q = round(struct.unpack_from('<f', d, q)[0], 4), q + 4
            if v:
                acc[ACCURACY_NAMES.get(k, (k,))[0]] = v
        p += 114
        spr, p = wstr(d, p)
        flags, burst, burst_ms = struct.unpack_from('<BBH', d, p)
        pv = [round(v, 4) for v in struct.unpack_from('<3f', d, p + 4)]
        p += 22
        o = p
        name = name.strip()
        if not name or name.lower() == 'empty':
            continue
        z = re.search(r'[xX]\s*(\d+(?:\.\d+)?)', name)
        b = re.search(r'(\d+)\s*burst', name, re.I)
        out.setdefault(str(wid), []).append({
            'mode': mode, 'name': name.replace('\n', ' '),
            'zoom': float(z.group(1)) if z else None,
            'burst': int(b.group(1)) if b else None, 'burstMs': burst_ms or None,
            'flags': flags, 'overlay': sprite_texture(spr), 'pv': pv if any(pv) else None,
            'acc': acc or None,
        })
    dst = os.path.join(ROOT, 'assets', 'data', 'weapon_modes.json')
    data = json.dumps(out, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    open(dst, 'wb').write(data)
    with gzip.open(dst + '.gz', 'wb', 9) as f:
        f.write(data)
    print(f'{len(out)} weapons with modes -> {dst} ({len(data)} bytes), parsed to {o} of {len(d)}')


if __name__ == '__main__':
    main()
