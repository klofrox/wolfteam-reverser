"""Turkish UI art: convert every wt_interface texture of the TR 2016 client (extracted_tr) that differs from the
US 2016 one, or exists only in TR, over assets/textures/wt_interface (Turkish captions, Joygame logo, TR-only icons).

Run after the US conversion (tools/dtx.py extracted/wt_interface assets/textures/wt_interface), then
tools/optimize_assets.py for the .webp copies. Run: python tools/apply_tr_textures.py
"""
import hashlib
import os
import sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(__file__))
from dtx import _convert  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
US = os.path.join(ROOT, "extracted", "wt_interface")
TR = os.path.join(ROOT, "extracted_tr", "wt_interface")
OUT = os.path.join(ROOT, "assets", "textures", "wt_interface")


def digest(path):
    return hashlib.md5(open(path, "rb").read()).digest()


def main():
    jobs = []
    for root, _, names in os.walk(TR):
        for n in names:
            if not n.lower().endswith(".dtx"):
                continue
            src = os.path.join(root, n)
            rel = os.path.relpath(src, TR)
            us = os.path.join(US, rel)
            if os.path.isfile(us) and os.path.getsize(us) == os.path.getsize(src) and digest(us) == digest(src):
                continue
            # asset paths are lower case (see tools/export_ui_layouts.py texture())
            jobs.append((src, os.path.join(OUT, os.path.splitext(rel)[0].lower() + ".png"), False))
    errors = 0
    with ProcessPoolExecutor() as pool:
        for src, _, err in pool.map(_convert, jobs, chunksize=16):
            if err:
                errors += 1
                print("ERR", os.path.relpath(src, TR), err)
    print(f"{len(jobs) - errors} Turkish textures written, {errors} errors")


if __name__ == "__main__":
    main()
