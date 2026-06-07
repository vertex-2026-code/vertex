"""
Skill 6: generate_promo_copy — 文案生成

触发场景：运营选定主推款后生成 Banner/Push/详情页文案
实现: 模板驱动，按 channel × tone 返回预设文案；有 DEEPSEEK_API_KEY 时调 LLM
"""
import os
import json
import sqlite3
import hashlib
from services.skills._base import STYLE_META, STYLE_NAME

# ── 文案模板 ──
TEMPLATES = {
    ("banner", "premium"): {
        "main": "{style_name} · 本季必入高级感",
        "sub": "AI 试戴实测 | {tag}风格 | 限时主推",
        "cta": "立即试戴 →",
    },
    ("banner", "playful"): {
        "main": "手残党福音！{style_name} 谁戴谁好看",
        "sub": "刷爆小红书的 {tag} 来了",
        "cta": "免费试戴 →",
    },
    ("banner", "urgent"): {
        "main": "最后 48h | {style_name} 限时折扣",
        "sub": "{tag} 爆款直降，错过再等一季",
        "cta": "马上抢 →",
    },
    ("push", "premium"): {
        "main": "你的专属 {tag} 推荐 | {style_name}",
        "sub": "AI 根据你的试戴偏好精选",
        "cta": "查看详情",
    },
    ("push", "playful"): {
        "main": "集美！{style_name} 也太好看了吧",
        "sub": "刚出炉的 {tag} 新款，手慢无",
        "cta": "去看看",
    },
    ("push", "urgent"): {
        "main": "别纠结了 | {style_name} 快卖完了",
        "sub": "{tag} 爆款最后库存",
        "cta": "立即下单",
    },
    ("detail_page", "premium"): {
        "main": "{style_name} · {tag}高定系列",
        "sub": "精选材质 | 专业美甲师推荐 | 7天无忧",
        "cta": "预约试戴",
    },
    ("detail_page", "playful"): {
        "main": "就是它了！{style_name}",
        "sub": "1000+ 人已试戴 | 好评率 98%",
        "cta": "我也要试",
    },
    ("detail_page", "urgent"): {
        "main": "限时特惠 | {style_name}",
        "sub": "仅剩少量名额 | 手慢无",
        "cta": "立即锁定",
    },
    ("merchant_invite", "premium"): {
        "main": "邀您上新年 {tag} 款式",
        "sub": "平台 {tag} 需求上涨，您的风格高度匹配",
        "cta": "立即报名",
    },
    ("merchant_invite", "playful"): {
        "main": "商家大大，{tag} 风正刮到你店门口",
        "sub": "平台流量扶持 + AI 主推位",
        "cta": "申请入驻",
    },
    ("merchant_invite", "urgent"): {
        "main": "{tag} 品类紧急缺货 | 急召供应商",
        "sub": "平台流量倾斜 + 补贴 + 爆款预测",
        "cta": "立即响应",
    },
}

# 缓存目录
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_key(channel, tone, style_code):
    raw = f"{channel}|{tone}|{style_code}"
    return hashlib.md5(raw.encode()).hexdigest()


def _cached_get(key):
    cache_file = os.path.join(CACHE_DIR, f"copy_{key}.json")
    if os.path.exists(cache_file):
        mtime = os.path.getmtime(cache_file)
        import time
        if time.time() - mtime < 86400:
            with open(cache_file) as f:
                return json.load(f)
    return None


def _cache_set(key, data):
    cache_file = os.path.join(CACHE_DIR, f"copy_{key}.json")
    with open(cache_file, "w") as f:
        json.dump(data, f, ensure_ascii=False)


def generate_promo_copy(db, style_code, channel="banner", tone="premium"):
    cat, tag, _ = STYLE_META.get(style_code, ("?", "未知", 0))
    style_name = STYLE_NAME.get(style_code, style_code)

    key = (channel, tone) if (channel, tone) in TEMPLATES else ("banner", "premium")
    template = TEMPLATES[key]

    main = template["main"].format(style_name=style_name, tag=tag)
    sub = template["sub"].format(style_name=style_name, tag=tag)
    cta = template["cta"]

    # 尝试 LLM 增强
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if api_key:
        cache_key = _cache_key(channel, tone, style_code)
        cached = _cached_get(cache_key)
        if cached:
            return cached

        try:
            import requests
            resp = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{
                        "role": "user",
                        "content": (
                            f"你是美甲品类文案专家。为以下商品写一段{channel}渠道的{tone}调性文案。\n"
                            f"款式: {style_name}（{tag}风格）\n"
                            f"参考模板: 主标题「{main}」副标题「{sub}」CTA「{cta}」\n"
                            f"要求: 保持相同字段，优化用词使其更吸引人。返回 JSON: "
                            f'{{"main_copy":"...","sub_copy":"...","cta":"..."}}'
                        ),
                    }],
                    "temperature": 0.8,
                    "max_tokens": 200,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                llm = resp.json()["choices"][0]["message"]["content"]
                llm_data = json.loads(llm) if isinstance(llm, str) else llm
                result = {
                    "main_copy": llm_data.get("main_copy", main),
                    "sub_copy": llm_data.get("sub_copy", sub),
                    "cta": llm_data.get("cta", cta),
                    "char_count": len(llm_data.get("main_copy", "")) + len(llm_data.get("sub_copy", "")),
                    "channel": channel,
                    "tone": tone,
                    "style_code": style_code,
                    "source": "deepseek",
                }
                _cache_set(cache_key, result)
                return result
        except Exception:
            pass

    return {
        "main_copy": main,
        "sub_copy": sub,
        "cta": cta,
        "char_count": len(main) + len(sub),
        "channel": channel,
        "tone": tone,
        "style_code": style_code,
        "source": "template",
    }
