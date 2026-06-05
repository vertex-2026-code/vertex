"""
Vertex · 甲趣 - AI 美甲试戴 Flask 后端
更新:
- 支持自定义款式图上传 (custom_style_image base64)
- Seedream 输出 2K + 自适应比例
- 防止反馈重复提交（前端去重，后端来啥记啥）
"""
import os
import json
import time
import uuid
import base64
import sqlite3
import subprocess
import requests
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify, send_from_directory, g

# ============ 配置 ============
from openai import OpenAI

# ============ 配置 ============
ARK_API_KEY = os.environ.get("ARK_API_KEY", "")

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

DEFAULT_MODEL_VERSION = os.environ.get("SEEDREAM_VERSION", "5.0")

if os.path.isdir("/opt/jiaqu"):
    BASE_DIR = "/opt/jiaqu"
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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

app = Flask(__name__, static_folder='static', static_url_path='/static')


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop('db', None)
    if db:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
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
    """)
    conn.close()


init_db()


BJT = timezone(timedelta(hours=8))


def now_iso():
    return datetime.now(BJT).isoformat()


def log_event(event_type, data):
    record = {"ts": now_iso(), "event": event_type, **data}
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


@app.route('/')
def index():
    resp = send_from_directory(STATIC_DIR, 'index.html')
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return resp


@app.route('/api/styles')
def list_styles():
    files = sorted([f for f in os.listdir(NAILS_DIR)
                    if f.lower().endswith(('.png', '.jpg', '.jpeg'))])
    styles = []
    for f in files:
        sid = os.path.splitext(f)[0]
        num = sid.replace('nail_', '').lstrip('0') or '0'
        cat = STYLE_CATEGORIES.get(sid, '?')
        styles.append({
            "id": sid,
            "name": f"款式 {num}",
            "url": f"/static/nails/{f}",
            "category": cat,
            "category_name": CATEGORY_NAMES.get(cat, ''),
        })
    return jsonify(styles)


@app.route('/api/shops')
def list_shops():
    return jsonify(MOCK_SHOPS)


@app.route('/api/tryon', methods=['POST'])
def tryon():
    """
    执行 AI 试戴
    Body 必须包含:
      - hand_image: 手部图 data URL
      - style_id: 预设款式 id  (与 custom_style_image 二选一)
      - custom_style_image: 自定义款式 data URL  (与 style_id 二选一)
    """
    data = request.get_json(force=True)
    hand_image = data.get('hand_image')
    style_id = data.get('style_id')
    custom_style_image = data.get('custom_style_image')
    user_id = data.get('user_id', 'anonymous')
    nickname = data.get('nickname', '')
    model_version = data.get('model_version', DEFAULT_MODEL_VERSION)
    if model_version not in MODELS:
        model_version = DEFAULT_MODEL_VERSION
    model_cfg = MODELS[model_version]

    if not hand_image:
        return jsonify({"error": "缺少手部照片"}), 400
    if not style_id and not custom_style_image:
        return jsonify({"error": "请选择款式或上传自定义款式图"}), 400

    # 决定第二张参考图：优先用 custom，其次找预设
    if custom_style_image:
        style_data_url = custom_style_image
        style_kind = "custom"
        style_label = "用户上传"
    else:
        style_path = None
        for ext in ('png', 'jpg', 'jpeg'):
            p = f"{NAILS_DIR}/{style_id}.{ext}"
            if os.path.exists(p):
                style_path = p
                break
        if not style_path:
            return jsonify({"error": f"款式 {style_id} 不存在"}), 404

        with open(style_path, 'rb') as f:
            style_b64 = base64.b64encode(f.read()).decode()
        style_data_url = f"data:image/png;base64,{style_b64}"
        style_kind = "preset"
        style_label = style_id

    request_id = uuid.uuid4().hex[:12]
    t0 = time.time()

    def save_upload(data_url, tag):
        try:
            header, b64 = data_url.split(",", 1)
            img_bytes = base64.b64decode(b64)
            path = f"{UPLOADS_DIR}/{request_id}_{tag}.png"
            with open(path, "wb") as fp:
                fp.write(img_bytes)
            return img_bytes
        except Exception:
            return None

    hand_bytes = save_upload(hand_image, "hand")
    if custom_style_image:
        save_upload(custom_style_image, "style")

    # 保存用户最新原始手部图片（覆盖式）
    if hand_bytes and user_id != 'anonymous':
        hand_orig_path = f"{HANDS_DIR}/{user_id}.png"
        try:
            with open(hand_orig_path, "wb") as fp:
                fp.write(hand_bytes)
            db = get_db()
            db.execute(
                "INSERT INTO hand_originals(user_id, image_path, updated_at) "
                "VALUES(?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET "
                "image_path=excluded.image_path, updated_at=excluded.updated_at",
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

    try:
        resp = client.images.generate(
            model=model_cfg["model_id"],
            prompt=model_cfg["prompt"],
            size="2k",
            extra_body={
                "image": [hand_image, style_data_url],
                "watermark": False,
            },
            n=1,
        )
        result_remote_url = resp.data[0].url

        img_data = requests.get(result_remote_url, timeout=30).content
        result_filename = f"{request_id}.png"
        with open(f"{RESULTS_DIR}/{result_filename}", 'wb') as f:
            f.write(img_data)

        latency = int((time.time() - t0) * 1000)

        log_event("tryon_success", {
            "request_id": request_id,
            "user_id": user_id,
            "nickname": nickname,
            "style_id": style_label,
            "style_kind": style_kind,
            "model_version": model_version,
            "latency_ms": latency,
            "result_url": f"/static/results/{result_filename}",
        })

        # 写入试戴历史
        if user_id != 'anonymous':
            try:
                style_url = ""
                if style_kind == "preset" and style_path:
                    style_url = f"/static/nails/{os.path.basename(style_path)}"
                elif style_kind == "custom":
                    style_url = f"/static/uploads/{request_id}_style.png"
                db = get_db()
                db.execute(
                    "INSERT INTO tryon_history"
                    "(user_id, request_id, style_id, hand_image_url, result_image_url, model_version, created_at) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?)",
                    (user_id, request_id, style_label, f"/static/uploads/{request_id}_hand.png",
                     f"/static/results/{result_filename}", model_version, now_iso()),
                )
                db.commit()
            except Exception:
                pass

        return jsonify({
            "request_id": request_id,
            "result_url": f"/static/results/{result_filename}",
            "latency_ms": latency,
        })
    except Exception as e:
        log_event("tryon_error", {
            "request_id": request_id,
            "user_id": user_id,
            "nickname": nickname,
            "style_id": style_label,
            "style_kind": style_kind,
            "model_version": model_version,
            "error": str(e),
        })
        return jsonify({"error": str(e)}), 500


@app.route('/api/feedback', methods=['POST'])
def feedback():
    data = request.get_json(force=True)
    user_id = data.get('user_id', 'anonymous')
    action = data.get('action')
    style_id = data.get('style_id')
    shop_id = data.get('shop_id')

    log_event("feedback", {
        "request_id": data.get('request_id'),
        "user_id": user_id,
        "nickname": data.get('nickname', ''),
        "style_id": style_id,
        "action": action,
        "shop_id": shop_id,
    })

    # 点赞时写入收藏夹
    if action == 'like' and user_id != 'anonymous' and style_id:
        try:
            style_url = ""
            if style_id and style_id != '用户上传':
                for ext in ('png', 'jpg', 'jpeg'):
                    if os.path.exists(f"{NAILS_DIR}/{style_id}.{ext}"):
                        style_url = f"/static/nails/{style_id}.{ext}"
                        break
            db = get_db()
            existing = db.execute(
                "SELECT id FROM favorites WHERE user_id=? AND style_id=?",
                (user_id, style_id),
            ).fetchone()
            if not existing:
                db.execute(
                    "INSERT INTO favorites(user_id, style_id, style_url, shop_id, shop_name, created_at) "
                    "VALUES(?, ?, ?, ?, ?, ?)",
                    (user_id, style_id, style_url, shop_id or "",
                     next((s["name"] for s in MOCK_SHOPS if s["id"] == shop_id), ""),
                     now_iso()),
                )
                db.commit()
        except Exception:
            pass

    return jsonify({"ok": True})


# ============ 用户数据 API ============

@app.route('/api/user/check')
def user_check():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "缺少 user_id"}), 400
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


@app.route('/api/user/migrate', methods=['POST'])
def user_migrate():
    data = request.get_json(force=True)
    old_id = data.get('old_id')
    new_id = data.get('new_id')
    if not old_id or not new_id or old_id == new_id:
        return jsonify({"error": "参数无效"}), 400
    db = get_db()
    db.execute("UPDATE hand_originals SET user_id=? WHERE user_id=?", (new_id, old_id))
    db.execute("UPDATE favorites SET user_id=? WHERE user_id=?", (new_id, old_id))
    db.execute("UPDATE tryon_history SET user_id=? WHERE user_id=?", (new_id, old_id))
    db.commit()
    old_hand = os.path.join(HANDS_DIR, f"{old_id}.png")
    new_hand = os.path.join(HANDS_DIR, f"{new_id}.png")
    if os.path.exists(old_hand):
        os.rename(old_hand, new_hand)
        db.execute("UPDATE hand_originals SET image_path=? WHERE user_id=?",
                   (f"/static/uploads/hands/{new_id}.png", new_id))
        db.commit()
    log_event("user_migrate", {"old_id": old_id, "new_id": new_id})
    return jsonify({"ok": True})


@app.route('/api/user/hand')
def user_hand():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "缺少 user_id"}), 400
    db = get_db()
    row = db.execute("SELECT image_path, updated_at FROM hand_originals WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        return jsonify({"image_path": None})
    return jsonify({"image_path": row["image_path"], "updated_at": row["updated_at"]})


@app.route('/api/user/favorites')
def user_favorites_list():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "缺少 user_id"}), 400
    db = get_db()
    rows = db.execute(
        "SELECT id, style_id, style_url, shop_id, shop_name, created_at "
        "FROM favorites WHERE user_id=? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/user/favorites', methods=['POST'])
def user_favorites_add():
    data = request.get_json(force=True)
    user_id = data.get('user_id')
    style_id = data.get('style_id')
    if not user_id or not style_id:
        return jsonify({"error": "缺少 user_id 或 style_id"}), 400
    style_url = data.get('style_url', '')
    shop_id = data.get('shop_id', '')
    shop_name = data.get('shop_name', '')
    if shop_id and not shop_name:
        shop_name = next((s["name"] for s in MOCK_SHOPS if s["id"] == shop_id), "")
    db = get_db()
    existing = db.execute(
        "SELECT id FROM favorites WHERE user_id=? AND style_id=? AND shop_id=?",
        (user_id, style_id, shop_id),
    ).fetchone()
    if existing:
        return jsonify({"ok": True, "id": existing["id"], "already_exists": True})
    cur = db.execute(
        "INSERT INTO favorites(user_id, style_id, style_url, shop_id, shop_name, created_at) "
        "VALUES(?, ?, ?, ?, ?, ?)",
        (user_id, style_id, style_url, shop_id, shop_name, now_iso()),
    )
    db.commit()
    return jsonify({"ok": True, "id": cur.lastrowid})


@app.route('/api/user/favorites/<int:fav_id>', methods=['DELETE'])
def user_favorites_delete(fav_id):
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "缺少 user_id"}), 400
    db = get_db()
    db.execute("DELETE FROM favorites WHERE id=? AND user_id=?", (fav_id, user_id))
    db.commit()
    return jsonify({"ok": True})


@app.route('/api/user/history')
def user_history():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "缺少 user_id"}), 400
    db = get_db()
    rows = db.execute(
        "SELECT id, request_id, style_id, hand_image_url, result_image_url, model_version, created_at "
        "FROM tryon_history WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
        (user_id,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/health')
def health():
    return jsonify({"status": "ok", "ts": now_iso()})


# ============ B 端运营大屏 ============

def load_logs():
    if not os.path.exists(LOG_FILE):
        return []
    records = []
    with open(LOG_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


@app.route('/admin')
def admin():
    return send_from_directory(STATIC_DIR, 'admin.html')


@app.route('/api/admin/stats')
def admin_stats():
    logs = load_logs()
    starts = [r for r in logs if r.get('event') == 'tryon_start']
    successes = [r for r in logs if r.get('event') == 'tryon_success']
    feedbacks = [r for r in logs if r.get('event') == 'feedback']
    likes = [r for r in feedbacks if r.get('action') == 'like']
    dislikes = [r for r in feedbacks if r.get('action') == 'dislike']
    books = [r for r in feedbacks if r.get('action') == 'book']

    # 款式热度
    style_counts = {}
    for r in starts:
        sid = r.get('style_id', '?')
        style_counts[sid] = style_counts.get(sid, 0) + 1
    top_styles = sorted(style_counts.items(), key=lambda x: -x[1])[:10]

    # 款式喜欢率
    style_likes = {}
    style_fb_total = {}
    for r in feedbacks:
        if r.get('action') in ('like', 'dislike'):
            sid = r.get('style_id', '?')
            style_fb_total[sid] = style_fb_total.get(sid, 0) + 1
            if r.get('action') == 'like':
                style_likes[sid] = style_likes.get(sid, 0) + 1
    like_rates = {}
    for sid, total in style_fb_total.items():
        like_rates[sid] = round(style_likes.get(sid, 0) / total * 100, 1)

    # 门店预约
    shop_counts = {}
    for r in books:
        shop = r.get('shop_id', '?')
        shop_counts[shop] = shop_counts.get(shop, 0) + 1
    top_shops = sorted(shop_counts.items(), key=lambda x: -x[1])

    # 用户活跃度
    user_counts = {}
    for r in starts:
        uid = r.get('nickname') or r.get('user_id', '?')
        user_counts[uid] = user_counts.get(uid, 0) + 1
    top_users = sorted(user_counts.items(), key=lambda x: -x[1])[:10]

    # 平均延迟
    latencies = [r.get('latency_ms', 0) for r in successes if r.get('latency_ms')]
    avg_latency = round(sum(latencies) / len(latencies)) if latencies else 0

    # 风格分类统计（用户上传的 custom 图不属于预设风格分类）
    cat_counts = {}
    for r in starts:
        if r.get('style_kind') == 'custom':
            continue
        cat = STYLE_CATEGORIES.get(r.get('style_id', ''), '?')
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    cat_stats = sorted(cat_counts.items(), key=lambda x: -x[1])

    return jsonify({
        "total_tryons": len(starts),
        "total_success": len(successes),
        "total_likes": len(likes),
        "total_dislikes": len(dislikes),
        "total_books": len(books),
        "avg_latency_ms": avg_latency,
        "top_styles": top_styles,
        "like_rates": like_rates,
        "top_shops": top_shops,
        "top_users": top_users,
        "category_stats": cat_stats,
        "category_names": CATEGORY_NAMES,
    })


@app.route('/api/admin/chat', methods=['POST'])
def admin_chat():
    data = request.get_json(force=True)
    user_msg = data.get('message', '')
    if not user_msg:
        return jsonify({"error": "消息不能为空"}), 400

    try:
        result = subprocess.run(
            ["openclaw", "agent", "--message", user_msg, "--json",
             "--session-id", "vertex-admin", "--timeout", "120"],
            capture_output=True, text=True, timeout=130,
        )
        if result.returncode != 0:
            return jsonify({"error": f"OpenClaw 错误: {result.stderr.strip()[-200:]}"}), 500

        output = result.stdout.strip()

        def extract_reply(raw):
            """从 OpenClaw --json 输出中提取文本，支持数组和对象两种格式"""
            for line in reversed(raw.split("\n")):
                line = line.strip()
                if not (line.startswith("{") or line.startswith("[")):
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, list):
                    texts = [item.get("text", "") for item in parsed if isinstance(item, dict) and item.get("text")]
                    if texts:
                        return texts[-1]
                elif isinstance(parsed, dict):
                    return parsed.get("reply") or parsed.get("content") or parsed.get("message") or parsed.get("text") or str(parsed)
            return None

        reply = extract_reply(output)
        if reply:
            return jsonify({"reply": reply})

        return jsonify({"reply": output or "AI 未返回有效内容，请重试"})
    except subprocess.TimeoutExpired:
        return jsonify({"error": "AI 响应超时，请重试"}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500



# ============ 广场 API ============

@app.route('/api/plaza/share', methods=['POST'])
def plaza_share():
    data = request.get_json(force=True)
    user_id = data.get('user_id')
    result_image_url = data.get('result_image_url')
    if not user_id or not result_image_url:
        return jsonify({"error": "缺少参数"}), 400
    db = get_db()
    db.execute(
        "INSERT INTO plaza(user_id, request_id, style_id, result_image_url, caption, created_at) "
        "VALUES(?, ?, ?, ?, ?, ?)",
        (user_id, data.get('request_id'), data.get('style_id'),
         result_image_url, data.get('caption', ''), now_iso()),
    )
    db.commit()
    log_event("plaza_share", {"user_id": user_id, "style_id": data.get('style_id')})
    return jsonify({"ok": True})


@app.route('/api/plaza/feed')
def plaza_feed():
    db = get_db()
    rows = db.execute(
        "SELECT id, user_id, style_id, result_image_url, caption, likes, created_at "
        "FROM plaza ORDER BY RANDOM()"
    ).fetchall()
    return jsonify({"items": [dict(r) for r in rows], "total": len(rows)})


@app.route('/api/plaza/<int:post_id>/like', methods=['POST'])
def plaza_like(post_id):
    db = get_db()
    db.execute("UPDATE plaza SET likes = likes + 1 WHERE id = ?", (post_id,))
    db.commit()
    row = db.execute("SELECT likes FROM plaza WHERE id = ?", (post_id,)).fetchone()
    if not row:
        return jsonify({"error": "帖子不存在"}), 404
    return jsonify({"ok": True, "likes": row["likes"]})


if __name__ == '__main__':
    print(f"Vertex · 甲趣启动 | BASE_DIR={BASE_DIR} | 日志: {LOG_FILE}")
    app.run(host='0.0.0.0', port=5000, debug=False)
