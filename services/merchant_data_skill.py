from __future__ import annotations

import hashlib
import json
import os
import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


BJT = timezone(timedelta(hours=8))
DEFAULT_PASSWORD = "demo123456"
DATASET_SUMMARY_FILENAME = "merchant_dataset_summary.json"

PRIMARY_STYLES = {
    "A": ["奶白法式", "冰透猫眼", "裸粉极简", "水晶点缀", "雾感奶咖"],
    "B": ["草莓奶冻", "腮红渐变", "蝴蝶结甜心", "樱花果冻", "奶油爱心"],
    "C": ["碎钻镜面", "极光闪片", "金属流光", "珍珠法式", "银河亮片"],
    "D": ["烟熏冷调", "黑银金属", "深酒红猫眼", "暗夜蓝灰", "冷感雾黑"],
    "E": ["多巴胺撞色", "异形拼贴", "雪花晶石", "未来感光疗", "解构拼色"],
}

CITY_DISTRICTS = {
    "北京": ["三里屯", "国贸", "五道口", "望京", "中关村", "朝阳大悦城"],
    "上海": ["静安寺", "徐家汇", "陆家嘴", "新天地", "五角场", "虹桥"],
    "深圳": ["南山", "福田", "后海", "万象天地", "车公庙", "海岸城"],
    "广州": ["天河", "珠江新城", "太古汇", "番禺", "北京路", "琶洲"],
    "杭州": ["湖滨", "钱江新城", "滨江", "城西银泰", "武林", "未来科技城"],
}

SHOP_PREFIX = ["云釉", "鹿屿", "慢糖", "光屿", "雾白", "朝露", "镜汐", "棠枝", "森屿", "星釉"]
SHOP_SUFFIX = ["美甲研究所", "Nail Studio", "美甲会所", "甲艺空间", "美学社", "设计所"]


@dataclass
class MerchantAccount:
    username: str
    password_hash: str
    shop_id: str
    shop_name: str
    display_name: str
    role: str = "merchant"
    enabled_for_portal: int = 1


def ensure_merchant_data_schema(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS merchant_accounts (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            shop_id TEXT NOT NULL,
            shop_name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'merchant',
            enabled_for_portal INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS merchant_profiles (
            shop_id TEXT PRIMARY KEY,
            shop_name TEXT NOT NULL,
            city TEXT NOT NULL,
            district TEXT NOT NULL,
            style TEXT NOT NULL,
            style_name TEXT NOT NULL,
            rating REAL NOT NULL,
            review_count INTEGER NOT NULL,
            avg_ticket INTEGER NOT NULL,
            monthly_revenue INTEGER NOT NULL,
            repeat_customer_rate REAL NOT NULL,
            refund_rate REAL NOT NULL,
            complaint_rate REAL NOT NULL,
            store_status TEXT NOT NULL,
            hero_sku_id TEXT,
            hero_sku_name TEXT,
            owner_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS merchant_style_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id TEXT NOT NULL,
            style_id TEXT NOT NULL,
            style_name TEXT NOT NULL,
            category TEXT NOT NULL,
            price INTEGER NOT NULL,
            cost INTEGER NOT NULL,
            duration_minutes INTEGER NOT NULL,
            search_volume_30d INTEGER NOT NULL,
            click_volume_30d INTEGER NOT NULL,
            cart_volume_30d INTEGER NOT NULL,
            group_buy_orders_30d INTEGER NOT NULL,
            ctr REAL NOT NULL,
            conversion_rate REAL NOT NULL,
            refund_orders_30d INTEGER NOT NULL,
            favorite_count_30d INTEGER NOT NULL,
            share_count_30d INTEGER NOT NULL,
            impression_volume_30d INTEGER NOT NULL,
            cpc REAL NOT NULL,
            gmv_30d INTEGER NOT NULL,
            inventory_status TEXT NOT NULL,
            launch_stage TEXT NOT NULL,
            trend_signal TEXT NOT NULL,
            title_tags TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_merchant_style_shop ON merchant_style_catalog(shop_id);

        CREATE TABLE IF NOT EXISTS merchant_shop_daily_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id TEXT NOT NULL,
            date TEXT NOT NULL,
            search_volume INTEGER NOT NULL,
            click_volume INTEGER NOT NULL,
            consultation_volume INTEGER NOT NULL,
            group_buy_orders INTEGER NOT NULL,
            revenue INTEGER NOT NULL,
            ad_spend INTEGER NOT NULL,
            repeat_orders INTEGER NOT NULL,
            refund_orders INTEGER NOT NULL,
            favorites_added INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_merchant_daily_shop_date ON merchant_shop_daily_metrics(shop_id, date DESC);

        CREATE TABLE IF NOT EXISTS merchant_style_daily_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id TEXT NOT NULL,
            style_id TEXT NOT NULL,
            date TEXT NOT NULL,
            search_volume INTEGER NOT NULL,
            click_volume INTEGER NOT NULL,
            group_buy_orders INTEGER NOT NULL,
            favorites_added INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_merchant_style_daily_shop_style_date ON merchant_style_daily_metrics(shop_id, style_id, date DESC);
        """
    )
    conn.close()


def generate_merchant_dataset_skill(
    base_dir: str,
    merchant_count: int = 1000,
    min_styles_per_shop: int = 18,
    max_styles_per_shop: int = 36,
    days: int = 30,
    seed: int = 20260606,
    replace_existing: bool = True,
    enable_portal_accounts: bool = True,
) -> dict[str, Any]:
    safe_count = max(1, min(int(merchant_count or 1000), 5000))
    min_styles = max(8, min(int(min_styles_per_shop or 18), 80))
    max_styles = max(min_styles, min(int(max_styles_per_shop or 36), 120))
    safe_days = max(7, min(int(days or 30), 180))

    data_dir = os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    db_path = os.path.join(data_dir, "jiaqu.db")
    ensure_merchant_data_schema(db_path)

    rng = random.Random(seed)
    now = datetime.now(BJT)
    created_at = now.isoformat()
    conn = sqlite3.connect(db_path)

    if replace_existing:
        conn.execute("DELETE FROM merchant_accounts")
        conn.execute("DELETE FROM merchant_profiles")
        conn.execute("DELETE FROM merchant_style_catalog")
        conn.execute("DELETE FROM merchant_shop_daily_metrics")
        conn.execute("DELETE FROM merchant_style_daily_metrics")

    profiles = []
    style_rows = []
    shop_daily_rows = []
    style_daily_rows = []
    accounts = []
    sample_accounts = []

    for index in range(1, safe_count + 1):
        shop_id = f"m_shop_{index:04d}"
        style = rng.choice(list(PRIMARY_STYLES.keys()))
        city = rng.choice(list(CITY_DISTRICTS.keys()))
        district = rng.choice(CITY_DISTRICTS[city])
        shop_name = _build_shop_name(rng, district)
        rating = round(rng.uniform(4.1, 4.95), 1)
        review_count = rng.randint(60, 4200)
        avg_ticket = _category_ticket(style, rng)
        repeat_rate = round(rng.uniform(0.18, 0.62), 3)
        refund_rate = round(rng.uniform(0.01, 0.09), 3)
        complaint_rate = round(rng.uniform(0.002, 0.03), 3)
        owner_name = f"{district}店主"
        style_count = rng.randint(min_styles, max_styles)
        skus = _build_shop_styles(rng, shop_id, style, style_count, created_at)

        total_revenue = sum(item["gmv_30d"] for item in skus)
        hero = max(skus, key=lambda item: (item["group_buy_orders_30d"], item["click_volume_30d"]))

        profiles.append((
            shop_id, shop_name, city, district, style, _style_name(style), rating, review_count,
            avg_ticket, total_revenue, repeat_rate, refund_rate, complaint_rate, "active",
            hero["style_id"], hero["style_name"], owner_name, created_at, created_at,
        ))
        style_rows.extend([
            (
                item["shop_id"], item["style_id"], item["style_name"], item["category"], item["price"], item["cost"],
                item["duration_minutes"], item["search_volume_30d"], item["click_volume_30d"], item["cart_volume_30d"],
                item["group_buy_orders_30d"], item["ctr"], item["conversion_rate"], item["refund_orders_30d"],
                item["favorite_count_30d"], item["share_count_30d"], item["impression_volume_30d"], item["cpc"],
                item["gmv_30d"], item["inventory_status"], item["launch_stage"], item["trend_signal"],
                json.dumps(item["title_tags"], ensure_ascii=False), created_at, created_at,
            )
            for item in skus
        ])

        shop_daily_rows.extend(_build_shop_daily_rows(rng, shop_id, total_revenue, safe_days, created_at))
        style_daily_rows.extend(_build_style_daily_rows(rng, skus, safe_days, created_at))

        username = f"merchant_{index:04d}"
        account = MerchantAccount(
            username=username,
            password_hash=_hash_password(DEFAULT_PASSWORD),
            shop_id=shop_id,
            shop_name=shop_name,
            display_name=f"{shop_name} 商家",
            enabled_for_portal=1 if enable_portal_accounts else 0,
        )
        accounts.append((account.username, account.password_hash, account.shop_id, account.shop_name, account.display_name, account.role, account.enabled_for_portal, created_at, created_at))
        if len(sample_accounts) < 12:
            sample_accounts.append({"username": username, "password": DEFAULT_PASSWORD, "shop_id": shop_id, "shop_name": shop_name})

    conn.executemany(
        """
        INSERT INTO merchant_profiles(
            shop_id, shop_name, city, district, style, style_name, rating, review_count, avg_ticket,
            monthly_revenue, repeat_customer_rate, refund_rate, complaint_rate, store_status,
            hero_sku_id, hero_sku_name, owner_name, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        profiles,
    )
    conn.executemany(
        """
        INSERT INTO merchant_style_catalog(
            shop_id, style_id, style_name, category, price, cost, duration_minutes, search_volume_30d,
            click_volume_30d, cart_volume_30d, group_buy_orders_30d, ctr, conversion_rate, refund_orders_30d,
            favorite_count_30d, share_count_30d, impression_volume_30d, cpc, gmv_30d, inventory_status,
            launch_stage, trend_signal, title_tags, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        style_rows,
    )
    conn.executemany(
        """
        INSERT INTO merchant_shop_daily_metrics(
            shop_id, date, search_volume, click_volume, consultation_volume, group_buy_orders, revenue,
            ad_spend, repeat_orders, refund_orders, favorites_added, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        shop_daily_rows,
    )
    conn.executemany(
        """
        INSERT INTO merchant_style_daily_metrics(
            shop_id, style_id, date, search_volume, click_volume, group_buy_orders, favorites_added, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        style_daily_rows,
    )
    conn.executemany(
        """
        INSERT INTO merchant_accounts(
            username, password_hash, shop_id, shop_name, display_name, role, enabled_for_portal, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        accounts,
    )
    conn.commit()
    conn.close()

    summary = {
        "generated_at": created_at,
        "merchant_count": safe_count,
        "styles_total": len(style_rows),
        "style_daily_rows": len(style_daily_rows),
        "shop_daily_rows": len(shop_daily_rows),
        "portal_accounts_enabled": enable_portal_accounts,
        "default_password": DEFAULT_PASSWORD,
        "sample_accounts": sample_accounts,
        "tables": [
            "merchant_accounts",
            "merchant_profiles",
            "merchant_style_catalog",
            "merchant_shop_daily_metrics",
            "merchant_style_daily_metrics",
        ],
    }
    with open(os.path.join(data_dir, DATASET_SUMMARY_FILENAME), "w", encoding="utf-8") as fp:
        json.dump(summary, fp, ensure_ascii=False, indent=2)
    return summary


def get_dataset_summary(base_dir: str) -> dict[str, Any] | None:
    path = os.path.join(base_dir, "data", DATASET_SUMMARY_FILENAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def get_merchant_dataset_overview(base_dir: str) -> dict[str, Any]:
    db_path = os.path.join(base_dir, "data", "jiaqu.db")
    if not os.path.exists(db_path):
        return {
            "summary": get_dataset_summary(base_dir),
            "totals": {
                "merchants": 0,
                "styles": 0,
                "shop_daily_rows": 0,
                "style_daily_rows": 0,
                "portal_accounts": 0,
            },
            "cities": [],
            "styles": [],
        }
    ensure_merchant_data_schema(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    totals = {
        "merchants": conn.execute("SELECT COUNT(*) FROM merchant_profiles").fetchone()[0],
        "styles": conn.execute("SELECT COUNT(*) FROM merchant_style_catalog").fetchone()[0],
        "shop_daily_rows": conn.execute("SELECT COUNT(*) FROM merchant_shop_daily_metrics").fetchone()[0],
        "style_daily_rows": conn.execute("SELECT COUNT(*) FROM merchant_style_daily_metrics").fetchone()[0],
        "portal_accounts": conn.execute("SELECT COUNT(*) FROM merchant_accounts WHERE enabled_for_portal = 1").fetchone()[0],
    }
    cities = [
        dict(row)
        for row in conn.execute(
            "SELECT city, COUNT(*) AS merchant_count FROM merchant_profiles GROUP BY city ORDER BY merchant_count DESC, city ASC"
        ).fetchall()
    ]
    styles = [
        dict(row)
        for row in conn.execute(
            "SELECT style, style_name, COUNT(*) AS merchant_count FROM merchant_profiles GROUP BY style, style_name ORDER BY merchant_count DESC, style ASC"
        ).fetchall()
    ]
    conn.close()
    return {
        "summary": get_dataset_summary(base_dir),
        "totals": totals,
        "cities": cities,
        "styles": styles,
    }


def list_generated_merchants(
    base_dir: str,
    page: int = 1,
    page_size: int = 24,
    query: str = "",
    city: str = "",
    style: str = "",
) -> dict[str, Any]:
    db_path = os.path.join(base_dir, "data", "jiaqu.db")
    if not os.path.exists(db_path):
        return {"items": [], "page": 1, "page_size": 24, "total": 0}
    ensure_merchant_data_schema(db_path)
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or 24), 100))
    safe_query = str(query or "").strip()
    safe_city = str(city or "").strip()
    safe_style = str(style or "").strip()

    where = []
    params: list[Any] = []
    if safe_query:
        where.append("(p.shop_id LIKE ? OR p.shop_name LIKE ? OR COALESCE(a.username, '') LIKE ?)")
        keyword = f"%{safe_query}%"
        params.extend([keyword, keyword, keyword])
    if safe_city:
        where.append("p.city = ?")
        params.append(safe_city)
    if safe_style:
        where.append("(p.style = ? OR p.style_name = ?)")
        params.extend([safe_style, safe_style])
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    total = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM merchant_profiles p
        LEFT JOIN (
            SELECT shop_id, MIN(username) AS username, MAX(enabled_for_portal) AS enabled_for_portal
            FROM merchant_accounts
            GROUP BY shop_id
        ) a ON a.shop_id = p.shop_id
        {where_sql}
        """,
        params,
    ).fetchone()[0]

    rows = conn.execute(
        f"""
        SELECT
            p.shop_id,
            p.shop_name,
            p.city,
            p.district,
            p.style,
            p.style_name,
            p.rating,
            p.review_count,
            p.avg_ticket,
            p.monthly_revenue,
            p.repeat_customer_rate,
            p.refund_rate,
            p.complaint_rate,
            p.hero_sku_name,
            COALESCE(a.username, '') AS username,
            COALESCE(a.enabled_for_portal, 0) AS enabled_for_portal,
            COALESCE(stats.style_count, 0) AS style_count,
            COALESCE(stats.search_volume_30d, 0) AS search_volume_30d,
            COALESCE(stats.click_volume_30d, 0) AS click_volume_30d,
            COALESCE(stats.group_buy_orders_30d, 0) AS group_buy_orders_30d,
            COALESCE(stats.gmv_30d, 0) AS gmv_30d,
            COALESCE(stats.avg_ctr, 0) AS avg_ctr,
            COALESCE(stats.avg_conversion_rate, 0) AS avg_conversion_rate
        FROM merchant_profiles p
        LEFT JOIN (
            SELECT shop_id, MIN(username) AS username, MAX(enabled_for_portal) AS enabled_for_portal
            FROM merchant_accounts
            GROUP BY shop_id
        ) a ON a.shop_id = p.shop_id
        LEFT JOIN (
            SELECT
                shop_id,
                COUNT(*) AS style_count,
                SUM(search_volume_30d) AS search_volume_30d,
                SUM(click_volume_30d) AS click_volume_30d,
                SUM(group_buy_orders_30d) AS group_buy_orders_30d,
                SUM(gmv_30d) AS gmv_30d,
                AVG(ctr) AS avg_ctr,
                AVG(conversion_rate) AS avg_conversion_rate
            FROM merchant_style_catalog
            GROUP BY shop_id
        ) stats ON stats.shop_id = p.shop_id
        {where_sql}
        ORDER BY p.monthly_revenue DESC, p.rating DESC, p.shop_id ASC
        LIMIT ? OFFSET ?
        """,
        [*params, safe_page_size, (safe_page - 1) * safe_page_size],
    ).fetchall()
    conn.close()
    return {
        "items": [dict(row) for row in rows],
        "page": safe_page,
        "page_size": safe_page_size,
        "total": int(total),
    }


def get_generated_merchant_detail(
    base_dir: str,
    shop_id: str,
    style_limit: int = 16,
    daily_limit: int = 14,
) -> dict[str, Any] | None:
    db_path = os.path.join(base_dir, "data", "jiaqu.db")
    if not os.path.exists(db_path):
        return None
    ensure_merchant_data_schema(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    profile = conn.execute(
        """
        SELECT shop_id, shop_name, city, district, style, style_name, rating, review_count, avg_ticket,
               monthly_revenue, repeat_customer_rate, refund_rate, complaint_rate, store_status,
               hero_sku_id, hero_sku_name, owner_name, created_at, updated_at
        FROM merchant_profiles
        WHERE shop_id = ?
        """,
        (str(shop_id or "").strip(),),
    ).fetchone()
    if not profile:
        conn.close()
        return None

    account = conn.execute(
        """
        SELECT username, shop_id, shop_name, display_name, enabled_for_portal
        FROM merchant_accounts
        WHERE shop_id = ?
        ORDER BY username ASC
        LIMIT 1
        """,
        (shop_id,),
    ).fetchone()
    totals = conn.execute(
        """
        SELECT
            COUNT(*) AS style_count,
            COALESCE(SUM(search_volume_30d), 0) AS search_volume_30d,
            COALESCE(SUM(click_volume_30d), 0) AS click_volume_30d,
            COALESCE(SUM(cart_volume_30d), 0) AS cart_volume_30d,
            COALESCE(SUM(group_buy_orders_30d), 0) AS group_buy_orders_30d,
            COALESCE(SUM(refund_orders_30d), 0) AS refund_orders_30d,
            COALESCE(SUM(gmv_30d), 0) AS gmv_30d,
            COALESCE(AVG(ctr), 0) AS avg_ctr,
            COALESCE(AVG(conversion_rate), 0) AS avg_conversion_rate
        FROM merchant_style_catalog
        WHERE shop_id = ?
        """,
        (shop_id,),
    ).fetchone()
    top_styles = conn.execute(
        """
        SELECT style_id, style_name, category, price, duration_minutes, search_volume_30d, click_volume_30d,
               cart_volume_30d, group_buy_orders_30d, ctr, conversion_rate, refund_orders_30d,
               favorite_count_30d, share_count_30d, gmv_30d, inventory_status, launch_stage, trend_signal, title_tags
        FROM merchant_style_catalog
        WHERE shop_id = ?
        ORDER BY group_buy_orders_30d DESC, click_volume_30d DESC, search_volume_30d DESC
        LIMIT ?
        """,
        (shop_id, max(1, min(int(style_limit or 16), 40))),
    ).fetchall()
    low_conversion_styles = conn.execute(
        """
        SELECT style_id, style_name, category, price, search_volume_30d, click_volume_30d, group_buy_orders_30d,
               ctr, conversion_rate, refund_orders_30d, trend_signal
        FROM merchant_style_catalog
        WHERE shop_id = ?
        ORDER BY conversion_rate ASC, click_volume_30d DESC, search_volume_30d DESC
        LIMIT 8
        """,
        (shop_id,),
    ).fetchall()
    recent_daily_metrics = conn.execute(
        """
        SELECT date, search_volume, click_volume, consultation_volume, group_buy_orders, revenue,
               ad_spend, repeat_orders, refund_orders, favorites_added
        FROM merchant_shop_daily_metrics
        WHERE shop_id = ?
        ORDER BY date DESC
        LIMIT ?
        """,
        (shop_id, max(1, min(int(daily_limit or 14), 60))),
    ).fetchall()
    conn.close()

    return {
        "profile": dict(profile),
        "account": dict(account) if account else None,
        "totals": dict(totals) if totals else {},
        "top_styles": [_normalize_style_row(dict(row)) for row in top_styles],
        "low_conversion_styles": [_normalize_style_row(dict(row)) for row in low_conversion_styles],
        "recent_daily_metrics": [dict(row) for row in reversed(recent_daily_metrics)],
    }


def authenticate_merchant(base_dir: str, username: str, password: str) -> dict[str, Any] | None:
    account = _load_account(base_dir, username=username)
    if not account:
        return None
    if account["password_hash"] != _hash_password(password):
        return None
    if not int(account.get("enabled_for_portal") or 0):
        return None
    return build_merchant_identity(base_dir, account["shop_id"], username=account["username"])


def build_merchant_identity(base_dir: str, shop_id: str, username: str | None = None) -> dict[str, Any] | None:
    profile = get_merchant_profile(base_dir, shop_id)
    if not profile:
        return None
    return {
        "username": username or f"{shop_id}_merchant",
        "shop_id": profile["shop_id"],
        "shop_name": profile["shop_name"],
        "style": profile["style"],
        "style_name": profile["style_name"],
        "city": profile["city"],
        "district": profile["district"],
        "rating": profile["rating"],
        "avg_ticket": profile["avg_ticket"],
        "source": profile.get("source") or "generated_dataset",
    }


def get_merchant_profile(base_dir: str, shop_id: str) -> dict[str, Any] | None:
    db_path = os.path.join(base_dir, "data", "jiaqu.db")
    if not os.path.exists(db_path):
        return None
    ensure_merchant_data_schema(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT shop_id, shop_name, city, district, style, style_name, rating, review_count, avg_ticket,
               monthly_revenue, repeat_customer_rate, refund_rate, complaint_rate, store_status,
               hero_sku_id, hero_sku_name, owner_name
        FROM merchant_profiles
        WHERE shop_id = ?
        """,
        (shop_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    data = dict(row)
    data["source"] = "generated_dataset"
    return data


def list_portal_accounts(base_dir: str, limit: int = 20) -> list[dict[str, Any]]:
    db_path = os.path.join(base_dir, "data", "jiaqu.db")
    if not os.path.exists(db_path):
        return []
    ensure_merchant_data_schema(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT username, shop_id, shop_name, display_name
        FROM merchant_accounts
        WHERE enabled_for_portal = 1
        ORDER BY username
        LIMIT ?
        """,
        (max(1, min(int(limit or 20), 100)),),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def seed_demo_portal_accounts(base_dir: str, shops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    db_path = os.path.join(base_dir, "data", "jiaqu.db")
    ensure_merchant_data_schema(db_path)
    conn = sqlite3.connect(db_path)
    now = datetime.now(BJT).isoformat()
    seeded = []
    for index, shop in enumerate(shops, start=1):
        username = f"demo_merchant_{index:02d}"
        password_hash = _hash_password(DEFAULT_PASSWORD)
        style = str(shop.get("style") or "A")
        shop_name = str(shop.get("name") or shop["id"])
        conn.execute(
            """
            INSERT INTO merchant_accounts(
                username, password_hash, shop_id, shop_name, display_name, role, enabled_for_portal, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'merchant', 1, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                password_hash=excluded.password_hash,
                shop_id=excluded.shop_id,
                shop_name=excluded.shop_name,
                display_name=excluded.display_name,
                enabled_for_portal=1,
                updated_at=excluded.updated_at
            """,
            (username, password_hash, shop["id"], shop_name, f"{shop_name} 商家", now, now),
        )
        conn.execute(
            """
            INSERT INTO merchant_profiles(
                shop_id, shop_name, city, district, style, style_name, rating, review_count, avg_ticket,
                monthly_revenue, repeat_customer_rate, refund_rate, complaint_rate, store_status,
                hero_sku_id, hero_sku_name, owner_name, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(shop_id) DO UPDATE SET
                shop_name=excluded.shop_name,
                style=excluded.style,
                style_name=excluded.style_name,
                rating=excluded.rating,
                avg_ticket=excluded.avg_ticket,
                updated_at=excluded.updated_at
            """,
            (
                shop["id"],
                shop_name,
                "北京",
                _guess_demo_district(shop_name),
                style,
                _style_name(style),
                float(shop.get("rating") or 4.6),
                320,
                int(shop.get("price_avg") or 198),
                int((shop.get("price_avg") or 198) * 240),
                0.34,
                0.018,
                0.006,
                "active",
                None,
                None,
                f"{shop_name} 店主",
                now,
                now,
            ),
        )
        seeded.append({"username": username, "password": DEFAULT_PASSWORD, "shop_id": shop["id"], "shop_name": shop_name})
    conn.commit()
    conn.close()
    return seeded


def _load_account(base_dir: str, username: str) -> dict[str, Any] | None:
    db_path = os.path.join(base_dir, "data", "jiaqu.db")
    if not os.path.exists(db_path):
        return None
    ensure_merchant_data_schema(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT username, password_hash, shop_id, shop_name, display_name, enabled_for_portal
        FROM merchant_accounts
        WHERE username = ?
        """,
        (str(username or "").strip(),),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _hash_password(password: str) -> str:
    return hashlib.sha256(f"vertex-merchant::{password}".encode("utf-8")).hexdigest()


def _normalize_style_row(row: dict[str, Any]) -> dict[str, Any]:
    tags = row.get("title_tags")
    if isinstance(tags, str):
        try:
            parsed = json.loads(tags)
        except json.JSONDecodeError:
            parsed = []
        row["title_tags"] = parsed if isinstance(parsed, list) else []
    return row


def _build_shop_name(rng: random.Random, district: str) -> str:
    return f"{rng.choice(SHOP_PREFIX)}{district}{rng.choice(SHOP_SUFFIX)}"


def _guess_demo_district(shop_name: str) -> str:
    for token in ("Sanlitun", "Wudaokou", "Guomao", "Wangjing", "Zhongguancun"):
        if token.lower() in shop_name.lower():
            return token
    return "北京"


def _style_name(style_code: str) -> str:
    return {
        "A": "简约清透",
        "B": "甜美可爱",
        "C": "闪耀华丽",
        "D": "冷感暗黑",
        "E": "趋势实验",
    }[style_code]


def _category_ticket(style_code: str, rng: random.Random) -> int:
    ranges = {
        "A": (128, 228),
        "B": (138, 258),
        "C": (188, 368),
        "D": (168, 338),
        "E": (198, 398),
    }
    low, high = ranges[style_code]
    return rng.randint(low, high)


def _build_shop_styles(rng: random.Random, shop_id: str, style_code: str, count: int, created_at: str) -> list[dict[str, Any]]:
    catalog = []
    trend_words = {
        "A": ["冰透", "奶白", "裸粉", "微闪", "极简"],
        "B": ["甜心", "果冻", "蝴蝶结", "奶油", "樱花"],
        "C": ["碎钻", "镜面", "珍珠", "银河", "极光"],
        "D": ["冷灰", "暗夜", "金属", "烟熏", "酒红"],
        "E": ["撞色", "多巴胺", "解构", "未来感", "异形"],
    }
    for index in range(1, count + 1):
        prefix = rng.choice(PRIMARY_STYLES[style_code])
        suffix = rng.choice(trend_words[style_code])
        style_id = f"{shop_id}_sku_{index:03d}"
        style_name = f"{prefix}·{suffix}{index}"
        price = max(88, _category_ticket(style_code, rng) + rng.randint(-40, 60))
        cost = max(38, int(price * rng.uniform(0.28, 0.55)))
        search_volume = rng.randint(180, 6800)
        ctr = round(rng.uniform(0.08, 0.42), 3)
        click_volume = max(30, int(search_volume * ctr))
        cart_volume = max(5, int(click_volume * rng.uniform(0.1, 0.45)))
        conversion_rate = round(rng.uniform(0.03, 0.22), 3)
        orders = max(0, int(click_volume * conversion_rate))
        refund_orders = min(orders, int(orders * rng.uniform(0.0, 0.08)))
        favorite_count = max(0, int(click_volume * rng.uniform(0.08, 0.3)))
        share_count = max(0, int(click_volume * rng.uniform(0.03, 0.18)))
        impression_volume = max(search_volume + rng.randint(100, 3000), int(search_volume * rng.uniform(1.1, 2.4)))
        gmv = price * max(orders - refund_orders, 0)
        catalog.append({
            "shop_id": shop_id,
            "style_id": style_id,
            "style_name": style_name,
            "category": style_code,
            "price": price,
            "cost": cost,
            "duration_minutes": rng.choice([45, 60, 75, 90, 105, 120]),
            "search_volume_30d": search_volume,
            "click_volume_30d": click_volume,
            "cart_volume_30d": cart_volume,
            "group_buy_orders_30d": orders,
            "ctr": ctr,
            "conversion_rate": conversion_rate,
            "refund_orders_30d": refund_orders,
            "favorite_count_30d": favorite_count,
            "share_count_30d": share_count,
            "impression_volume_30d": impression_volume,
            "cpc": round(rng.uniform(0.4, 3.8), 2),
            "gmv_30d": gmv,
            "inventory_status": rng.choice(["normal", "limited", "featured"]),
            "launch_stage": rng.choice(["new", "growing", "steady", "declining"]),
            "trend_signal": rng.choice(["up", "flat", "up", "down"]),
            "title_tags": [rng.choice(trend_words[style_code]), rng.choice(["团购主推", "店铺爆款", "春夏新款", "高转化", "门店招牌"])],
            "created_at": created_at,
        })
    return catalog


def _build_shop_daily_rows(rng: random.Random, shop_id: str, monthly_revenue: int, days: int, created_at: str) -> list[tuple[Any, ...]]:
    rows = []
    baseline = max(800, int(monthly_revenue / max(days, 1)))
    for offset in range(days):
        day = (datetime.now(BJT) - timedelta(days=offset)).date().isoformat()
        revenue = max(400, int(baseline * rng.uniform(0.65, 1.35)))
        search = max(80, int(revenue / rng.uniform(2.2, 4.8)))
        click = max(20, int(search * rng.uniform(0.12, 0.35)))
        orders = max(1, int(click * rng.uniform(0.04, 0.16)))
        rows.append((
            shop_id,
            day,
            search,
            click,
            max(4, int(click * rng.uniform(0.08, 0.26))),
            orders,
            revenue,
            max(50, int(revenue * rng.uniform(0.06, 0.2))),
            max(0, int(orders * rng.uniform(0.2, 0.55))),
            max(0, int(orders * rng.uniform(0.0, 0.08))),
            max(1, int(click * rng.uniform(0.03, 0.14))),
            created_at,
        ))
    return rows


def _build_style_daily_rows(rng: random.Random, styles: list[dict[str, Any]], days: int, created_at: str) -> list[tuple[Any, ...]]:
    rows = []
    tracked = styles[: min(12, len(styles))]
    for item in tracked:
        base_search = max(20, int(item["search_volume_30d"] / max(days, 1)))
        base_click = max(5, int(item["click_volume_30d"] / max(days, 1)))
        base_order = max(0, int(item["group_buy_orders_30d"] / max(days, 1)))
        for offset in range(days):
            day = (datetime.now(BJT) - timedelta(days=offset)).date().isoformat()
            search = max(0, int(base_search * rng.uniform(0.55, 1.45)))
            click = max(0, int(base_click * rng.uniform(0.55, 1.45)))
            orders = max(0, int(base_order * rng.uniform(0.35, 1.65)))
            rows.append((
                item["shop_id"],
                item["style_id"],
                day,
                search,
                click,
                orders,
                max(0, int(click * rng.uniform(0.03, 0.18))),
                created_at,
            ))
    return rows
