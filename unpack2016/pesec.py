import struct, sys, math, collections
for path in sys.argv[1:]:
    b = open(path, 'rb').read()
    pe = struct.unpack_from('<I', b, 0x3c)[0]
    nsec = struct.unpack_from('<H', b, pe + 6)[0]
    optsz = struct.unpack_from('<H', b, pe + 20)[0]
    opt = pe + 24
    ep, = struct.unpack_from('<I', b, opt + 16)
    base, = struct.unpack_from('<I', b, opt + 28)
    print(path, 'base', hex(base), 'EP', hex(ep), 'size', len(b))
    dd = opt + 96
    names = ['export', 'import', 'res', 'exc', 'sec', 'reloc', 'dbg', 'arch', 'gp', 'tls', 'lcfg', 'bimp', 'iat', 'dimp', 'clr']
    for i, n in enumerate(names):
        rva, sz = struct.unpack_from('<II', b, dd + i * 8)
        if sz: print('  dir', n, hex(rva), hex(sz))
    so = opt + optsz
    for i in range(nsec):
        s = so + i * 40
        name = b[s:s + 8].rstrip(b'\0')
        vs, va, rs, ro, _, _, _, _, ch = struct.unpack_from('<IIIIIIHHI', b, s + 8)
        d = b[ro:ro + rs]
        c = collections.Counter(d)
        ent = -sum(v / len(d) * math.log2(v / len(d)) for v in c.values()) if d else 0
        print('  %-8r va %08x vs %08x raw %08x rs %08x ch %08x ent %.2f' % (name, va, vs, ro, rs, ch, ent))
