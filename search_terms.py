import sqlite3

conn = sqlite3.connect('translation_memory.db')
c = conn.cursor()

terms = [
    '克罗丽科', '寇尔芙', '闪电', '维普蕾', '帕拉达嘉', '莉塔拉', '曼尼安保', 
    '链讯集团', '莉迪亚', '兰汀', '奇洛薇格', '翡图萨', '黑眼', '希岸', '狂猎', '安菲娅', '伊莱莎'
]

import sys
sys.stdout.reconfigure(encoding='utf-8')

for t in terms:
    rows = c.execute("SELECT source_cn, target_en FROM translations WHERE source_cn LIKE ? LIMIT 3", (f"%{t}%",)).fetchall()
    print(f"=== {t} ===")
    for r in rows:
        print(f"  CN: {r[0][:50]}")
        print(f"  EN: {r[1][:50]}")

