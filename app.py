import base64
import json
import os
import queue
import sqlite3
import subprocess
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

import requests
from flask import Flask, g, jsonify, request, send_from_directory, session
from services.style_taxonomy import TAG_TO_CAT, CATEGORY_NAMES_MAP
from services.skills import SKILL_MAP
from openai import OpenAI

ARK_API_KEY = os.environ.get("ARK_API_KEY", "")
DEFAULT_MODEL_VERSION = os.environ.get("SEEDREAM_VERSION", "5.0")

MODELS = {
    "4.5": {
        "model_id": "doubao-seedream-4-5-251128",
        "prompt": (
            "图像编辑任务：以第一张图为基底，仅对指甲区域做局部修改。"
            "第一张图是用户真实手部照片，第二张图是美甲款式参考。"
            "【必须逐像素保留】：手部轮廓、五根手指的完整形状与数量、"
            "每根手指的弯曲角度与姿势、皮肤纹理与肤色、戒指、"
            "背景、光照方向、阴影、构图、图像宽高比。"
            "【唯一允许修改】：每根手指甲面的颜色与图案，"
            "参考第二张图的美甲设计逐指替换。"
            "【严禁】：重新生成手部结构、增减手指数量、改变手指姿势、"
            "改变手掌朝向、添加或移除戒指、改变拍摄角度。"
            "如不确定某区域是否为指甲，保持原图不变。"
        ),
    },
    "5.0": {
        "model_id": "doubao-seedream-5-0-260128",
        "prompt": (
            "局部编辑任务：以 image_1 为基底进行精准局部修改。"
            "image_1 是用户的真实手部照片，image_2 是美甲款式参考图。"
            "唯一编辑区域：image_1 中每根手指甲面（指甲盖部分）。"
            "编辑内容：将每片指甲的颜色与图案替换为 image_2 中对应的美甲设计。"
            "严格保持不变：手部轮廓、五指完整、手指姿势、皮肤纹理与肤色、"
            "戒指、袖口、背景、光照、阴影、构图、宽高比。"
            "禁止重新绘制手部任何非指甲区域。如不确定某区域是否为指甲，按原图保留。"
        ),
    },
}

BASE_DIR = "/opt/jiaqu" if os.path.isdir("/opt/jiaqu") else os.path.dirname(os.path.abspath(__file__))
DATA_DIR = f"{BASE_DIR}/data"
RESULTS_DIR = f"{BASE_DIR}/static/results"
UPLOADS_DIR = f"{BASE_DIR}/static/uploads"
NAILS_DIR = f"{BASE_DIR}/static/nails"
STATIC_DIR = f"{BASE_DIR}/static"
HANDS_DIR = f"{BASE_DIR}/static/uploads/hands"

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(HANDS_DIR, exist_ok=True)

LOG_FILE = f"{DATA_DIR}/tryon.jsonl"
DB_PATH = f"{DATA_DIR}/jiaqu.db"

client = OpenAI(
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    api_key=ARK_API_KEY,
)

MOCK_SHOPS = [
    {"id": "shop_001", "name": "Maison Pureté · 三里屯", "style": "A", "rating": 4.8, "distance_km": 0.5, "price_avg": 188, "desc": "简约清透风"},
    {"id": "shop_002", "name": "Fleur Rosé · 五道口", "style": "B", "rating": 4.6, "distance_km": 1.2, "price_avg": 168, "desc": "甜美可爱风"},
    {"id": "shop_003", "name": "Bijou Lumière · 国贸", "style": "C", "rating": 4.9, "distance_km": 2.1, "price_avg": 328, "desc": "华丽璀璨风"},
    {"id": "shop_004", "name": "Noir Atelier · 望京", "style": "D", "rating": 4.7, "distance_km": 1.8, "price_avg": 258, "desc": "暗黑酷飒风"},
    {"id": "shop_005", "name": "L'Avant-Garde · 中关村", "style": "E", "rating": 4.5, "distance_km": 2.5, "price_avg": 298, "desc": "潮流前卫风"},
]

STYLE_CATEGORIES = {
    "nail_01": "A", "nail_10": "A", "nail_13": "A", "nail_14": "A", "nail_23": "A",
    "nail_02": "B", "nail_05": "B", "nail_15": "B", "nail_16": "B", "nail_25": "B",
    "nail_06": "C", "nail_11": "C", "nail_17": "C", "nail_18": "C", "nail_19": "C",
    "nail_03": "D", "nail_08": "D", "nail_09": "D", "nail_12": "D",
    "nail_04": "E", "nail_07": "E", "nail_20": "E", "nail_21": "E", "nail_22": "E", "nail_24": "E",
}

CATEGORY_NAMES = {
    "A": "简约清透", "B": "甜美可爱", "C": "华丽璀璨", "D": "暗黑酷飒", "E": "潮流前卫",
}

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "vertex-merchant-dev-secret")
BJT = timezone(timedelta(hours=8))


def now_iso():
    return datetime.now(BJT).isoformat()


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS hand_originals (
            user_id TEXT PRIMARY KEY,
            image_path TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            style_id TEXT NOT NULL,
            style_url TEXT,
            shop_id TEXT,
            shop_name TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tryon_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            request_id TEXT NOT NULL,
            style_id TEXT,
            hand_image_url TEXT,
            result_image_url TEXT,
            model_version TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_fav_user ON favorites(user_id);
        CREATE INDEX IF NOT EXISTS idx_history_user ON tryon_history(user_id);
        CREATE TABLE IF NOT EXISTS plaza (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            request_id TEXT,
            style_id TEXT,
            result_image_url TEXT NOT NULL,
            caption TEXT DEFAULT '',
            likes INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_plaza_created ON plaza(created_at DESC);
        CREATE TABLE IF NOT EXISTS community_trends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            platform TEXT NOT NULL,
            style_tag TEXT NOT NULL,
            mention_count INTEGER NOT NULL,
            growth_rate REAL NOT NULL,
            sample_posts TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ct_date ON community_trends(date);
        CREATE INDEX IF NOT EXISTS idx_ct_tag ON community_trends(style_tag);
        CREATE TABLE IF NOT EXISTS operation_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_date TEXT NOT NULL,
            metric_type TEXT NOT NULL,
            metric_value REAL NOT NULL,
            style_code TEXT,
            style_tag TEXT,
            color_family TEXT,
            style_category TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_om_date ON operation_metrics(metric_date);
        CREATE INDEX IF NOT EXISTS idx_om_type ON operation_metrics(metric_type);
        CREATE TABLE IF NOT EXISTS gmv_targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period_type TEXT NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            target_value REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS promo_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date TEXT NOT NULL,
            action_type TEXT NOT NULL,
            target_tag TEXT,
            target_style TEXT,
            boost_factor REAL NOT NULL,
            duration_days INTEGER DEFAULT 3,
            expected_gmv_lift REAL,
            actual_gmv_lift REAL,
            description TEXT
        );
        """
    )
    conn.close()


init_db()

try:
    from services.merchant_data_skill import seed_demo_portal_accounts
    seed_demo_portal_accounts(BASE_DIR, MOCK_SHOPS)
except Exception:
    pass


def _merchant_identity_from_mock(shop_id: str, username: str | None = None):
    shop = next((item for item in MOCK_SHOPS if item["id"] == shop_id), None)
    if not shop:
        return None
    return {
        "username": username or f"{shop_id}_merchant",
        "shop_id": shop["id"],
        "shop_name": shop["name"],
        "style": shop["style"],
        "style_name": CATEGORY_NAMES.get(shop["style"], shop["style"]),
        "city": "北京",
        "district": shop["name"].split("-")[-1].strip() if "-" in shop["name"] else "北京",
        "rating": shop["rating"],
        "avg_ticket": shop["price_avg"],
        "source": "mock_demo",
    }


def get_current_merchant(optional: bool = False):
    shop_id = session.get("merchant_shop_id")
    username = session.get("merchant_username")
    if not shop_id:
        if optional:
            return None
        return None
    try:
        from services.merchant_data_skill import build_merchant_identity
        identity = build_merchant_identity(BASE_DIR, shop_id, username=username)
    except Exception:
        identity = None
    if identity:
        return identity
    mock_identity = _merchant_identity_from_mock(shop_id, username=username)
    if mock_identity:
        return mock_identity
    if optional:
        return None
    return None


def log_event(event_type, data):
    record = {"ts": now_iso(), "event": event_type, **data}
    with open(LOG_FILE, "a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_logs():
    if not os.path.exists(LOG_FILE):
        return []
    records = []
    with open(LOG_FILE, encoding="utf-8") as fp:
        for line in fp:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def save_data_url(data_url, path):
    header, b64 = data_url.split(",", 1)
    data = base64.b64decode(b64)
    with open(path, "wb") as fp:
        fp.write(data)
    return data


def _compress_hand_to_jpg(user_id):
    """把 hands/{uid}.png 压成 hands/{uid}.jpg（600×600 q80）。
    沿用 nails 双版本架构：png 原图留作复用源 / AI fallback，jpg 给前端展示。
    带宽 375 KB/s 下 1.5MB hand → 4s，35KB jpg → 0.1s。
    """
    try:
        from PIL import Image
        png_path = f"{HANDS_DIR}/{user_id}.png"
        jpg_path = f"{HANDS_DIR}/{user_id}.jpg"
        if not os.path.exists(png_path):
            return
        with Image.open(png_path) as im:
            im = im.convert("RGB")
            im.thumbnail((600, 600), Image.LANCZOS)
            im.save(jpg_path, "JPEG", quality=80, optimize=True, progressive=True)
    except Exception:
        pass


@app.route("/")
def index():
    resp = send_from_directory(STATIC_DIR, "index.html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@app.route("/admin")
def admin():
    resp = send_from_directory(STATIC_DIR, "admin.html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@app.route("/merchant")
def merchant():
    resp = send_from_directory(STATIC_DIR, "merchant.html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@app.route("/merchant-dataset")
def merchant_dataset():
    resp = send_from_directory(STATIC_DIR, "merchant_dataset.html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@app.route("/health")
def health():
    return jsonify({"status": "ok", "ts": now_iso()})


@app.route("/api/merchant/auth/session")
def merchant_auth_session():
    merchant = get_current_merchant(optional=True)
    if not merchant:
        return jsonify({"authenticated": False})
    return jsonify({"authenticated": True, "merchant": merchant})


@app.route("/api/merchant/auth/login", methods=["POST"])
def merchant_auth_login():
    from services.merchant_data_skill import authenticate_merchant
    data = request.get_json(force=True)
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400
    merchant = authenticate_merchant(BASE_DIR, username=username, password=password)
    if not merchant:
        return jsonify({"error": "账号不存在、密码错误，或当前账号未开放商家端登录"}), 401
    session["merchant_username"] = merchant["username"]
    session["merchant_shop_id"] = merchant["shop_id"]
    return jsonify({"authenticated": True, "merchant": merchant})


@app.route("/api/merchant/auth/logout", methods=["POST"])
def merchant_auth_logout():
    session.pop("merchant_username", None)
    session.pop("merchant_shop_id", None)
    return jsonify({"ok": True})


@app.route("/api/merchant/auth/demo-accounts")
def merchant_auth_demo_accounts():
    from services.merchant_data_skill import list_portal_accounts
    return jsonify({"accounts": list_portal_accounts(BASE_DIR, limit=20)})


@app.route("/api/merchant/data/generate", methods=["POST"])
def merchant_data_generate():
    from services.merchant_data_skill import generate_merchant_dataset_skill
    data = request.get_json(force=True)
    summary = generate_merchant_dataset_skill(
        BASE_DIR,
        merchant_count=int(data.get("merchant_count", 1000)),
        min_styles_per_shop=int(data.get("min_styles_per_shop", 18)),
        max_styles_per_shop=int(data.get("max_styles_per_shop", 36)),
        days=int(data.get("days", 30)),
        seed=int(data.get("seed", 20260606)),
        replace_existing=bool(data.get("replace_existing", True)),
        enable_portal_accounts=bool(data.get("enable_portal_accounts", True)),
    )
    return jsonify(summary)


@app.route("/api/admin/merchant-dataset/summary")
def admin_merchant_dataset_summary():
    from services.merchant_data_skill import get_merchant_dataset_overview
    return jsonify(get_merchant_dataset_overview(BASE_DIR))


@app.route("/api/admin/merchant-dataset/shops")
def admin_merchant_dataset_shops():
    from services.merchant_data_skill import list_generated_merchants
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 24, type=int)
    query = request.args.get("query", "", type=str)
    city = request.args.get("city", "", type=str)
    style = request.args.get("style", "", type=str)
    return jsonify(list_generated_merchants(
        BASE_DIR,
        page=page,
        page_size=page_size,
        query=query,
        city=city,
        style=style,
    ))


@app.route("/api/admin/merchant-dataset/shop/<shop_id>")
def admin_merchant_dataset_shop_detail(shop_id: str):
    from services.merchant_data_skill import get_generated_merchant_detail
    style_limit = request.args.get("style_limit", 16, type=int)
    daily_limit = request.args.get("daily_limit", 14, type=int)
    detail = get_generated_merchant_detail(BASE_DIR, shop_id=shop_id, style_limit=style_limit, daily_limit=daily_limit)
    if not detail:
        return jsonify({"error": "merchant not found"}), 404
    return jsonify(detail)


@app.route("/api/styles")
def list_styles():
    from services.style_taxonomy import STYLE_TO_USER_TAGS
    # 只列 jpg/jpeg 缩略图给前端；png 原图保留给 AI 试戴用（见 /api/tryon nails_orig/）
    files = sorted([f for f in os.listdir(NAILS_DIR) if f.lower().endswith((".jpg", ".jpeg"))])
    styles = []
    for f in files:
        sid = os.path.splitext(f)[0]
        num = sid.replace("nail_", "").lstrip("0") or "0"
        cat = STYLE_CATEGORIES.get(sid, "?")
        styles.append({
            "id": sid,
            "name": f"款式 {num}",
            "url": f"/static/nails/{f}",
            "category": cat,
            "category_name": CATEGORY_NAMES.get(cat, ""),
            "user_tags": STYLE_TO_USER_TAGS.get(sid, []),
        })
    return jsonify(styles)


@app.route("/api/shops")
def list_shops():
    return jsonify(MOCK_SHOPS)


@app.route("/api/shops/for_style")
def shops_for_style():
    """试戴完点「找门店」用：1 家完美匹配主理店 + 2-3 家备选。
    定义：
      primary = 与试戴款 category 严格匹配的店（rating × 距离权重排序取 top 1）
      alternatives = 剩余店里：
        - 用户偏好契合度（favorites/tryon_history 出现过的 category 加分）+ 距离 排序
        - 取 top 2，命中用户偏好 → badge 「你常戴 · X 风格」，否则 「X 风格 · 近」
      自定义款（__custom__ / 用户上传）兜底按距离排前 3 家，文案不承诺风格匹配。
    """
    style_id = request.args.get("style_id", "")
    user_id = request.args.get("user_id", "").strip()

    # 用户偏好的 categories（从 favorites + tryon_history 推断）
    pref_cats = set()
    if user_id and user_id != "anonymous":
        try:
            db = get_db()
            for r in db.execute("SELECT style_id FROM favorites WHERE user_id=?", (user_id,)).fetchall():
                c = STYLE_CATEGORIES.get(r["style_id"])
                if c: pref_cats.add(c)
            for r in db.execute("SELECT style_id FROM tryon_history WHERE user_id=?", (user_id,)).fetchall():
                c = STYLE_CATEGORIES.get(r["style_id"])
                if c: pref_cats.add(c)
        except Exception:
            pass

    # 兜底：自定义款或无法识别的 style_id → 按距离 top 3，不承诺风格匹配
    target_cat = STYLE_CATEGORIES.get(style_id)
    if not target_cat:
        sorted_by_dist = sorted(MOCK_SHOPS, key=lambda s: s["distance_km"])[:3]
        return jsonify({
            "primary": None,
            "alternatives": [
                {**s, "badge": f"{CATEGORY_NAMES.get(s['style'], s['style'])} · {s['distance_km']} km",
                 "badge_kind": "neutral"}
                for s in sorted_by_dist
            ],
            "mode": "custom",
        })

    # 主推：试戴款 category 严格匹配
    matched = [s for s in MOCK_SHOPS if s["style"] == target_cat]
    if matched:
        primary_shop = max(matched, key=lambda s: s["rating"] / (1 + s["distance_km"] * 0.3))
    else:
        primary_shop = None

    # 备选：除主推外的店，按"偏好契合 + 距离"打分取前 2
    rest = [s for s in MOCK_SHOPS if not primary_shop or s["id"] != primary_shop["id"]]
    def alt_score(s):
        pref_bonus = 3.0 if s["style"] in pref_cats else 0.0
        return pref_bonus + s["rating"] / (1 + s["distance_km"] * 0.3)
    alternatives = sorted(rest, key=alt_score, reverse=True)[:2]

    def badge_for_alt(s):
        cat_name = CATEGORY_NAMES.get(s["style"], s["style"])
        if s["style"] in pref_cats:
            return {"badge": f"你常戴 · {cat_name}", "badge_kind": "pref"}
        return {"badge": f"{cat_name} · {s['distance_km']} km", "badge_kind": "neutral"}

    return jsonify({
        "primary": {
            **primary_shop,
            "badge": f"完美匹配 · {CATEGORY_NAMES.get(target_cat, target_cat)}",
            "badge_kind": "primary",
        } if primary_shop else None,
        "alternatives": [{**s, **badge_for_alt(s)} for s in alternatives],
        "mode": "matched",
        "target_category_name": CATEGORY_NAMES.get(target_cat, target_cat),
    })


@app.route("/api/styles/tags")
def list_user_style_tags():
    """C 端细分筛选 chip 用：13 个用户视角风格 tag 列表 + 每个 tag 命中款数。"""
    from services.style_taxonomy import USER_STYLE_TAGS, STYLE_TO_USER_TAGS
    counts = {}
    for sid, tags in STYLE_TO_USER_TAGS.items():
        for t in tags:
            counts[t] = counts.get(t, 0) + 1
    return jsonify([{"tag": t, "count": counts.get(t, 0)} for t in USER_STYLE_TAGS])


@app.route("/api/tryon", methods=["POST"])
def tryon():
    data = request.get_json(force=True)
    hand_image = data.get("hand_image")
    style_id = data.get("style_id")
    custom_style_image = data.get("custom_style_image")
    user_id = data.get("user_id", "anonymous")
    nickname = data.get("nickname", "")
    model_version = data.get("model_version", DEFAULT_MODEL_VERSION)
    if model_version not in MODELS:
        model_version = DEFAULT_MODEL_VERSION
    if not hand_image:
        return jsonify({"error": "missing hand_image"}), 400
    if not style_id and not custom_style_image:
        return jsonify({"error": "missing style_id or custom_style_image"}), 400

    request_id = uuid.uuid4().hex[:12]
    model_cfg = MODELS[model_version]
    style_path = None
    style_label = style_id or "custom"
    style_kind = "custom" if custom_style_image else "preset"

    try:
        save_data_url(hand_image, f"{UPLOADS_DIR}/{request_id}_hand.png")
        if custom_style_image:
            style_data_url = custom_style_image
            save_data_url(custom_style_image, f"{UPLOADS_DIR}/{request_id}_style.png")
        else:
            # 优先用高清原图（nails_orig）给 AI 试戴，缩略图（nails）只给前端展示
            orig_dir = f"{BASE_DIR}/static/nails_orig"
            for ext in ("png", "jpg", "jpeg"):
                p = f"{orig_dir}/{style_id}.{ext}"
                if os.path.exists(p):
                    style_path = p
                    break
            if not style_path:
                for ext in ("png", "jpg", "jpeg"):
                    p = f"{NAILS_DIR}/{style_id}.{ext}"
                    if os.path.exists(p):
                        style_path = p
                        break
            if not style_path:
                return jsonify({"error": f"style {style_id} not found"}), 404
            with open(style_path, "rb") as fp:
                style_data_url = "data:image/png;base64," + base64.b64encode(fp.read()).decode()

        if user_id != "anonymous":
            hand_orig_path = f"{HANDS_DIR}/{user_id}.png"
            save_data_url(hand_image, hand_orig_path)
            _compress_hand_to_jpg(user_id)
            db = get_db()
            db.execute(
                "INSERT INTO hand_originals(user_id, image_path, updated_at) VALUES(?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET image_path=excluded.image_path, updated_at=excluded.updated_at",
                (user_id, f"/static/uploads/hands/{user_id}.png", now_iso()),
            )
            db.commit()
    except Exception:
        pass

    log_event("tryon_start", {
        "request_id": request_id,
        "user_id": user_id,
        "nickname": nickname,
        "style_id": style_label,
        "style_kind": style_kind,
        "model_version": model_version,
    })

    t0 = time.time()
    try:
        resp = client.images.generate(
            model=model_cfg["model_id"],
            prompt=model_cfg["prompt"],
            size="2k",
            extra_body={"image": [hand_image, style_data_url], "watermark": False},
            n=1,
        )
        img_data = requests.get(resp.data[0].url, timeout=30).content
        result_filename = f"{request_id}.png"
        result_png_path = f"{RESULTS_DIR}/{result_filename}"
        with open(result_png_path, "wb") as fp:
            fp.write(img_data)
        # 顺手压一份 jpg 缩略图给 plaza grid 用（png 原图留给下载/分享）
        try:
            from PIL import Image
            with Image.open(result_png_path) as im:
                im = im.convert("RGB")
                im.thumbnail((800, 800), Image.LANCZOS)
                im.save(result_png_path[:-4] + ".jpg", "JPEG", quality=80, optimize=True, progressive=True)
        except Exception:
            pass
        latency = int((time.time() - t0) * 1000)
        result_url = f"/static/results/{result_filename}"
        log_event("tryon_success", {
            "request_id": request_id,
            "user_id": user_id,
            "nickname": nickname,
            "style_id": style_label,
            "style_kind": style_kind,
            "model_version": model_version,
            "latency_ms": latency,
            "result_url": result_url,
        })
        if user_id != "anonymous":
            db = get_db()
            style_url = f"/static/nails/{os.path.basename(style_path)}" if style_path else f"/static/uploads/{request_id}_style.png"
            db.execute(
                "INSERT INTO tryon_history(user_id, request_id, style_id, hand_image_url, result_image_url, model_version, created_at) "
                "VALUES(?, ?, ?, ?, ?, ?, ?)",
                (user_id, request_id, style_label, f"/static/uploads/{request_id}_hand.png", result_url, model_version, now_iso()),
            )
            db.commit()
        return jsonify({"request_id": request_id, "result_url": result_url, "latency_ms": latency})
    except Exception as exc:
        log_event("tryon_error", {
            "request_id": request_id,
            "user_id": user_id,
            "nickname": nickname,
            "style_id": style_label,
            "style_kind": style_kind,
            "model_version": model_version,
            "error": str(exc),
        })
        return jsonify({"error": str(exc)}), 500


@app.route("/api/feedback", methods=["POST"])
def feedback():
    data = request.get_json(force=True)
    user_id = data.get("user_id", "anonymous")
    style_id = data.get("style_id")
    shop_id = data.get("shop_id", "")
    action = data.get("action")
    log_event("feedback", {
        "request_id": data.get("request_id"),
        "user_id": user_id,
        "nickname": data.get("nickname", ""),
        "style_id": style_id,
        "action": action,
        "shop_id": shop_id,
    })
    if action == "like" and user_id != "anonymous" and style_id:
        db = get_db()
        style_url = ""
        for ext in ("png", "jpg", "jpeg"):
            if os.path.exists(f"{NAILS_DIR}/{style_id}.{ext}"):
                style_url = f"/static/nails/{style_id}.{ext}"
                break
        shop_name = next((s["name"] for s in MOCK_SHOPS if s["id"] == shop_id), "")
        existing = db.execute("SELECT id FROM favorites WHERE user_id=? AND style_id=?", (user_id, style_id)).fetchone()
        if not existing:
            db.execute(
                "INSERT INTO favorites(user_id, style_id, style_url, shop_id, shop_name, created_at) VALUES(?, ?, ?, ?, ?, ?)",
                (user_id, style_id, style_url, shop_id, shop_name, now_iso()),
            )
            db.commit()
    return jsonify({"ok": True})


@app.route("/api/user/check")
def user_check():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "missing user_id"}), 400
    db = get_db()
    hand = db.execute("SELECT updated_at FROM hand_originals WHERE user_id=?", (user_id,)).fetchone()
    history_count = db.execute("SELECT COUNT(*) FROM tryon_history WHERE user_id=?", (user_id,)).fetchone()[0]
    fav_count = db.execute("SELECT COUNT(*) FROM favorites WHERE user_id=?", (user_id,)).fetchone()[0]
    return jsonify({
        "exists": bool(hand or history_count or fav_count),
        "has_hand": bool(hand),
        "hand_updated_at": hand["updated_at"] if hand else None,
        "history_count": history_count,
        "fav_count": fav_count,
    })


@app.route("/api/user/migrate", methods=["POST"])
def user_migrate():
    data = request.get_json(force=True)
    old_id = data.get("old_id")
    new_id = data.get("new_id")
    if not old_id or not new_id or old_id == new_id:
        return jsonify({"error": "invalid params"}), 400
    db = get_db()
    db.execute("UPDATE hand_originals SET user_id=? WHERE user_id=?", (new_id, old_id))
    db.execute("UPDATE favorites SET user_id=? WHERE user_id=?", (new_id, old_id))
    db.execute("UPDATE tryon_history SET user_id=? WHERE user_id=?", (new_id, old_id))
    db.commit()
    old_hand = os.path.join(HANDS_DIR, f"{old_id}.png")
    new_hand = os.path.join(HANDS_DIR, f"{new_id}.png")
    if os.path.exists(old_hand):
        os.rename(old_hand, new_hand)
        # 同步 rename / 重新生成 jpg
        old_jpg = os.path.join(HANDS_DIR, f"{old_id}.jpg")
        new_jpg = os.path.join(HANDS_DIR, f"{new_id}.jpg")
        if os.path.exists(old_jpg):
            os.rename(old_jpg, new_jpg)
        else:
            _compress_hand_to_jpg(new_id)
        db.execute("UPDATE hand_originals SET image_path=? WHERE user_id=?", (f"/static/uploads/hands/{new_id}.png", new_id))
        db.commit()
    log_event("user_migrate", {"old_id": old_id, "new_id": new_id})
    return jsonify({"ok": True})


@app.route("/api/user/hand")
def user_hand():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "missing user_id"}), 400
    row = get_db().execute("SELECT image_path, updated_at FROM hand_originals WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        return jsonify({"image_path": None})
    # 展示用 jpg 缩略图（如果存在）；DB 字段保留 png 不动，符合"原图必保存"约定
    image_path = row["image_path"]
    jpg_disk = os.path.join(HANDS_DIR, f"{user_id}.jpg")
    if os.path.exists(jpg_disk):
        image_path = f"/static/uploads/hands/{user_id}.jpg"
    return jsonify({"image_path": image_path, "updated_at": row["updated_at"]})


@app.route("/api/user/favorites")
def user_favorites_list():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "missing user_id"}), 400
    rows = get_db().execute(
        "SELECT id, style_id, style_url, shop_id, shop_name, created_at FROM favorites WHERE user_id=? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/user/favorites", methods=["POST"])
def user_favorites_add():
    data = request.get_json(force=True)
    user_id = data.get("user_id")
    style_id = data.get("style_id")
    if not user_id or not style_id:
        return jsonify({"error": "missing user_id or style_id"}), 400
    shop_id = data.get("shop_id", "")
    shop_name = data.get("shop_name") or next((s["name"] for s in MOCK_SHOPS if s["id"] == shop_id), "")
    db = get_db()
    existing = db.execute("SELECT id FROM favorites WHERE user_id=? AND style_id=? AND shop_id=?", (user_id, style_id, shop_id)).fetchone()
    if existing:
        return jsonify({"ok": True, "id": existing["id"], "already_exists": True})
    cur = db.execute(
        "INSERT INTO favorites(user_id, style_id, style_url, shop_id, shop_name, created_at) VALUES(?, ?, ?, ?, ?, ?)",
        (user_id, style_id, data.get("style_url", ""), shop_id, shop_name, now_iso()),
    )
    db.commit()
    return jsonify({"ok": True, "id": cur.lastrowid})


@app.route("/api/user/favorites/<int:fav_id>", methods=["DELETE"])
def user_favorites_delete(fav_id):
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "missing user_id"}), 400
    db = get_db()
    db.execute("DELETE FROM favorites WHERE id=? AND user_id=?", (fav_id, user_id))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/user/history")
def user_history():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "missing user_id"}), 400
    rows = get_db().execute(
        "SELECT id, request_id, style_id, hand_image_url, result_image_url, model_version, created_at "
        "FROM tryon_history WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
        (user_id,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])



@app.route('/api/user/recommend')
def user_recommend():
    """
    个性化推荐 Skill —— 统一打分 + 三档切权重 + 强制可解释。

    分档（按个人信号强度）：
      signal = |favorites| + |history| + |likes|
      cold:  signal == 0   —— 外部爆款 + 站内验证款主导
      warm:  signal == 1   —— 个性 + trend 五五开
      hot:   signal >= 2   —— 个性主导（基于真实用户分布: 14 人卡在 2 次）

    打分维度（每维归一化到 [0, 1]）：
      P 个人分类偏好  | F 个人细标签 (MVP=0)  | G 站内 7 天热度 × 好评率
      E 外部社区爬升  | M 广场互动          | S 季节
      减项 N 反感
    """
    user_id = (request.args.get('user_id') or '').strip()
    logs = load_logs()
    now = datetime.now(BJT)
    week_ago = now - timedelta(days=7)

    # ---------- 1. 全局信号（一次循环搞定 G 维度 + 当前用户 like/dislike）----------
    style_likes, style_fb_total, recent_counts = {}, {}, {}
    user_likes, user_dislikes = set(), set()
    for r in logs:
        sid = r.get('style_id')
        if not sid or sid not in STYLE_CATEGORIES:
            continue  # 过滤 'custom' / '用户上传' / 脏数据
        evt = r.get('event')
        if evt == 'feedback':
            action = r.get('action')
            if action in ('like', 'dislike'):
                style_fb_total[sid] = style_fb_total.get(sid, 0) + 1
                if action == 'like':
                    style_likes[sid] = style_likes.get(sid, 0) + 1
                if user_id and (r.get('user_id') == user_id or r.get('nickname') == user_id):
                    (user_likes if action == 'like' else user_dislikes).add(sid)
        elif evt == 'tryon_start':
            try:
                if datetime.fromisoformat(r.get('ts', '')) >= week_ago:
                    recent_counts[sid] = recent_counts.get(sid, 0) + 1
            except (TypeError, ValueError):
                pass

    def like_rate(sid):
        return (style_likes.get(sid, 0) + 1) / (style_fb_total.get(sid, 0) + 2)

    all_sids = list(STYLE_CATEGORIES.keys())
    raw_g = {s: (recent_counts.get(s, 0) + 0.5) * like_rate(s) for s in all_sids}
    max_g = max(raw_g.values()) or 1.0
    G = {s: raw_g[s] / max_g for s in all_sids}

    # ---------- 2. 用户 DB 信号（收藏 + 试戴历史）----------
    fav_sids, history_sids = set(), set()
    if user_id:
        db = get_db()
        fav_sids = {r['style_id'] for r in db.execute(
            "SELECT style_id FROM favorites WHERE user_id=?", (user_id,)
        ).fetchall() if r['style_id'] in STYLE_CATEGORIES}
        history_sids = {r['style_id'] for r in db.execute(
            "SELECT style_id FROM tryon_history WHERE user_id=?", (user_id,)
        ).fetchall() if r['style_id'] in STYLE_CATEGORIES}

    signal_count = len(fav_sids) + len(history_sids) + len(user_likes)
    if signal_count == 0:
        tier = "cold"
        W = {"P": 0.0, "G": 0.25, "E": 0.35, "M": 0.20, "S": 0.15, "lam": 0.0}
    elif signal_count == 1:
        tier = "warm"
        W = {"P": 0.20, "G": 0.20, "E": 0.30, "M": 0.15, "S": 0.10, "lam": 0.5}
    else:
        tier = "hot"
        W = {"P": 0.45, "G": 0.15, "E": 0.15, "M": 0.10, "S": 0.05, "lam": 1.0}

    # ---------- 3. P 维度：个人分类偏好（收藏 +3 / like +2 / 试戴 +1）----------
    cat_w = {}
    for sid in fav_sids:     cat_w[STYLE_CATEGORIES[sid]] = cat_w.get(STYLE_CATEGORIES[sid], 0) + 3
    for sid in user_likes:   cat_w[STYLE_CATEGORIES[sid]] = cat_w.get(STYLE_CATEGORIES[sid], 0) + 2
    for sid in history_sids: cat_w[STYLE_CATEGORIES[sid]] = cat_w.get(STYLE_CATEGORIES[sid], 0) + 1
    sum_cat = sum(cat_w.values()) or 1
    def P(sid):
        return cat_w.get(STYLE_CATEGORIES[sid], 0) / sum_cat

    # ---------- 4. E 维度：外部社区（近 3 天 growth × mention 占比）----------
    e_by_cat = {}   # cat -> score
    e_top_tag = {}  # cat -> 该分类下涨得最猛的细标签（reason 用）
    try:
        rows = get_db().execute("""
            SELECT style_tag,
                   AVG(growth_rate) AS g,
                   SUM(mention_count) AS m
            FROM community_trends
            WHERE date >= date('now','-3 day')
            GROUP BY style_tag
        """).fetchall()
        max_m = max((r['m'] for r in rows), default=0) or 1
        for r in rows:
            tag = r['style_tag']
            cat = TAG_TO_CAT.get(tag)
            if not cat:
                continue
            # growth ∈ [-0.2, 0.22]，映射到 [0, 1]
            g_norm = max(0, (r['g'] + 0.2) / 0.4)
            m_norm = r['m'] / max_m
            score = g_norm * m_norm
            if score > e_by_cat.get(cat, 0):
                e_by_cat[cat] = score
                e_top_tag[cat] = tag
    except Exception:
        pass
    def E(sid):
        return e_by_cat.get(STYLE_CATEGORIES[sid], 0)

    # ---------- 5. M 维度：广场互动（total_likes / 25 截断到 [0,1]）----------
    plaza_likes = {}
    try:
        for r in get_db().execute(
            "SELECT style_id, SUM(likes) AS s FROM plaza "
            "WHERE style_id IS NOT NULL GROUP BY style_id"
        ).fetchall():
            sid = r['style_id']
            if sid in STYLE_CATEGORIES:
                plaza_likes[sid] = r['s'] or 0
    except Exception:
        pass
    def M(sid):
        return min(1.0, plaza_likes.get(sid, 0) / 25.0)

    # ---------- 6. S 维度：季节（按当前月份选标签）----------
    month = now.month
    if month in (5, 6, 7, 8):
        seasonal_tags = {"冰透", "多巴胺撞色", "奶油裸色"}
        season_name = "夏季"
    elif month in (12, 1, 2):
        seasonal_tags = {"雪花", "暗黑金属", "奶咖"}
        season_name = "冬季"
    elif month in (9, 10, 11):
        seasonal_tags = {"美拉德", "奶咖", "暗黑金属"}
        season_name = "秋季"
    else:
        seasonal_tags = {"奶油裸色", "草莓甜心"}
        season_name = "春季"
    seasonal_cats = {TAG_TO_CAT[t] for t in seasonal_tags if t in TAG_TO_CAT}
    def S(sid):
        return 1.0 if STYLE_CATEGORIES[sid] in seasonal_cats else 0.0

    # ---------- 7. 算总分（排除已收藏）----------
    score = {}
    for sid in all_sids:
        if sid in fav_sids:
            continue
        n = 1.0 if sid in user_dislikes else 0.0
        score[sid] = (
            W["P"] * P(sid) +
            W["G"] * G[sid] +
            W["E"] * E(sid) +
            W["M"] * M(sid) +
            W["S"] * S(sid) -
            W["lam"] * n
        )

    # ---------- 8. 排序 + 多样性（同分类最多 2 个）----------
    ranked = sorted(score.keys(), key=lambda s: -score[s])
    picks, cat_count = [], {}
    for sid in ranked:
        c = STYLE_CATEGORIES[sid]
        if cat_count.get(c, 0) >= 2:
            continue
        picks.append(sid)
        cat_count[c] = cat_count.get(c, 0) + 1
        if len(picks) >= 7:
            break
    # 兜底补足 7 个（如果多样性卡得太严）
    if len(picks) < 7:
        for sid in ranked:
            if sid not in picks:
                picks.append(sid)
            if len(picks) >= 7:
                break

    # ---------- 9. reason：选「实际贡献最大」的那个维度作为理由 ----------
    def build_reason(sid):
        c = STYLE_CATEGORIES[sid]
        contribs = [
            ("P", W["P"] * P(sid)),
            ("E", W["E"] * E(sid)),
            ("M", W["M"] * M(sid)),
            ("S", W["S"] * S(sid)),
            ("G", W["G"] * G[sid]),
        ]
        contribs.sort(key=lambda x: -x[1])
        top_dim, top_val = contribs[0]
        if top_val < 0.01:
            return "平台口碑款"
        if top_dim == "P":
            return f"和你喜欢的「{CATEGORY_NAMES[c]}」同风格"
        if top_dim == "E":
            tag = e_top_tag.get(c)
            return f"{tag} 正在小红书爆" if tag else f"外部社区「{CATEGORY_NAMES[c]}」爬升"
        if top_dim == "M":
            n = int(plaza_likes.get(sid, 0))
            return f"广场已被赞 {n} 次"
        if top_dim == "S":
            return f"{season_name}应季款"
        return "平台 7 天口碑榜"

    # ---------- 10. 构造响应（保持数组形态，前端无需大改）----------
    # 同上：只取 jpg 缩略图，避免前端同时拉 png+jpg 两份
    files = {os.path.splitext(f)[0]: f for f in os.listdir(NAILS_DIR)
             if f.lower().endswith(('.jpg', '.jpeg'))}
    result = []
    for sid in picks:
        f = files.get(sid)
        if not f:
            continue
        cat = STYLE_CATEGORIES.get(sid, '')
        num = sid.replace('nail_', '').lstrip('0') or '0'
        result.append({
            "id": sid,
            "name": f"款式 {num}",
            "url": f"/static/nails/{f}",
            "category": cat,
            "category_name": CATEGORY_NAMES.get(cat, ''),
            "reason": build_reason(sid),
            "tier": tier,
        })
    return jsonify(result)


@app.route("/api/user/ai_recommend", methods=["POST"])
def user_ai_recommend():
    """
    AI 深度分析 —— 让 OpenClaw 加载 user-style-analyst skill，
    对单个用户出结构化分析报告。
    成本：每次调用约 10-15s + tokens，所以走用户主动触发。
    """
    import re
    data = request.get_json(force=True) or {}
    user_id = (data.get("user_id") or "").strip()
    if not user_id:
        return jsonify({"error": "user_id 不能为空"}), 400

    prompt = (
        f"你是甲趣用户风格分析师。请严格按 /workspace/skills/user-style-analyst/SKILL.md "
        f"的工作流程，分析用户「{user_id}」并**只**输出一段 JSON（不要 markdown 包装、"
        f"不要解释文字、不要前后缀）。\n\n"
        f"必须步骤（不省略）：\n"
        f"1. sqlite3 /workspace/tryon-data/jiaqu.db 查 favorites / tryon_history "
        f"算 signal_count 和 tier (0=cold, 1=warm, >=2=hot)\n"
        f"2. sqlite3 查 community_trends 近 3 天 group by style_tag，取 top 2 rising + top 2 declining\n"
        f"3. 按 SKILL.md 6 维公式给 25 款 (nail_01..nail_25) 打分，挑 top 7\n"
        f"4. 输出 JSON schema：\n"
        f'{{"user_id":"...", "tier":"...", "signal_count":N, '
        f'"user_profile":{{"summary":"..."}}, '
        f'"external_signal":{{"top_rising":[{{"tag":"...","growth":"+X%"}}], "top_declining":[...]}}, '
        f'"recommendations":[{{"rank":1, "style_id":"nail_XX", '
        f'"title":"猫眼 · 暗夜冰川", "style_tags":["猫眼","独特小众"], '
        f'"reason":"..."}}]}}\n\n'
        f"输出规则（重要，违反则报告无效）：\n"
        f"- title 形如「工艺 · 意象」，2-6 字 + 间隔点 + 2-6 字；工艺取自 style_tags 第一项\n"
        f"- style_tags 必须从这 13 个里选 1-3 个：中短款 / 显白夏天 / 简约高级 / 杏仁款 / "
        f"独特小众 / 猫眼 / 帕斯蒂尔风 / 韩系 / 本甲款 / 多巴胺 / 清冷感 / 甜酷风格 / 裸色系\n"
        f"- recommendations 数组里**相邻两张不能同 A-E 大类**（避免 3 张华丽璀璨连排这种刻意聚堆）\n"
        f"- 不要输出 category / category_name / score / business_insight 字段（已废弃）\n"
        f"- 不要省略 reason 字段。不要编造数据。reason 1-2 句话讲为什么推给这个用户。"
    )

    try:
        result = subprocess.run(
            ["openclaw", "agent", "--message", prompt, "--json",
             "--session-id", f"vertex-user-{user_id}", "--timeout", "240"],
            capture_output=True, text=True, timeout=260,
        )
        if result.returncode != 0:
            return jsonify({"error": f"OpenClaw 调用失败: {result.stderr.strip()[-200:]}"}), 500

        from services.merchant_skills import _normalize_openclaw_result
        normalized = _normalize_openclaw_result(result.stdout.strip())
        reply_val = normalized.get("reply") or result.stdout.strip() or ""

        # OpenClaw 偶尔已经把 reply 解析成 dict，直接用；否则按 string 处理
        parsed = None
        if isinstance(reply_val, dict):
            parsed = reply_val
            reply_text = json.dumps(reply_val, ensure_ascii=False)
        elif isinstance(reply_val, list):
            parsed = {"items": reply_val}
            reply_text = json.dumps(reply_val, ensure_ascii=False)
        else:
            reply_text = str(reply_val)
            try:
                parsed = json.loads(reply_text)
            except (ValueError, TypeError):
                m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", reply_text, re.S)
                if m:
                    try: parsed = json.loads(m.group(1))
                    except (ValueError, TypeError): pass
                if parsed is None:
                    m = re.search(r"(\{[^{}]*\"recommendations\"[\s\S]*\})", reply_text, re.S)
                    if m:
                        try: parsed = json.loads(m.group(1))
                        except (ValueError, TypeError): pass

        return jsonify({
            "user_id": user_id,
            "reply": reply_text,
            "parsed": parsed,
            "progress": normalized.get("progress", []),
        })
    except subprocess.TimeoutExpired:
        return jsonify({"error": "AI 分析超时（>4 分钟）"}), 504
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500



@app.route("/api/admin/stats")
def admin_stats():
    logs = load_logs()
    starts = [r for r in logs if r.get("event") == "tryon_start"]
    successes = [r for r in logs if r.get("event") == "tryon_success"]
    feedbacks = [r for r in logs if r.get("event") == "feedback"]
    likes = [r for r in feedbacks if r.get("action") == "like"]
    dislikes = [r for r in feedbacks if r.get("action") == "dislike"]
    books = [r for r in feedbacks if r.get("action") == "book"]
    style_counts = Counter(r.get("style_id", "?") for r in starts)
    style_likes = Counter(r.get("style_id", "?") for r in likes)
    style_fb_total = Counter(r.get("style_id", "?") for r in feedbacks if r.get("action") in ("like", "dislike"))
    like_rates = {sid: round(style_likes.get(sid, 0) / total * 100, 1) for sid, total in style_fb_total.items() if total}
    shop_counts = Counter(r.get("shop_id", "?") for r in books)
    user_counts = Counter(r.get("nickname") or r.get("user_id", "?") for r in starts)
    latencies = [r.get("latency_ms", 0) for r in successes if r.get("latency_ms")]
    cat_counts = Counter(STYLE_CATEGORIES.get(r.get("style_id", ""), "?") for r in starts)

    # ── DB 数据：用户 + 款式目录 + 商家汇总 ──
    db = get_db()
    # 用户总量
    db_users = db.execute("SELECT COUNT(DISTINCT user_id) FROM tryon_history").fetchone()[0] or 0
    db_favs = db.execute("SELECT COUNT(*) FROM favorites").fetchone()[0] or 0
    db_plaza = db.execute("SELECT COUNT(*) FROM plaza").fetchone()[0] or 0
    # 款式总量
    db_styles_total = 0
    try:
        db_styles_total = db.execute("SELECT COUNT(*) FROM merchant_style_catalog").fetchone()[0] or 0
    except: pass
    # 商家总量 + 月GMV
    db_shops = 0; shop_gmv_total = 0
    try:
        db_shops = db.execute("SELECT COUNT(DISTINCT shop_id) FROM merchant_profiles").fetchone()[0] or 0
        gmv_r = db.execute("SELECT SUM(revenue) FROM merchant_shop_daily_metrics").fetchone()
        shop_gmv_total = int(gmv_r[0]) if gmv_r and gmv_r[0] else 0
    except: pass
    # Top 商家（按营收）
    top_shops_by_rev = []
    try:
        top_shops_by_rev = [[r[0], r[1], r[2]] for r in db.execute(
            "SELECT m.shop_id, m.shop_name, SUM(s.revenue) FROM merchant_shop_daily_metrics s "
            "JOIN merchant_profiles m ON s.shop_id=m.shop_id GROUP BY s.shop_id ORDER BY 3 DESC LIMIT 5"
        ).fetchall()]
    except: pass
    # 款式风格分布
    style_cat_dist = []
    try:
        style_cat_dist = [[r[0], r[1]] for r in db.execute(
            "SELECT category, COUNT(*) FROM merchant_style_catalog GROUP BY category ORDER BY 2 DESC"
        ).fetchall()]
    except: pass

    return jsonify({
        "total_tryons": len(starts),
        "total_success": len(successes),
        "total_likes": len(likes),
        "total_dislikes": len(dislikes),
        "total_books": len(books),
        "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else 0,
        "top_styles": style_counts.most_common(10),
        "like_rates": like_rates,
        "top_shops": shop_counts.most_common(),
        "top_users": user_counts.most_common(10),
        "category_stats": cat_counts.most_common(),
        "category_names": CATEGORY_NAMES,
        # DB 增强数据
        "db_users": db_users,
        "db_favs": db_favs,
        "db_plaza": db_plaza,
        "db_styles_total": db_styles_total,
        "db_shops": db_shops,
        "shop_gmv_total": shop_gmv_total,
        "top_shops_by_rev": top_shops_by_rev,
        "style_cat_dist": style_cat_dist,
    })


def extract_openclaw_reply(raw):
    from services.merchant_skills import _normalize_openclaw_result
    return _normalize_openclaw_result(raw).get("reply")


@app.route("/api/admin/chat", methods=["POST"])
def admin_chat():
    data = request.get_json(force=True)
    user_msg = data.get("message", "")
    if not user_msg:
        return jsonify({"error": "message cannot be empty"}), 400
    try:
        # 意图检测 → 预调 skill 注入数据到 prompt
        augmented_msg = _inject_skill_context(get_db(), user_msg)

        result = subprocess.run(
            ["openclaw", "agent", "--message", augmented_msg, "--json",
             "--session-id", "vertex-admin", "--timeout", "120"],
            capture_output=True, text=True, timeout=130,
        )
        if result.returncode != 0:
            return jsonify({"error": f"OpenClaw error: {result.stderr.strip()[-200:]}"}), 500
        from services.merchant_skills import _normalize_openclaw_result
        normalized = _normalize_openclaw_result(result.stdout.strip())
        return jsonify({
            "reply": normalized.get("reply") or result.stdout.strip() or "No valid AI output.",
            "progress": normalized.get("progress", []),
            "meta": normalized.get("meta"),
            "debug": normalized.get("debug", {}),
        })
    except subprocess.TimeoutExpired:
        return jsonify({"error": "AI response timeout"}), 504
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def _inject_skill_context(db, msg: str) -> str:
    """检测用户意图，预调 skill，把数据注入 prompt"""
    context = ""
    m = msg.lower()

    if any(w in m for w in ["gmv", "营收", "收入", "销售额", "月报", "日报", "完成率"]):
        from services.gmv_data import get_gmv_overview
        d = get_gmv_overview(db)
        context = (f"\n\n[实时GMV数据]\n"
                   f"本月GMV: ¥{d['month_gmv']:,}, 目标: ¥{d['target']:,}, "
                   f"完成率: {d['completion_pct']}%, 缺口: ¥{d['gap']:,}, "
                   f"30天曲线: {[(c['date'][-5:], int(c['gmv']/1000)) for c in d['curve'][-7:]]}")

    if any(w in m for w in ["归因", "拆解", "为什么涨", "为什么跌", "原因"]):
        from services.gmv_data import get_gmv_breakdown
        d = get_gmv_breakdown(db)
        factors = "; ".join(f"{f['name']}贡献¥{f['contribution']:,}" for f in d.get("factors", [])[:4])
        context += (f"\n\n[GMV归因分析]\n{d['narrative']}\n因子: {factors}")

    if any(w in m for w in ["排行", "款式", "哪个款", "最赚钱", "拖后腿", "热门"]):
        from services.gmv_data import get_styles_ranking
        d = get_styles_ranking(db, 8)
        top = "; ".join(f"{s['style_code']}({s['style_tag']}) ¥{s['gmv']:,}" for s in d.get("styles", [])[:5])
        context += f"\n\n[款式GMV排行]\nTop5: {top}"

    if any(w in m for w in ["风险", "异常", "预警", "下滑"]):
        from services.skills.detect_risk import detect_risks
        d = detect_risks(db)
        risks = "; ".join(f"{r['type']}:{r['target']}" for r in d.get("risks", [])[:3])
        context += f"\n\n[风险预警]\n{d['risk_count']}项: {risks}" if risks else ""

    if any(w in m for w in ["建议", "增长", "做什么", "接下来", "推荐", "策略"]):
        from services.gmv_data import get_recommendations
        d = get_recommendations(db)
        recs = "; ".join(f"{r['rank']}.{r['action_type']} +¥{r['expected_lift']:,}" for r in d.get("recommendations", [])[:3])
        context += f"\n\n[GMV增长建议]\n{recs}"

    if any(w in m for w in ["文案", "copy", "banner", "push"]):
        # 从消息中提取款式
        import re
        style_match = re.search(r'(shop_\d+_sku_\d+|nail_\d+)', msg)
        sc = style_match.group(1) if style_match else "nail_03"
        from services.skills.generate_promo_copy import generate_promo_copy
        d = generate_promo_copy(db, sc, channel="banner", tone="playful")
        context += (f"\n\n[文案参考]\n款式:{sc}\n主标题:{d['main_copy']}\n副标题:{d['sub_copy']}\nCTA:{d['cta']}")

    if context:
        return f"{msg}\n\n---\n以下为系统预置的实时运营数据，请基于这些数据回答用户问题，给出具体数字和可执行的建议：{context}"
    return msg


@app.route("/api/merchant/skills")
def merchant_skills():
    from services.merchant_skills import build_merchant_skills
    merchant = get_current_merchant(optional=True)
    if not merchant:
        return jsonify({"error": "请先登录商家账号"}), 401
    shop_id = merchant["shop_id"]
    period_days = int(request.args.get("period_days", "14"))
    try:
        return jsonify(build_merchant_skills(BASE_DIR, shop_id=shop_id, period_days=period_days))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ============ 实时事件管道 ============

_sse_clients = []  # list[queue.Queue]
_sse_lock = threading.Lock()


def _broadcast_event(event_type, payload):
    """向所有 SSE 客户端推送事件"""
    msg = f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
    dead = []
    with _sse_lock:
        for q in _sse_clients:
            try:
                q.put_nowait(msg)
            except Exception:
                dead.append(q)
        for q in dead:
            _sse_clients.remove(q)


@app.route('/api/events/stream')
def events_stream():
    """SSE 端点: 运营看板连接此 URL 接收实时推送"""
    def generate():
        q = queue.Queue()
        with _sse_lock:
            _sse_clients.append(q)
        try:
            # 首条: 当前 GMV 快照
            from services.gmv_data import get_gmv_overview
            snap = get_gmv_overview(get_db())
            yield f"event: snapshot\ndata: {json.dumps(snap, ensure_ascii=False)}\n\n"
            while True:
                try:
                    msg = q.get(timeout=30)
                    yield msg
                except queue.Empty:
                    yield ": heartbeat\n\n"
        except GeneratorExit:
            pass
        finally:
            with _sse_lock:
                if q in _sse_clients:
                    _sse_clients.remove(q)
    return app.response_class(generate(), mimetype='text/event-stream',
                              headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/api/events/push', methods=['POST'])
def events_push():
    """接收商家事件并写入数据库，同时广播给运营端

    事件类型:
      - new_order:   {"event":"new_order","shop_id":"...","style_id":"...","revenue":299}
      - new_style:   {"event":"new_style","shop_id":"...","style_id":"...","style_name":"...","category":"...","price":299}
      - daily_batch: {"event":"daily_batch","shop_id":"...","date":"2026-06-07","revenue":...,"orders":...,"views":...}
      - style_batch: {"event":"style_metric","shop_id":"...","style_id":"...","date":"...","orders":...,"views":...,"favs":...}
    """
    data = request.get_json(force=True)
    event_type = data.get("event", "")
    db = get_db()

    try:
        if event_type == "new_order":
            date_str = data.get("date", datetime.now(BJT).strftime("%Y-%m-%d"))
            sid = data["style_id"]
            shop_id = data["shop_id"]
            rev = data.get("revenue", 0)
            ts = now_iso()

            # 更新店铺日指标 (先查后写，表无 unique 约束)
            existing = db.execute(
                "SELECT id FROM merchant_shop_daily_metrics WHERE shop_id=? AND date=?",
                (shop_id, date_str)).fetchone()
            if existing:
                db.execute(
                    "UPDATE merchant_shop_daily_metrics SET revenue=revenue+?, group_buy_orders=group_buy_orders+1 WHERE id=?",
                    (rev, existing[0]))
            else:
                db.execute(
                    "INSERT INTO merchant_shop_daily_metrics(shop_id,date,revenue,group_buy_orders,search_volume,click_volume,consultation_volume,ad_spend,repeat_orders,refund_orders,favorites_added,created_at) "
                    "VALUES(?,?,?,1,10,5,2,0,0,0,0,?)",
                    (shop_id, date_str, rev, ts))

            # 更新款式日指标
            sexist = db.execute(
                "SELECT id FROM merchant_style_daily_metrics WHERE shop_id=? AND style_id=? AND date=?",
                (shop_id, sid, date_str)).fetchone()
            if sexist:
                db.execute(
                    "UPDATE merchant_style_daily_metrics SET group_buy_orders=group_buy_orders+1, click_volume=click_volume+5 WHERE id=?",
                    (sexist[0],))
            else:
                db.execute(
                    "INSERT INTO merchant_style_daily_metrics(shop_id,style_id,date,search_volume,click_volume,group_buy_orders,favorites_added,created_at) "
                    "VALUES(?,?,?,10,5,1,0,?)",
                    (shop_id, sid, date_str, ts))
            db.commit()

            from services.gmv_data import get_gmv_overview
            snap = get_gmv_overview(db)
            _broadcast_event("gmv_update", snap)
            return jsonify({"ok": True, "action": "new_order"})

        elif event_type == "new_style":
            db.execute("""
                INSERT INTO merchant_style_catalog
                (shop_id, style_id, style_name, category, price, cost, duration_minutes,
                 search_volume_30d, click_volume_30d, cart_volume_30d, group_buy_orders_30d,
                 ctr, conversion_rate, refund_orders_30d, favorite_count_30d, share_count_30d,
                 impression_volume_30d, cpc, gmv_30d, inventory_status, launch_stage, trend_signal, title_tags, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, 45, 0, 0, 0, 0, 0.0, 0.0, 0, 0, 0, 0, 0.0, 0, 'in_stock', 'new', 'stable', '', ?, ?)
            """, (data["shop_id"], data["style_id"], data.get("style_name", ""),
                  data.get("category", ""), data.get("price", 200), data.get("cost", 80),
                  now_iso(), now_iso()))
            db.commit()

            _broadcast_event("new_style", data)
            return jsonify({"ok": True, "action": "new_style"})

        elif event_type == "daily_batch":
            date_str = data.get("date", datetime.now(BJT).strftime("%Y-%m-%d"))
            shop_id = data["shop_id"]
            ts = now_iso()
            existing = db.execute(
                "SELECT id FROM merchant_shop_daily_metrics WHERE shop_id=? AND date=?",
                (shop_id, date_str)).fetchone()
            if existing:
                db.execute(
                    "UPDATE merchant_shop_daily_metrics SET revenue=?, group_buy_orders=?, search_volume=?, click_volume=?, consultation_volume=?, ad_spend=?, repeat_orders=?, refund_orders=?, favorites_added=? WHERE id=?",
                    (data.get("revenue", 0), data.get("orders", 0), data.get("views", 0),
                     data.get("clicks", 0), data.get("consultations", 0), data.get("ad_spend", 0),
                     data.get("repeat_orders", 0), data.get("refund_orders", 0),
                     data.get("favorites", 0), existing[0]))
            else:
                db.execute(
                    "INSERT INTO merchant_shop_daily_metrics(shop_id,date,revenue,group_buy_orders,search_volume,click_volume,consultation_volume,ad_spend,repeat_orders,refund_orders,favorites_added,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (shop_id, date_str, data.get("revenue", 0), data.get("orders", 0),
                     data.get("views", 0), data.get("clicks", 0), data.get("consultations", 0),
                     data.get("ad_spend", 0), data.get("repeat_orders", 0),
                     data.get("refund_orders", 0), data.get("favorites", 0), ts))
            db.commit()

            _broadcast_event("gmv_update", {"date": date_str, "shop_id": data["shop_id"]})
            return jsonify({"ok": True, "action": "daily_batch"})

        else:
            return jsonify({"error": f"Unknown event type: {event_type}"}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============ GMV 运营看板 ============

@app.route('/admin/kpi')
def admin_kpi():
    return send_from_directory(STATIC_DIR, 'admin_kpi.html')


@app.route('/api/admin/gmv_overview')
def gmv_overview():
    from services.gmv_data import get_gmv_overview
    return jsonify(get_gmv_overview(get_db()))


@app.route('/api/admin/gmv_breakdown')
def gmv_breakdown():
    from services.gmv_data import get_gmv_breakdown
    return jsonify(get_gmv_breakdown(get_db()))


@app.route('/api/admin/gmv_top_styles')
def gmv_top_styles():
    from services.gmv_data import get_styles_ranking
    return jsonify(get_styles_ranking(get_db()))


@app.route('/api/admin/gmv_recommend')
def gmv_recommend():
    from services.gmv_data import get_recommendations
    return jsonify(get_recommendations(get_db()))


# ============ Skills API ============

@app.route('/api/admin/skills/<skill_name>')
def skill_endpoint(skill_name):
    fn = SKILL_MAP.get(skill_name)
    if not fn:
        return jsonify({"error": f"Unknown skill: {skill_name}"}), 404
    db = get_db()
    params = {}
    for k, v in request.args.items():
        if v.isdigit():
            params[k] = int(v)
        elif v.replace('.', '', 1).isdigit():
            params[k] = float(v)
        else:
            params[k] = v
    try:
        return jsonify(fn(db, **params))
    except TypeError:
        return jsonify(fn(db))


@app.route("/api/merchant/skills/registry")
def merchant_skills_registry():
    from services.merchant_skills import list_skill_registry
    return jsonify(list_skill_registry())


@app.route("/api/merchant/openclaw/status")
def merchant_openclaw_status():
    from services.merchant_skills import get_openclaw_status
    return jsonify(get_openclaw_status())


@app.route("/api/merchant/custom-skills")
def merchant_custom_skills():
    from services.merchant_skills import list_custom_skills
    merchant = get_current_merchant(optional=True)
    if not merchant:
        return jsonify({"error": "请先登录商家账号"}), 401
    return jsonify({"skills": list_custom_skills(BASE_DIR, shop_id=merchant["shop_id"])})


@app.route("/api/merchant/custom-skills", methods=["POST"])
def merchant_custom_skills_create():
    from services.merchant_skills import create_custom_skill
    merchant = get_current_merchant(optional=True)
    if not merchant:
        return jsonify({"error": "请先登录商家账号"}), 401
    data = request.get_json(force=True)
    message = data.get("message", "")
    if not message:
        return jsonify({"error": "message cannot be empty"}), 400
    try:
        return jsonify(create_custom_skill(
            BASE_DIR,
            message=message,
            shop_id=merchant["shop_id"],
            period_days=int(data.get("period_days", 14)),
            use_openclaw=bool(data.get("use_openclaw", True)),
        ))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/merchant/history")
def merchant_history():
    from services.merchant_skills import list_merchant_history
    merchant = get_current_merchant(optional=True)
    if not merchant:
        return jsonify({"error": "请先登录商家账号"}), 401
    limit = int(request.args.get("limit", "24"))
    return jsonify({"records": list_merchant_history(BASE_DIR, limit=limit, shop_id=merchant["shop_id"])})


@app.route("/api/merchant/history", methods=["POST"])
def merchant_history_save():
    from services.merchant_skills import save_merchant_history
    merchant = get_current_merchant(optional=True)
    if not merchant:
        return jsonify({"error": "请先登录商家账号"}), 401
    data = request.get_json(force=True)
    payload = data.get("payload")
    if not isinstance(payload, dict):
        return jsonify({"error": "payload must be an object"}), 400
    try:
        data["shop_id"] = merchant["shop_id"]
        data["shop_name"] = merchant["shop_name"]
        record = save_merchant_history(BASE_DIR, data)
        return jsonify({"record": record})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/merchant/agent/run-skill", methods=["POST"])
def merchant_agent_run_skill():
    from services.merchant_skills import run_openclaw_skill
    merchant = get_current_merchant(optional=True)
    if not merchant:
        return jsonify({"error": "请先登录商家账号"}), 401
    data = request.get_json(force=True)
    skill_id = data.get("skill_id")
    if not skill_id:
        return jsonify({"error": "missing skill_id"}), 400
    try:
        return jsonify(run_openclaw_skill(
            BASE_DIR,
            skill_id=skill_id,
            shop_id=merchant["shop_id"],
            period_days=int(data.get("period_days", 14)),
            user_message=data.get("message", ""),
            use_openclaw=bool(data.get("use_openclaw", True)),
        ))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/merchant/agent/chat", methods=["POST"])
def merchant_agent_chat():
    from services.merchant_skills import dispatch_openclaw_agent
    merchant = get_current_merchant(optional=True)
    if not merchant:
        return jsonify({"error": "请先登录商家账号"}), 401
    data = request.get_json(force=True)
    message = data.get("message", "")
    if not message:
        return jsonify({"error": "message cannot be empty"}), 400
    try:
        return jsonify(dispatch_openclaw_agent(
            BASE_DIR,
            message=message,
            shop_id=merchant["shop_id"],
            period_days=int(data.get("period_days", 14)),
            use_openclaw=bool(data.get("use_openclaw", True)),
        ))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/plaza/share", methods=["POST"])
def plaza_share():
    data = request.get_json(force=True)
    user_id = data.get("user_id")
    result_image_url = data.get("result_image_url")
    if not user_id or not result_image_url:
        return jsonify({"error": "missing params"}), 400
    db = get_db()
    db.execute(
        "INSERT INTO plaza(user_id, request_id, style_id, result_image_url, caption, created_at) VALUES(?, ?, ?, ?, ?, ?)",
        (user_id, data.get("request_id"), data.get("style_id"), result_image_url, data.get("caption", ""), now_iso()),
    )
    db.commit()
    log_event("plaza_share", {"user_id": user_id, "style_id": data.get("style_id")})
    return jsonify({"ok": True})


@app.route("/api/plaza/feed")
def plaza_feed():
    rows = get_db().execute(
        "SELECT id, user_id, style_id, result_image_url, caption, likes, created_at FROM plaza ORDER BY created_at DESC"
    ).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        # 优先用 jpg 缩略图（scripts/compress_results.py 生成的），原 png 留给用户下载/分享
        url = d.get("result_image_url") or ""
        if url.endswith(".png"):
            jpg_url = url[:-4] + ".jpg"
            jpg_path = f"{BASE_DIR}{jpg_url}"
            if os.path.exists(jpg_path):
                d["result_image_url"] = jpg_url
        items.append(d)
    return jsonify({"items": items, "total": len(items)})


@app.route("/api/plaza/<int:post_id>/like", methods=["POST"])
def plaza_like(post_id):
    db = get_db()
    db.execute("UPDATE plaza SET likes = likes + 1 WHERE id = ?", (post_id,))
    db.commit()
    row = db.execute("SELECT likes FROM plaza WHERE id = ?", (post_id,)).fetchone()
    if not row:
        return jsonify({"error": "post not found"}), 404
    return jsonify({"ok": True, "likes": row["likes"]})


if __name__ == "__main__":
    print(f"Vertex JiaQu started | BASE_DIR={BASE_DIR} | LOG_FILE={LOG_FILE}")
    app.run(host="0.0.0.0", port=5000, debug=False)
