"""Convert every first-person (PV) weapon model used by the catalog to assets/models/pv/*.glb.

Models are converted once each WITHOUT textures: ltb2gltf names the materials skin0, skin1, ...
by LTB texture index, and the client assigns textures per weapon from weapondata o580
(pv_model_and_skins = [model, skin for index 0, skin for index 1, ...]), so the 600+ skin
variants share ~200 model files. Writes assets/models/pv/index.json {model path: glb name}.
The third-person (hand-held, weapondata o730 hh_model) models go the same way to
assets/models/hh/ (skin from o4b0 hh_skin, assigned by the client to material skin0).

  python tools/convert_weapons.py [--force]
"""
import json
import os
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ltb  # noqa: E402
import ltb2gltf  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "assets", "models", "pv")
OUT_HH = os.path.join(ROOT, "assets", "models", "hh")


def glb_name(model):
    return os.path.splitext(os.path.basename(model.replace("\\", "/")))[0].lower().replace(" ", "_") + ".glb"


def convert(job):
    model, force, out = job
    src = os.path.join(ROOT, "extracted", model.replace("\\", "/").lower())
    dst = os.path.join(out, glb_name(model))
    if os.path.exists(dst) and not force:
        return model, "skip"
    try:
        with open(src, "rb") as f:
            m = ltb.parse(f.read())
        ltb2gltf.build(m, dst, (), [], 0.01, os.path.splitext(os.path.basename(src))[0], None)
        return model, "ok"
    except Exception:
        return model, "ERR " + traceback.format_exc(limit=1).strip().splitlines()[-1]


def main():
    force = "--force" in sys.argv
    cat = json.load(open(os.path.join(ROOT, "client", "ui", "catalog.json"), encoding="utf-8"))["items"]
    stats = {w["id"]: w for w in json.load(open(os.path.join(ROOT, "assets", "data", "weapons_min.json"), encoding="utf-8"))}
    models, hh = set(), set()
    # weapons that are not shop items: 3 = HELX, the Destruction time bomb (key 5)
    extra = {"3": {"cat": "weapon"}}
    for k, v in {**cat, **extra}.items():
        if v["cat"] == "weapon":
            m = stats[int(k)]["pv_model_and_skins"][0]
            if m:
                models.add(m)
            if stats[int(k)].get("hh_model"):
                hh.add(stats[int(k)]["hh_model"])
    # parts the weapon upgrades show on the gun (silencer / scope / grip, ui/upgrades.json "pv")
    up = json.load(open(os.path.join(ROOT, "client", "ui", "upgrades.json"), encoding="utf-8"))["upgrades"]
    models |= {u["pv"][0] for u in up.values() if u.get("pv") and u.get("sock") is not None}
    for out, names in ((OUT, models), (OUT_HH, hh)):
        os.makedirs(out, exist_ok=True)
        index, errors = {}, []
        with ProcessPoolExecutor(max_workers=4) as pool:
            for model, status in pool.map(convert, [(m, force, out) for m in sorted(names)]):
                if status.startswith("ERR"):
                    errors.append((model, status))
                else:
                    index[model.lower().replace("\\", "/")] = glb_name(model)
        json.dump(index, open(os.path.join(out, "index.json"), "w"), indent=0)
        print(f"{os.path.basename(out)}: {len(index)} / {len(names)} models, {len(errors)} errors")
        for m, e in errors[:15]:
            print("  ", m, e)


if __name__ == "__main__":
    main()
