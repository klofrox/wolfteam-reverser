"""Xenesis File System (.xfs) reader/extractor for WolfTeam archives.

Layout (reverse engineered from config.xfs / wolf.xfs):
  file header : u32 footer_offset, u16 0
  footer      : chunk(64-byte "XFS " header) + chunk(directory)
  directory   : pre-order tree of records
                u32 child_count, u8 name_len, name,
                u48 data_offset, u32 size, u32 stored_size, u8 is_file
  file data   : sequence of chunks at data_offset, stored_size bytes in total

Chunk header (u24 little-endian `v` first):
  v & 0x400000                  -> stored:      len = v & 0x3fffff, u16 check, raw bytes
  v & 0x800000                  -> compressed:  usize = v & 0x3fffff, u24 csize, u16 check, zlib
  otherwise                     -> compressed:  csize = v, u16 check, zlib (usize 0x10000)
The footer uses compact forms: the XFS header is u8 csize (usize 64) and the
directory is u24 usize + u24 csize, neither with a check field.

Usage:
  python xfs.py list    <archive.xfs> [filter]
  python xfs.py extract <archive.xfs> <out_dir> [filter]
  python xfs.py verify  <archive.xfs>
"""
import os
import struct
import sys
import zlib


def _u24(b, o=0):
    return b[o] | b[o + 1] << 8 | b[o + 2] << 16


class Entry:
    __slots__ = ('path', 'offset', 'size', 'stored', 'is_file')

    def __init__(self, path, offset, size, stored, is_file):
        self.path, self.offset, self.size, self.stored, self.is_file = path, offset, size, stored, is_file


class XFS:
    def __init__(self, path):
        self.f = open(path, 'rb')
        footer = struct.unpack('<I', self.f.read(4))[0]
        self.f.seek(footer)
        clen = self.f.read(1)[0]
        self.header = zlib.decompress(self.f.read(clen))
        if self.header[:4] != b'XFS ':
            raise ValueError('not an XFS archive')
        h = self.f.read(6)
        usize, csize = _u24(h), _u24(h, 3)
        directory = zlib.decompress(self.f.read(csize))
        if len(directory) != usize:
            raise ValueError('directory size mismatch')
        self.entries = []
        self._parse_dir(directory)

    def _parse_dir(self, d):
        pos = 0
        stack = []  # [name, remaining_children]
        while pos < len(d):
            count = struct.unpack_from('<I', d, pos)[0]
            n = d[pos + 4]
            name = d[pos + 5:pos + 5 + n].decode('cp949', errors='replace')
            pos += 5 + n
            off_lo, off_hi, size, stored, is_file = struct.unpack_from('<IHIIB', d, pos)
            pos += 15
            parent = '/'.join(s[0] for s in stack[1:])
            path = f'{parent}/{name}' if parent else name
            if stack:
                stack[-1][1] -= 1
            if is_file:
                self.entries.append(Entry(path, off_lo | off_hi << 32, size, stored, True))
            else:
                if stack:  # skip the Root node itself in paths
                    self.entries.append(Entry(path, 0, 0, 0, False))
                stack.append([name, count])
            while stack and stack[-1][1] == 0:
                stack.pop()

    def files(self):
        return [e for e in self.entries if e.is_file]

    def read(self, e):
        self.f.seek(e.offset)
        raw = self.f.read(e.stored)
        out = bytearray()
        pos = 0
        while pos < len(raw):
            v = _u24(raw, pos)
            if v & 0x400000:
                n = v & 0x3fffff
                pos += 5
                out += raw[pos:pos + n]
                pos += n
                continue
            if v & 0x800000:
                usize, csize = v & 0x3fffff, _u24(raw, pos + 3)
                pos += 8
            else:
                usize, csize = 0x10000, v
                pos += 5
            chunk = zlib.decompress(raw[pos:pos + csize])
            if len(chunk) != usize:
                raise ValueError(f'{e.path}: chunk size {len(chunk)} != {usize}')
            out += chunk
            pos += csize
        if len(out) != e.size:
            raise ValueError(f'{e.path}: size {len(out)} != {e.size}')
        return bytes(out)


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    sys.stdout.reconfigure(encoding='utf-8')
    cmd, arc = argv[1], XFS(argv[2])
    if cmd == 'list':
        flt = argv[3].lower() if len(argv) > 3 else ''
        for e in arc.files():
            if flt in e.path.lower():
                print(f'{e.size:>10} {e.stored:>10} {e.offset:#012x} {e.path}')
        print(f'{len(arc.files())} files', file=sys.stderr)
    elif cmd == 'extract':
        out_dir = argv[3]
        flt = argv[4].lower() if len(argv) > 4 else ''
        n = 0
        for e in arc.files():
            if flt not in e.path.lower():
                continue
            dst = os.path.join(out_dir, *e.path.split('/'))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, 'wb') as o:
                o.write(arc.read(e))
            n += 1
        print(f'extracted {n} files to {out_dir}')
    elif cmd == 'verify':
        bad = 0
        for e in arc.files():
            try:
                arc.read(e)
            except Exception as ex:  # report and keep going
                bad += 1
                print('FAIL', ex)
        print(f'{len(arc.files())} files, {bad} failures')
        return 1 if bad else 0
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
