# -*- coding: utf-8 -*-
import json
import re

with open(r'output\untranslated_chunks\chunk_020.json', 'r', encoding='utf-8') as f:
    chunk_data = json.load(f)

source_keys = list(chunk_data['translations'].keys())

with open('skills_inspected.txt', 'w', encoding='utf-8') as out:
    for idx in [237, 238, 239, 240, 241]:
        src = source_keys[idx]
        out.write(f"=== [{idx}] ===\n")
        parts = src.split('\n')
        for p_i, p in enumerate(parts):
            out.write(f"P{p_i}: {p}\n")
            tags = re.findall(r'<color=[^>]+>.*?</color>', p)
            out.write(f"   Tags: {tags}\n")

print("Written to skills_inspected.txt")
