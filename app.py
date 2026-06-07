import base64
import json
import os
import sqlite3
import subprocess
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
    files = sorted([f for f in os.listdir(NAILS_DIR) if f.lower().endswith((".png", ".jpg", ".jpeg"))])
    styles = []
    for f in files:
        sid = os.path.splitext(f)[0]
        num = sid.replace("nail_", "").lstrip("0") or "0"
        cat = STYLE_CATEGORIES.get(sid, "?")
        styles.append({
            "id": sid,
            "name": f"Style {num}",
            "url": f"/static/nails/{f}",
            "category": cat,
            "category_name": CATEGORY_NAMES.get(cat, ""),
        })
    return jsonify(styles)


@app.route("/api/shops")
def list_shops():
    return jsonify(MOCK_SHOPS)


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
        with open(f"{RESULTS_DIR}/{result_filename}", "wb") as fp:
            fp.write(img_data)
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
    return jsonify({"image_path": row["image_path"], "updated_at": row["updated_at"]} if row else {"image_path": None})


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
    files = {os.path.splitext(f)[0]: f for f in os.listdir(NAILS_DIR)
             if f.lower().endswith(('.png', '.jpg', '.jpeg'))}
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
        f'"recommendations":[{{"rank":1, "style_id":"nail_XX", "category":"E", '
        f'"category_name":"潮流前卫", "score":0.42, "reason":"..."}}], '
        f'"business_insight":"..."}}\n\n'
        f"不要省略 reason 字段。不要编造数据。"
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
        result = subprocess.run(
            ["openclaw", "agent", "--message", user_msg, "--json", "--session-id", "vertex-admin", "--timeout", "120"],
            capture_output=True,
            text=True,
            timeout=130,
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


# ============ GMV 运营看板 ============

@app.route('/admin/kpi')
def admin_kpi():
    return send_from_directory(STATIC_DIR, 'admin_kpi.html')


@app.route('/api/admin/gmv_overview')
def gmv_overview():
    db = get_db()

    month_gmv_row = db.execute(
        "SELECT SUM(metric_value) FROM operation_metrics "
        "WHERE metric_type='category_gmv' AND metric_date BETWEEN '2026-06-01' AND '2026-06-04'"
    ).fetchone()
    month_gmv = month_gmv_row[0] or 0

    total_gmv_row = db.execute(
        "SELECT SUM(metric_value) FROM operation_metrics WHERE metric_type='category_gmv'"
    ).fetchone()
    total_gmv = total_gmv_row[0] or 0

    target_row = db.execute(
        "SELECT target_value FROM gmv_targets WHERE period_type='monthly' AND period_start='2026-06-01'"
    ).fetchone()
    target = target_row[0] if target_row else 1500000
    completion_pct = round(month_gmv / target * 100, 1)

    curve_rows = db.execute(
        "SELECT metric_date, metric_value FROM operation_metrics "
        "WHERE metric_type='category_gmv' ORDER BY metric_date"
    ).fetchall()
    curve = [{"date": r[0], "gmv": r[1]} for r in curve_rows]

    recent_dates = [r[0] for r in curve_rows[-7:]]
    recent_vals = [r[1] for r in curve_rows[-7:]]
    if len(recent_vals) >= 2:
        n = len(recent_vals)
        avg_growth = sum(
            (recent_vals[i] - recent_vals[i-1]) / recent_vals[i-1]
            for i in range(1, n)
        ) / (n - 1)
        last_val = recent_vals[-1]
        forecast = last_val * ((1 + avg_growth) ** 26)
        forecast = round(min(forecast, target * 2))
    else:
        forecast = target

    promos = [
        {"date": r[0], "action_type": r[1], "target_tag": r[2],
         "description": r[3]}
        for r in db.execute(
            "SELECT event_date, action_type, target_tag, description FROM promo_events ORDER BY event_date"
        ).fetchall()
    ]

    return jsonify({
        "month_gmv": month_gmv,
        "total_gmv": total_gmv,
        "target": target,
        "completion_pct": completion_pct,
        "gap": target - month_gmv,
        "forecast_end_of_month": forecast,
        "forecast_pct": round(forecast / target * 100, 1),
        "curve": curve,
        "promo_events": promos,
    })


@app.route('/api/admin/gmv_breakdown')
def gmv_breakdown():
    db = get_db()
    date_range = request.args.get('range', 'month')

    if date_range == 'week':
        where = "AND metric_date BETWEEN '2026-05-29' AND '2026-06-04'"
    elif date_range == 'all':
        where = ""
    else:
        where = "AND metric_date BETWEEN '2026-06-01' AND '2026-06-04'"

    def val(mtype):
        r = db.execute(
            f"SELECT SUM(metric_value) FROM operation_metrics WHERE metric_type=? {where}",
            (mtype,),
        ).fetchone()
        return r[0] or 0

    gmv = val("category_gmv")
    orders = val("category_order_count")
    aov = val("category_aov")
    views = val("category_view_count")
    cvr_sum = db.execute(
        f"SELECT AVG(metric_value) FROM operation_metrics WHERE metric_type='category_cvr' {where}",
    ).fetchone()[0] or 0

    def prev_val(mtype):
        r = db.execute(
            "SELECT SUM(metric_value) FROM operation_metrics WHERE metric_type=? "
            "AND metric_date BETWEEN '2026-05-22' AND '2026-05-28'",
            (mtype,),
        ).fetchone()
        return r[0] or 0

    prev_gmv = prev_val("category_gmv")
    prev_orders = prev_val("category_order_count")
    prev_aov = prev_val("category_aov")
    prev_views = prev_val("category_view_count")

    def chg(cur, prev):
        if prev == 0:
            return 0
        return round((cur - prev) / prev * 100, 1)

    prev_cvr_sum = db.execute(
        "SELECT AVG(metric_value) FROM operation_metrics WHERE metric_type='category_cvr' "
        "AND metric_date BETWEEN '2026-05-22' AND '2026-05-28'"
    ).fetchone()[0] or 0

    order_contrib = round((orders - prev_orders) * aov)
    aov_contrib = round((aov - prev_aov) * orders)
    view_contrib = round((views - prev_views) * cvr_sum * aov)
    cvr_contrib = round((cvr_sum - prev_cvr_sum) * views * aov)

    return jsonify({
        "gmv": gmv,
        "orders": orders,
        "aov": round(aov, 2),
        "views": views,
        "cvr": round(cvr_sum, 4),
        "gmv_change_pct": chg(gmv, prev_gmv),
        "orders_change_pct": chg(orders, prev_orders),
        "aov_change_pct": chg(aov, prev_aov),
        "views_change_pct": chg(views, prev_views),
        "cvr_change_pct": chg(cvr_sum, prev_cvr_sum),
        "order_contrib": order_contrib,
        "aov_contrib": aov_contrib,
        "view_contrib": view_contrib,
        "cvr_contrib": cvr_contrib,
    })


@app.route('/api/admin/gmv_top_styles')
def gmv_top_styles():
    db = get_db()

    rows = db.execute("""
        SELECT style_code, style_tag, style_category,
               SUM(CASE WHEN metric_type='style_gmv' THEN metric_value ELSE 0 END) AS gmv,
               SUM(CASE WHEN metric_type='style_view_count' THEN metric_value ELSE 0 END) AS views,
               SUM(CASE WHEN metric_type='style_tryon_count' THEN metric_value ELSE 0 END) AS tryons,
               SUM(CASE WHEN metric_type='style_favorite_count' THEN metric_value ELSE 0 END) AS favorites
        FROM operation_metrics
        WHERE style_code IS NOT NULL
        GROUP BY style_code
        ORDER BY gmv DESC
    """).fetchall()

    total_gmv = sum(r[3] for r in rows)
    result = []
    for r in rows:
        code, tag, cat, gmv, views, tryons, favs = r

        recent = db.execute(
            "SELECT SUM(metric_value) FROM operation_metrics "
            "WHERE style_code=? AND metric_type='style_gmv' AND metric_date BETWEEN '2026-05-29' AND '2026-06-04'",
            (code,),
        ).fetchone()[0] or 0
        prior = db.execute(
            "SELECT SUM(metric_value) FROM operation_metrics "
            "WHERE style_code=? AND metric_type='style_gmv' AND metric_date BETWEEN '2026-05-22' AND '2026-05-28'",
            (code,),
        ).fetchone()[0] or 0
        chg_pct = round((recent - prior) / prior * 100, 1) if prior else 0

        result.append({
            "style_code": code,
            "style_tag": tag,
            "style_category": cat,
            "gmv": gmv,
            "gmv_share_pct": round(gmv / total_gmv * 100, 1) if total_gmv else 0,
            "views": views,
            "tryons": tryons,
            "favorites": favs,
            "change_pct": chg_pct,
        })

    return jsonify({"styles": result, "total_gmv": total_gmv})


@app.route('/api/admin/gmv_recommend')
def gmv_recommend():
    db = get_db()

    month_gmv = db.execute(
        "SELECT SUM(metric_value) FROM operation_metrics "
        "WHERE metric_type='category_gmv' AND metric_date BETWEEN '2026-06-01' AND '2026-06-04'"
    ).fetchone()[0] or 0

    target_row = db.execute(
        "SELECT target_value FROM gmv_targets WHERE period_type='monthly'"
    ).fetchone()
    target = target_row[0] if target_row else 1500000

    top = db.execute("""
        SELECT style_code, style_tag, SUM(metric_value) AS gmv
        FROM operation_metrics
        WHERE metric_type='style_gmv' AND style_code IS NOT NULL
        GROUP BY style_code ORDER BY gmv DESC LIMIT 3
    """).fetchall()

    bottom = db.execute("""
        SELECT style_code, style_tag, SUM(metric_value) AS gmv
        FROM operation_metrics
        WHERE metric_type='style_gmv' AND style_code IS NOT NULL
        GROUP BY style_code ORDER BY gmv ASC LIMIT 3
    """).fetchall()

    promos = db.execute(
        "SELECT description, expected_gmv_lift FROM promo_events ORDER BY event_date DESC LIMIT 3"
    ).fetchall()

    trends = db.execute("""
        SELECT style_tag, ROUND(AVG(growth_rate)*100, 1) AS avg_growth
        FROM community_trends WHERE date >= '2026-06-01'
        GROUP BY style_tag ORDER BY avg_growth DESC LIMIT 5
    """).fetchall()

    gap = target - month_gmv

    recs = []
    rising_tags = [t[0] for t in trends if t[1] > 5]
    declining_tags = [t[0] for t in trends if t[1] < -5]

    if rising_tags:
        top_rising_style = db.execute(
            "SELECT style_code, SUM(metric_value) FROM operation_metrics "
            "WHERE metric_type='style_gmv' AND style_tag=? "
            "GROUP BY style_code ORDER BY SUM(metric_value) DESC LIMIT 1",
            (rising_tags[0],),
        ).fetchone()
        if top_rising_style:
            est_lift = int(gap * 0.25)
            recs.append({
                "action": f"给 {top_rising_style[0]}（{rising_tags[0]}）加 Banner 主推位",
                "expected_gmv_lift": est_lift,
                "cost": "低 · 改配置即可",
                "roi": "高",
                "reason": f"社区 {rising_tags[0]} 热度上升 {trends[0][1]}%，顺势主推变现",
            })

    if declining_tags:
        bottom_declining = db.execute(
            "SELECT style_code, SUM(metric_value) FROM operation_metrics "
            "WHERE metric_type='style_gmv' AND style_tag=? "
            "GROUP BY style_code ORDER BY SUM(metric_value) DESC LIMIT 1",
            (declining_tags[0],),
        ).fetchone()
        if bottom_declining:
            est_lift = int(gap * 0.15)
            recs.append({
                "action": f"对 {bottom_declining[0]}（{declining_tags[0]}）做限时折扣清库存",
                "expected_gmv_lift": est_lift,
                "cost": "中 · 需商家配合",
                "roi": "中",
                "reason": f"{declining_tags[0]} 社区热度跌 {trends[-1][1] if trends else 'N/A'}%，清仓回笼资金",
            })

    recs.append({
        "action": "推美拉德/多巴胺撞色高价款，目标提 AOV 15%",
        "expected_gmv_lift": int(gap * 0.20),
        "cost": "低 · 调整推荐权重",
        "roi": "高",
        "reason": "高价款 AOV ¥240+，CVR 不输平价，利润空间大",
    })

    recs.append({
        "action": "推送通知召回 7 天未活跃用户 + 收藏未试戴用户",
        "expected_gmv_lift": int(gap * 0.15),
        "cost": "低 · Push 一次",
        "roi": "中",
        "reason": "低成本拉回存量用户，预计 CVR 3-5%",
    })

    total_lift = sum(r["expected_gmv_lift"] for r in recs)
    forecast_with_all = month_gmv + total_lift

    return jsonify({
        "month_gmv": month_gmv,
        "target": target,
        "gap": gap,
        "top_styles": [{"code": r[0], "tag": r[1], "gmv": r[2]} for r in top],
        "declining_styles": [{"code": r[0], "tag": r[1], "gmv": r[2]} for r in bottom],
        "recent_promos": [{"desc": r[0], "lift": r[1]} for r in promos],
        "rising_trends": [{"tag": r[0], "growth": r[1]} for r in trends[:3]],
        "recommendations": recs,
        "total_lift_if_all": total_lift,
        "forecast_if_all": forecast_with_all,
        "would_hit_target": forecast_with_all >= target,
    })


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
        "SELECT id, user_id, style_id, result_image_url, caption, likes, created_at FROM plaza ORDER BY RANDOM()"
    ).fetchall()
    return jsonify({"items": [dict(r) for r in rows], "total": len(rows)})


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
