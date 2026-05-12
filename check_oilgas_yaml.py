import zipfile
from pathlib import Path

targets = [
    'Oil and Gas Safety.v3i.yolo26.zip',
    'Construction Equipment.v2i.yolo26.zip',
    'analog_pressure_gauge.v21i.yolo26.zip',
    'Airbus Oil Storage Detection.zip',
]

for zname in targets:
    zp = Path('dataset') / zname
    if not zp.exists():
        # try partial match
        matches = list(Path('dataset').glob(f'*{zname.split(".")[0]}*'))
        if matches:
            zp = matches[0]
        else:
            print(f'NOT FOUND: {zname}\n'); continue
    print(f'=== {zp.stem[:65]} ===')
    with zipfile.ZipFile(zp) as zf:
        for fname in ['data.yaml', '_darknet.labels']:
            if fname in zf.namelist():
                print(zf.read(fname).decode()[:400])
                break
    print()
