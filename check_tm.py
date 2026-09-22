import json
import sqlite3

with open(r'C:\Users\Paruhas.c\Downloads\langpackage_scripts\output\untranslated_chunks\chunk_010.json', 'r', encoding='utf-8') as f:
    chunk = json.load(f)

keys = list(chunk['translations'].keys())
print('Total keys in chunk_010:', len(keys))

conn = sqlite3.connect(r'C:\Users\Paruhas.c\Downloads\langpackage_scripts\translation_memory.db')
c = conn.cursor()
tables = c.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
print('TM tables:', tables)

for table in tables:
    tname = table[0]
    schema = c.execute(f"PRAGMA table_info({tname});").fetchall()
    print(f"Table {tname}: {schema}")

matches = 0
found = {}
for k in keys:
    res = c.execute("SELECT target_en FROM translations WHERE source_cn = ?", (k,)).fetchone()
    if res and res[0] and res[0].strip():
        matches += 1
        found[k] = res[0]

print(f"Exact matches in TM: {matches} / {len(keys)}")
for i, (k, v) in enumerate(list(found.items())[:10]):
    print(f"[{i}] CN: {k}\n    EN: {v}")

