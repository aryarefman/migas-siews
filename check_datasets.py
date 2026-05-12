import zipfile
from pathlib import Path
from collections import Counter

dataset_dir = Path('dataset')
zips = sorted(dataset_dir.glob('*.zip'))

header = f"{'Dataset':<52} {'Train':>6} {'Val':>6} {'Test':>6} {'Total':>7}"
print(header)
print('-' * len(header))

for zp in zips:
    try:
        with zipfile.ZipFile(zp) as zf:
            imgs = [n for n in zf.namelist() if n.endswith(('.jpg', '.png', '.jpeg'))]
            splits = Counter(n.split('/')[0] for n in imgs if '/' in n)
            train = splits.get('train', 0)
            val   = splits.get('valid', splits.get('val', 0))
            test  = splits.get('test', 0)
            name  = zp.stem[:51]
            print(f"{name:<52} {train:>6} {val:>6} {test:>6} {len(imgs):>7}")
    except Exception as e:
        print(f"{zp.name[:51]:<52} ERROR: {e}")
