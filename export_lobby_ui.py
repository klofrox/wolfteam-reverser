"""Export the original lobby / battle-room / make-room textures and a map list
the web client can draw at the coordinates in attributes/section/*.txt.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dtx import decode

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_US = os.path.join(ROOT, "extracted", "wt_interface")
SRC_TR = os.path.join(ROOT, "extracted_tr", "wt_interface")   # Joygame TR 2016: Turkish art / TR map list


def src(*parts):
    """A file of the TR client when it has one, else the US client's."""
    tr = os.path.join(SRC_TR, *parts)
    return tr if os.path.isfile(tr) else os.path.join(SRC_US, *parts)
OUT = os.path.join(ROOT, "client", "ui", "tex")

FILES = [
    "lobby/lb_bg.dtx",
    "lobby/lb_button_make.dtx",
    "lobby/lb_button_quick.dtx",
    "lobby/lb_button_refresh.dtx",
    "lobby/lb_ch_tab.dtx",
    "lobby/lb_chat_tab.dtx",
    "lobby/lb_cate_num.dtx",
    "lobby/lb_cate_status.dtx",
    "lobby/lb_cate_type.dtx",
    "lobby/lb_cate_map.dtx",
    "lobby/lb_room_bar.dtx",
    "lobby/lb_rock.dtx",
    "lobby/lb_chck.dtx",
    "lobby/lb_userinfo_window.dtx",
    "all/a_page.dtx",
    "all/a_close.dtx",
    "all/a_button_ok.dtx",
    "all/a_button_cancel.dtx",
    "all/a_check.dtx",
    "all/a_lb_button_tutorial.dtx",
    "makeroom/mr_bg.dtx",
    "makeroom/mr_class_l_limit_0.dtx",
    "makeroom/mr_class_l_limit_1.dtx",
    "makeroom/mr_class_l_limit_2.dtx",
    "makeroom/mr_class_l_limit_3.dtx",
    "makeroom/mr_class_l_limit_4.dtx",
    "makeroom/mr_class_u_limit_0.dtx",
    "makeroom/mr_class_u_limit_1.dtx",
    "makeroom/mr_class_u_limit_2.dtx",
    "makeroom/mr_class_u_limit_3.dtx",
    "makeroom/mr_class_u_limit_4.dtx",
    "combobox/mr_combobg_01.dtx",
    "combobox/mr_combobg_02.dtx",
    "combobox/mr_combobg_03.dtx",
    "combobox/cb_button_down.dtx",
    "combobox/mr_button_down.dtx",
    "combobox/mr_popup.dtx",
    "battleroom/br_bg.dtx",
    "battleroom/br_button_gamestart.dtx",
    "battleroom/br_button_gameready.dtx",
    "battleroom/br_button_invite.dtx",
    "battleroom/br_button_team.dtx",
    "battleroom/br_button_setting.dtx",
    "battleroom/br_bar_red.dtx",
    "battleroom/br_bar_blue.dtx",
    "battleroom/br_bar_master_red.dtx",
    "battleroom/br_bar_master_blue.dtx",
    "makeroom/mr_mode_all.dtx",
    "makeroom/mr_mode_h_h.dtx",
    "makeroom/mr_mode_w_w.dtx",
    "makeroom/mr_mode_h_w.dtx",
    "makeroom/mr_mode_g_g.dtx",
    "makeroom/mr_mode_k_k.dtx",
    "makeroom/mr_mode_p_p.dtx",
    "makeroom/mr_mode_s_s.dtx",
    "makeroom/mr_mode_hw_hw.dtx",
    "makeroom/mr_mode_wh1.dtx",
    "makeroom/mr_mode_wh2.dtx",
    "makeroom/mr_mode_wh3.dtx",
    "makeroom/mr_mode_all_vs_all.dtx",
    "makeroom/mr_mode__ai_sub__multi.dtx",
    "makeroom/mr_mode__ai_sub__single.dtx",
    "battleroom/br_bar_ready_red.dtx",
    "battleroom/br_bar_ready_blue.dtx",
    "battleroom/br_bar_playing_red.dtx",
    "battleroom/br_bar_playing_blue.dtx",
    "battleroom/observe_icon.dtx",
    "messagebox/mb_popup_bg.dtx",
    "messagebox/mb_popup_InputBack.dtx",
]


def find_dtx(rel):
    direct = src(*rel.split("/"))
    if os.path.isfile(direct):
        return direct
    want = rel.replace("\\", "/").lower()
    for base in (SRC_TR, SRC_US):
        for dirpath, _, names in os.walk(base):
            for name in names:
                full = os.path.join(dirpath, name)
                if os.path.relpath(full, base).replace("\\", "/").lower() == want:
                    return full
    return None


def convert(rel):
    src = find_dtx(rel)
    if not src:
        print("MISSING", rel)
        return False
    with open(src, "rb") as f:
        img, hdr = decode(f.read())
    if img.getchannel("A").getextrema() == (0, 0):   # BGRA art with alpha 0 (combobox fields): the game draws it opaque
        img.putalpha(255)
    dst = os.path.join(OUT, os.path.splitext(rel)[0] + ".png")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    img.save(dst, "PNG", optimize=False)
    print(f"{rel} {hdr['width']}x{hdr['height']}")
    return True


def load_strings():
    path = src("attributes", "stringtable", "stringtable.txt")
    raw = open(path, "rb").read(4)
    enc = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "latin1"
    out = {}
    for line in open(path, encoding=enc):
        m = re.match(r'^(\d+)\t"(.*)"\s*$', line.rstrip("\n"))
        if m:
            out[int(m.group(1))] = m.group(2)
    return out


def asset_png(path):
    """WT_Interface/loading/ld_map_x.dtx -> 'loading/ld_map_x.png' (assets/textures/wt_interface, lower case)."""
    rel = re.sub(r"(?i).*wt_interface[\\/]+", "", path.strip().strip('"')).replace("\\", "/")
    rel = re.sub(r"/+", "/", os.path.splitext(rel)[0] + ".png").lower()
    return rel if os.path.isfile(os.path.join(ROOT, "assets", "textures", "wt_interface", rel)) else None


def nums(text):
    return [float(x.rstrip("f")) for x in re.findall(r"-?\d+(?:\.\d+)?f?", text)]


def load_screens():
    """map/maploadattributes.txt: MapID -> loading screen art (air view, title strip rect)."""
    path = src("attributes", "map", "maploadattributes.txt")
    raw = open(path, "rb").read()
    text = raw.decode("utf-16", errors="replace") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("latin1")
    text = "\n".join(l.split("//")[0] for l in text.splitlines())
    out = {}
    for block in re.findall(r"\[START\](.*?)\[END\]", text, re.S):
        def field(name):
            m = re.search(rf"^\s*{name}\s+(.*)$", block, re.M)
            return m.group(1).strip() if m else ""
        try:
            mid = int(field("MapID"))
        except ValueError:
            continue
        out[mid] = {
            "airView": asset_png(field("MapAirView")) if field("MapAirView") else None,
            "title": asset_png(field("MapNameTexture")) if field("MapNameTexture") else None,
            "titleRect": [int(v) for v in nums(field("MapNameRect"))] or None,
            "miniTitleRect": [int(v) for v in nums(field("MiniMapNameRect"))] or None,   # in play/pl_map_title.dtx
            "bombScreens": [asset_png(m) for m in re.findall(r'^\s*BombScreen\s+"([^"]+)"', block, re.M)],
        }
    return out


def load_maps(strings):
    index = json.load(open(os.path.join(ROOT, "assets", "maps", "maps.json"), encoding="utf-8"))
    by_source = {}
    for entry in index:
        by_source[os.path.basename(entry["source"]).lower()] = entry["name"]
    raw = open(src("attributes", "map", "mapattribute.txt"), "rb").read(4)
    enc = "utf-16" if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff") else "latin1"
    text = open(src("attributes", "map", "mapattribute.txt"), encoding=enc).read()
    blocks = re.findall(r"\[START\](.*?)\[END\]", text, re.S)
    grouped = {}
    screens = load_screens()
    miss_left = [0]
    for block in blocks:
        def field(name):
            m = re.search(rf'^{name}\s+"([^"]*)"', block, re.M)
            if m:
                return m.group(1)
            m = re.search(rf"^{name}\s+(\S+)", block, re.M)
            return m.group(1) if m else ""
        filename = field("MapFileName").strip('"')
        if not filename:
            continue
        base = os.path.basename(filename.replace("\\", "/")).lower()
        folder = by_source.get(base)
        if not folder:
            if miss_left[0] < 5:
                print("NO SOURCE", base)
                miss_left[0] += 1
            continue
        glb = os.path.join(ROOT, "assets", "maps", folder, folder + ".glb")
        if not os.path.isfile(glb):
            if miss_left[0] < 8:
                print("NO GLB", glb)
                miss_left[0] += 1
            continue
        name_id = field("MapName")
        try:
            title = strings.get(int(name_id), folder)
        except ValueError:
            title = folder
        rel = field("MapTexture").replace("\\", "/").strip().strip('"')
        rel = re.sub(r"(?i).*wt_interface/+", "", rel).lstrip("/")
        rel = re.sub(r"/+", "/", rel)
        rec = grouped.setdefault(folder, {"id": folder, "name": title, "texture": None, "modes": []})
        mode = field("MapType")
        if mode and mode not in rec["modes"]:
            rec["modes"].append(mode)
        try:
            mid = int(field("MapIdentity"))
        except ValueError:
            mid = None
        if mid is not None and mid in screens and "loading" not in rec:
            rec["loading"] = screens[mid]
        mini = field("MiniMapTexture")
        if mini and "minimap" not in rec:
            m = re.search(r"^MiniMapRect\s+(.*)$", block, re.M)
            rect = nums(m.group(1).split("//")[0]) if m else []
            if asset_png(mini) and len(rect) == 4:
                rec["minimap"] = {"tex": asset_png(mini), "rect": rect}
        flags = [[int(v) for v in nums(f)] for f in re.findall(r"^FlagPos\s+(.*)$", block, re.M)]
        if flags and mode:
            rec.setdefault("flags", {})[mode] = flags
        if rel.lower().endswith(".dtx"):
            rec["texture"] = os.path.splitext(rel)[0] + ".png"
            rec["_dtx"] = rel
        if mode == "FM_BATTLE":
            rec["name"] = title
    print("blocks", len(blocks), "grouped", len(grouped), "sources", len(by_source))
    maps = []
    for rec in grouped.values():
        dtx = rec.pop("_dtx", None)
        if dtx:
            convert(dtx)
        if rec["name"] == rec["id"] and rec["texture"]:
            # 2016 maps whose MapName id is missing from the string table: name them after the preview art
            base = os.path.splitext(os.path.basename(rec["texture"]))[0]
            base = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", base).replace("_", " ").replace("-", " ")
            rec["name"] = " ".join(w if w.isupper() else w.capitalize() for w in base.split())
        maps.append(rec)
    maps.sort(key=lambda m: m["name"].lower())
    return maps


def main():
    for rel in FILES:
        convert(rel)
    strings = load_strings()
    maps = load_maps(strings)
    titles = [strings[i] for i in range(220, 230) if i in strings]
    payload = {"maps": maps, "roomNames": titles}
    dst = os.path.join(ROOT, "client", "ui", "maps.json")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    json.dump(payload, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("maps", len(maps))


if __name__ == "__main__":
    main()
