# -*- coding: utf-8 -*-
import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect('translation_memory.db')
c = conn.cursor()

with open('output/untranslated_chunks/chunk_020.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

keys = list(data['translations'].keys())
print(f"Total keys: {len(keys)}")

tm_matches = {}
for i, k in enumerate(keys):
    c.execute('SELECT target_en FROM translations WHERE source_cn = ?', (k,))
    row = c.fetchone()
    if row and row[0]:
        tm_matches[k] = row[0]

print(f"Found {len(tm_matches)} exact matches in TM.")
with open('chunk_020_tm_matches.json', 'w', encoding='utf-8') as f:
    json.dump(tm_matches, f, ensure_ascii=False, indent=2)

with open('chunk_020_keys.json', 'w', encoding='utf-8') as f:
    json.dump(keys, f, ensure_ascii=False, indent=2)

print("Saved chunk_020_tm_matches.json and chunk_020_keys.json")
