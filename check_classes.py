import zipfile
from pathlib import Path
from collections import Counter

# Dataset menarik untuk dicek
targets = [
    'labeled_safety.v1i.yolo26.zip',         # 4740 imgs — PPE?
    'Oil and Gas Safety.v3i.yolo26.zip',      # 11077 imgs — MIGAS?
    'Construction Safety - Open hole - Excavation Detection.v5-detr.yolo26.zip',  # 1842 imgs
]

for zname in targets:
    zp = Path('dataset') / zname
    if not zp.exists():
        print(f'NOT FOUND: {zname}\n')
        continue

    print(f'=== {zp.stem[:70]} ===')
    with zipfile.ZipFile(zp) as zf:
        all_files = zf.namelist()

        # README
        for readme in ['README.dataset.txt', 'README.roboflow.txt']:
            if readme in all_files:
                txt = zf.read(readme).decode()[:500]
                print(txt)
                break

        # Class distribution
        labels = [n for n in all_files if '/labels/' in n and n.endswith('.txt')][:300]
        counts = Counter()
        for lf in labels:
            for line in zf.read(lf).decode().strip().splitlines():
                if line.strip():
                    try: counts[int(line.split()[0])] += 1
                    except: pass
        print(f'\nClasses found (from first 300 labels):')
        for cid in sorted(counts):
            print(f'  class {cid}: {counts[cid]:5d} instances')
        print(f'Max class ID: {max(counts) if counts else -1}')
    print()
