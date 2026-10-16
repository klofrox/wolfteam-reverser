"""Convert every world .dat under extracted/worlds and write assets/maps/maps.json."""
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import world2gltf  # noqa: E402

root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
src = os.path.join(root, 'extracted', 'worlds')
out = os.path.join(root, 'assets', 'maps')
tex = os.path.abspath(os.path.join(root, 'assets', 'textures'))
done = []
for dp, _, names in os.walk(src):
    for n in sorted(names):
        if not n.lower().endswith('.dat'):
            continue
        rel = os.path.relpath(os.path.join(dp, n), src).replace(os.sep, '/')
        name = os.path.splitext(n)[0].replace(' ', '_')
        try:
            world2gltf.convert(os.path.join(dp, n), out, tex, 0.01, name)
            done.append({'name': name, 'source': rel})
        except Exception:
            print('FAILED', rel)
            traceback.print_exc()
with open(os.path.join(out, 'maps.json'), 'w', encoding='utf-8') as f:
    json.dump(sorted(done, key=lambda m: m['name']), f, indent=1)
print(f'{len(done)} maps converted')
