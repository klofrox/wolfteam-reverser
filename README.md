# WolfTeam Web Port – Tools

Asset converters, data builders and test scripts for a browser port of the **WolfTeam (2016 client)**.
They turn the original game files into formats a web client can load (glTF, PNG/WebP, JSON) and
generate the game data used by the Python server and the Three.js client.

> **No game files are included in this repository.** You need your own legally obtained copy of the
> WolfTeam 2016 client. The scripts read from it and write the converted output locally.

## Requirements

- Python 3.10+
- Node.js (only for `demo/showcase.mjs`)
- Java + Ghidra (only for the scripts in `ghidra/`)
- Some converters may import extra Python packages; install whatever an import error asks for.

## Typical workflow

Run everything from the project root (the folder that contains `tools/`, `client/` and `server.py`).

1. **Unpack the game archives** with `xfs.py` (Xenesis `.xfs` reader/extractor).
   Put the result in `extracted/` (the scripts expect this layout).
2. **Convert the art**:
   - `dtx.py`, `vtf2png.py` – textures to PNG
   - `ltb.py`, `ltb2gltf.py` – character, weapon and prop models to `.glb`
   - `world.py`, `world2gltf.py`, `convert_all_maps.py` – maps to glTF + lightmaps
   - `convert_chars.py`, `convert_weapons.py`, `convert_props.py` – batch converters
3. **Build the game data** (`build_*.py`): item catalog, game modes, wolves, weapon modes,
   surfaces/impacts, FX, collision, chat filters, social data and more. Output goes to
   `client/ui/*.json` and `assets/data/`.
4. **Optimize for hosting** with `optimize_assets.py` (WebP next to PNGs, `.gz` next to large files).
5. **Refresh the code map** with `codemap.py` (writes `docs/CODEMAP.md`).

## What is in here

| Group | Files |
|---|---|
| Archive / format readers | `xfs.py`, `xfs_walk.py`, `dtx.py`, `ltb.py`, `world.py`, `gamedata.py` |
| Converters | `ltb2gltf.py`, `world2gltf.py`, `convert_*.py`, `vtf2png.py` |
| Data builders | `build_*.py`, `export_ui_layouts.py`, `export_lobby_ui.py` |
| Localization | `apply_tr_sounds.py`, `apply_tr_textures.py` |
| Audits / tests | `audit_skinning.py`, `audit_weapons.py`, `test_wallshot.py` |
| Hosting | `optimize_assets.py`, `build_preload.py` |
| Reverse-engineering helpers | `unpack2016/` (PE/section tooling), `ghidra/` (Ghidra scripts) |
| Demo | `demo/showcase.mjs` |
| Misc | `codemap.py` |

Each script starts with a one-line description of what it does; most can be run with
`python tools/<script>.py` and print their usage or paths on start.

## Notes

- Formats handled are LithTech Jupiter: `.xfs` archives, `.dtx` textures, `.ltb` models,
  world `.dat` (v85) and the `wt_attributes/*.dat` game database.
- `test_wallshot.py` starts against a local server and registers throw-away test accounts;
  run it only against your own local instance.
- Converted output is derived from copyrighted game content. Do not redistribute it.

## Disclaimer

This is an unofficial, non-commercial fan/research project. WolfTeam and all related assets
belong to their respective owners. This project is not affiliated with or endorsed by them.
