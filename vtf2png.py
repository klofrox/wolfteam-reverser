# Convert a Source engine texture (.vtf, DXT1 / DXT3 / DXT5) to PNG: python tools/vtf2png.py in.vtf out.png
import io, struct, sys
from PIL import Image

src = sys.argv[1]
dst = sys.argv[2]
d = open(src, "rb").read()
w, h = struct.unpack_from("<HH", d, 16)
fmt = struct.unpack_from("<i", d, 52)[0]
blocks = {13: ("DXT1", 8), 14: ("DXT3", 16), 15: ("DXT5", 16)}
if fmt not in blocks:
    sys.exit(f"unsupported VTF format {fmt}")
name, bs = blocks[fmt]
size = (w // 4) * (h // 4) * bs
raw = d[len(d) - size:]   # the biggest mip is stored last
hdr = b"DDS " + struct.pack("<7I", 124, 0x1007 | 0x80000, h, w, size, 0, 1) + b"\0" * 44
hdr += struct.pack("<II4s5I", 32, 4, name.encode(), 0, 0, 0, 0, 0) + struct.pack("<5I", 0x1000, 0, 0, 0, 0)
im = Image.open(io.BytesIO(hdr + raw)).convert("RGBA")
im.save(dst)
print(name, im.size, "->", dst)
