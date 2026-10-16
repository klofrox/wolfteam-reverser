"""Convert the game-mode props to assets/models/props/*.glb (with their skins embedded).

  battlestation_body / _siren   Conquest stations (WBattleStation Filename), siren tinted by owner in the client
  mainarea                      Destruction bomb site (WBombArea Filename): light ray + base plate
  groundtimebomb                planted C4 (T_BOMB blink animation)
  ctfflag_0 / ctfflag_1         CTF flags (ctfflag.ltb with skins ctfflag0 / ctfflag1)

  python tools/convert_props.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ltb  # noqa: E402
import ltb2gltf  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "assets", "models", "props")
TEX = os.path.join(ROOT, "assets", "textures")

JOBS = [
    ("battlestation_body", "wt_props/models/battlestation_body.ltb", ["wt_props/skins/battlestation.png"]),
    ("battlestation_siren", "wt_props/models/battlestation_siren.ltb", ["wt_props/skins/battlestation_siren.png"]),
    ("mainarea", "wt_models/bombarea/mainarea.ltb", ["wt_models/bombarea/a-ray01.png", "wt_models/bombarea/abase512.png"]),
    ("groundtimebomb", "wt_props/models/groundtimebomb.ltb",
     ["wt_guns/skins_pv/wt_pv_timebomb.png", "wt_fx/tbomblight/timebomb_lm/wt_pv_timebomb_lm01.png"]
     + ["wt_guns/skins_pv/wt_pv_timebomb.png"] * 3),
    ("ctfflag_0", "wt_props/models/ctfflag.ltb", ["wt_props/skins/ctfflag0.png"]),
    ("ctfflag_1", "wt_props/models/ctfflag.ltb", ["wt_props/skins/ctfflag1.png"]),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, src, skins in JOBS:
        with open(os.path.join(ROOT, "extracted", src), "rb") as f:
            model = ltb.parse(f.read())
        paths = [os.path.join(TEX, s) for s in skins]
        missing = [s for s, p in zip(skins, paths) if not os.path.exists(p)]
        g = ltb2gltf.build(model, os.path.join(OUT, name + ".glb"), (), paths, 0.01, name, None)
        print(f"{name}: {len(g.j.get('meshes', []))} meshes, {len(g.j.get('animations', []))} anims"
              + (f", missing skins {missing}" if missing else ""))


if __name__ == "__main__":
    main()
