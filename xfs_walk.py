"""wolf.xfs chunk walker (format research)."""
import sys, zlib, struct, collections

def walk(path, limit=None, verbose=False):
    f = open(path, 'rb')
    magic = f.read(6)
    stats = collections.Counter()
    pos = 6
    n = 0
    while True:
        h = f.read(3)
        if len(h) < 3:
            break
        flag = h[2]
        if flag == 0x80:
            rest = f.read(5)
            usize = h[0] | h[1] << 8
            csize = rest[0] | rest[1] << 8 | rest[2] << 16
            chk = rest[3:5]
            hl = 8
        elif flag == 0x00:
            chk = f.read(2)
            csize = h[0] | h[1] << 8
            usize = 0x10000
            hl = 5
        elif flag & 0x40:
            chk = f.read(2)
            csize = (h[0] | h[1] << 8) or 0x10000
            usize = csize
            hl = 5
        else:
            ctx_pos = pos
            f.seek(pos); ctx = f.read(48)
            print(f'unknown flag {flag:#x} at {pos:#x} after {n} chunks: {ctx.hex(" ")}')
            return stats
        data = f.read(csize)
        if verbose:
            print(f'{pos:#x} flag={flag:#x} c={csize} u={usize}')
        stats[flag] += 1
        pos += hl + csize
        n += 1
        if limit and n >= limit:
            break
    print('end at', hex(pos), stats)
    return stats

if __name__ == '__main__':
    walk(sys.argv[1], verbose='-v' in sys.argv)
