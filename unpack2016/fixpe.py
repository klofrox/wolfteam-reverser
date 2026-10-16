"""Memory image -> loadable PE: raw layout = virtual layout, ImageBase = the base it was dumped at."""
import struct, sys
src, dst, base = sys.argv[1], sys.argv[2], int(sys.argv[3], 16)
b = bytearray(open(src, 'rb').read())
pe = struct.unpack_from('<I', b, 0x3c)[0]
nsec = struct.unpack_from('<H', b, pe + 6)[0]
optsz = struct.unpack_from('<H', b, pe + 20)[0]
opt = pe + 24
struct.pack_into('<I', b, opt + 28, base)                       # ImageBase
salign = struct.unpack_from('<I', b, opt + 32)[0]
struct.pack_into('<I', b, opt + 36, salign)                     # FileAlignment = SectionAlignment
for i in (1, 4, 5, 6, 12):                                      # import / security / reloc / debug / iat dirs are stale
    struct.pack_into('<II', b, opt + 96 + i * 8, 0, 0)
so = opt + optsz
for i in range(nsec):
    s = so + i * 40
    vs, va = struct.unpack_from('<II', b, s + 8)
    vs = min(vs, len(b) - va)
    struct.pack_into('<IIII', b, s + 8, vs, va, vs, va)
    struct.pack_into('<I', b, s + 36, 0xE0000060)               # code | data | rwx
    b[s:s + 8] = (b'.s%d' % i).ljust(8, b'\0')
open(dst, 'wb').write(b)
print('ok', dst)
