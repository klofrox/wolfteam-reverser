"""LithTech Jupiter DTX (version -5) texture decoder / converter.

Header (164 bytes, little-endian):
  u32 res_type, i32 version (-5), u16 width, u16 height, u16 mipmaps,
  u16 sections, i32 iflags, i32 user_flags, u8 extra[12], char command[128]
  extra[2] is the pixel format: 3 = BGRA8888, 4 = DXT1, 5 = DXT3, 6 = DXT5.
Mip levels follow the header, largest first.

Usage:
  python dtx.py <file.dtx> <out.png>
  python dtx.py <src_dir> <out_dir> [--webp]     (batch, keeps folder layout,
                                                 writes textures.json index)
"""
import json
import os
import struct
import sys
from concurrent.futures import ProcessPoolExecutor

from PIL import Image

HEADER_SIZE = 164
FORMATS = {3: 'BGRA8888', 4: 'DXT1', 5: 'DXT3', 6: 'DXT5'}
BCN = {4: 1, 5: 2, 6: 3}

# iflags bits (LithTech dtxmgr.h)
IFLAGS = {
    0x1: 'fullbrite', 0x2: 'prefer16bit', 0x4: 'mipsalloced', 0x8: 'sectionsfixed',
    0x40: 'nosyscache', 0x80: 'prefer4444', 0x100: 'prefer5551',
    0x200: '32bitsyscopy', 0x400: 'cubemap', 0x800: 'bumpmap', 0x1000: 'lumbumpmap',
}


def read_header(data):
    res_type, version, w, h, mips, sections, iflags, uflags = struct.unpack_from('<IiHHHHii', data, 0)
    extra = data[24:36]
    command = data[36:164].split(b'\0', 1)[0].decode('latin1')
    return {
        'version': version, 'width': w, 'height': h, 'mipmaps': mips,
        'sections': sections, 'iflags': iflags, 'user_flags': uflags,
        'format': FORMATS.get(extra[2], f'unknown({extra[2]})'), 'bpp_ident': extra[2],
        'texture_group': extra[0], 'mipmaps_to_use': extra[1],
        'detail_scale': struct.unpack_from('<f', extra, 6)[0],
        'flags': [n for b, n in IFLAGS.items() if iflags & b],
        'command': command,
    }


def mip0_size(fmt, w, h):
    if fmt == 3:
        return w * h * 4
    bw, bh = max(1, (w + 3) // 4), max(1, (h + 3) // 4)
    return bw * bh * (8 if fmt == 4 else 16)


def decode(data):
    hdr = read_header(data)
    if hdr['version'] != -5:
        raise ValueError(f'unsupported DTX version {hdr["version"]}')
    fmt, w, h = hdr['bpp_ident'], hdr['width'], hdr['height']
    pix = data[HEADER_SIZE:HEADER_SIZE + mip0_size(fmt, w, h)]
    if fmt == 3:
        img = Image.frombytes('RGBA', (w, h), pix, 'raw', 'BGRA')
    elif fmt in BCN:
        img = Image.frombytes('RGBA', (w, h), pix, 'bcn', BCN[fmt])
    else:
        raise ValueError(f'unsupported pixel format {fmt}')
    return img, hdr


def _convert(job):
    src, dst, webp = job
    try:
        with open(src, 'rb') as f:
            img, hdr = decode(f.read())
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if webp:
            img.save(dst, 'WEBP', quality=90, method=4)
        else:
            img.save(dst, 'PNG', optimize=False)
        hdr['alpha_range'] = list(img.getchannel('A').getextrema())
        return src, hdr, None
    except Exception as ex:  # report per file, keep the batch going
        return src, None, str(ex)


def convert_dir(src_dir, out_dir, webp=False):
    ext = '.webp' if webp else '.png'
    jobs = []
    for root, _, names in os.walk(src_dir):
        for n in names:
            if n.lower().endswith('.dtx'):
                src = os.path.join(root, n)
                rel = os.path.relpath(src, src_dir)
                jobs.append((src, os.path.join(out_dir, os.path.splitext(rel)[0] + ext), webp))
    index, errors = {}, []
    with ProcessPoolExecutor() as pool:
        for src, hdr, err in pool.map(_convert, jobs, chunksize=32):
            rel = os.path.relpath(src, src_dir).replace('\\', '/')
            if err:
                errors.append((rel, err))
            else:
                index[rel] = hdr
    with open(os.path.join(out_dir, 'textures.json'), 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=1)
    print(f'converted {len(index)} / {len(jobs)} textures, {len(errors)} errors')
    for rel, err in errors[:20]:
        print('  ERR', rel, err)
    return 1 if errors else 0


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    if os.path.isdir(argv[1]):
        return convert_dir(argv[1], argv[2], '--webp' in argv)
    with open(argv[1], 'rb') as f:
        img, hdr = decode(f.read())
    img.save(argv[2])
    print(json.dumps(hdr, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
