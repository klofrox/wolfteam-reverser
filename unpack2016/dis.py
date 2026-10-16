import sys, capstone
b = open(sys.argv[1], 'rb').read(); base = int(sys.argv[2], 16)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
for a in sys.argv[3:]:
    a, n = (a.split(':') + ['40'])[:2]; a = int(a, 16); n = int(n)
    print('==== %x' % a)
    for j in md.disasm(b[a - base:a - base + n * 8], a):
        print('%08x  %s %s' % (j.address, j.mnemonic, j.op_str)); n -= 1
        if n <= 0: break
