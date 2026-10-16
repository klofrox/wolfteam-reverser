"""Find 2013 cshell functions in the 2016 dump by matching byte windows.
usage: fmatch.py <2013 pe> <2016 mem> <2016 base hex> <2013 fn hex>[:len] ...
Prints the best 2016 start candidates (votes = windows that land on the same start)."""
import sys, struct, collections
pe13 = open(sys.argv[1], 'rb').read()
mem16 = open(sys.argv[2], 'rb').read(); base16 = int(sys.argv[3], 16)
p = struct.unpack_from('<I', pe13, 0x3c)[0]
base13 = struct.unpack_from('<I', pe13, p + 24 + 28)[0]
nsec = struct.unpack_from('<H', pe13, p + 6)[0]; so = p + 24 + struct.unpack_from('<H', pe13, p + 20)[0]
secs = [struct.unpack_from('<IIII', pe13, so + i * 40 + 8) for i in range(nsec)]
def rd13(va, n):
    rva = va - base13
    for vs, sva, rs, ro in secs:
        if sva <= rva < sva + rs: return pe13[ro + rva - sva: ro + rva - sva + n]
CODE_END = 0x10ea000
W = 9
for arg in sys.argv[4:]:
    a, n = (arg.split(':') + ['600'])[:2]; a = int(a, 16); n = int(n)
    fb = rd13(a, n)
    votes = collections.Counter()
    for off in range(0, len(fb) - W, 2):
        w = fb[off:off + W]
        if w.count(0) > 4 or w.count(0xcc) > 2: continue
        hits = []; i = 0
        while len(hits) < 4 and (i := mem16.find(w, i, CODE_END)) >= 0: hits.append(i); i += 1
        if 0 < len(hits) <= 3:
            for h in hits: votes[(h - off) & ~0] += 1
    print('%x ->' % a, ', '.join('%08x(%d)' % (base16 + s, v) for s, v in votes.most_common(4)))
