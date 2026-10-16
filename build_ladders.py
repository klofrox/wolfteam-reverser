"""Add Ladder volume brush boxes ("boxes") to the converted maps' objects.json without reconverting them (world2gltf does it for new conversions)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from world2gltf import ladder_boxes  # noqa: E402

root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
src = os.path.join(root, 'extracted', 'worlds')
out = os.path.join(root, 'assets', 'maps')

with open(os.path.join(out, 'maps.json'), encoding='utf-8') as f:
    maps = json.load(f)
total = found = 0
for m in maps:
    path = os.path.join(out, m['name'], 'objects.json')
    if not os.path.exists(path):
        continue
    with open(path, encoding='utf-8') as f:
        objs = json.load(f)
    ladders = [o for o in objs['objects'] if o.get('type') == 'Ladder']
    if not ladders:
        continue
    with open(os.path.join(src, m['source']), 'rb') as f:
        data = f.read()
    scale = objs.get('scale', 0.01)
    for o in ladders:
        o['props'].pop('box', None)
        o['props']['boxes'] = ladder_boxes(data, o['props'].get('Name', ''), scale)
        total += 1
        found += bool(o['props']['boxes'])
        if not o['props']['boxes']:
            print('no box:', m['name'], o['props'].get('Name'))
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(objs, f, ensure_ascii=False, indent=1)
print(f'{found} / {total} ladders have a box')
