"""
共享基础设施：日期工具、DB 查询封装、款式元数据。

本文件不依赖 Flask（不 import app），所有函数接受 db connection 作为参数，
确保 skill 函数在 pytest 和 Flask 路由中都能直接调用。
"""
import sqlite3
from datetime import date, timedelta

# ── 款式元数据（从 mock_operation_metrics.py 提取，常量化）──
# style_code → (category, tag, base_weight)
STYLE_META = {
    "nail_01": ("A", "冰透", 1.0), "nail_10": ("A", "冰透", 0.8),
    "nail_13": ("A", "冰透", 0.6), "nail_14": ("A", "奶油裸色", 0.7),
    "nail_23": ("A", "奶油裸色", 0.5),
    "nail_02": ("B", "奶咖", 1.0), "nail_05": ("B", "奶咖", 0.8),
    "nail_15": ("B", "奶咖", 0.6), "nail_16": ("B", "草莓甜心", 0.7),
    "nail_25": ("B", "草莓甜心", 0.5),
    "nail_06": ("C", "碎钻", 1.0), "nail_11": ("C", "碎钻", 0.8),
    "nail_17": ("C", "碎钻", 0.6), "nail_18": ("C", "镭射极光", 0.7),
    "nail_19": ("C", "镭射极光", 0.5),
    "nail_03": ("D", "美拉德", 1.0), "nail_08": ("D", "美拉德", 0.8),
    "nail_09": ("D", "暗黑金属", 0.7), "nail_12": ("D", "暗黑金属", 0.5),
    "nail_04": ("E", "多巴胺撞色", 1.0), "nail_07": ("E", "多巴胺撞色", 0.9),
    "nail_20": ("E", "多巴胺撞色", 0.7), "nail_21": ("E", "雪花", 0.6),
    "nail_22": ("E", "雪花", 0.5), "nail_24": ("E", "雪花", 0.4),
}

try:
    from services.style_taxonomy import CATEGORY_NAMES_MAP, TAG_TO_CAT, FINE_TAGS
except ImportError:
    CATEGORY_NAMES_MAP = {
        "A": "简约清透", "B": "甜美可爱", "C": "华丽璀璨",
        "D": "暗黑酷飒", "E": "潮流前卫",
    }
    TAG_TO_CAT = {
        "冰透": "A", "奶油裸色": "A", "奶咖": "B", "草莓甜心": "B",
        "碎钻": "C", "镭射极光": "C", "美拉德": "D", "暗黑金属": "D",
        "雪花": "E", "多巴胺撞色": "E",
    }
    FINE_TAGS = list(TAG_TO_CAT.keys())

CAT_TO_TAGS = {}
for tag, cat in TAG_TO_CAT.items():
    CAT_TO_TAGS.setdefault(cat, []).append(tag)

STYLE_NAME = {code: f"款式 {code.replace('nail_', '').lstrip('0') or '0'}" for code in STYLE_META}


# ── 日期工具 ──

TODAY = date.today()

def parse_period(period: str, ref_date=None):
    """period → (start_date, end_date)"""
    d = ref_date or TODAY
    if period == "today":
        return (d, d)
    elif period == "yesterday":
        y = d - timedelta(days=1)
        return (y, y)
    elif period == "this_week":
        start = d - timedelta(days=d.weekday())
        return (start, d)
    elif period == "last_week":
        end = d - timedelta(days=d.weekday() + 1)
        start = end - timedelta(days=6)
        return (start, end)
    elif period == "this_month":
        return (d.replace(day=1), d)
    elif period == "last_month":
        first_this = d.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        return (last_prev.replace(day=1), last_prev)
    elif period == "last_30_days":
        return (d - timedelta(days=29), d)
    elif period == "last_7_days":
        return (d - timedelta(days=6), d)
    # fallback: this_month
    return (d.replace(day=1), d)


def prev_period(start, end):
    """Given a period (start, end), return the same-length previous period."""
    delta = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=delta - 1)
    return (prev_start, prev_end)


def days_remaining(end):
    """从今天到 end 还剩多少天（含 end）"""
    return max(0, (end - TODAY).days + 1)


# ── DB 查询封装 ──

def query_one(db, sql, params=()):
    """返回单行 dict，无结果返回 {}"""
    row = db.execute(sql, params).fetchone()
    return dict(row) if row else {}


def query_all(db, sql, params=()):
    """返回 list[dict]"""
    return [dict(r) for r in db.execute(sql, params).fetchall()]


def safe_div(a, b):
    """安全除法，b=0 时返回 0"""
    return a / b if b else 0.0


# ── 通用查询 ──

def sum_metric(db, metric_type, start, end, style_code=None):
    """聚合某指标在某时间段的 SUM"""
    if style_code:
        row = db.execute(
            "SELECT SUM(metric_value) FROM operation_metrics "
            "WHERE metric_type=? AND metric_date BETWEEN ? AND ? AND style_code=?",
            (metric_type, start.isoformat(), end.isoformat(), style_code),
        ).fetchone()
    else:
        row = db.execute(
            "SELECT SUM(metric_value) FROM operation_metrics "
            "WHERE metric_type=? AND metric_date BETWEEN ? AND ?",
            (metric_type, start.isoformat(), end.isoformat()),
        ).fetchone()
    return row[0] if row and row[0] else 0.0


def avg_metric(db, metric_type, start, end):
    """聚合某指标在某时间段的 AVG"""
    row = db.execute(
        "SELECT AVG(metric_value) FROM operation_metrics "
        "WHERE metric_type=? AND metric_date BETWEEN ? AND ?",
        (metric_type, start.isoformat(), end.isoformat()),
    ).fetchone()
    return row[0] if row and row[0] else 0.0
