# -*- coding: utf-8 -*-
import shutil
import json
import os

src = r'output/untranslated_chunks/chunk_001_verified.json'
dst = r'output/untranslated_chunks/chunk_001.json'

with open(src, 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Read {len(data['translations'])} translations from {src}")

with open(dst, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Successfully copied and formatted into {dst}")
print(f"Final file size: {os.path.getsize(dst)} bytes")
