import zipfile
import os

models_dir = r"c:\Users\arya4\migas-siews\backend\Model"
for f in os.listdir(models_dir):
    if f.endswith(".zip"):
        print(f"Contents of {f}:")
        with zipfile.ZipFile(os.path.join(models_dir, f), 'r') as zip_ref:
            zip_ref.printdir()
        print("-" * 20)
