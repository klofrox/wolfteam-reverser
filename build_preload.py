"""Builds client/ui/preload.json: the files the menus need right away (login, server list,
lobby, shop/inventory, HUD), fetched behind the start-up loading screen so the menus never
pop in piece by piece. Paths are relative to client/.

Sources: string literals in client/js/*.js (textures, UI sounds, layouts), every texture the
listed layouts use, all of client/ui/tex and the shared JSON tables.
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENT = os.path.join(ROOT, "client")
WT_IF = os.path.join(ROOT, "assets", "textures", "wt_interface")
SND = os.path.join(ROOT, "extracted", "wt_snd", "interface")


def rel(path):
    return os.path.relpath(path, CLIENT).replace(os.sep, "/")


def main():
    js = ""
    for name in sorted(os.listdir(os.path.join(CLIENT, "js"))):
        if name.endswith(".js"):
            with open(os.path.join(CLIENT, "js", name), encoding="utf-8") as f:
                js += f.read()

    files = []
    seen = set()

    def add(path):
        if os.path.isfile(path) and path not in seen:
            seen.add(path)
            files.append(rel(path))

    for name in ("catalog.json", "maps.json"):
        add(os.path.join(CLIENT, "ui", name))
    for name in ("ranks.json", "strings.json"):
        add(os.path.join(CLIENT, "ui", "layouts", name))

    # textures named in the code: ui/tex/<p> (TEX) or assets/textures/wt_interface/<p> (A())
    for p in sorted(set(re.findall(r"'([A-Za-z0-9_/.-]+\.png)'", js))):
        add(os.path.join(CLIENT, "ui", "tex", p))
        add(os.path.join(WT_IF, p))
    for dirpath, _, names in os.walk(os.path.join(CLIENT, "ui", "tex")):
        for n in sorted(names):
            add(os.path.join(dirpath, n))

    for s in sorted(set(re.findall(r"sound\('([a-z_0-9]+)'", js)) | {"lower_menu_over", "lower_menu_click"}):
        add(os.path.join(SND, s + ".wav"))

    layouts = set(re.findall(r"loadLayout\('(\w+)', '(\w+)'\)", js))
    for group, name in sorted(layouts):
        path = os.path.join(CLIENT, "ui", "layouts", group, name + ".json")
        add(path)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            for c in json.load(f):
                for t in c.get("tex") or []:
                    add(os.path.join(WT_IF, re.sub(r"^wt_interface/", "", t)))

    sizes = sum(os.path.getsize(os.path.join(CLIENT, p)) for p in files)
    out = os.path.join(CLIENT, "ui", "preload.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"bytes": sizes, "files": files}, f, indent=0)
    print(f"{len(files)} files, {sizes / 1e6:.1f} MB -> {rel(out)}")


if __name__ == "__main__":
    main()
