"""Wolf attack timings per type from the third-person models' keyframe commands -> client/ui/wolfkeys.json.

Every wolf clip carries "FIRE_KEY <weapon id>" at the hit moment (a bare FIRE_KEY = the type's own attack of that
slot). Basic = wt_new_wolf_ch.ltb, mutants = wt_wolf_<type>_ch.ltb (extracted_2013). Per type and clip:
{"ms": length, "hits": [[ms, weapon id or null], ...]}. Used by client/js/wolf.js (WolfClaws.setTimings).

Run from webport/: python tools/build_wolfkeys.py
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ltb  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = os.path.join(ROOT, 'extracted_2013', 'wt_chars', 'models')
TYPES = {'basic': 'wt_new_wolf_ch', 'power': 'wt_wolf_power_ch', 'guardian': 'wt_wolf_guardian_ch',
         'ghost': 'wt_wolf_ghost_ch', 'berserker': 'wt_wolf_berserker_ch', 'smart': 'wt_wolf_smart_ch',
         'ghost2': 'wt_wolf_ghost2_ch', 'ice': 'wt_wolf_ice_ch', 'psycho': 'wt_wolf_psycho_ch'}
CLIPS = ['UMFi1', 'UMFi2', 'UMFi3', 'LJA', 'UMJA', 'T_Bodyatk', 'T_BodyatkL', 'T_BodyatkR', 'T_Specialatk', 'T_BITE',
         'T_CRY', 'UMTF', 'UMTR', 'UMTH', 'T_DBM', 'T_Fi1', 'T_WallDash', 'UMTr']
FIRE = re.compile(r'FIRE_KEY\s*(\d*)')


def clips_of(path):
    m = ltb.parse(open(path, 'rb').read())
    out = {}
    lower = {c.lower(): c for c in CLIPS}
    for a in m.anims:
        name = lower.get(a['name'].lower())
        if not name:
            continue
        keys = a['keys']
        hits = []
        for t, cmd in keys:
            for g in FIRE.findall(cmd or ''):
                hits.append([t, int(g) if g else None])
        out[name] = {'ms': keys[-1][0] if keys else 0, 'hits': hits}
    return out


def main():
    data = {}
    for t, f in TYPES.items():
        p = os.path.join(MODELS, f + '.ltb')
        if os.path.exists(p):
            data[t] = clips_of(p)
    dst = os.path.join(ROOT, 'client', 'ui', 'wolfkeys.json')
    with open(dst, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, separators=(',', ':'))
    print(f'{len(data)} types -> {dst}')


if __name__ == '__main__':
    main()
