"""
Skill: persona_strategy — 风格 persona 战略洞察

10 大 persona（韩系纯欲 / 甜酷辣妹 / 甜美少女 / 简约清透 / 田园花卉 /
新娘法式 / 御姐冷艳 / 老钱贵气 / 千金轻奢 / Clean Girl ...）
跨商家聚合：每个 persona 的商家数、平均营收、客单、评分、款式总数、
            款式平均 GMV、热门主色、热门工艺

用途: admin 决策"主推哪个 persona 战略"、"哪个 persona 还有商家上新空间"
"""
import json
from collections import Counter


def persona_strategy(db, limit_per_persona=8, top_n_personas=10):
    """聚合按 style_persona_name 的商家与款式表现"""
    limit_per_persona = max(3, min(int(limit_per_persona or 8), 20))
    top_n_personas = max(3, min(int(top_n_personas or 10), 20))

    persona_rows = db.execute("""
        SELECT
            style_persona_name,
            COUNT(*) AS shop_count,
            ROUND(AVG(monthly_revenue)) AS avg_revenue,
            ROUND(AVG(avg_ticket)) AS avg_ticket,
            ROUND(AVG(rating), 2) AS avg_rating,
            ROUND(AVG(repeat_customer_rate), 3) AS avg_repeat,
            ROUND(AVG(refund_rate), 3) AS avg_refund
        FROM merchant_profiles
        WHERE style_persona_name != ''
        GROUP BY style_persona_name
        ORDER BY shop_count DESC
        LIMIT ?
    """, (top_n_personas,)).fetchall()

    personas = []
    for p in persona_rows:
        persona_name = p[0]

        style_agg = db.execute("""
            SELECT
                COUNT(*) AS style_count,
                ROUND(AVG(gmv_30d)) AS avg_gmv_30d,
                ROUND(SUM(gmv_30d)) AS total_gmv_30d,
                ROUND(AVG(ctr), 3) AS avg_ctr,
                ROUND(AVG(conversion_rate), 3) AS avg_cvr,
                ROUND(AVG(cpc), 2) AS avg_cpc
            FROM merchant_style_catalog
            WHERE style_persona_name = ?
        """, (persona_name,)).fetchone()

        color_rows = db.execute("""
            SELECT primary_color, COUNT(*) AS n
            FROM merchant_style_catalog
            WHERE style_persona_name = ? AND primary_color != ''
            GROUP BY primary_color
            ORDER BY n DESC
            LIMIT 5
        """, (persona_name,)).fetchall()

        tech_counter = Counter()
        tech_raw = db.execute("""
            SELECT core_techniques FROM merchant_style_catalog
            WHERE style_persona_name = ? AND core_techniques != '[]'
        """, (persona_name,)).fetchall()
        for (raw,) in tech_raw:
            try:
                arr = json.loads(raw) if raw else []
            except json.JSONDecodeError:
                arr = []
            tech_counter.update(arr)

        top_shops = db.execute("""
            SELECT shop_id, shop_name, city, monthly_revenue, rating
            FROM merchant_profiles
            WHERE style_persona_name = ?
            ORDER BY monthly_revenue DESC
            LIMIT ?
        """, (persona_name, limit_per_persona)).fetchall()

        personas.append({
            "persona_name": persona_name,
            "shop_count": p[1],
            "avg_revenue": p[2],
            "avg_ticket": p[3],
            "avg_rating": p[4],
            "avg_repeat_rate": p[5],
            "avg_refund_rate": p[6],
            "style_count": style_agg[0],
            "avg_style_gmv_30d": style_agg[1],
            "total_style_gmv_30d": style_agg[2],
            "avg_ctr": style_agg[3],
            "avg_cvr": style_agg[4],
            "avg_cpc": style_agg[5],
            "top_colors": [{"color": c[0], "count": c[1]} for c in color_rows],
            "top_techniques": [{"technique": t, "count": n} for t, n in tech_counter.most_common(5)],
            "top_shops": [
                {"shop_id": s[0], "shop_name": s[1], "city": s[2],
                 "monthly_revenue": s[3], "rating": s[4]}
                for s in top_shops
            ],
        })

    return {
        "total_personas": len(personas),
        "personas": personas,
    }
