# -*- coding: utf-8 -*-
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect('translation_memory.db')
c = conn.cursor()

terms = [
    '梅兰妮', '曼苏拉', '欧菲露妮', '沃夫加', '毕宿五', '米蒂尔', '曜石兔玩偶',
    '恶兆之钥', '肃清僭礼', '女仆本色', '忠诚誓约', '旧式黑棘', '黑棘',
    '残响绝峰', '残躯为誓', '残躯传响', '残镇夺径', '浮光派对', '海天碧浪',
    '水蓝色的假日', '永远的冒险', '水花挑战者', '水花擂台', '水幕屏障',
    '榴弹模组', '绝·对·没·问·题', '影侍', '铁血覆写', '指令追加', '除尘标记',
    '代理链接', '侍从协振', '血光映射', '绝域清场', '暗流地格', '伞病毒',
    '淬铁为骨', '深渊同栖', '活动层贴纸', '海伦娜001', '梅德常服', '梅德雨中'
]

for t in terms:
    c.execute('SELECT target_en FROM translations WHERE source_cn = ? LIMIT 1', (t,))
    r = c.fetchone()
    if r:
        print(f"{t} == exact: {r[0]}")
    else:
        c.execute('SELECT source_cn, target_en FROM translations WHERE source_cn LIKE ? LIMIT 1', (f'%{t}%',))
        r2 = c.fetchone()
        if r2:
            print(f"{t} ~= partial ({r2[0]}): {r2[1]}")
        else:
            print(f"{t} -- not found")
