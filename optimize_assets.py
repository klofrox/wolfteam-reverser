"""Smaller downloads for hosting: a .webp next to every texture .png and a .gz next to big model / data / sound files.

The originals stay; server.py sends the .webp when the browser accepts image/webp (same .png URL, so the client
code does not change) and the .gz to gzip-capable browsers, each only while it is at least as new as its source
(a re-converted png / glb is served as is until this tool runs again).

  python tools/optimize_assets.py            (incremental: only missing / outdated files)
  python tools/optimize_assets.py --force
  python tools/optimize_assets.py --alpha    (re-encode only the pngs with fully transparent pixels)

WebP: lossy quality 85, alpha lossless (alpha-tested foliage / fences keep clean edges); kept only when smaller
than the png. exact: the colour under alpha 0 is kept. Without it the encoder blanked it, and many DTX skins carry
an all-zero alpha the game never reads (PV hand gloves wt_pv_hand_r/b, additive FX): they came out black and blocky.
"""
import gzip
import os
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PNG_DIRS = [os.path.join(ROOT, "assets"), os.path.join(ROOT, "client", "ui")]
GZ_DIRS = [os.path.join(ROOT, "assets"), os.path.join(ROOT, "client"), os.path.join(ROOT, "extracted", "wt_snd")]
GZ_EXT = {".glb", ".json", ".wav", ".js", ".css", ".html", ".txt"}
GZ_MIN = 4096


def stale(src, dst):
    return not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src)


def to_webp(job):
    src, force = job
    dst = os.path.splitext(src)[0] + ".webp"
    if not force and not stale(src, dst):
        return 0, 0, "skip"
    try:
        from PIL import Image
        with Image.open(src) as im:
            if force == "alpha" and not (im.mode in ("RGBA", "LA", "P") and im.convert("RGBA").getchannel("A").getextrema()[0] == 0):
                return 0, 0, "skip"
            if im.mode == "P":
                im = im.convert("RGBA")
            elif im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
            im.save(dst, "WEBP", quality=85, alpha_quality=100, method=4, exact=True)
        a, b = os.path.getsize(src), os.path.getsize(dst)
        if b >= a:   # nothing gained: let the png be served
            os.remove(dst)
            return a, a, "bigger"
        return a, b, "ok"
    except Exception as e:
        if os.path.exists(dst):
            os.remove(dst)
        return 0, 0, f"ERR {e}"


def to_gz(job):
    src, force = job
    dst = src + ".gz"
    if not force and not stale(src, dst):
        return 0, 0, "skip"
    with open(src, "rb") as f:
        data = gzip.compress(f.read(), 9)
    if len(data) >= os.path.getsize(src) * 0.95:
        if os.path.exists(dst):
            os.remove(dst)
        return 0, 0, "bigger"
    with open(dst, "wb") as f:
        f.write(data)
    return os.path.getsize(src), len(data), "ok"


def walk(dirs, pred):
    for d in dirs:
        for r, _, files in os.walk(d):
            for x in files:
                p = os.path.join(r, x)
                if pred(x, p):
                    yield p


def run(name, fn, files, force):
    before = after = done = errors = 0
    with ProcessPoolExecutor() as pool:
        for a, b, status in pool.map(fn, [(f, force) for f in files], chunksize=32):
            before += a
            after += b
            done += status == "ok"
            if status.startswith("ERR"):
                errors += 1
                if errors <= 5:
                    print(name, status)
    print(f"{name}: {done} written of {len(files)}, {before >> 20} MB -> {after >> 20} MB, {errors} errors")


def main():
    force = "--force" in sys.argv
    pngs = list(walk(PNG_DIRS, lambda x, p: x.lower().endswith(".png")))
    if "--alpha" in sys.argv:
        run("webp", to_webp, pngs, "alpha")
        return
    run("webp", to_webp, pngs, force)
    gzs = list(walk(GZ_DIRS, lambda x, p: os.path.splitext(x)[1].lower() in GZ_EXT and os.path.getsize(p) >= GZ_MIN))
    run("gzip", to_gz, gzs, force)


if __name__ == "__main__":
    main()
