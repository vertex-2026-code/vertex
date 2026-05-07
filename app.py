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
import subprocess
import requests
from datetime import datetime, timezone
from flask import Flask, request, jsonify, send_from_directory
from openai import OpenAI

# ============ 配置 ============
ARK_API_KEY = os.environ.get("ARK_API_KEY", "")
MODEL_ID = "doubao-seedream-4-5-251128"

PROMPT = (
    "保留第一张图片中的手部，包括手型、肤色、手指姿势、戒指和背景，"
    "全部完全不变。仅将每根手指的指甲款式替换为第二张图片中的美甲"
    "设计风格、颜色、图案。输出图片必须保持第一张图的整体构图和氛围。"
)

if os.path.isdir("/opt/jiaqu"):
    BASE_DIR = "/opt/jiaqu"
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = f"{BASE_DIR}/data"
RESULTS_DIR = f"{BASE_DIR}/static/results"
UPLOADS_DIR = f"{BASE_DIR}/static/uploads"
NAILS_DIR = f"{BASE_DIR}/static/nails"
STATIC_DIR = f"{BASE_DIR}/static"

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

LOG_FILE = f"{DATA_DIR}/tryon.jsonl"

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


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def log_event(event_type, data):
    record = {"ts": now_iso(), "event": event_type, **data}
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


@app.route('/')
def index():
    return send_from_directory(STATIC_DIR, 'index.html')


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
        except Exception:
            pass

    save_upload(hand_image, "hand")
    if custom_style_image:
        save_upload(custom_style_image, "style")

    log_event("tryon_start", {
        "request_id": request_id,
        "user_id": user_id,
        "nickname": nickname,
        "style_id": style_label,
        "style_kind": style_kind,
    })

    try:
        # 高清自适应输出：保持手图比例 + 2K 分辨率
        resp = client.images.generate(
            model=MODEL_ID,
            prompt=PROMPT,
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
            "latency_ms": latency,
            "result_url": f"/static/results/{result_filename}",
        })

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
            "error": str(e),
        })
        return jsonify({"error": str(e)}), 500


@app.route('/api/feedback', methods=['POST'])
def feedback():
    data = request.get_json(force=True)
    log_event("feedback", {
        "request_id": data.get('request_id'),
        "user_id": data.get('user_id', 'anonymous'),
        "nickname": data.get('nickname', ''),
        "style_id": data.get('style_id'),
        "action": data.get('action'),
        "shop_id": data.get('shop_id'),
    })
    return jsonify({"ok": True})


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

    # 风格分类统计
    cat_counts = {}
    for r in starts:
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


if __name__ == '__main__':
    print(f"Vertex · 甲趣启动 | BASE_DIR={BASE_DIR} | 日志: {LOG_FILE}")
    app.run(host='0.0.0.0', port=5000, debug=False)
