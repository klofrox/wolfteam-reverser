"""Animation key strings of the first-person weapon models (LTB keyframe commands) -> assets/data/pv_keys.json.

{ "<pv ltb basename, lower case>": { "<anim>": [[ms, "command"], ...] } }
Commands seen: "sound_key N" (N 1-3 = weapondata o524 reload sounds, 4 = select sound), "fire_key", "SHELL_CASING",
"DefaultMode" / "WeaponMode" (sniper: leave / re-enter the scope around the bolt), piece show / hide keys.
Run: python tools/build_pv_keys.py   (reads extracted/wt_guns/models_pv)
"""
import gzip
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import ltb  # noqa: E402


def main():
    src = os.path.join(ROOT, 'extracted', 'wt_guns', 'models_pv')
    out = {}
    for name in sorted(os.listdir(src)):
        if not name.lower().endswith('.ltb'):
            continue
        try:
            m = ltb.parse(open(os.path.join(src, name), 'rb').read())
        except Exception as e:   # render-style / odd versions: no keys to take
            print('skip', name, e)
            continue
        anims = {a['name']: [[t, s] for t, s in a['keys'] if s] for a in m.anims}
        anims = {k: v for k, v in anims.items() if v}
        if anims:
            out[name.lower()] = anims
    dst = os.path.join(ROOT, 'assets', 'data', 'pv_keys.json')
    data = json.dumps(out, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    open(dst, 'wb').write(data)
    with gzip.open(dst + '.gz', 'wb', 9) as f:
        f.write(data)
    print(f'{len(out)} models -> {dst} ({len(data)} bytes)')


if __name__ == '__main__':
    main()
