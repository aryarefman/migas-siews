import zipfile
from pathlib import Path
from collections import Counter

targets = [
    'Oil and Gas Safety.v3i.yolo26.zip',
    'Construction Equipment.v2i.yolo26.zip',
    'analog_pressure_gauge.v21i.yolo26.zip',
]

for zname in targets:
    zp = Path('dataset') / zname
    if not zp.exists():
        print(f'NOT FOUND: {zname}\n'); continue
    print(f'=== {zp.stem[:60]} ===')
    with zipfile.ZipFile(zp) as zf:
        all_files = zf.namelist()
        for fname in ['data.yaml', 'README.dataset.txt']:
            if fname in all_files:
                print(zf.read(fname).decode()[:600])
                break
        labels = [n for n in all_files if '/labels/' in n and n.endswith('.txt')]
        counts = Counter()
        for lf in labels[:300]:
            for line in zf.read(lf).decode().strip().splitlines():
                if line.strip():
                    try: counts[int(line.split()[0])] += 1
                    except: pass
        print(f'Classes: {len(counts)} | Max ID: {max(counts) if counts else -1}')
        for cid in sorted(counts):
            print(f'  class {cid}: {counts[cid]} instances')
    print()
