import sys, struct
b = open(sys.argv[1], 'rb').read(); base = int(sys.argv[2], 16)
for t in sys.argv[3:]:
    t = int(t, 16); out = []
    for i in range(0x1000, 0x10ea000 - 5):
        if b[i] == 0xE8 and (base + i + 5 + struct.unpack_from('<i', b, i + 1)[0]) & 0xffffffff == t: out.append('%08x' % (base + i))
    print('%x callers:' % t, ' '.join(out[:30]))
