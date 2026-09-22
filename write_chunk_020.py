# -*- coding: utf-8 -*-
import json
import re
from build_chunk_020 import translations

chunk_file = r'output\untranslated_chunks\chunk_020.json'
with open(chunk_file, 'r', encoding='utf-8') as f:
    chunk_data = json.load(f)

source_keys = list(chunk_data['translations'].keys())

report = []
report.append(f"Total source keys: {len(source_keys)}")
report.append(f"Total translations: {len(translations)}")

if len(source_keys) != len(translations):
    report.append(f"ERROR: Length mismatch: {len(source_keys)} vs {len(translations)}")
else:
    name_checks = {
        '春田': 'Springfield',
        '代理人': 'Agent',
        '桑朵莱希': 'Centaureissi',
        '纳甘': 'Nagant',
        '莫辛纳甘': 'Mosin-Nagant',
        '科谢尼娅': 'Ksenia',
        '波波沙': 'PPSh-41',
        '安朵丝': 'Andoris',
        '比悠卡': 'Byuka',
        '米什缇': 'Mishti',
        '可露凯': 'Clukay',
        '乌尔丽德': 'Ullrid',
        '贝丝蒂': 'Besti',
        '芙铃': 'Fulin',
        '指挥官': 'Commander'
    }

    errors = []

    for idx, (src, tr) in enumerate(zip(source_keys, translations)):
        # 1. Non-empty
        if not tr.strip():
            errors.append(f"[{idx}] Translation is empty!")

        # 2. Color tags
        src_colors = re.findall(r'<color=[^>]+>', src)
        tr_colors = re.findall(r'<color=[^>]+>', tr)
        if src_colors != tr_colors:
            errors.append(f"[{idx}] Color tag mismatch:\n  Src: {src_colors}\n  Tr:  {tr_colors}")

        src_close_colors = src.count('</color>')
        tr_close_colors = tr.count('</color>')
        if src_close_colors != tr_close_colors:
            errors.append(f"[{idx}] </color> count mismatch: {src_close_colors} vs {tr_close_colors}")

        # Placeholders {0}, {1}, {}, etc.
        src_braces = re.findall(r'\{[0-9]*\}', src)
        tr_braces = re.findall(r'\{[0-9]*\}', tr)
        if src_braces != tr_braces:
            errors.append(f"[{idx}] Placeholder mismatch:\n  Src: {src_braces}\n  Tr:  {tr_braces}")

        # Delimiter |
        if '|' in src and '|' not in tr:
            errors.append(f"[{idx}] Missing '|' delimiter in translation!")

        # Check required names
        for cn_name, en_name in name_checks.items():
            if cn_name in src and en_name not in tr:
                errors.append(f"[{idx}] Missing name '{en_name}' for '{cn_name}'")

    if errors:
        report.append(f"FAILED with {len(errors)} errors:")
        for e in errors:
            report.append(f" - {e}")
    else:
        report.append("ALL CHECKS PASSED! Writing translated file...")
        for k, tr in zip(source_keys, translations):
            chunk_data['translations'][k] = tr

        with open(chunk_file, 'w', encoding='utf-8') as f:
            json.dump(chunk_data, f, ensure_ascii=False, indent=2)

        report.append("File successfully overwritten.")

with open('chunk_020_status.txt', 'w', encoding='utf-8') as out:
    out.write("\n".join(report))

print("Status written to chunk_020_status.txt")
