from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent

datasets = {
    'jalan_berlubang': ROOT / 'dataset' / 'jalan berlubang.v3-tambahan-dataset.yolo26',
    'rust_corrosion':  ROOT / 'dataset' / 'Rust Corrosion Detection.v16i.yolo26',
}

for name, base in datasets.items():
    print(f'=== {name} ===')
    if not base.exists():
        print(f'  NOT FOUND: {base}')
        print()
        continue
    items = [p.name for p in base.iterdir() if not p.name.startswith('.')][:15]
    print(f'Root: {items}')
    for split in ['train','valid','val','test']:
        img_p = base / split / 'images'
        lbl_p = base / split / 'labels'
        if img_p.exists():
            ni = len(list(img_p.glob('*.*')))
            nl = len(list(lbl_p.glob('*.txt'))) if lbl_p.exists() else 0
            print(f'  [{split}] images={ni}  labels={nl}')
    lbl_dir = base / 'train' / 'labels'
    if not lbl_dir.exists():
        lbl_dir = base / 'valid' / 'labels'
    counts = Counter()
    for lf in lbl_dir.glob('*.txt'):
        for line in lf.read_text().strip().splitlines():
            if line.strip():
                try: counts[int(line.split()[0])] += 1
                except: pass
    print(f'  Class dist: {dict(sorted(counts.items()))}')
    for fname in ['data.yaml','README.dataset.txt','README.roboflow.txt']:
        fp = base / fname
        if fp.exists():
            print(f'  [{fname}]:')
            for ln in fp.read_text()[:500].splitlines():
                print(f'    {ln}')
    print()
