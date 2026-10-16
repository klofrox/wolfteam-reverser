"""Find instructions using [reg + disp] in a memory dump (code section only) with capstone.
usage: dispscan.py <dump> <base hex> <code_end hex> <disp hex>[,<disp>...] [context]"""
import sys, struct, capstone
b = open(sys.argv[1], 'rb').read()
base = int(sys.argv[2], 16); end = int(sys.argv[3], 16)
disps = [int(x, 16) for x in sys.argv[4].split(',')]
ctx = int(sys.argv[5]) if len(sys.argv) > 5 else 0
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
md.skipdata = True
for disp in disps:
    pat = struct.pack('<I', disp)
    i = 0x1000
    seen = set()
    while True:
        i = b.find(pat, i, end)
        if i < 0: break
        # try instruction starts 2..4 bytes before the displacement
        for back in (2, 3, 4):
            s = i - back
            insn = next(md.disasm(b[s:s + 15], base + s, 1), None)
            if insn and insn.size >= back + 4 and ('0x%x]' % disp) in insn.op_str and s not in seen:
                seen.add(s)
                print('%08x  %-6s %s' % (insn.address, insn.mnemonic, insn.op_str))
                if ctx:
                    for j in md.disasm(b[s - ctx * 4:s + ctx * 4], base + s - ctx * 4):
                        if j.address >= base + s - ctx * 3: print('      %08x  %s %s' % (j.address, j.mnemonic, j.op_str))
                break
        i += 1
