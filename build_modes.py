"""Game modes for the web port: client/ui/modes.json, read by both the client (js/modes.js) and the
hub (realtime.py / modes.py).

  modes   mode id (mapattribute MapType) -> rules: which rule set, who may be a wolf, which weapons,
          what the mission counts. Names follow wt_attributes/modelist.dat (main mode + "Human vs Human",
          "Wolf vs Wolf", "Wolf vs Human", grenade / knife / pistol / snipe / heavy weapon variants).
  maps    map id -> objective objects from assets/maps/<map>/objects.json, in three.js units
          (WBattleStation -> stations A..E by BS_ID, WBombArea -> bomb sites B1/B2 by BombAreaID,
          CTFBase -> flag bases, CFSMNpcSpawner -> celebrity, WDieArea -> kill boxes, supply boxes).

Also adds stronghold_ctf (CTF map that mapattribute.txt does not list) to client/ui/maps.json,
with the loading screen / minimap of stronghold_dm. Rerun after tools/export_lobby_ui.py.

  python tools/build_modes.py
"""
import json
import math
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
S = 0.01   # LithTech units -> three.js units

# id: label, rule, kinds, weapons, mission
#   rule    dm | conquest | exconquest | bomb | icehold | hero | wolfhunt | ctf | pve (pve.py)
#   kinds   any (transform freely) | human (no wolves) | wolf (wolves only) | hvw (red humans, blue wolves)
#           | single (the players are blue wolves, the bots red humans)
#           | infect (wolfhunt: teams are picked per round, the killed become wolves)
#   weapons None | knife | pistol | sniper | grenade | heavy
#   mission points | rounds (what "N pts" / "N rounds" in the room settings count) | pve | boss (difficulty)
M = {
    "FM_BATTLE": ("DeathMatch", "dm", "any", None, "points"),
    "FM_DM_WOLFvsWOLF": ("Wolf vs Wolf", "dm", "wolf", None, "points"),
    "FM_BATTLEWOLF": ("Human vs Wolf Mode", "dm", "hvw", None, "points"),
    "FM_BATTLEC_KNIFE": ("Knife Mode", "dm", "human", "knife", "points"),
    "FM_BATTLEC_PISTOL": ("Pistol Mode", "dm", "human", "pistol", "points"),
    "FM_BATTLEC_SNIPER": ("Snipe Mode", "dm", "human", "sniper", "points"),
    "FM_BATTLEC_GRENADE": ("Grenade Mode", "dm", "human", "grenade", "points"),
    "FM_BATTLE_C_HEAVYWEAPON": ("Heavy Weapon", "dm", "human", "heavy", "points"),
    "FM_LADDER_DM_CLASSIC": ("DeathMatch Human vs Human", "dm", "human", None, "points"),
    "FM_LADDER_DM_WOLFCLASSIC": ("DeathMatch Wolf vs Wolf", "dm", "wolf", None, "points"),
    "FM_LADDER_DM_HUMANVSWOLF": ("DeathMatch Wolf vs Human", "dm", "hvw", None, "points"),
    "FM_FLAG": ("Conquest", "conquest", "any", None, "rounds"),
    "FM_FLAGWOLF": ("Wolf Conquest", "conquest", "hvw", None, "rounds"),
    "FM_FLAGWOLFWAR": ("Conquest Wolf vs Wolf", "conquest", "wolf", None, "rounds"),
    "FM_FLAGC_GRENADE": ("Conquest Grenade", "conquest", "human", "grenade", "rounds"),
    "FM_ADVANCED": ("EX-Conquest", "exconquest", "any", None, "points"),
    "FM_ICEHOLD": ("Ice Hold", "icehold", "any", None, "rounds"),
    "FM_ICEHOLDC_GRENADE": ("Ice Hold Grenade", "icehold", "human", "grenade", "rounds"),
    "FM_ICEHOLDC_SNIPER": ("Ice Hold Snipe", "icehold", "human", "sniper", "rounds"),
    "FM_BOMB": ("Destruction", "bomb", "any", None, "rounds"),
    "FM_BOMBWOLF": ("Destruction Wolf vs Human", "bomb", "hvw", None, "rounds"),
    "FM_BOMBC_GRENADE": ("Destruction Grenade", "bomb", "human", "grenade", "rounds"),
    "FM_WOLFHUNT_REVOLT": ("Wolfhunt", "wolfhunt", "infect", None, "rounds"),
    "FM_WOLFHUNT_COUNTERATTACK": ("Counter Attack", "wolfhunt", "infect", None, "rounds"),
    "FM_WOLFHUNT_DOMINATE": ("Wolfhunt Dominate", "wolfhunt", "infect", "heavy", "rounds"),
    "FM_HERO_BATTLE": ("Hero Match", "hero", "any", None, "rounds"),
    "FM_HEROC_KNIFE": ("Hero Knife", "hero", "human", "knife", "rounds"),
    "FM_HEROC_PISTOL": ("Hero Pistol", "hero", "human", "pistol", "rounds"),
    "FM_HEROC_SNIPER": ("Hero Snipe", "hero", "human", "sniper", "rounds"),
    "FM_HEROC_GRENADE": ("Hero Grenade", "hero", "human", "grenade", "rounds"),
    "FM_HEROC_HEAVYWEAPON": ("Hero Heavy Weapon", "hero", "human", "heavy", "rounds"),
    "FM_FLAG_CELEBRITY": ("Celebrity", "conquest", "any", None, "rounds"),
    "FM_FLAG_CELEBRITY_CLASSIC": ("Celebrity Human vs Human", "conquest", "human", None, "rounds"),
    "FM_FLAG_CELEBRITY_WOLFCLASSIC": ("Celebrity Wolf vs Wolf", "conquest", "wolf", None, "rounds"),
    "FM_FLAG_CELEBRITY_HUMANvsWOLF": ("Celebrity Wolf vs Human", "conquest", "hvw", None, "rounds"),
    "FM_FLAG_CELEBRITY_GRENADE": ("Celebrity Grenade", "conquest", "human", "grenade", "rounds"),
    "FM_CTF": ("CTF Wolf vs Wolf", "ctf", "wolf", None, "points"),
    # PvE (pve.py): the players are humans against AI wolf waves; the mission picks the difficulty
    "FM_AI_WOLFRUSH": ("Wolf Rush", "pve", "human", None, "pve"),
    "GAME_MODE_WOLF_RUSH_BOSS": ("Wolf Rush Boss", "pve", "human", None, "boss"),
    # single wolf (pve.py SingleWolfRules): the players are wolves against soldier bots; mission = difficulty
    "FM_AI_BATTLE_SINGLE": ("Tek Kurt (AI)", "single", "single", None, "single"),
}

# room settings choices per mission type ("N pts" / "N rounds"); the first is the default
MISSIONS = {
    "points": ["160 pts", "80 pts", "120 pts", "200 pts", "10 rounds", "5 rounds"],
    "rounds": ["5 rounds", "3 rounds", "7 rounds", "10 rounds"],
    "exconquest": ["200 pts", "100 pts", "300 pts"],
    "ctf": ["32 pts", "16 pts", "48 pts"],
    "pve": ["Normal", "Kolay", "Zor", "Cehennem"],
    "boss": ["Boss"],
    "single": ["Normal", "Kolay", "Zor"],
}

# make-room menu: main entries and the variants each one swaps in (modelist.dat order)
MENU = [
    ("FM_BATTLE", ["FM_BATTLE", "FM_LADDER_DM_CLASSIC", "FM_DM_WOLFvsWOLF", "FM_BATTLEWOLF", "FM_BATTLEC_GRENADE",
                   "FM_BATTLEC_KNIFE", "FM_BATTLEC_PISTOL", "FM_BATTLEC_SNIPER", "FM_BATTLE_C_HEAVYWEAPON"]),
    ("FM_FLAG", ["FM_FLAG", "FM_FLAGWOLFWAR", "FM_FLAGWOLF", "FM_FLAGC_GRENADE"]),
    ("FM_ICEHOLD", ["FM_ICEHOLD", "FM_ICEHOLDC_GRENADE", "FM_ICEHOLDC_SNIPER"]),
    ("FM_BOMB", ["FM_BOMB", "FM_BOMBWOLF", "FM_BOMBC_GRENADE"]),
    ("FM_ADVANCED", ["FM_ADVANCED"]),
    ("FM_WOLFHUNT_REVOLT", ["FM_WOLFHUNT_REVOLT", "FM_WOLFHUNT_COUNTERATTACK", "FM_WOLFHUNT_DOMINATE"]),
    ("FM_HERO_BATTLE", ["FM_HERO_BATTLE", "FM_HEROC_GRENADE", "FM_HEROC_KNIFE", "FM_HEROC_PISTOL", "FM_HEROC_SNIPER",
                        "FM_HEROC_HEAVYWEAPON"]),
    ("FM_CTF", ["FM_CTF"]),
    ("FM_AI_WOLFRUSH", ["FM_AI_WOLFRUSH", "GAME_MODE_WOLF_RUSH_BOSS", "FM_AI_BATTLE_SINGLE"]),
    ("FM_FLAG_CELEBRITY", ["FM_FLAG_CELEBRITY", "FM_FLAG_CELEBRITY_WOLFCLASSIC", "FM_FLAG_CELEBRITY_CLASSIC",
                           "FM_FLAG_CELEBRITY_HUMANvsWOLF", "FM_FLAG_CELEBRITY_GRENADE"]),
]
MENU_LABEL = {"FM_BATTLE": "DeathMatch", "FM_FLAG": "Conquest", "FM_ICEHOLD": "Ice Hold", "FM_BOMB": "Destruction",
              "FM_ADVANCED": "EX-Conquest", "FM_WOLFHUNT_REVOLT": "Wolfhunt", "FM_HERO_BATTLE": "Hero Match",
              "FM_CTF": "CTF", "FM_FLAG_CELEBRITY": "Celebrity", "FM_AI_WOLFRUSH": "AI / PvE"}

CELEBRITY = ["ceyda", "esra", "hanna", "eliana"]   # worlds/fsmmodelbutes FSMMODEL0..3


def r3(v):
    return [round(float(x), 3) for x in v]


def map_objects(name):
    path = os.path.join(ROOT, "assets", "maps", name, "objects.json")
    if not os.path.exists(path):
        return None
    objs = json.load(open(path, encoding="utf-8"))["objects"]
    out = {"stations": [], "bombs": [], "ctf": [], "celebrity": None, "die": [], "supply": []}
    for o in objs:
        t, p = o["type"], o["props"]
        pos = p.get("position")
        if pos is None:
            continue
        if t == "WBattleStation":
            out["stations"].append({"bs": int(p.get("BS_ID", 0)), "pos": r3(pos), "r": round(p.get("Radius", 300) * S, 3),
                                    "time": float(p.get("ConquestTime", 3.0))})
        elif t == "WBombArea":
            out["bombs"].append({"id": int(p.get("BombAreaID", 0)), "pos": r3(pos), "r": round(p.get("Radius", 200) * S, 3)})
        elif t == "CTFBase":
            out["ctf"].append({"team": "blue" if int(p.get("CTFBaseTeam", 0)) == 1 else "red", "pos": r3(pos)})
        elif t == "CFSMNpcSpawner" and "CELEBRITY" in str(p.get("FSMType", "")):
            out["celebrity"] = {"pos": r3(pos)}
        elif t == "WDieArea":
            # axis-aligned box: Dims are half extents in LithTech units, Z flipped like the world
            d = p.get("Dims") or [0, 0, 0]
            out["die"].append({"pos": r3(pos), "half": r3([d[0] * S, d[1] * S, d[2] * S])})
        elif t in ("WHPSupplyBox", "WAmmoSupplyBox"):
            out["supply"].append({"kind": "hp" if t == "WHPSupplyBox" else "ammo", "pos": r3(pos),
                                  "r": round(p.get("Radius", 300) * S, 3), "every": float(p.get("SupplyTime", 5000)) / 1000})
    out["stations"].sort(key=lambda s: s["bs"])
    for i, s in enumerate(out["stations"]):
        s["id"] = "ABCDEFGH"[i] if i < 8 else str(i)
    out["bombs"].sort(key=lambda b: b["id"])
    for i, b in enumerate(out["bombs"]):
        b["name"] = f"B{i + 1}"
    # spawn groups: maps use Team0 (red) / Team1 (blue); some CTF maps have NoTeam for one side.
    teams = {}
    for o in objs:
        if o["type"] == "GameStartPoint":
            teams.setdefault(o["props"].get("Team", "NoTeam"), []).append(o["props"]["position"])
    if "Team0" not in teams and len(teams) == 2 and out["ctf"]:
        # match each spawn group to the nearest flag base
        red_base = next((b["pos"] for b in out["ctf"] if b["team"] == "red"), None)
        if red_base:
            def dist(group):
                cx = sum(p[0] for p in group) / len(group)
                cz = sum(p[2] for p in group) / len(group)
                return math.hypot(cx - red_base[0], cz - red_base[2])
            a, b = sorted(teams, key=lambda k: dist(teams[k]))
            out["spawnTeams"] = {"red": a, "blue": b}
    return {k: v for k, v in out.items() if v}


# Turkish labels: the TR 2016 client's mapmodeinfostringtable ModeName (Ölüm Oyunu, İşgal, Yıkım, Uyku, Kurt Avı,
# Bayrak Yakalama, Kurt Hücumu ...), without the "Modu" suffix as the lobby shows them; modes the TR file
# does not name follow the same words.
TR_LABEL = {
    "FM_BATTLE": "Ölüm Oyunu", "FM_DM_WOLFvsWOLF": "Ölüm Oyunu Kurt vs Kurt", "FM_BATTLEWOLF": "İnsan vs Kurt",
    "FM_BATTLEC_KNIFE": "Bıçak", "FM_BATTLEC_PISTOL": "Tabanca", "FM_BATTLEC_SNIPER": "Keskin Nişancı",
    "FM_BATTLEC_GRENADE": "Bomba", "FM_BATTLE_C_HEAVYWEAPON": "Ağır Silah",
    "FM_LADDER_DM_CLASSIC": "Ölüm Oyunu İnsan vs İnsan", "FM_LADDER_DM_WOLFCLASSIC": "Ölüm Oyunu Kurt vs Kurt",
    "FM_LADDER_DM_HUMANVSWOLF": "Ölüm Oyunu Kurt vs İnsan",
    "FM_FLAG": "İşgal", "FM_FLAGWOLF": "Kurt İşgali", "FM_FLAGWOLFWAR": "Kurt Savaşı", "FM_FLAGC_GRENADE": "İşgal Bomba",
    "FM_ADVANCED": "EX-İşgal", "FM_ICEHOLD": "Uyku", "FM_ICEHOLDC_GRENADE": "Uyku Bomba", "FM_ICEHOLDC_SNIPER": "Uyku Keskin Nişancı",
    "FM_BOMB": "Yıkım", "FM_BOMBWOLF": "Yıkım İnsan vs Kurt", "FM_BOMBC_GRENADE": "Yıkım Bomba",
    "FM_WOLFHUNT_REVOLT": "Kurt Avı İsyan", "FM_WOLFHUNT_COUNTERATTACK": "Kurt Avı Karşı Saldırı",
    "FM_WOLFHUNT_DOMINATE": "Kurt Avı Hakimiyet",
    "FM_HERO_BATTLE": "Kahraman", "FM_HEROC_KNIFE": "Kahraman Bıçak", "FM_HEROC_PISTOL": "Kahraman Tabanca",
    "FM_HEROC_SNIPER": "Kahraman Keskin Nişancı", "FM_HEROC_GRENADE": "Kahraman Bomba", "FM_HEROC_HEAVYWEAPON": "Kahraman Ağır Silah",
    "FM_FLAG_CELEBRITY": "Ünlü Kurtarma", "FM_FLAG_CELEBRITY_CLASSIC": "Ünlü Kurtarma İnsan vs İnsan",
    "FM_FLAG_CELEBRITY_WOLFCLASSIC": "Ünlü Kurtarma Kurt vs Kurt", "FM_FLAG_CELEBRITY_HUMANvsWOLF": "Ünlü Kurtarma Kurt vs İnsan",
    "FM_FLAG_CELEBRITY_GRENADE": "Ünlü Kurtarma Bomba", "FM_CTF": "Bayrak Yakalama",
    "FM_AI_WOLFRUSH": "Kurt Hücumu", "GAME_MODE_WOLF_RUSH_BOSS": "Kurt Akını Hesaplaşma", "FM_AI_BATTLE_SINGLE": "Tek Kurt (AI)",
}
TR_MENU = {"DeathMatch": "Ölüm Oyunu", "Conquest": "İşgal", "Ice Hold": "Uyku", "Destruction": "Yıkım",
           "EX-Conquest": "EX-İşgal", "Wolfhunt": "Kurt Avı", "Hero Match": "Kahraman", "CTF": "Bayrak Yakalama",
           "AI / PvE": "AI / PvE", "Celebrity": "Ünlü Kurtarma"}


def main():
    maps_path = os.path.join(ROOT, "client", "ui", "maps.json")
    lobby = json.load(open(maps_path, encoding="utf-8"))
    ids = {m["id"] for m in lobby["maps"]}
    if "stronghold_ctf" not in ids:
        base = next((m for m in lobby["maps"] if m["id"] == "stronghold_dm"), None)
        entry = {"id": "stronghold_ctf", "name": "Stronghold CTF", "texture": base["texture"] if base else None,
                 "modes": ["FM_CTF"]}
        for k in ("loading", "minimap"):
            if base and k in base:
                entry[k] = base[k]
        lobby["maps"].append(entry)
        json.dump(lobby, open(maps_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("added stronghold_ctf to maps.json")
    modes = {k: {"label": TR_LABEL.get(k, v[0]), "rule": v[1], "kinds": v[2], "weapons": v[3], "mission": v[4],
                 "celebrity": k.startswith("FM_FLAG_CELEBRITY")} for k, v in M.items()}
    missions = {}
    for k, v in modes.items():
        missions[k] = MISSIONS["exconquest" if v["rule"] == "exconquest" else "ctf" if v["rule"] == "ctf" else v["mission"]]
    objectives = {}
    for m in lobby["maps"]:
        o = map_objects(m["id"])
        if o:
            objectives[m["id"]] = o
    # which modes a map can really host: objective modes need their objects
    need = {"conquest": "stations", "exconquest": "stations", "bomb": "bombs", "ctf": "ctf"}
    # mapattribute lists no map for FM_BATTLEWOLF: host it where the ladder Wolf vs Human DM is played
    alias = {"FM_BATTLEWOLF": "FM_LADDER_DM_HUMANVSWOLF", "FM_AI_BATTLE_SINGLE": "FM_BATTLE"}
    playable = {}
    for m in lobby["maps"]:
        o = objectives.get(m["id"], {})
        listed = list(m["modes"]) + [a for a, src in alias.items() if src in m["modes"] and a not in m["modes"]]
        playable[m["id"]] = [x for x in listed if x in modes and (need.get(modes[x]["rule"]) is None or o.get(need[modes[x]["rule"]]))]
    out = {"modes": modes, "missions": missions, "celebrities": CELEBRITY,
           "menu": [{"id": top, "label": TR_MENU.get(MENU_LABEL[top], MENU_LABEL[top]), "variants": [[v, modes[v]["label"]] for v in sub]} for top, sub in MENU],
           "playable": playable, "maps": objectives}
    dst = os.path.join(ROOT, "client", "ui", "modes.json")
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    counts = {}
    for lst in playable.values():
        for x in lst:
            counts[x] = counts.get(x, 0) + 1
    print("modes.json:", len(modes), "modes,", len(objectives), "maps with objects")
    print({k: counts.get(k, 0) for k in modes})


if __name__ == "__main__":
    main()
