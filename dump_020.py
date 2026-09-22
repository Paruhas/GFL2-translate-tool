# -*- coding: utf-8 -*-
import json
import sqlite3

conn = sqlite3.connect('translation_memory.db')
cur = conn.cursor()

with open(r'output\untranslated_chunks\chunk_020.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

items = list(data['translations'].keys())

with open('chunk_020_analysis.txt', 'w', encoding='utf-8') as out:
    for idx, k in enumerate(items):
        cur.execute('SELECT target_en, source_type FROM translations WHERE source_cn = ?', (k,))
        row = cur.fetchone()
        tm_info = f" -> [{row[0]}] ({row[1]})" if row else ""
        out.write(f"[{idx}] {k}{tm_info}\n")

print(f"Total keys: {len(items)}")
