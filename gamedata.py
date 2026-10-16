"""WolfTeam game database (wt_attributes/*.dat) readers.

Each reader mirrors the loader in cshell.dll field by field (addresses noted), so
the binary layout is exact; field keys are the offsets the client stores them at
(e.g. 'o490'), plus 'p*' for values kept only in the client's XOR-protected
variables. Human-readable names are added only where established (see NAMES).

Usage: python gamedata.py <wt_attributes dir> <out dir>   -> writes JSON tables
"""
import json
import os
import re
import struct
import sys


# Client data version. The 2016 (Aug) US client grew several records; its cshell.dll is
# packed, so the 2016 differences were found by aligning the files against the 2013 layout.
V = 2013


def _new_u16(s):
    """u16 present only in 2016 data (read via raw() so the 2013/2016 field aligner skips it)."""
    return int.from_bytes(s.raw(2), 'little')


def _new_wstr(s):
    n = int.from_bytes(s.raw(2), 'little')
    return s.raw(n * 2).decode('utf-16-le', errors='replace')


def _new_u32(s):
    return int.from_bytes(s.raw(4), 'little')


class Stream:
    def __init__(self, data):
        self.d = data
        self.p = 0

    def eof(self):
        return self.p >= len(self.d)

    def raw(self, n):
        if self.p + n > len(self.d):
            raise EOFError(f'read {n} at {self.p:#x} past end {len(self.d):#x}')
        v = self.d[self.p:self.p + n]
        self.p += n
        return v

    def u8(self):
        return self.raw(1)[0]

    def i8(self):
        return struct.unpack('<b', self.raw(1))[0]

    def u16(self):
        return struct.unpack('<H', self.raw(2))[0]

    def u32(self):
        return struct.unpack('<I', self.raw(4))[0]

    def f32(self):
        return struct.unpack('<f', self.raw(4))[0]

    def num(self):
        """4 bytes whose type the loader does not reveal: int if it looks like one, else float."""
        b = self.raw(4)
        i = struct.unpack('<i', b)[0]
        if -1_000_000 < i < 1_000_000:
            return i
        f = struct.unpack('<f', b)[0]
        return round(f, 6)

    def wstr(self):
        n = self.u16()
        return self.raw(n * 2).decode('utf-16-le', errors='replace')


# ---------------------------------------------------------------- Human / Wolf vars
# FUN_34144e50: common 38-byte block shared by HumanVars and WolfVars
COMMON = ['flag', 'c0', 'c1', 'c2', 'c3', 'c4', 'c5', 'c6', 'c7', 'c8', 'c9', 'c10', 'c11',
          'c12', 'c13', 'c14', 'c15', 'c16', 'c17']


COMMON_2016 = ['c2016_%d' % i for i in range(7)]   # 14 bytes appended to the common block in 2016


def _common(s):
    v = [s.u8(), s.u16(), s.u16()] + [s.u16() for _ in range(4)] + [s.u16()]
    v += [s.u16() for _ in range(4)] + [s.u16() for _ in range(4)]
    v += [s.u8(), s.u16(), s.u16(), s.u16()]
    if V >= 2016:
        v += [_new_u16(s) for _ in range(7)]
    return v


def read_humanvars(data):  # FUN_34145dd0
    s = Stream(data)
    rows = []
    while not s.eof():
        key = s.u16()
        v = _common(s) + [s.u8(), s.u8(), s.u16()]
        names = ['key'] + COMMON + (COMMON_2016 if V >= 2016 else []) + ['h0', 'h1', 'h2']
        if V >= 2016:
            v += [_new_u16(s) for _ in range(3)]
            names += ['h3', 'h4', 'h5']
        rows.append(dict(zip(names, [key] + v)))
    return rows


def read_wolfvars(data):  # FUN_34146210
    s = Stream(data)
    rows = []
    while not s.eof():
        key = s.u16()
        v = _common(s)
        v += [s.u16() for _ in range(4)] + [s.u8(), s.u8(), s.u16(), s.u8(), s.u8(), s.u16(), s.u8(), s.u8()]
        names = ['key'] + COMMON + (COMMON_2016 if V >= 2016 else []) + ['w0', 'w1', 'w2', 'w3', 'w4', 'w5', 'w6', 'w7', 'w8', 'w9', 'w10', 'w11']
        if V >= 2016:
            v.append(_new_u16(s))
            names.append('w12')
        rows.append(dict(zip(names, [key] + v)))
    return rows


# ---------------------------------------------------------------- WeaponData
def _accuracy_block(s):  # FUN_34135440, stored at weapon+0x34
    keys = ['a0', 'o34_00', 'a1', 'a2', 'a3', 'a4', 'o34_c8', 'a5', 'o34_70_u8', 'a6', 'o34_50',
            'a7', 'a8', 'a9', 'a10', 'o34_6c', 'a11', 'a12', 'a13', 'a14', 'a15', 'o34_68_u8',
            'a16', 'a17', 'a18', 'a19', 'a20']
    out = {}
    for k in keys:
        out[k] = s.u8() if k.endswith('_u8') else round(s.f32(), 6)
    return out


def _weapon_mode(s):  # FUN_34069a80, one of the 5 sub-records of a weapon
    r = {}
    r['o490'] = s.u32()
    r['o2cd'] = s.u8()
    r['o2d0'] = s.wstr()
    r['p0'] = s.u16()
    r['p1'] = s.u16()
    r['o40c'] = s.wstr()
    r['o4dc'] = s.u8()
    r['o133'] = s.u8()
    r['skip0'] = s.num()
    r['o72c'] = s.num()
    r['p2'] = s.num()
    r['o34'] = _accuracy_block(s)
    for k in ['o2c0', 'o0', 'o4e4', 'o2cc', 'o4cc', 'o378', 'o398', 'o4f4']:
        r[k] = s.u8()
    r['o70c'] = s.u16()
    r['o470'] = s.wstr()
    r['o45c'] = s.num()
    r['o47c'] = s.wstr()
    r['o474'] = s.num()
    r['o444'] = s.u16()
    for k in ['o44c', 'o464', 'o448', 'o428']:
        r[k] = s.num()
    r['o460'] = s.u8()
    r['o450'] = s.u8()
    r['o42c'] = s.num()
    r['p3'] = s.u8()
    r['p4'] = s.u16()
    if r['o490'] in (0, 1, 2, 3, 6):
        r['p5'] = s.u16()
        r['p6'] = s.u16()
        r['o47a'] = s.u16()
    r['o768'] = s.u8()
    r['o110'] = s.u8()
    r['o132'] = s.u8()
    r['o486'] = [s.num() for _ in range(4)]
    r['o114'] = [s.num() for _ in range(5)]
    r['o4e0'] = s.i8()
    r['o4fc'] = [s.u8() for _ in range(3)]
    for k in ['o3fc', 'o708', 'o10', 'o504']:
        r[k] = s.u8()
    for k in ['o14', 'o100', 'o104', 'o108', 'o4', 'o8', 'oc', 'o4e8', 'o4ec', 'o4f0']:
        r[k] = s.num()
    for k in ['o2c4', 'o2c8', 'o3f8', 'o4d8', 'o500', 'o3a4']:
        r[k] = s.wstr()
    if V >= 2016:
        r['o3a4_hh'] = _new_wstr(s)   # 2016: third-person side FX next to o3a4 (pv side FX)
    r['o1'] = s.u8()
    r['o580'] = [s.wstr() for _ in range(8)]
    r['o660'] = [s.wstr() for _ in range(6)]
    r['o138'] = [s.wstr() for _ in range(8)]
    r['o218'] = [s.wstr() for _ in range(6)]
    r['o12c'] = [round(s.f32(), 4) for _ in range(3)]
    r['o404'] = [round(s.f32(), 4) for _ in range(3)]
    for k in ['o710', 'o730', 'o4b0', 'o18', 'o37c']:
        r[k] = s.wstr()
    r['o400'] = s.num()
    r['o72e'] = s.u16()
    r['o524'] = [s.wstr() for _ in range(3)]
    r['o4f8'] = s.num()
    r['o494'] = s.wstr()
    r['o134'] = s.num()
    r['o2ec'] = [s.wstr() for _ in range(5)]
    r['o128'] = s.num()
    return r


def read_weapondata(data):  # FUN_340733e0 -> FUN_3406dd60 -> FUN_34069a80
    s = Stream(data)
    weapons = []
    while not s.eof():
        w = {'id': s.u32(), 'h_u16': s.u32() if V >= 2016 else s.u16(), 'h_u8': s.u8(), 'modes': []}
        for i in range(5):
            if i:
                w['modes'].append({'hdr': [s.u32(), s.u32() if V >= 2016 else s.u16(), s.u8()]})
            else:
                w['modes'].append({})
            w['modes'][-1].update(_weapon_mode(s))
        weapons.append(w)
    return weapons


def read_upgradedata(data):  # FUN_34075280: u32 id + weapon mode record (deltas)
    s = Stream(data)
    out = {}
    while not s.eof():
        i = s.u32()
        out[i] = _weapon_mode(s)
    return out


def read_text_table(data, nstr):  # weaponText (FUN_34072330), upgradeText (FUN_34071ce0)
    s = Stream(data)
    out = {}
    while not s.eof():
        i = s.u16()
        out[i] = [s.wstr() for _ in range(nstr)]
    return out


# Field meanings. confidence: 'confirmed' = matched against upgrade descriptions
# (upgradetext.dat states which stats each upgrade changes, upgradedata.dat holds
# the deltas, FUN_34135f60 adds them onto the weapon); 'statistical' = fits the
# per-class distribution (snipers / rifles / pistols / melee) but not yet traced in code.
NAMES = {
    'p0': ('weapon_points', 'confirmed', 'every upgrade has it; text "WP %d (+)"'),
    'p2': ('fire_interval_ms', 'statistical', 'autos 95-110 (~600 rpm), pump SUPAS 1200, bolt EM-40 1750, grenade 5000; most "Cyclic Rate (+)" upgrades lower it; outlier MSD-90 4000'),
    'p3': ('weight', 'confirmed', '"Weight (+)" +2/+3, "Weight (-)" -2'),
    'p4': ('reload_ms', 'statistical', 'rifle 3000, pistol 3300, sniper 2800'),
    'p5': ('clip_size', 'statistical', 'pistol 25, rifle 30, sniper 10, melee 1'),
    'p6': ('spare_clips', 'statistical', 'mostly 3, sniper 2'),
    'o45c': ('damage', 'statistical', 'pistol 48, rifle 60, sniper 210; damage-trading upgrades lower it'),
    'o444': ('move_speed', 'statistical', 'bolt sniper 130, shotgun 180-200, pistol 220-250, rifle 250-280, melee 100; outlier MSD-90 480'),
    'o448': ('penetration', 'confirmed', '"Penetration (+)" +30/+50, silencer "(-)" -20'),
    'o400': ('loudness', 'confirmed', 'silencers "Loudness (-)" -3000/-2300'),
    'o450': ('wolf_stun', 'confirmed', '"Wolf Stun (+)" +3..+5, "(-)" -2'),
    'o460': ('stopping_power', 'confirmed', '"Stopping Power (+)" +2..+4'),
    # recoil percentages (cshell kick FUN_340a88f0 / recovery FUN_340a9910 read them from the player's weapon copy)
    'o2c0': ('recoil_view_pct', 'confirmed', 'kick: share of the current recoil that lifts the view (M4 95, MP5 90)'),
    'o0': ('recoil_side_view_pct', 'confirmed', 'kick: share of the side kick applied to the view yaw'),
    'o4e4': ('recoil_recover_pct', 'confirmed', 'recovery: share of the vertical recovery that also lowers the recoil value'),
    'o2cc': ('recoil_side_recover_pct', 'confirmed', 'recovery: share of the side recovery (internal accumulator only)'),
    'o768': ('burst_limit', 'statistical', '255 for automatics, 10 sniper, 1 melee'),
    'o504': ('pellets', 'confirmed', '2016 object.lto FUN_6cf90e80: rays per shot = byte [weapon+0x3c9] (2013 +0x504); rifles 1, shotguns 6-8'),
    'o2c8': ('ammo_type', 'confirmed', 'strings like "5.56*45mm"'),
    'o2d0': ('mode_name', 'confirmed', 'e.g. "normal"'),
    'o40c': ('icon', 'confirmed', 'WT_Interface\\item\\*.dtx'),
    'o580': ('pv_model_and_skins', 'confirmed', '[first-person model, skins in LTB texture order]'),
    'o660': ('pv_render_styles', 'confirmed', 'WT_RS\\*.ltb per piece'),
    'o138': ('ui_model_and_skins', 'confirmed', 'WT_Guns\\Models_UI\\*'),
    'o218': ('ui_render_styles', 'confirmed', 'WT_RS\\*.ltb'),
    'o730': ('hh_model', 'confirmed', 'third-person (hand held) model'),
    'o4b0': ('hh_skin', 'confirmed', 'third-person skin'),
    'o710': ('pv_muzzle_fx', 'confirmed', ''),
    'o18': ('hh_muzzle_fx', 'confirmed', ''),
    'o37c': ('fire_sound', 'confirmed', ''),
    'o494': ('select_sound', 'confirmed', ''),
    'o470': ('projectile_type', 'confirmed', 'e.g. "Bullet"'),
    'o4d8': ('impact_fx', 'confirmed', 'e.g. "UWBullet"'),
    'o500': ('bullet_fx', 'confirmed', 'e.g. "BulletFmj"'),
    'o490': ('weapon_class', 'statistical', '6 every knife, 2 explosive grenades (MK-5G, stick), 3 smoke / mass grenades'),
    'o474': ('explosion_damage', 'statistical', 'grenades only: MK-5G 210, stick 230, mass 40, smoke 0'),
    'o428': ('explosion_radius', 'guess', 'MK-5G / stick 250, mass 100; 250 on knives too (meaning there unknown)'),
    'o134': ('quick_interval_ms', 'guess', 'knives 500 (quick slash; p2 1334 = strong stab), grenades 800'),
}
# accuracy block (FUN_34135440 offsets in brackets). Recoil: cshell kick FUN_340a88f0, recovery FUN_340a9910;
# spread: per shot FUN_34124a60, per frame FUN_341fd820, crosshair FUN_34121b40. Degrees, degrees per second;
# spread is a side offset at effective_range distance (crosshair point = forward * a19 + right * spread).
# The _2 set replaces the first once recoil_phase2_shots (spread_phase2_shots) shots were fired in a row.
ACCURACY_NAMES = {
    'a0': ('recoil_base', 'confirmed', '[0x24] kick: the recoil value is raised to at least this before adding'),
    'o34_00': ('recoil_chance', 'confirmed', '[0x00] kick: % chance that the shot adds recoil (MP5 70)'),
    'a1': ('recoil_add_min', 'confirmed', '[0x84] kick: random add min (degrees)'),
    'a2': ('recoil_vertical', 'confirmed', '[0xc0] kick: random add max, raised to recoil_add_min; "Recoil Control (+)" lowers it'),
    'a3': ('recoil_recovery', 'confirmed', '[0x14] recovery: degrees per second; flash hider "Vertical Recoil Recovery (+)" raises it'),
    'a4': ('recoil_side', 'confirmed', '[0x40] kick: side kick centre (degrees, random sign)'),
    'o34_c8': ('recoil_side_rand', 'confirmed', '[0xc8] kick: side kick +- range (0 when the chance roll failed)'),
    'a5': ('recoil_side_recovery', 'confirmed', '[0x58] recovery: side degrees per second'),
    'o34_70_u8': ('recoil_phase2_shots', 'confirmed', '[0x70] shots in a row before the _2 recoil set (0 = never)'),
    'a6': ('recoil_base_2', 'confirmed', '[0x48]'),
    'o34_50': ('recoil_chance_2', 'confirmed', '[0x50]'),
    'a7': ('recoil_add_min_2', 'confirmed', '[0x38]'),
    'a8': ('recoil_vertical_2', 'confirmed', '[0xa8] raised to recoil_add_min_2'),
    'a9': ('recoil_recovery_2', 'confirmed', '[0x0c]'),
    'a10': ('recoil_side_2', 'confirmed', '[0x7c]'),
    'o34_6c': ('recoil_side_rand_2', 'confirmed', '[0x6c]'),
    'a11': ('recoil_side_recovery_2', 'confirmed', '[0x8c]'),
    'a12': ('recoil_max', 'confirmed', '[0x74] kick: the pending view climb is capped at this (degrees)'),
    'a13': ('base_inaccuracy', 'confirmed', '[0x2c] spread minimum; "Accuracy (+)" lowers it; unscoped sniper 1000'),
    'a14': ('spread_per_shot', 'confirmed', '[0x9c] spread added per shot'),
    'a15': ('spread_recovery', 'confirmed', '[0x60] spread lost per second'),
    'o34_68_u8': ('spread_phase2_shots', 'confirmed', '[0x68] shots in a row before the _2 spread values (0 = never)'),
    'a16': ('spread_per_shot_2', 'confirmed', '[0xb8]'),
    'a17': ('spread_recovery_2', 'confirmed', '[0x94]'),
    'a18': ('crosshair_max', 'confirmed', '[0x1c] spread maximum = base_inaccuracy + this; "Focus (+)" lowers it'),
    'a19': ('effective_range', 'confirmed', '[0x04] "Effective Range (+)" +100; also the spread distance'),
    'a20': ('effective_range_2', 'confirmed', '[0xb0] changes together with a19'),
}


def named_weapons(weapons, texts):
    """Compact per-weapon table with named fields for the web client."""
    out = []
    for w in weapons:
        modes = []
        for m in w['modes']:
            nm = {name: m[k] for k, (name, _, _) in NAMES.items() if k in m}
            nm['accuracy'] = {ACCURACY_NAMES.get(k, (k,))[0]: v for k, v in m['o34'].items()}
            nm['raw'] = {k: v for k, v in m.items() if k not in NAMES and k != 'o34'}
            modes.append(nm)
        t = texts.get(w['id'])
        out.append({'id': w['id'], 'name': t[0] if t else None, 'modes': modes})
    return out


def fill_names(named, catalog_path):
    """2016 weapontext.dat was not updated (527 of 824 weapons have no text): take the shop name of the same code
    (client/ui/catalog.json, built by build_catalog.py from shopdata / exitemtext / forge.dat)."""
    if not os.path.isfile(catalog_path):
        print('fill_names: no catalog.json, skipped')
        return
    items = json.load(open(catalog_path, encoding='utf-8')).get('items', {})
    n = 0
    for w in named:
        if not w['name'] and (items.get(str(w['id'])) or {}).get('name'):
            w['name'] = items[str(w['id'])]['name']
            n += 1
    print(f'fill_names: {n} names from the catalog')


def fix_auto_snipers(named, pv_keys_path):
    """Self-loading snipers (ETSR-1, MSD-90, ESL-8 families: no bolt key in the PV Fire clip, 0.13-0.2 s Fire
    animation, 10-20 round clips) carry p2 = 3000-4000, ten times a believable cycle (SVDR 420, PSZ-1 290);
    read as ms they fired once every 4 s. Divide by 10. Bolt-action ones (DefaultMode / WeaponMode keys) keep theirs."""
    if not os.path.isfile(pv_keys_path):
        print('fix_auto_snipers: no pv_keys.json, skipped')
        return
    with open(pv_keys_path, encoding='utf-8') as f:
        keys = json.load(f)
    fixed = []
    for w in named:
        m = w['modes'][0]
        if not 6000 <= w['id'] < 7000 or (m.get('fire_interval_ms') or 0) < 2500:
            continue
        ltb = str((m.get('pv_model_and_skins') or [''])[0]).replace('\\', '/').split('/')[-1].lower()
        fire = next((v for k, v in keys.get(ltb, {}).items() if k.lower() == 'fire'), [])
        if any(re.search(r'defaultmode|weaponmode', str(c), re.I) for _, c in fire):
            continue
        m['fire_interval_ms'] = round(m['fire_interval_ms'] / 10)
        fixed.append(w['id'])
    print(f'fix_auto_snipers: {len(fixed)} self-loading snipers, fire interval / 10')


READERS = {
    'humanvars.dat': read_humanvars,
    'wolfvars.dat': read_wolfvars,
    'weapondata.dat': read_weapondata,
}


def detect_version(src):
    """2016 weapondata widened the weapon header u16 (0xffff) to u32 (0xffffffff)."""
    with open(os.path.join(src, 'weapondata.dat'), 'rb') as f:
        head = f.read(8)
    return 2016 if head[4:8] == bytes([0xff] * 4) else 2013


def main(src, dst):
    global V
    V = detect_version(src)
    print('data version', V)
    os.makedirs(dst, exist_ok=True)
    for name, fn in READERS.items():
        with open(os.path.join(src, name), 'rb') as f:
            rows = fn(f.read())
        out = os.path.join(dst, os.path.splitext(name)[0] + '.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
        print(f'{name}: {len(rows)} records -> {out}')

    def load(name, fn):
        with open(os.path.join(src, name), 'rb') as f:
            return fn(f.read())

    def dump(name, obj):
        with open(os.path.join(dst, name), 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)

    weapons = load('weapondata.dat', read_weapondata)
    wtext = load('weapontext.dat', lambda d: read_text_table(d, 5))
    utext = load('upgradetext.dat', lambda d: read_text_table(d, 4))
    upgrades = load('upgradedata.dat', read_upgradedata)
    dump('weapontext.json', {str(k): v for k, v in wtext.items()})
    dump('upgradetext.json', {str(k): v for k, v in utext.items()})
    dump('upgradedata.json', {str(k): v for k, v in upgrades.items()})
    named = named_weapons(weapons, wtext)
    fill_names(named, os.path.join(dst, '..', '..', 'client', 'ui', 'catalog.json'))
    fix_auto_snipers(named, os.path.join(dst, 'pv_keys.json'))
    dump('weapons.json', named)
    # slim copy for the web client: named fields of the first (default) mode only
    slim = []
    for w in named:
        m = w['modes'][0]
        raw = m['raw']
        slim.append({'id': w['id'], 'name': w['name'], **{k: v for k, v in m.items() if k != 'raw'},
                     # unconfirmed vectors, kept for tuning the first-person view
                     'raw_view_offset': [raw['o100'], raw['o104'], raw['o108']],
                     'raw_o12c': raw['o12c'], 'raw_o404': raw['o404'],
                     # o524: the reload sounds, in the order the reload plays them (mag out / in / bolt)
                     'reload_sounds': [s for s in raw.get('o524', []) if s],
                     'raw_o42c': raw.get('o42c', 0),
                     # modes 1-4 carry only accuracy deltas, ADDED to mode 0 by stance (cshell FUN_3411be70 picks the
                     # stance, FUN_341365d0 copies mode 0 and adds): crouching (held 0.5 s) = mode 0 alone,
                     # 1 standing still, 2 walking, 3 running, 4 in the air. Non-zero fields only.
                     'stance_accuracy': [{k: v for k, v in (sm.get('accuracy') or {}).items() if v}
                                         for sm in w['modes'][1:5]]})
    with open(os.path.join(dst, 'weapons_min.json'), 'w', encoding='utf-8') as f:
        json.dump(slim, f, ensure_ascii=False, separators=(',', ':'))
    dump('field_names.json', {'weapon': {k: {'name': n, 'confidence': c, 'evidence': e} for k, (n, c, e) in NAMES.items()},
                              'accuracy': {k: {'name': n, 'confidence': c, 'evidence': e} for k, (n, c, e) in ACCURACY_NAMES.items()}})
    print(f'weapons.json: {len(weapons)} weapons, {len(upgrades)} upgrades, {len(NAMES) + len(ACCURACY_NAMES)} named fields')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main(sys.argv[1], sys.argv[2])
