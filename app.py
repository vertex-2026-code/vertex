"""
甲趣 - AI 美甲试戴 Flask 后端 (v2)
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

BASE_DIR = "/opt/jiaqu"
DATA_DIR = f"{BASE_DIR}/data"
RESULTS_DIR = f"{BASE_DIR}/static/results"
NAILS_DIR = f"{BASE_DIR}/static/nails"
STATIC_DIR = f"{BASE_DIR}/static"

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

LOG_FILE = f"{DATA_DIR}/tryon.jsonl"

client = OpenAI(
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    api_key=ARK_API_KEY,
)

MOCK_SHOPS = [
    {"id": "shop_001", "name": "粉黛美甲(陆家嘴店)", "rating": 4.8, "distance_km": 0.5, "price_avg": 188},
    {"id": "shop_002", "name": "莫里斯美甲(静安寺店)", "rating": 4.6, "distance_km": 1.2, "price_avg": 268},
    {"id": "shop_003", "name": "甲艺工坊(田子坊店)", "rating": 4.9, "distance_km": 2.1, "price_avg": 158},
    {"id": "shop_004", "name": "Nail Lab(新天地店)", "rating": 4.7, "distance_km": 1.8, "price_avg": 328},
    {"id": "shop_005", "name": "甜心美甲(豫园店)", "rating": 4.5, "distance_km": 2.5, "price_avg": 128},
]

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
        styles.append({
            "id": sid,
            "name": f"款式 {num}",
            "url": f"/static/nails/{f}",
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

    log_event("tryon_start", {
        "request_id": request_id,
        "user_id": user_id,
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
        "style_id": data.get('style_id'),
        "action": data.get('action'),
        "shop_id": data.get('shop_id'),
    })
    return jsonify({"ok": True})


@app.route('/health')
def health():
    return jsonify({"status": "ok", "ts": now_iso()})


if __name__ == '__main__':
    print(f"🎀 甲趣 v2 启动 → 日志: {LOG_FILE}")
    app.run(host='0.0.0.0', port=5000, debug=False)
