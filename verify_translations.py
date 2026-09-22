# -*- coding: utf-8 -*-
import json
import re
import sys
sys.stdout.reconfigure(encoding='utf-8')

from trans_part1 import part1
from trans_part2 import part2
from trans_part3 import part3
from trans_part4 import part4
from trans_part5 import part5
from trans_part6 import part6

all_trans = {}
all_trans.update(part1)
all_trans.update(part2)
all_trans.update(part3)
all_trans.update(part4)
all_trans.update(part5)
all_trans.update(part6)

print(f"Total translated keys collected: {len(all_trans)}")

orig_path = r'output/untranslated_chunks/chunk_001.json'
with open(orig_path, 'r', encoding='utf-8') as f:
    orig_data = json.load(f)

orig_keys = list(orig_data['translations'].keys())
print(f"Total keys in original chunk_001.json: {len(orig_keys)}")

missing = [k for k in orig_keys if k not in all_trans]
extra = [k for k in all_trans if k not in orig_data['translations']]

if missing:
    print(f"ERROR: {len(missing)} keys missing!")
    for m in missing[:10]:
        print("  Missing:", repr(m))
else:
    print("SUCCESS: 0 missing keys!")

if extra:
    print(f"ERROR: {len(extra)} extra keys!")
    for e in extra[:10]:
        print("  Extra:", repr(e))
else:
    print("SUCCESS: 0 extra keys!")

# Validate tags and placeholders
tag_errors = 0
for k, v in all_trans.items():
    # Check placeholders like {0}, {1}, etc.
    k_places = sorted(re.findall(r'\{[0-9]+\}', k))
    v_places = sorted(re.findall(r'\{[0-9]+\}', v))
    if k_places != v_places:
        print(f"Placeholder mismatch:\n  K: {k}\n  V: {v}\n  {k_places} vs {v_places}")
        tag_errors += 1

    # Check [VAL...]
    k_vals = sorted(re.findall(r'\[VAL[0-9]+\]', k))
    v_vals = sorted(re.findall(r'\[VAL[0-9]+\]', v))
    if k_vals != v_vals:
        print(f"VAL tag mismatch:\n  K: {k[:60]}...\n  {k_vals} vs {v_vals}")
        tag_errors += 1

    # Check <color=...>
    k_colors = sorted(re.findall(r'<color=#[0-9a-fA-F]+>', k))
    v_colors = sorted(re.findall(r'<color=#[0-9a-fA-F]+>', v))
    if k_colors != v_colors:
        print(f"Color tag mismatch:\n  K: {k[:60]}...\n  {k_colors} vs {v_colors}")
        tag_errors += 1

    # Check </color>
    k_end_colors = len(re.findall(r'</color>', k))
    v_end_colors = len(re.findall(r'</color>', v))
    if k_end_colors != v_end_colors:
        print(f"</color> count mismatch:\n  K: {k[:60]}...\n  {k_end_colors} vs {v_end_colors}")
        tag_errors += 1

    # Check <size=...>
    k_sizes = sorted(re.findall(r'<size=[0-9]+>', k))
    v_sizes = sorted(re.findall(r'<size=[0-9]+>', v))
    if k_sizes != v_sizes:
        print(f"Size tag mismatch:\n  K: {k[:60]}...\n  {k_sizes} vs {v_sizes}")
        tag_errors += 1

    # Check <b> and </b>
    k_b = len(re.findall(r'<b>', k))
    v_b = len(re.findall(r'<b>', v))
    if k_b != v_b:
        print(f"<b> count mismatch:\n  K: {k[:60]}...\n  {k_b} vs {v_b}")
        tag_errors += 1

if tag_errors == 0:
    print("SUCCESS: All tags, placeholders, and formatting verified perfectly!")
else:
    print(f"WARNING: {tag_errors} tag mismatches detected!")

# Build the final translated JSON structure matching the original exactly
result = {
    "_prompt": orig_data.get("_prompt", ""),
    "translations": {k: all_trans[k] for k in orig_keys}
}

out_path = r'output/untranslated_chunks/chunk_001_verified.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"Saved verified JSON with {len(result['translations'])} translated items to {out_path}")
