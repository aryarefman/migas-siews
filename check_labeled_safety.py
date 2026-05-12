import zipfile
from pathlib import Path
from collections import Counter

zp = Path('dataset/labeled_safety.v1i.yolo26.zip')
with zipfile.ZipFile(zp) as zf:
    all_files = zf.namelist()

    for fname in ['README.dataset.txt', 'README.roboflow.txt', 'data.yaml', '_darknet.labels']:
        if fname in all_files:
            print(f'=== {fname} ===')
            print(zf.read(fname).decode()[:1000])
            print()

    labels = [n for n in all_files if '/labels/' in n and n.endswith('.txt')]
    counts = Counter()
    for lf in labels[:500]:
        for line in zf.read(lf).decode().strip().splitlines():
            if line.strip():
                try: counts[int(line.split()[0])] += 1
                except: pass

    print(f'Class distribution (dari {len(labels)} label files):')
    total = sum(counts.values())
    for cid in sorted(counts):
        print(f'  class {cid}: {counts[cid]:6d} instances ({counts[cid]/total*100:.1f}%)')
    print(f'Jumlah kelas: {len(counts)} | Max ID: {max(counts) if counts else -1}')
