"""
Skill 6: generate_promo_copy — 文案生成

触发场景：运营选定主推款后生成 Banner/Push/详情页文案
实现: 模板驱动，按 channel × tone 返回预设文案；有 DEEPSEEK_API_KEY 时调 LLM
"""
import os
import json
import sqlite3
import hashlib
from services.skills._base import STYLE_META, STYLE_NAME, safe_div

# ── 款式视觉描述 ──
# 导入在 TEMPLATES 定义之前

# ── 款式视觉描述（让受众一眼脑补出美甲长什么样）──
STYLE_DESCRIPTIONS = {
    "nail_01": "冰透裸感",   "nail_10": "冰晶琉璃",   "nail_13": "清透雾感",   "nail_14": "奶油裸肌",   "nail_23": "裸感丝绒",
    "nail_02": "奶咖丝滑",   "nail_05": "焦糖玛奇朵", "nail_15": "拿铁艺术",   "nail_16": "草莓甜心",   "nail_25": "蜜桃甜吻",
    "nail_06": "碎钻星河",   "nail_11": "钻光涟漪",   "nail_17": "碎钻星雨",   "nail_18": "极光幻境",   "nail_19": "镭射虹彩",
    "nail_03": "暗夜美拉德", "nail_08": "摩卡暗涌",   "nail_09": "黑金铬影",   "nail_12": "暗夜鎏金",
    "nail_04": "霓虹多巴胺", "nail_07": "幻彩碰撞",   "nail_20": "撞色狂欢",   "nail_21": "雪花秘语",   "nail_22": "冰霜童话",   "nail_24": "初雪轻吻",
}

# ── 文案模板（网感向）──
TEMPLATES = {
    ("banner", "premium"): {
        "main": "{style_desc} · 本季定番",
        "sub": "{tag}天花板 | AI 上手指南 | 限时主推位",
        "cta": "免费试戴 →",
    },
    ("banner", "playful"): {
        "main": "姐妹们！{style_desc} 谁戴谁白",
        "sub": "刷爆小🍠的 {tag} 美甲来啦，显白到犯规",
        "cta": "我先试为敬 →",
    },
    ("banner", "urgent"): {
        "main": "⏳ 最后 48h | {style_desc} 限时直降",
        "sub": "{tag} 断货预警 · 这波错过等一季",
        "cta": "马上下手 →",
    },
    ("push", "premium"): {
        "main": "{style_desc}｜你的 AI 专属推荐",
        "sub": "根据你的试戴记录，这款 {tag} 甲匹配度 97%",
        "cta": "查看详情",
    },
    ("push", "playful"): {
        "main": "绝了！{style_desc} 上手也太高级了",
        "sub": "{tag} 新款刚出炉，已经有 200+ 人抢先试了",
        "cta": "我也要试",
    },
    ("push", "urgent"): {
        "main": "别再纠结了｜{style_desc} 库存告急",
        "sub": "{tag} 人气款仅剩 23 个名额，手慢无",
        "cta": "立即锁定",
    },
    ("detail_page", "premium"): {
        "main": "{style_desc} · {tag}高定系列",
        "sub": "专业美甲师逐指手绘质感 | AI 试戴所见即所得 | 7 天无忧售后",
        "cta": "预约试戴",
    },
    ("detail_page", "playful"): {
        "main": "就它了！{style_desc} 真的绝",
        "sub": "1,200+ 人已试戴 · 好评率 98% · 显白指数 ⭐⭐⭐⭐⭐",
        "cta": "我也要试",
    },
    ("detail_page", "urgent"): {
        "main": "限时特惠｜{style_desc}",
        "sub": "仅剩最后几个名额 · 这价以后不会有了",
        "cta": "立即锁定",
    },
    ("merchant_invite", "premium"): {
        "main": "{tag} 品类增长 {growth}%，邀您首批入驻",
        "sub": "平台搜索量月增 230% · 您的风格精准匹配 · 享首月流量扶持",
        "cta": "立即报名",
    },
    ("merchant_invite", "playful"): {
        "main": "老板！{tag} 风正刮到你店门口",
        "sub": "平台流量倾斜 + AI 主推位 = 躺赚这波红利",
        "cta": "申请入驻",
    },
    ("merchant_invite", "urgent"): {
        "main": "急召 {tag} 供应商｜平台缺口 40%",
        "sub": "首页主推位空缺 + 流量白白流失 = 你的利润空间",
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
    style_desc = STYLE_DESCRIPTIONS.get(style_code, style_name)

    # 社区趋势增长率（用于商家邀请文案）
    growth_pct = ""
    try:
        rows = db.execute(
            "SELECT AVG(growth_rate) FROM community_trends WHERE style_tag=? AND date >= DATE('now', '-7 days')",
            (tag,),
        ).fetchone()
        if rows and rows[0]:
            g = round(rows[0] * 100, 1)
            growth_pct = f"+{g}%" if g > 0 else f"{g}%"
        else:
            growth_pct = "+230%"
    except Exception:
        growth_pct = "+230%"

    key = (channel, tone) if (channel, tone) in TEMPLATES else ("banner", "premium")
    template = TEMPLATES[key]

    main = template["main"].format(style_name=style_name, style_desc=style_desc, tag=tag, growth=growth_pct)
    sub = template["sub"].format(style_name=style_name, style_desc=style_desc, tag=tag, growth=growth_pct)
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
