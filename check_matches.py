import json
import sqlite3

with open(r'C:\Users\Paruhas.c\Downloads\langpackage_scripts\output\untranslated_chunks\chunk_010.json', 'r', encoding='utf-8') as f:
    chunk = json.load(f)

keys = list(chunk['translations'].keys())

conn = sqlite3.connect(r'C:\Users\Paruhas.c\Downloads\langpackage_scripts\translation_memory.db')
c = conn.cursor()

tm_matches = {}
for k in keys:
    res = c.execute("SELECT target_en FROM translations WHERE source_cn = ?", (k,)).fetchone()
    if res and res[0] and res[0].strip():
        tm_matches[k] = res[0]

print(f"TM matches: {len(tm_matches)} / {len(keys)}")

# check translations.json
with open(r'C:\Users\Paruhas.c\Downloads\langpackage_scripts\translations.json', 'r', encoding='utf-8') as f:
    tj = json.load(f)

tj_matches = {}
for k in keys:
    if k in tj and tj[k] and tj[k].strip():
        tj_matches[k] = tj[k]

print(f"translations.json matches: {len(tj_matches)} / {len(keys)}")

with open('chunk_010_matches.json', 'w', encoding='utf-8') as f:
    json.dump({'tm': tm_matches, 'tj': tj_matches}, f, ensure_ascii=False, indent=2)
