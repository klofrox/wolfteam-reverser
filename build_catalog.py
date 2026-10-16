"""Build the item catalog the web lobby, inventory and shop use.

Sources (all from the shipped client):
  wt_attributes/weapondata.dat  -> weapon icon (o40c)          via assets/data/weapondata.json
  wt_attributes/weapontext.dat  -> weapon name / description    via assets/data/weapontext.json
  wt_attributes/exitemdata.dat  -> item code + icon (u32 code at record start, icon wstr at +55 (regex match starts 2 bytes later))
  wt_attributes/exitemtext.dat  -> u16 code, wstr name, wstr desc, wstr desc2
  wt_attributes/shopdata.dat    -> 350-byte (2016: 354) records: u32 index, u32 code, u8 flags...,
                                   price tables (see PRICE_SLOTS; partly decoded)
  wt_attributes/setitemdata.dat -> packages: 140-byte records, u32 code + 17 x (u32 item, u32 days) -> "contents"
  extracted_tr (Joygame TR 2016) -> Turkish names / texts, the TR set table, TR-only items (TR_ITEMS)

Output: client/ui/catalog.json  {items: {code: {...}}, starter: [...]}
"""
import json
import os
import re
import struct
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
import item_effects  # noqa: E402  (webport/item_effects.py: effect patterns)
ATTR = os.path.join(ROOT, "extracted", "wt_attributes")
TEX = os.path.join(ROOT, "assets", "textures", "wt_interface")

# shopdata price slots. Gold table at +90/+94/+98 and AP table at +290/+294/+298 hold
# 1 / 7 / 30 day prices (e.g. EM-92 FS 500/2500/10000 G, 50/180/500 AP). Records whose
# flag byte (+8) is 4 have a third table at +234/+238/+242 with the same 1:5:20 ratio but
# ~50x smaller numbers (C-95 120/600/2400) - taken to be Wolf Coin (WC) prices.
GOLD = [(90, 1), (94, 7), (98, 30)]
WC = [(234, 1), (238, 7), (242, 30)]
AP = [(290, 1), (294, 7), (298, 30)]


def icon_path(dtx):
    """'WT_Interface\\Item\\C-95 BASE.dtx' -> 'item/c-95 base.png' if the PNG exists."""
    if not dtx:
        return None
    rel = re.sub(r"(?i)^wt_interface[\\/]+", "", dtx.strip()).replace("\\", "/")
    rel = os.path.splitext(rel)[0].lower() + ".png"
    return rel if os.path.isfile(os.path.join(TEX, rel)) else None


def wstr(b, p):
    n = struct.unpack_from("<H", b, p)[0]
    return b[p + 2:p + 2 + n * 2].decode("utf-16-le", errors="replace"), p + 2 + n * 2


def read_exitemtext(attr=None):
    b = open(os.path.join(attr or ATTR, "exitemtext.dat"), "rb").read()
    out, p = {}, 0
    while p + 2 <= len(b):
        code = struct.unpack_from("<H", b, p)[0]
        name, p = wstr(b, p + 2)
        desc, p = wstr(b, p)
        _, p = wstr(b, p)
        out[code] = (name.strip(), desc.strip())
    return out


def read_exitemdata():
    return read_exitemdata_at(ATTR)


def read_exitemdata_at(attr):
    b = open(os.path.join(attr, "exitemdata.dat"), "rb").read()
    out = {}
    for m in re.finditer(rb"(?:[\x20-\x7e]\x00){8,}", b):
        s = m.group().decode("utf-16-le")[1:]
        if "item" not in s.lower() or "\\large\\" in s.lower():
            continue
        code = struct.unpack_from("<I", b, m.start() - 57)[0]
        out.setdefault(code, s)
    return out


def read_shop():
    return read_shop_at(ATTR)


def read_shop_at(attr):
    b = open(os.path.join(attr, "shopdata.dat"), "rb").read()
    # 2013: 350-byte records; 2016 appends a u32 (record 2 then starts at 354)
    size = 354 if b[354:358] == struct.pack("<I", 2) else 350
    out = {}
    for k in range(len(b) // size):
        r = b[k * size:(k + 1) * size]
        code = struct.unpack_from("<I", r, 4)[0]
        u = lambda o: struct.unpack_from("<I", r, o)[0]
        gold = [{"days": d, "price": u(o)} for o, d in GOLD if u(o)]
        wc = [{"days": d, "price": u(o)} for o, d in WC if u(o)]
        ap = [{"days": d, "price": u(o)} for o, d in AP if u(o)]
        if gold or ap or wc:
            out[code] = {"gold": gold, "wc": wc, "ap": ap}
    return out


def read_setitems(attr=None):
    """setitemdata.dat: package code -> [[item, days], ...] (the shop gives the contents, not the package)"""
    b = open(os.path.join(attr or ATTR, "setitemdata.dat"), "rb").read()
    out = {}
    for o in range(0, len(b) - 139, 140):
        code = struct.unpack_from("<I", b, o)[0]
        its = [list(struct.unpack_from("<II", b, o + 4 + 8 * i)) for i in range(17)]
        its = [x for x in its if x[0]]
        if its:
            out[code] = its
    return out


# TR-only items worth adding (the TR codes of DO parts, Ceyda / Esra are copies of US items already in the list).
# 14516 "Character Pack (Celebrity)" has no set record even in TR: Ceyda + Esra (US 30216 / 30217) is our filling.
TR_ITEMS = {14516: {"name": "Karakter Paketi (Ünlü)", "desc": "Ceyda Ersoy ve Esra Ersoy karakterleri (30 gün).",
                    "contents": [[30216, 30], [30217, 30]]}}
# Turkish words for part / package names the TR text file lacks (US-only items), as the TR items name them
TR_WORDS = [(r"\bSpecial Parts Package\b", "Özel Parça Paketi"), (r"\bCharacter Pack\b", "Karakter Paketi"),
            (r"\bElbow ?Protector\b", "Dirseklik"), (r"\bKnee ?Protector\b", "Dizlik"), (r"\bHelmet\b", "Miğfer"),
            (r"\bHat\b", "Şapka"), (r"\bGoggles?\b", "Gözlük"), (r"\bMask\b", "Maske"), (r"\bVest\b", "Yelek"),
            (r"\bGloves?\b", "Eldiven"), (r"\bBoots\b", "Bot"), (r"\bHair\b", "Saç"), (r"\bChoker\b", "Gerdanlık"),
            (r"\bLook Package\b", "Görünüş Paketi"), (r"\bWolf\b", "Kurt"), (r"\(Summer\)", "(Yaz)")]


def turkish_name(name):
    for pat, tr in TR_WORDS:
        name = re.sub(pat, tr, name, flags=re.I)
    return name


def read_forge_names():
    """forge.dat: ... u32 code, wstr name, wstr icon ... - the only place the 2016 client
    ships names for weapons added after 2013 (weapontext.dat / exitemtext.dat were not updated)."""
    b = open(os.path.join(ATTR, "forge.dat"), "rb").read()
    out = {}
    for m in re.finditer(rb"(?:[\x20-\x7e]\x00){2,}", b):
        st = m.start() - 2
        if st < 4:
            continue
        n = struct.unpack_from("<H", b, st)[0]
        end = st + 2 + n * 2
        if n < 2 or end + 2 > len(b) or end > m.end() + 2:
            continue
        name = b[st + 2:end].decode("utf-16-le", errors="replace")
        n2 = struct.unpack_from("<H", b, end)[0]
        icon = b[end + 2:end + 2 + n2 * 2].decode("utf-16-le", errors="replace")
        if "interface" in icon.lower() and "\\" not in name:
            out.setdefault(struct.unpack_from("<I", b, st - 4)[0], name.strip())
    return out


def name_from_icon(dtx):
    base = os.path.splitext(dtx.replace("\\", "/").split("/")[-1])[0]
    return re.sub(r"[_]+", " ", base).strip().upper() if base else ""


BONUS_PCT = re.compile(r"(\d+)\s*%\s*(?:more\s+|additional\s+|extra\s+)?"
                       r"(gp\s*(?:and|&|\+)\s*gold|gold\s*(?:and|&|\+)\s*gp|gp|gold|exp)", re.I)
BONUS_PLUS = re.compile(r"\b(gp|gold|exp)\s*\+\s*(\d+)\s*%", re.I)


def reward_bonus(name, desc):
    """GP / Gold reward bonus stated in an item's text ("Gain 30% GP", "GP +20%")."""
    t = f"{name} {desc}".replace("\n", " ")
    gp = gold = 0
    for m in BONUS_PCT.finditer(t):
        v, k = int(m.group(1)), m.group(2).lower()
        if "gp" in k or "exp" in k:
            gp = max(gp, v)
        if "gold" in k:
            gold = max(gold, v)
    for m in BONUS_PLUS.finditer(t):
        v, k = int(m.group(2)), m.group(1).lower()
        if k == "gold":
            gold = max(gold, v)
        else:
            gp = max(gp, v)
    return {"gp": gp, "gold": gold} if gp or gold else None


def weapon_slot(code):
    t = code // 1000
    return {1: "secondary", 2: "knife", 9: "grenade"}.get(t, "primary" if 3 <= t <= 8 else None)


# Wolf kings of the Wolfhunt mode (Asmon "Sadece Kurt Avında geçerlidir", Leviathan): EX codes (100xx) whose icon
# sits in the power folder; they listed under GÜÇ+ > Vb and could be worn next to the wolf types
WOLFHUNT_KINGS = {10083, 10084}


def power_sub(icon):
    i = icon.lower()
    if "backpack" in i or "bag" in i:
        return "bag"
    if "tattoo" in i or "tatoo" in i:
        return "tattoo"
    if "scratch" in i:
        return "scratch"
    return "etc"


def main():
    wdata = {w["id"]: w for w in json.load(open(os.path.join(ROOT, "assets", "data", "weapondata.json"), encoding="utf-8"))}
    wtext = {int(k): v for k, v in json.load(open(os.path.join(ROOT, "assets", "data", "weapontext.json"), encoding="utf-8")).items()}
    etext = read_exitemtext()
    edata = read_exitemdata()
    shop = read_shop()

    forge = read_forge_names()
    wstats = {w["id"]: w for w in json.load(open(os.path.join(ROOT, "assets", "data", "weapons_min.json"), encoding="utf-8"))}

    items = {}
    for code, w in wdata.items():
        slot = weapon_slot(code)
        text = wtext.get(code)
        if not slot or (text and not text[4].strip()):
            continue  # internal / strong-attack / dummy entries
        dtx = w["modes"][0].get("o40c", "")
        name = (text[0].strip() if text else "") or forge.get(code) or name_from_icon(dtx)
        if not name or (not text and code not in forge and code not in shop):
            continue
        st = wstats.get(code, {})
        items[code] = {
            "id": code, "name": name, "cat": "weapon", "sub": slot, "icon": icon_path(dtx),
            "desc": text[1].strip() if text else "",
            "weight": text[2] if text else f"{st.get('weight', 0) / 10:g} Kg",
            "ammo": text[3] if text else f"{st.get('clip_size', 0)} rounds x {st.get('spare_clips', 0)}",
            "class": text[4].strip() if text else {"primary": "Primary", "secondary": "Secondary", "knife": "Knife", "grenade": "Hand Grenade"}[slot],
        }
    for code, dtx in edata.items():
        name, desc = etext.get(code, ("", ""))
        name = name or forge.get(code, "")
        if not name and code in shop:
            name = name_from_icon(dtx)
        if not name:
            continue
        icon = icon_path(dtx)
        folder = dtx.lower().split("\\")[2] if dtx.count("\\") >= 3 else ""
        cat = {"character": "char", "power": "power"}.get(folder, "ex")
        if code in WOLFHUNT_KINGS:   # icon in the power folder, but an EX code: not a GÜÇ+ item to wear
            cat = "ex"
        items[code] = {
            "id": code, "name": name, "cat": cat, "sub": power_sub(dtx) if cat == "power" else cat,
            "icon": icon, "desc": desc,
        }
    for it in items.values():
        if it["cat"] != "weapon":
            b = reward_bonus(it["name"], it.get("desc", ""))
            if b:
                it["bonus"] = b
            # worn effects (armor, HP, speed, WP...) are read from the English text too: item_effects.py's
            # patterns are English and the Turkish text below replaces desc
            fx = item_effects.parse(it.get("desc", ""))
            if fx:
                it["fx"] = fx
            if item_effects.ACTIVE.search(it["name"]):
                it["active"] = True   # used up in a match (Steam Pack, Medical Kit, Skill Up), not worn
    # Turkish names / descriptions from the TR 2016 client (Joygame) once the bonuses are read from the English text
    tr_attr = os.path.join(ROOT, "extracted_tr", "wt_attributes")
    has_tr = os.path.isfile(os.path.join(tr_attr, "exitemtext.dat"))
    tr_named = set()
    if has_tr:
        for code, (name, desc) in read_exitemtext(tr_attr).items():
            it = items.get(code)
            if it and it["cat"] != "weapon":
                if name:
                    it["name"] = name
                    tr_named.add(code)
                if desc:
                    it["desc"] = desc
    for code, it in items.items():
        if code not in tr_named and (it["cat"] == "char" or re.search(r"\bPack(age)?\b", it["name"])):
            it["name"] = turkish_name(it["name"])
    # packages: the TR set table (TR shop), the US one for codes TR lacks
    sets = read_setitems()
    if has_tr:
        sets.update(read_setitems(tr_attr))
    if has_tr:
        tr_data = read_exitemdata_at(tr_attr)
        tr_shop = read_shop_at(tr_attr)
        shop.update(tr_shop)   # TR shop prices (447 differ from US; the 60 items TR does not sell keep US prices)
        for code, extra in TR_ITEMS.items():
            dtx = tr_data.get(code, "")
            items[code] = {"id": code, "name": extra["name"], "cat": "ex", "sub": "ex", "icon": icon_path(dtx),
                           "desc": extra["desc"], "tr": True}
            if code in tr_shop:
                shop[code] = tr_shop[code]
            sets.setdefault(code, extra["contents"])
    for code, its in sets.items():
        if code in items:
            items[code]["contents"] = [x for x in its if x[0] in items]
    sold = 0
    for code, it in items.items():
        if code in shop:
            it["price"] = shop[code]
            sold += 1
    starter = [c for c in (3001, 1001, 2001, 9001) if c in items]   # equipped part of server.py STARTER (2016 TR new account)
    out = {"items": {str(k): v for k, v in sorted(items.items())}, "starter": starter}
    dst = os.path.join(ROOT, "client", "ui", "catalog.json")
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    by = {}
    for it in items.values():
        by[it["cat"]] = by.get(it["cat"], 0) + 1
    print("items", len(items), by, "priced", sold, "no icon", sum(1 for i in items.values() if not i["icon"]), "starter", starter)


if __name__ == "__main__":
    main()
