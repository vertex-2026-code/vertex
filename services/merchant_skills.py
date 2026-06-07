"""
OpenClaw-schedulable merchant SKILLS for Vertex.

This module defines a SKILL registry that OpenClaw can reason over. Each SKILL
has an id, trigger examples, data sources, output schema, and an execution
prompt. The local analyzers are kept as deterministic fallback/context so the
UI can still render if OpenClaw is unavailable.
"""
from __future__ import annotations

import ast
import json
import os
import re
import sqlite3
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

BJT = timezone(timedelta(hours=8))

CATEGORY_NAMES = {
    "A": "minimal_clean",
    "B": "sweet_cute",
    "C": "glam_sparkle",
    "D": "dark_cool",
    "E": "trend_avant_garde",
}

STYLE_CATEGORIES = {
    "nail_01": "A", "nail_10": "A", "nail_13": "A", "nail_14": "A", "nail_23": "A",
    "nail_02": "B", "nail_05": "B", "nail_15": "B", "nail_16": "B", "nail_25": "B",
    "nail_06": "C", "nail_11": "C", "nail_17": "C", "nail_18": "C", "nail_19": "C",
    "nail_03": "D", "nail_08": "D", "nail_09": "D", "nail_12": "D",
    "nail_04": "E", "nail_07": "E", "nail_20": "E", "nail_21": "E", "nail_22": "E", "nail_24": "E",
}

SHOPS = [
    {"id": "shop_001", "name": "Maison Purete - Sanlitun", "style": "A", "rating": 4.8, "price_avg": 188},
    {"id": "shop_002", "name": "Fleur Rose - Wudaokou", "style": "B", "rating": 4.6, "price_avg": 168},
    {"id": "shop_003", "name": "Bijou Lumiere - Guomao", "style": "C", "rating": 4.9, "price_avg": 328},
    {"id": "shop_004", "name": "Noir Atelier - Wangjing", "style": "D", "rating": 4.7, "price_avg": 258},
    {"id": "shop_005", "name": "L'Avant-Garde - Zhongguancun", "style": "E", "rating": 4.5, "price_avg": 298},
]

SHOP_BY_ID = {shop["id"]: shop for shop in SHOPS}
DEFAULT_REMOTE_CHAT_PATH = "/api/admin/chat"
CUSTOM_SKILLS_FILENAME = "merchant_custom_skills.json"
MERCHANT_HISTORY_FILENAME = "merchant_history.json"


SKILL_REGISTRY: dict[str, dict[str, Any]] = {
    "merchant_style_profile": {
        "name": "Merchant style profile",
        "description": "Summarize the merchant's own nail style, strengths, risks, and future direction.",
        "trigger_examples": [
            "Analyze my store style",
            "What is my shop's strongest nail style?",
            "Summarize my merchant style profile",
        ],
        "data_sources": ["data/tryon.jsonl", "data/jiaqu.db:plaza", "data/jiaqu.db:community_trends"],
        "output_schema": {
            "style_summary": "string",
            "primary_category": "string",
            "style_mix": "array",
            "strengths": "array",
            "risks": "array",
            "recommended_direction": "array",
        },
        "actions": ["refresh_primary_styles", "generate_style_variants"],
    },
    "periodic_ops_report": {
        "name": "Periodic operations report",
        "description": "Analyze merchant and platform operations for a selected period.",
        "trigger_examples": [
            "Give me a 14-day operations report",
            "Analyze this week's store performance",
            "What changed in the last month?",
        ],
        "data_sources": ["data/tryon.jsonl", "data/jiaqu.db:plaza"],
        "output_schema": {
            "metrics": "object",
            "trend_summary": "string",
            "alerts": "array",
            "actions": "array",
        },
        "actions": ["boost_shop_exposure", "improve_booking_cta", "refresh_primary_styles"],
    },
    "same_style_competitor_analysis": {
        "name": "Same-style competitor analysis",
        "description": "Compare the current merchant with shops in similar style bands.",
        "trigger_examples": [
            "Compare me with same-style shops",
            "Which competitor is stronger?",
            "Find my gaps against similar stores",
        ],
        "data_sources": ["data/tryon.jsonl", "merchant shop metadata"],
        "output_schema": {
            "competitive_position": "string",
            "peer_group": "array",
            "advantages": "array",
            "gaps": "array",
            "opportunities": "array",
        },
        "actions": ["competitor_gap_followup", "adjust_price_or_campaign"],
    },
    "hot_style_launch": {
        "name": "Hot style launch",
        "description": "Find hot style candidates and recommend launch/generation actions.",
        "trigger_examples": [
            "Find styles I should launch",
            "Which nails can become hot styles?",
            "Generate hot style launch suggestions",
        ],
        "data_sources": ["data/tryon.jsonl", "data/jiaqu.db:plaza", "data/jiaqu.db:community_trends"],
        "output_schema": {
            "hot_candidates": "array",
            "recommended_launch_plan": "array",
            "actions": "array",
        },
        "actions": ["promote_shop", "promote_homepage", "generate_variant", "campaign_ready"],
    },
    "cold_style_retire": {
        "name": "Cold style retire",
        "description": "Detect low-performing styles and suggest observe/revise/deprioritize/retire actions.",
        "trigger_examples": [
            "Which styles should I retire?",
            "Find cold styles",
            "What should be deprioritized?",
        ],
        "data_sources": ["data/tryon.jsonl", "data/jiaqu.db:community_trends"],
        "output_schema": {
            "cold_candidates": "array",
            "risk_reasoning": "array",
            "actions": "array",
        },
        "actions": ["observe", "revise", "deprioritize", "retire"],
    },
    "automation_queue": {
        "name": "Automation queue",
        "description": "Compose multiple SKILL outputs into an actionable merchant operations queue.",
        "trigger_examples": [
            "Make an action queue for my store",
            "What should I do this week?",
            "Automatically arrange launch and retire tasks",
        ],
        "data_sources": ["outputs of all merchant skills", "data/tryon.jsonl", "data/jiaqu.db"],
        "output_schema": {
            "summary": "string",
            "items": "array",
        },
        "actions": ["launch_hot_style", "retire_or_revise_cold_style", "ops_alert", "competitor_gap_followup"],
    },
}


def list_skill_registry() -> dict[str, Any]:
    return {"skills": SKILL_REGISTRY, "skill_ids": list(SKILL_REGISTRY.keys())}


def list_custom_skills(base_dir: str, shop_id: str | None = None) -> list[dict[str, Any]]:
    skills = _load_custom_skills(base_dir)
    if shop_id:
        return [item for item in skills if str(item.get("shop_id") or "").strip() == str(shop_id).strip()]
    return skills


def list_merchant_history(base_dir: str, limit: int = 24, shop_id: str | None = None) -> list[dict[str, Any]]:
    items = _load_merchant_history(base_dir)
    if shop_id:
        items = [item for item in items if str(item.get("shop_id") or "").strip() == str(shop_id).strip()]
    safe_limit = max(1, min(int(limit or 24), 100))
    return items[:safe_limit]


def save_merchant_history(base_dir: str, entry: dict[str, Any], limit: int = 80) -> dict[str, Any]:
    path = _merchant_history_path(base_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    items = _load_merchant_history(base_dir)
    normalized = _normalize_history_entry(entry)
    items = [item for item in items if item.get("id") != normalized["id"]]
    items.insert(0, normalized)
    safe_limit = max(10, min(int(limit or 80), 200))
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(items[:safe_limit], fp, ensure_ascii=False, indent=2)
    return normalized


def create_custom_skill(
    base_dir: str,
    message: str,
    shop_id: str | None = None,
    period_days: int = 14,
    use_openclaw: bool = True,
    timeout: int = 120,
) -> dict[str, Any]:
    shop_id = _validate_shop(base_dir, shop_id)
    cleaned_message = (message or "").strip()
    if not cleaned_message:
        raise ValueError("message cannot be empty")

    result = {
        "mode": "custom_skill_created",
        "shop": _shop_public_for_id(base_dir, shop_id),
        "period_days": period_days,
    }

    spec = None
    openclaw_result = {"used": False, "reply": None, "error": None}
    if use_openclaw:
        prompt = build_custom_skill_prompt(base_dir, cleaned_message, shop_id, period_days)
        openclaw_result = _call_openclaw(prompt, session_id=f"vertex-merchant-create-skill-{shop_id}", timeout=timeout)
        spec = _extract_custom_skill_spec(openclaw_result.get("reply"))

    if not spec:
        spec = _fallback_custom_skill_spec(cleaned_message)

    spec["shop_id"] = shop_id
    saved_skill = save_custom_skill(base_dir, spec)
    result["created_skill"] = saved_skill
    result["skill"] = saved_skill
    result["openclaw"] = openclaw_result
    return result


def get_openclaw_status() -> dict[str, Any]:
    runtime = _openclaw_runtime()
    command_path = shutil.which("openclaw")
    config_paths = [
        os.path.expanduser("~/.joyclaw/openclaw.json"),
        os.path.expanduser("~/.openclaw/openclaw.json"),
        "/root/.openclaw/openclaw.json",
    ]
    existing_config = next((path for path in config_paths if os.path.exists(path)), None)
    if runtime["transport"] == "remote_http":
        reason = f"Remote OpenClaw proxy is configured via {runtime['remote_url']}. Reachability is checked when a request is sent."
        available = True
    elif runtime["transport"] == "local_cli":
        reason = "OpenClaw CLI is available on PATH."
        available = True
    elif existing_config:
        reason = "OpenClaw config exists, but no usable transport is available. Configure OPENCLAW_REMOTE_BASE_URL or install the local openclaw CLI."
        available = False
    else:
        reason = "No usable OpenClaw transport is configured."
        available = False
    return {
        "available": available,
        "transport": runtime["transport"],
        "requested_transport": runtime["requested_transport"],
        "command_path": command_path,
        "config_path": existing_config,
        "remote_base_url": runtime["remote_base_url"],
        "remote_url": runtime["remote_url"],
        "remote_source": runtime["remote_source"],
        "reason": reason,
    }


def build_merchant_skills(base_dir: str, shop_id: str | None = None, period_days: int = 14) -> dict[str, Any]:
    """Return deterministic local SKILL outputs used as fallback/context."""
    shop_id = _validate_shop(base_dir, shop_id)
    period_days = max(1, int(period_days or 14))
    generated_snapshot = _load_generated_shop_snapshot(base_dir, shop_id, period_days)
    if generated_snapshot:
        return _build_generated_merchant_skills(base_dir, shop_id, period_days, generated_snapshot)
    data = _load_context(base_dir)
    profile = merchant_style_profile(data, shop_id)
    report = periodic_ops_report(data, shop_id, period_days)
    competitors = competitor_analysis(data, shop_id)
    hot = hot_style_launch_suggestions(data, shop_id)
    cold = cold_style_retire_suggestions(data, shop_id)
    queue = automation_queue(shop_id, profile, report, competitors, hot, cold)
    return {
        "mode": "local_fallback",
        "shop": _shop_public_for_id(base_dir, shop_id),
        "period_days": period_days,
        "generated_at": datetime.now(BJT).isoformat(),
        "overview": {
            "has_chart_data": False,
            "period_days": period_days,
            "daily_series": [],
            "totals": {},
        },
        "skills": {
            "merchant_style_profile": profile,
            "periodic_ops_report": report,
            "same_style_competitor_analysis": competitors,
            "hot_style_launch": hot,
            "cold_style_retire": cold,
            "automation_queue": queue,
        },
    }


def run_openclaw_skill(
    base_dir: str,
    skill_id: str,
    shop_id: str | None = None,
    period_days: int = 14,
    user_message: str = "",
    timeout: int = 120,
    use_openclaw: bool = True,
) -> dict[str, Any]:
    """Run one SKILL through OpenClaw, with local fallback bundled."""
    shop_id = _validate_shop(base_dir, shop_id)
    skill_definition = _resolve_skill_definition(base_dir, skill_id, shop_id=shop_id)

    local_payload = build_merchant_skills(base_dir, shop_id, period_days)
    prompt = build_skill_prompt(base_dir, skill_id, shop_id, period_days, user_message, local_payload, skill_definition=skill_definition)
    result = {
        "mode": "openclaw_skill",
        "skill_id": skill_id,
        "shop": local_payload.get("shop") or _shop_public_for_id(base_dir, shop_id),
        "period_days": period_days,
        "prompt": prompt,
        "skill_definition": skill_definition,
        "local_fallback": _local_fallback_for_skill(local_payload, skill_id, skill_definition),
    }
    if not use_openclaw:
        result["openclaw"] = {"used": False, "reply": None, "error": None}
        return result

    openclaw = _call_openclaw(prompt, session_id=f"vertex-merchant-{shop_id}-{skill_id}", timeout=timeout)
    result["openclaw"] = openclaw
    return result


def dispatch_openclaw_agent(
    base_dir: str,
    message: str,
    shop_id: str | None = None,
    period_days: int = 14,
    timeout: int = 120,
    use_openclaw: bool = True,
) -> dict[str, Any]:
    """Merchant chat entry: OpenClaw chooses and executes one or more SKILLS."""
    shop_id = _validate_shop(base_dir, shop_id)
    local_payload = build_merchant_skills(base_dir, shop_id, period_days)
    prompt = build_agent_prompt(base_dir, message, shop_id, period_days, local_payload)
    result = {
        "mode": "openclaw_agent_dispatch",
        "shop": local_payload.get("shop") or _shop_public_for_id(base_dir, shop_id),
        "period_days": period_days,
        "registry": list_skill_registry(),
        "prompt": prompt,
        "local_fallback": local_payload,
    }
    if not use_openclaw:
        result["openclaw"] = {"used": False, "reply": None, "error": None}
        return result

    result["openclaw"] = _call_openclaw(prompt, session_id=f"vertex-merchant-agent-{shop_id}", timeout=timeout)
    return result


def build_skill_prompt(
    base_dir: str,
    skill_id: str,
    shop_id: str,
    period_days: int,
    user_message: str,
    local_payload: dict[str, Any],
    skill_definition: dict[str, Any] | None = None,
) -> str:
    skill = skill_definition or _resolve_skill_definition(base_dir, skill_id)
    context = _skill_context(base_dir, shop_id, period_days, local_payload)
    return (
        "You are OpenClaw running a Vertex merchant operations SKILL.\n"
        "Return Chinese business-facing output, but keep the top-level response valid JSON.\n"
        "Do not invent unavailable metrics. If data is missing, say so and use the fallback snapshot.\n\n"
        f"SKILL_ID: {skill_id}\n"
        f"SKILL_DEFINITION:\n{json.dumps(skill, ensure_ascii=False, indent=2)}\n\n"
        f"MERCHANT_CONTEXT:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        f"USER_MESSAGE: {user_message or '(fixed skill trigger)'}\n\n"
        "Required top-level JSON shape:\n"
        "{\n"
        f'  "skill_id": "{skill_id}",\n'
        '  "used_data_sources": [],\n'
        '  "analysis": {},\n'
        '  "actions": [],\n'
        '  "ui_summary": "short Chinese summary for merchant UI"\n'
        "}\n"
    )


def build_agent_prompt(
    base_dir: str,
    message: str,
    shop_id: str,
    period_days: int,
    local_payload: dict[str, Any],
) -> str:
    context = _skill_context(base_dir, shop_id, period_days, local_payload)
    return (
        "You are OpenClaw, the merchant-side agent for Vertex nail salon intelligence.\n"
        "Your job is to understand the merchant's message, choose one or more SKILLS from the registry, "
        "read/consider the available local data, and return a structured execution result.\n"
        "Return Chinese business-facing content, but keep the top-level response valid JSON.\n\n"
        f"MERCHANT_MESSAGE: {message}\n\n"
        f"SKILL_REGISTRY:\n{json.dumps(SKILL_REGISTRY, ensure_ascii=False, indent=2)}\n\n"
        f"MERCHANT_CONTEXT:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        "Required top-level JSON shape:\n"
        "{\n"
        '  "intent": "merchant intent in Chinese",\n'
        '  "selected_skills": [],\n'
        '  "skill_results": {},\n'
        '  "actions": [],\n'
        '  "ui_summary": "short Chinese summary for merchant UI",\n'
        '  "workflow_suggestion": null\n'
        "}\n"
    )


def build_custom_skill_prompt(base_dir: str, message: str, shop_id: str, period_days: int) -> str:
    local_payload = build_merchant_skills(base_dir, shop_id, period_days)
    context = _skill_context(base_dir, shop_id, period_days, local_payload)
    return (
        "You are designing a saved merchant SKILL for the Vertex merchant workbench.\n"
        "Return valid JSON only. The merchant will save this SKILL into the left sidebar and run it later.\n"
        "Make the SKILL practical, concise, and business-facing in Chinese.\n"
        "Prefer a short clear name, one-line description, and one execution message.\n\n"
        f"MERCHANT_REQUEST: {message}\n\n"
        f"AVAILABLE_BASE_SKILLS:\n{json.dumps(SKILL_REGISTRY, ensure_ascii=False, indent=2)}\n\n"
        f"MERCHANT_CONTEXT:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        "Required JSON shape:\n"
        "{\n"
        '  "id": "ascii_snake_case_id",\n'
        '  "name": "Chinese skill name",\n'
        '  "desc": "one sentence description",\n'
        '  "message": "the exact execution message to run this skill later",\n'
        '  "estimated_seconds": 75,\n'
        '  "trigger_examples": ["example 1", "example 2"],\n'
        '  "output_schema": {"summary": "string", "actions": "array"},\n'
        '  "actions": ["base_skill_id_or_action_name"]\n'
        "}\n"
    )


def merchant_style_profile(data: dict[str, Any], shop_id: str) -> dict[str, Any]:
    shop = SHOP_BY_ID[shop_id]
    starts = data["starts"]
    shop_books = [r for r in data["books"] if r.get("shop_id") == shop_id]
    cat_counter = Counter(_style_cat(r.get("style_id")) for r in starts)
    total = sum(cat_counter.values()) or 1
    style_mix = [
        {"category": cat, "name": CATEGORY_NAMES.get(cat, cat), "count": count, "ratio": round(count / total, 3)}
        for cat, count in cat_counter.most_common()
        if cat != "?"
    ]
    related = [_style_metrics(data, sid) for sid in _styles_for_category(shop["style"])]
    related = [item for item in related if item["tryons"] or item["likes"] or item["books"]]
    related.sort(key=lambda item: (item["booking_rate"], item["like_rate"], item["tryons"]), reverse=True)
    return {
        "skill": "merchant_style_profile",
        "shop_id": shop_id,
        "primary_category": shop["style"],
        "primary_category_name": CATEGORY_NAMES[shop["style"]],
        "style_summary": "Local fallback profile. OpenClaw should generate merchant-facing Chinese copy.",
        "style_mix": style_mix,
        "top_related_styles": related[:5],
        "strengths": ["primary_style_is_clear"] if related else [],
        "risks": [] if shop_books else ["no_shop_booking_signal"],
        "recommended_direction": [f"expand_{CATEGORY_NAMES[shop['style']]}_variants"],
    }


def periodic_ops_report(data: dict[str, Any], shop_id: str, period_days: int) -> dict[str, Any]:
    end = _latest_ts(data["logs"]) or datetime.now(BJT)
    current_start = end - timedelta(days=period_days)
    previous_start = current_start - timedelta(days=period_days)
    current = _period_metrics([r for r in data["logs"] if _in_range(r, current_start, end)], shop_id)
    previous = _period_metrics([r for r in data["logs"] if _in_range(r, previous_start, current_start)], shop_id)
    alerts = []
    if current["tryons"] and current["booking_rate"] < 0.08:
        alerts.append({"level": "medium", "message": "booking_rate_low"})
    if current["shop_books"] > max(2, previous["shop_books"] * 1.5):
        alerts.append({"level": "positive", "message": "shop_bookings_increased"})
    return {
        "skill": "periodic_ops_report",
        "window": {"start": current_start.isoformat(), "end": end.isoformat(), "days": period_days},
        "metrics": current,
        "previous_metrics": previous,
        "deltas": {key: _delta(current.get(key, 0), previous.get(key, 0)) for key in ("tryons", "likes", "books", "shop_books")},
        "trend_summary": "Local fallback report. OpenClaw should generate merchant-facing Chinese copy.",
        "top_categories": _top_categories(data["logs"]),
        "top_styles": _top_styles(data["logs"]),
        "alerts": alerts,
        "actions": _period_actions(current, shop_id),
    }


def competitor_analysis(data: dict[str, Any], shop_id: str) -> dict[str, Any]:
    shop = SHOP_BY_ID[shop_id]
    own = _shop_scorecard(data, shop_id)
    peers = []
    for peer in SHOPS:
        if peer["id"] == shop_id:
            continue
        card = _shop_scorecard(data, peer["id"])
        card["shop"] = _shop_public(peer)
        card["style_match"] = 1.0 if peer["style"] == shop["style"] else _category_similarity(shop["style"], peer["style"])
        peers.append(card)
    peers.sort(key=lambda item: (item["style_match"], item["booking_rate"], item["books"]), reverse=True)
    peer_group = peers[:3]
    gaps = []
    if own["booking_rate"] < _avg([p["booking_rate"] for p in peer_group]):
        gaps.append("booking_rate_below_peer_group")
    return {
        "skill": "same_style_competitor_analysis",
        "current_shop": {**_shop_public(shop), **own},
        "peer_group": peer_group,
        "competitive_position": "Local fallback competitor position.",
        "advantages": [] if gaps else ["booking_rate_not_below_peer_group"],
        "gaps": gaps,
        "opportunities": ["use_openclaw_to_generate_business_opportunities"],
    }


def hot_style_launch_suggestions(data: dict[str, Any], shop_id: str, limit: int = 6) -> dict[str, Any]:
    primary_cat = SHOP_BY_ID[shop_id]["style"]
    candidates = []
    for sid in sorted(STYLE_CATEGORIES):
        metrics = _style_metrics(data, sid)
        trend = data["trend_by_cat"].get(_style_cat(sid), {"mention_count": 0, "growth_rate": 0.0, "top_tags": []})
        plaza = data["plaza_by_style"].get(sid, {"posts": 0, "likes": 0})
        style_fit = 1.0 if _style_cat(sid) == primary_cat else _category_similarity(primary_cat, _style_cat(sid))
        score = min(metrics["tryons"], 30) * 1.2 + metrics["like_rate"] * 28 + metrics["booking_rate"] * 36
        score += min(plaza["likes"], 40) * 0.5 + max(trend["growth_rate"], 0) * 18 + style_fit * 12
        if metrics["tryons"] or trend["mention_count"] or plaza["posts"]:
            candidates.append({
                "style_id": sid,
                "category": _style_cat(sid),
                "score": round(score, 1),
                "reason": "local_hot_score",
                "metrics": metrics,
                "external_trend": trend,
                "plaza": plaza,
                "actions": _hot_actions(style_fit, metrics, trend),
            })
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return {"skill": "hot_style_launch", "hot_candidates": candidates[:limit]}


def cold_style_retire_suggestions(data: dict[str, Any], shop_id: str, limit: int = 6) -> dict[str, Any]:
    primary_cat = SHOP_BY_ID[shop_id]["style"]
    candidates = []
    for sid in sorted(STYLE_CATEGORIES):
        metrics = _style_metrics(data, sid)
        trend = data["trend_by_cat"].get(_style_cat(sid), {"mention_count": 0, "growth_rate": 0.0, "top_tags": []})
        style_fit = 1.0 if _style_cat(sid) == primary_cat else _category_similarity(primary_cat, _style_cat(sid))
        risk = 0
        risk += 24 if metrics["tryons"] <= 2 else 0
        risk += 24 if metrics["tryons"] and metrics["like_rate"] < 0.3 else 0
        risk += 20 if metrics["tryons"] and metrics["booking_rate"] < 0.05 else 0
        risk += 18 if trend["growth_rate"] < -0.03 else 0
        risk += 14 if style_fit < 0.45 else 0
        if risk:
            candidates.append({
                "style_id": sid,
                "category": _style_cat(sid),
                "risk_score": risk,
                "reason": "local_cold_risk_score",
                "metrics": metrics,
                "external_trend": trend,
                "suggested_action": _cold_action(risk),
            })
    candidates.sort(key=lambda item: item["risk_score"], reverse=True)
    return {"skill": "cold_style_retire", "cold_candidates": candidates[:limit]}


def automation_queue(
    shop_id: str,
    profile: dict[str, Any],
    report: dict[str, Any],
    competitors: dict[str, Any],
    hot: dict[str, Any],
    cold: dict[str, Any],
) -> dict[str, Any]:
    items = []
    for candidate in hot.get("hot_candidates", [])[:3]:
        items.append({
            "type": "launch_hot_style",
            "target": candidate["style_id"],
            "shop_id": shop_id,
            "priority": "high" if candidate["score"] >= 70 else "medium",
            "status": "ready",
            "reason": candidate["reason"],
            "actions": candidate["actions"],
        })
    for candidate in cold.get("cold_candidates", [])[:3]:
        items.append({
            "type": "retire_or_revise_cold_style",
            "target": candidate["style_id"],
            "shop_id": shop_id,
            "priority": "high" if candidate["risk_score"] >= 70 else "medium",
            "status": "pending_review",
            "reason": candidate["reason"],
            "suggested_action": candidate["suggested_action"],
        })
    for alert in report.get("alerts", []):
        items.append({
            "type": "ops_alert",
            "target": shop_id,
            "shop_id": shop_id,
            "priority": "medium",
            "status": "ready",
            "reason": alert["message"],
        })
    if competitors.get("gaps"):
        items.append({
            "type": "competitor_gap_followup",
            "target": shop_id,
            "shop_id": shop_id,
            "priority": "medium",
            "status": "ready",
            "reason": ";".join(competitors["gaps"]),
        })
    return {"skill": "automation_queue", "summary": f"{len(items)} local fallback action items generated.", "items": items}


def _skill_context(base_dir: str, shop_id: str, period_days: int, local_payload: dict[str, Any]) -> dict[str, Any]:
    data_dir = os.path.join(base_dir, "data")
    return {
        "shop": local_payload.get("shop") or _shop_public_for_id(base_dir, shop_id),
        "period_days": period_days,
        "data_paths": {
            "tryon_jsonl": os.path.join(data_dir, "tryon.jsonl"),
            "sqlite_db": os.path.join(data_dir, "jiaqu.db"),
            "openclaw_workspace_hint": "/workspace/tryon-data",
        },
        "style_categories": STYLE_CATEGORIES,
        "category_names": CATEGORY_NAMES,
        "local_snapshot": local_payload,
    }


def _call_openclaw(message: str, session_id: str, timeout: int = 120) -> dict[str, Any]:
    runtime = _openclaw_runtime()
    if runtime["transport"] == "remote_http":
        return _call_openclaw_remote_http(message, session_id=session_id, timeout=timeout, runtime=runtime)
    if runtime["transport"] != "local_cli":
        return {"used": True, "transport": "none", "reply": None, "error": "No OpenClaw transport is configured."}
    try:
        result = subprocess.run(
            ["openclaw", "agent", "--message", message, "--json", "--session-id", session_id, "--timeout", str(timeout)],
            capture_output=True,
            text=True,
            timeout=timeout + 10,
        )
    except subprocess.TimeoutExpired:
        return {"used": True, "transport": "local_cli", "reply": None, "error": "OpenClaw timeout"}
    except Exception as exc:
        return {"used": True, "transport": "local_cli", "reply": None, "error": str(exc)}
    if result.returncode != 0:
        return {"used": True, "transport": "local_cli", "reply": None, "error": result.stderr.strip()[-500:]}
    raw = result.stdout.strip()
    normalized = _normalize_openclaw_result(raw)
    return {
        "used": True,
        "transport": "local_cli",
        "reply": normalized["reply"],
        "progress": normalized["progress"],
        "meta": normalized["meta"],
        "debug": normalized["debug"],
        "error": None,
        "raw": raw,
    }


def _call_openclaw_remote_http(message: str, session_id: str, timeout: int, runtime: dict[str, Any]) -> dict[str, Any]:
    url = runtime.get("remote_url") or ""
    if not url:
        return {"used": True, "transport": "remote_http", "reply": None, "error": "Remote OpenClaw URL is not configured."}

    body = json.dumps({"message": message, "session_id": session_id}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout + 10) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        parsed = _safe_parse_json(raw)
        error = parsed.get("error") if isinstance(parsed, dict) and parsed.get("error") else raw[-500:]
        return {"used": True, "transport": "remote_http", "target": url, "reply": None, "error": error}
    except urllib.error.URLError as exc:
        return {"used": True, "transport": "remote_http", "target": url, "reply": None, "error": str(exc.reason)}
    except TimeoutError:
        return {"used": True, "transport": "remote_http", "target": url, "reply": None, "error": "OpenClaw remote timeout"}
    except Exception as exc:
        return {"used": True, "transport": "remote_http", "target": url, "reply": None, "error": str(exc)}

    parsed = _safe_parse_json(raw)
    if isinstance(parsed, dict):
        if parsed.get("error"):
            return {"used": True, "transport": "remote_http", "target": url, "reply": None, "error": str(parsed.get("error"))}
    normalized = _normalize_openclaw_result(parsed if parsed is not None else raw)
    return {
        "used": True,
        "transport": "remote_http",
        "target": url,
        "reply": normalized["reply"],
        "progress": normalized["progress"],
        "meta": normalized["meta"],
        "debug": normalized["debug"],
        "error": None,
        "raw": raw,
    }


def _extract_openclaw_reply(raw: str) -> Any:
    return _normalize_openclaw_result(raw).get("reply")


def _normalize_openclaw_result(value: Any) -> dict[str, Any]:
    source = _coerce_openclaw_source(value)
    reply = _extract_business_reply(source)
    if reply is None and isinstance(source, str):
        cleaned = source.strip()
        reply = cleaned or None
    return {
        "reply": reply,
        "progress": _extract_openclaw_progress(source),
        "meta": _extract_openclaw_meta(source),
        "debug": _extract_openclaw_debug(source),
    }


def _coerce_openclaw_source(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    parsed = _safe_parse_structured_text(value)
    if parsed is not None:
        return parsed
    return _extract_last_json_value(value) or value


def _extract_last_json_value(raw: str) -> Any:
    for line in reversed(raw.splitlines()):
        line = line.strip()
        if not line or line[0] not in "[{":
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None


def _extract_business_reply(reply: Any) -> Any:
    if isinstance(reply, dict):
        if _looks_like_business_reply(reply):
            return reply
        payloads = reply.get("result", {}).get("payloads") if isinstance(reply.get("result"), dict) else None
        if isinstance(payloads, list):
            extracted = _extract_reply_from_payloads(payloads)
            if extracted is not None:
                return extracted
        for key in ("reply", "content", "message", "text"):
            if key not in reply:
                continue
            extracted = _extract_business_reply(reply[key])
            if extracted is not None:
                return extracted
        return reply or None
    if isinstance(reply, list):
        extracted = _extract_reply_from_payloads(reply)
        return extracted if extracted is not None else (reply or None)
    if isinstance(reply, str):
        cleaned = reply.strip()
        if not cleaned:
            return None
        parsed = _parse_json_from_text(cleaned)
        if parsed is not None and parsed != cleaned:
            return _extract_business_reply(parsed)
        return parsed if parsed is not None else cleaned
    return reply


def _extract_reply_from_payloads(payloads: list[Any]) -> Any:
    payload_texts = _extract_payload_texts(payloads)
    for text in reversed(payload_texts):
        parsed = _parse_json_from_text(text)
        if parsed is not None:
            return parsed
    if payload_texts:
        return payload_texts[-1]
    for item in reversed(payloads):
        extracted = _extract_business_reply(item)
        if extracted is not None:
            return extracted
    return None


def _extract_payload_texts(payloads: list[Any]) -> list[str]:
    texts = []
    for item in payloads:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            texts.append(text.strip())
    return texts


def _extract_openclaw_progress(value: Any) -> list[str]:
    if isinstance(value, dict):
        explicit = _coerce_progress_list(value.get("progress"))
        if explicit:
            return explicit
        payloads = value.get("result", {}).get("payloads") if isinstance(value.get("result"), dict) else None
        if isinstance(payloads, list):
            progress = [text for text in _extract_payload_texts(payloads) if _parse_json_from_text(text) is None]
            return _dedupe_preserve_order(progress)
        for key in ("reply", "content", "message", "text"):
            if key not in value:
                continue
            nested = _extract_openclaw_progress(value[key])
            if nested:
                return nested
        return []
    if isinstance(value, list):
        progress = [text for text in _extract_payload_texts(value) if _parse_json_from_text(text) is None]
        if progress:
            return _dedupe_preserve_order(progress)
        for item in value:
            nested = _extract_openclaw_progress(item)
            if nested:
                return nested
        return []
    if isinstance(value, str):
        source = _coerce_openclaw_source(value)
        return _extract_openclaw_progress(source) if source is not value else []
    return []


def _extract_openclaw_meta(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        meta = value.get("meta")
        if isinstance(meta, dict) and meta:
            return meta
        duration_ms = value.get("duration_ms")
        if duration_ms is None:
            duration_ms = value.get("durationMs")
        if duration_ms is not None:
            return {"durationMs": duration_ms}
        for key in ("reply", "content", "message", "text"):
            if key not in value:
                continue
            nested = _extract_openclaw_meta(value[key])
            if nested:
                return nested
        return None
    if isinstance(value, str):
        source = _coerce_openclaw_source(value)
        return _extract_openclaw_meta(source) if source is not value else None
    return None


def _extract_openclaw_debug(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    debug = {}
    if value.get("runId"):
        debug["run_id"] = value["runId"]
    if value.get("status"):
        debug["status"] = value["status"]
    if value.get("summary"):
        debug["summary"] = value["summary"]
    return debug


def _looks_like_business_reply(value: dict[str, Any]) -> bool:
    payloads = value.get("result", {}).get("payloads") if isinstance(value.get("result"), dict) else None
    if isinstance(payloads, list):
        return False
    if any(key in value for key in ("runId", "status", "systemPromptReport", "skills", "tools")):
        return False
    business_keys = {
        "skill_id",
        "analysis",
        "actions",
        "ui_summary",
        "intent",
        "selected_skills",
        "skill_results",
        "workflow_suggestion",
        "used_data_sources",
        "items",
        "name",
        "description",
        "desc",
    }
    if any(key in value for key in business_keys):
        return True
    return bool(value.get("name") and value.get("message"))


def _coerce_progress_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _safe_parse_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _safe_parse_structured_text(raw: str) -> Any:
    parsed = _safe_parse_json(raw)
    if parsed is not None:
        if isinstance(parsed, str) and parsed != raw:
            return _safe_parse_structured_text(parsed)
        return parsed

    candidate = raw.strip()
    if not candidate or candidate[0] not in "\"'[{(":
        return None
    try:
        parsed = ast.literal_eval(candidate)
    except (SyntaxError, ValueError):
        return None
    if isinstance(parsed, str) and parsed != raw:
        return _safe_parse_structured_text(parsed)
    return parsed


def save_custom_skill(base_dir: str, skill: dict[str, Any]) -> dict[str, Any]:
    path = _custom_skills_path(base_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    items = _load_custom_skills(base_dir)
    normalized = _normalize_custom_skill_spec(skill)
    normalized["created_at"] = skill.get("created_at") or _service_now_iso()
    normalized["updated_at"] = _service_now_iso()

    replaced = False
    for index, item in enumerate(items):
        if item.get("id") == normalized["id"] and item.get("shop_id") == normalized.get("shop_id"):
            normalized["created_at"] = item.get("created_at") or normalized["created_at"]
            items[index] = normalized
            replaced = True
            break
    if not replaced:
        items.append(normalized)

    with open(path, "w", encoding="utf-8") as fp:
        json.dump(items, fp, ensure_ascii=False, indent=2)
    return normalized


def _load_custom_skills(base_dir: str) -> list[dict[str, Any]]:
    path = _custom_skills_path(base_dir)
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as fp:
            raw = json.load(fp)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
    skills = []
    for item in raw:
        if isinstance(item, dict):
            normalized = _normalize_custom_skill_spec(item)
            normalized["created_at"] = item.get("created_at") or normalized.get("created_at") or _service_now_iso()
            normalized["updated_at"] = item.get("updated_at") or normalized["created_at"]
            skills.append(normalized)
    skills.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return skills


def _custom_skills_path(base_dir: str) -> str:
    return os.path.join(base_dir, "data", CUSTOM_SKILLS_FILENAME)


def _merchant_history_path(base_dir: str) -> str:
    return os.path.join(base_dir, "data", MERCHANT_HISTORY_FILENAME)


def _resolve_skill_definition(base_dir: str, skill_id: str, shop_id: str | None = None) -> dict[str, Any]:
    if skill_id in SKILL_REGISTRY:
        return {"id": skill_id, "kind": "builtin", **SKILL_REGISTRY[skill_id]}
    for item in _load_custom_skills(base_dir):
        if shop_id and str(item.get("shop_id") or "").strip() != str(shop_id).strip():
            continue
        if item.get("id") == skill_id:
            return item
    raise ValueError(f"Unknown skill_id: {skill_id}")


def _build_generated_merchant_skills(
    base_dir: str,
    shop_id: str,
    period_days: int,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    profile = _generated_merchant_style_profile(snapshot)
    report = _generated_periodic_ops_report(snapshot, period_days)
    competitors = _generated_competitor_analysis(base_dir, snapshot, period_days)
    hot = _generated_hot_style_launch(snapshot)
    cold = _generated_cold_style_retire(snapshot)
    queue = automation_queue(shop_id, profile, report, competitors, hot, cold)
    return {
        "mode": "local_fallback",
        "shop": snapshot["shop"],
        "period_days": period_days,
        "generated_at": datetime.now(BJT).isoformat(),
        "overview": _generated_dashboard_overview(snapshot, period_days),
        "skills": {
            "merchant_style_profile": profile,
            "periodic_ops_report": report,
            "same_style_competitor_analysis": competitors,
            "hot_style_launch": hot,
            "cold_style_retire": cold,
            "automation_queue": queue,
        },
    }


def _local_fallback_for_skill(local_payload: dict[str, Any], skill_id: str, skill_definition: dict[str, Any]) -> dict[str, Any]:
    if skill_id in local_payload.get("skills", {}):
        return local_payload["skills"][skill_id]
    related = {}
    for action in skill_definition.get("actions", []):
        if action in local_payload.get("skills", {}):
            related[action] = local_payload["skills"][action]
    return {
        "skill": skill_id,
        "kind": "custom_skill",
        "name": skill_definition.get("name", skill_id),
        "desc": skill_definition.get("desc", ""),
        "message": skill_definition.get("message", ""),
        "estimated_seconds": skill_definition.get("estimated_seconds", 75),
        "recommended_base_skills": skill_definition.get("actions", []),
        "related_snapshots": related,
    }


def _extract_custom_skill_spec(reply: Any) -> dict[str, Any] | None:
    structured = _extract_structured_reply(reply)
    if not isinstance(structured, dict):
        return None
    required = structured.get("name") and structured.get("desc") and structured.get("message")
    if not required:
        return None
    return _normalize_custom_skill_spec(structured)


def _extract_structured_reply(reply: Any) -> dict[str, Any] | None:
    if isinstance(reply, dict):
        if reply.get("name") and reply.get("message"):
            return reply
        if isinstance(reply.get("result"), dict) and isinstance(reply["result"].get("payloads"), list):
            payloads = reply["result"]["payloads"]
            for item in reversed(payloads):
                text = item.get("text") if isinstance(item, dict) else ""
                parsed = _parse_json_from_text(text)
                if isinstance(parsed, dict):
                    return parsed
        for key in ("reply", "content", "message", "text"):
            if key in reply:
                parsed = _extract_structured_reply(reply[key])
                if parsed:
                    return parsed
        return None
    if isinstance(reply, list):
        for item in reversed(reply):
            parsed = _extract_structured_reply(item)
            if parsed:
                return parsed
        return None
    if isinstance(reply, str):
        parsed = _parse_json_from_text(reply)
        return parsed if isinstance(parsed, dict) else None
    return None


def _parse_json_from_text(text: str | None) -> Any:
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    direct = _safe_parse_structured_text(cleaned)
    if direct is not None:
        return direct
    fenced = re.search(r"```json\s*([\s\S]*?)```", cleaned, re.IGNORECASE) or re.search(r"```\s*([\s\S]*?)```", cleaned)
    candidate = fenced.group(1).strip() if fenced else cleaned
    parsed_candidate = _safe_parse_structured_text(candidate)
    if parsed_candidate is not None:
        return parsed_candidate
    return _extract_last_json_value(candidate if fenced else cleaned)


def _normalize_custom_skill_spec(skill: dict[str, Any]) -> dict[str, Any]:
    name = str(skill.get("name") or "自定义商家技能").strip()
    desc = str(skill.get("desc") or skill.get("description") or "基于商家需求生成的自定义技能").strip()
    message = str(skill.get("message") or skill.get("prompt") or f"请执行技能：{name}").strip()
    skill_id = _slugify_skill_id(str(skill.get("id") or name or message))
    shop_id = str(skill.get("shop_id") or "").strip()
    actions = [str(item).strip() for item in skill.get("actions", []) if str(item).strip()] if isinstance(skill.get("actions"), list) else []
    trigger_examples = [str(item).strip() for item in skill.get("trigger_examples", []) if str(item).strip()] if isinstance(skill.get("trigger_examples"), list) else []
    output_schema = skill.get("output_schema") if isinstance(skill.get("output_schema"), dict) else {"summary": "string", "actions": "array"}
    estimated_seconds = _coerce_estimated_seconds(skill.get("estimated_seconds"))
    return {
        "id": skill_id,
        "kind": "custom",
        "name": name,
        "description": desc,
        "desc": desc,
        "message": message,
        "estimated_seconds": estimated_seconds,
        "trigger_examples": trigger_examples[:4],
        "output_schema": output_schema,
        "actions": actions[:8],
        "shop_id": shop_id,
    }


def _fallback_custom_skill_spec(message: str) -> dict[str, Any]:
    text = message.strip()
    title = _derive_skill_title(text)
    related_actions = [
        skill_id for skill_id, keywords in {
            "merchant_style_profile": ["风格", "画像", "定位"],
            "periodic_ops_report": ["周期", "周报", "月报", "运营"],
            "same_style_competitor_analysis": ["竞品", "对比", "同风格"],
            "hot_style_launch": ["爆款", "上新", "上线"],
            "cold_style_retire": ["冷门", "下架", "降权", "改款"],
            "automation_queue": ["动作", "任务", "队列", "自动化"],
        }.items()
        if any(token in text for token in keywords)
    ]
    if not related_actions:
        related_actions = ["automation_queue"]
    return {
        "id": _slugify_skill_id(title),
        "name": title,
        "desc": text[:60] if text else "自定义商家技能",
        "message": text,
        "estimated_seconds": 75,
        "trigger_examples": [text],
        "output_schema": {"summary": "string", "actions": "array"},
        "actions": related_actions,
    }


def _derive_skill_title(message: str) -> str:
    text = re.sub(r"[：:，。,.!?！\n]+", " ", message).strip()
    text = re.sub(r"\b(skill|skills)\b", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"^(请|帮我|我想|新建|创建|新增)\s*", "", text)
    if not text:
        return "自定义商家技能"
    return text[:18]


def _slugify_skill_id(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        text = f"custom_skill_{int(datetime.now(BJT).timestamp())}"
    if not text.startswith("custom_"):
        text = f"custom_{text}"
    return text[:48]


def _coerce_estimated_seconds(value: Any) -> int:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        seconds = 75
    return max(20, min(seconds, 180))


def _service_now_iso() -> str:
    return datetime.now(BJT).isoformat()


def _load_merchant_history(base_dir: str) -> list[dict[str, Any]]:
    path = _merchant_history_path(base_dir)
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as fp:
            raw = json.load(fp)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
    items = []
    for item in raw:
        if isinstance(item, dict):
            items.append(_normalize_history_entry(item))
    items.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return items


def _normalize_history_entry(entry: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_history_payload_for_display(_sanitize_history_payload(entry.get("payload")))
    shop_id = str(entry.get("shop_id") or "").strip()
    if shop_id and shop_id in SHOP_BY_ID:
        shop = _shop_public(SHOP_BY_ID[shop_id])
    else:
        shop = entry.get("shop") if isinstance(entry.get("shop"), dict) else None
    title = str(entry.get("title") or _derive_history_title(payload) or "商家记录").strip()
    summary = str(entry.get("summary") or "").strip()
    derived_summary = str(_derive_history_summary(payload) or "").strip()
    if not summary or _looks_like_raw_history_summary(summary):
        summary = derived_summary
    record_id = str(entry.get("id") or f"history_{uuid4().hex[:12]}").strip()
    created_at = str(entry.get("created_at") or _service_now_iso()).strip()
    return {
        "id": record_id,
        "type": str(entry.get("type") or "result").strip() or "result",
        "title": title,
        "summary": summary,
        "user_message": str(entry.get("user_message") or "").strip(),
        "skill_id": str(entry.get("skill_id") or "").strip(),
        "shop_id": shop_id,
        "shop_name": str(entry.get("shop_name") or (shop.get("name") if isinstance(shop, dict) else "") or "").strip(),
        "shop": shop,
        "period_days": int(entry.get("period_days") or 14),
        "created_at": created_at,
        "payload": payload,
    }


def _sanitize_history_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {}
        for key, value in payload.items():
            if key in {"prompt", "registry"}:
                continue
            sanitized[key] = _sanitize_history_payload(value)
        return sanitized
    if isinstance(payload, list):
        return [_sanitize_history_payload(item) for item in payload]
    return payload


def _normalize_history_payload_for_display(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    normalized = dict(payload)
    openclaw = normalized.get("openclaw")
    if isinstance(openclaw, dict):
        merged = dict(openclaw)
        for candidate in (openclaw.get("reply"), openclaw.get("raw")):
            parsed = _normalize_openclaw_result(candidate)
            if merged.get("reply") is None and parsed.get("reply") is not None:
                merged["reply"] = parsed["reply"]
            elif isinstance(merged.get("reply"), str) and parsed.get("reply") is not None:
                merged["reply"] = parsed["reply"]
            if not merged.get("progress") and parsed.get("progress"):
                merged["progress"] = parsed["progress"]
            if not merged.get("meta") and parsed.get("meta"):
                merged["meta"] = parsed["meta"]
            if not merged.get("debug") and parsed.get("debug"):
                merged["debug"] = parsed["debug"]
        normalized["openclaw"] = merged
    return normalized


def _looks_like_raw_history_summary(text: str) -> bool:
    cleaned = text.strip()
    if len(cleaned) > 180 and cleaned[:1] in "[{":
        return True
    markers = ('"runId"', '"payloads"', '"systemPromptReport"', '"finalAssistantVisibleText"')
    return any(marker in cleaned for marker in markers)


def _derive_history_title(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    if isinstance(payload.get("created_skill"), dict):
        return str(payload["created_skill"].get("name") or "").strip()
    if payload.get("mode") == "openclaw_agent_dispatch":
        return "商家自由会话"
    if payload.get("skill_definition") and isinstance(payload["skill_definition"], dict):
        return str(payload["skill_definition"].get("name") or "").strip()
    skill_id = str(payload.get("skill_id") or "").strip()
    if skill_id:
        definition = SKILL_REGISTRY.get(skill_id)
        if definition:
            return str(definition.get("name") or "").strip()
    return ""


def _derive_history_summary(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    if isinstance(payload.get("created_skill"), dict):
        return str(payload["created_skill"].get("desc") or payload["created_skill"].get("description") or "").strip()
    openclaw = payload.get("openclaw") if isinstance(payload.get("openclaw"), dict) else {}
    reply = openclaw.get("reply")
    if isinstance(reply, dict):
        if reply.get("ui_summary"):
            return str(reply["ui_summary"]).strip()
        analysis = reply.get("analysis")
        if isinstance(analysis, dict) and analysis.get("style_summary"):
            return str(analysis["style_summary"]).strip()
    if isinstance(reply, str):
        return reply.strip()[:120]
    fallback = payload.get("local_fallback")
    if isinstance(fallback, dict):
        for key in ("summary", "trend_summary", "style_summary", "desc"):
            if fallback.get(key):
                return str(fallback[key]).strip()
    return ""


def _openclaw_runtime() -> dict[str, Any]:
    requested_transport = (os.environ.get("OPENCLAW_TRANSPORT") or "remote_http").strip().lower()
    local_command_path = shutil.which("openclaw")
    remote_base_url, remote_source = _discover_remote_base_url()
    remote_chat_path = (os.environ.get("OPENCLAW_REMOTE_CHAT_PATH") or DEFAULT_REMOTE_CHAT_PATH).strip() or DEFAULT_REMOTE_CHAT_PATH
    if not remote_chat_path.startswith("/"):
        remote_chat_path = "/" + remote_chat_path
    remote_url = f"{remote_base_url}{remote_chat_path}" if remote_base_url else None

    if requested_transport == "auto":
        if remote_url:
            transport = "remote_http"
        elif local_command_path:
            transport = "local_cli"
        else:
            transport = "none"
    elif requested_transport == "remote_http":
        transport = "remote_http" if remote_url else "none"
    elif requested_transport == "local_cli":
        transport = "local_cli" if local_command_path else "none"
    else:
        transport = "none"

    return {
        "transport": transport,
        "requested_transport": requested_transport,
        "local_command_path": local_command_path,
        "remote_base_url": remote_base_url,
        "remote_url": remote_url,
        "remote_source": remote_source,
    }


def _discover_remote_base_url() -> tuple[str, str | None]:
    env_url = (os.environ.get("OPENCLAW_REMOTE_BASE_URL") or "").strip().rstrip("/")
    if env_url:
        return env_url, "env"

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        ("wiki", os.path.join(project_root, "wiki", "20260507.txt")),
        ("readme", os.path.join(project_root, "README.md")),
    ]
    pattern = re.compile(r"https?://[^\s\"']+:5000")
    for source, path in candidates:
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as fp:
                content = fp.read()
        except OSError:
            continue
        matches = [match.rstrip("/") for match in pattern.findall(content)]
        if not matches:
            continue
        non_local = [url for url in matches if urllib.parse.urlparse(url).hostname not in {"localhost", "127.0.0.1"}]
        if non_local:
            return non_local[0], source
        return matches[0], source
    return "", None


def _load_context(base_dir: str) -> dict[str, Any]:
    data_dir = os.path.join(base_dir, "data")
    logs = _load_logs(os.path.join(data_dir, "tryon.jsonl"))
    db_path = os.path.join(data_dir, "jiaqu.db")
    return {
        "logs": logs,
        "starts": [r for r in logs if r.get("event") == "tryon_start"],
        "successes": [r for r in logs if r.get("event") == "tryon_success"],
        "feedbacks": [r for r in logs if r.get("event") == "feedback"],
        "likes": [r for r in logs if r.get("event") == "feedback" and r.get("action") == "like"],
        "dislikes": [r for r in logs if r.get("event") == "feedback" and r.get("action") == "dislike"],
        "books": [r for r in logs if r.get("event") == "feedback" and r.get("action") == "book"],
        "plaza_by_style": _load_plaza(db_path),
        "trend_by_cat": _load_trends(db_path),
    }


def _load_logs(path: str) -> list[dict[str, Any]]:
    if not os.path.exists(path):
        return []
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        records = []
        try:
            with open(path, encoding=encoding) as fp:
                for line in fp:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            return records
        except UnicodeDecodeError:
            continue
    return []


def _load_plaza(db_path: str) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = defaultdict(lambda: {"posts": 0, "likes": 0})
    if not os.path.exists(db_path):
        return dict(result)
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT style_id, COUNT(*) AS posts, COALESCE(SUM(likes), 0) AS likes "
            "FROM plaza WHERE style_id IS NOT NULL AND style_id != '' GROUP BY style_id"
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return dict(result)
    for style_id, posts, likes in rows:
        if style_id in STYLE_CATEGORIES:
            result[style_id] = {"posts": int(posts), "likes": int(likes)}
    return dict(result)


def _load_trends(db_path: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = defaultdict(lambda: {"mention_count": 0, "growth_rate": 0.0, "top_tags": []})
    if not os.path.exists(db_path):
        return dict(result)
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT style_tag, SUM(mention_count) AS mentions, AVG(growth_rate) AS growth "
            "FROM community_trends GROUP BY style_tag"
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return dict(result)
    tag_to_cat = {
        "ice_clear": "A", "nude_cream": "A", "milk_coffee": "B", "strawberry_heart": "B",
        "rhinestone": "C", "laser_aurora": "C", "maillard": "D", "dark_metal": "D",
        "snowflake": "E", "dopamine_color": "E",
    }
    for tag, mentions, growth in rows:
        cat = tag_to_cat.get(str(tag), None)
        if not cat:
            cat = _guess_cat_from_tag(str(tag))
        result[cat]["mention_count"] += int(mentions or 0)
        result[cat]["growth_rate"] = round((result[cat]["growth_rate"] + float(growth or 0.0)) / 2, 4)
        result[cat]["top_tags"].append({"tag": tag, "mentions": int(mentions or 0), "growth_rate": float(growth or 0.0)})
    return dict(result)


def _guess_cat_from_tag(tag: str) -> str:
    if any(token in tag.lower() for token in ("sweet", "heart", "coffee")):
        return "B"
    if any(token in tag.lower() for token in ("stone", "aurora", "glam")):
        return "C"
    if any(token in tag.lower() for token in ("dark", "metal", "maillard")):
        return "D"
    if any(token in tag.lower() for token in ("snow", "dopamine", "color")):
        return "E"
    return "A"


def _style_metrics(data: dict[str, Any], style_id: str) -> dict[str, Any]:
    starts = [r for r in data["starts"] if r.get("style_id") == style_id]
    likes = [r for r in data["likes"] if r.get("style_id") == style_id]
    dislikes = [r for r in data["dislikes"] if r.get("style_id") == style_id]
    books = [r for r in data["books"] if r.get("style_id") == style_id]
    fb_total = len(likes) + len(dislikes)
    return {
        "style_id": style_id,
        "tryons": len(starts),
        "likes": len(likes),
        "dislikes": len(dislikes),
        "books": len(books),
        "like_rate": round(len(likes) / fb_total, 3) if fb_total else 0,
        "booking_rate": round(len(books) / len(starts), 3) if starts else 0,
    }


def _period_metrics(logs: list[dict[str, Any]], shop_id: str) -> dict[str, Any]:
    starts = [r for r in logs if r.get("event") == "tryon_start"]
    feedbacks = [r for r in logs if r.get("event") == "feedback"]
    likes = [r for r in feedbacks if r.get("action") == "like"]
    dislikes = [r for r in feedbacks if r.get("action") == "dislike"]
    books = [r for r in feedbacks if r.get("action") == "book"]
    shop_books = [r for r in books if r.get("shop_id") == shop_id]
    fb_total = len(likes) + len(dislikes)
    return {
        "tryons": len(starts),
        "likes": len(likes),
        "dislikes": len(dislikes),
        "books": len(books),
        "shop_books": len(shop_books),
        "like_rate": round(len(likes) / fb_total, 3) if fb_total else 0,
        "booking_rate": round(len(books) / len(starts), 3) if starts else 0,
        "shop_booking_share": round(len(shop_books) / len(books), 3) if books else 0,
    }


def _shop_scorecard(data: dict[str, Any], shop_id: str) -> dict[str, Any]:
    shop = SHOP_BY_ID[shop_id]
    styles = _styles_for_category(shop["style"])
    starts = [r for r in data["starts"] if r.get("style_id") in styles]
    likes = [r for r in data["likes"] if r.get("style_id") in styles]
    dislikes = [r for r in data["dislikes"] if r.get("style_id") in styles]
    books = [r for r in data["books"] if r.get("shop_id") == shop_id]
    fb_total = len(likes) + len(dislikes)
    return {
        "tryons": len(starts),
        "likes": len(likes),
        "books": len(books),
        "like_rate": round(len(likes) / fb_total, 3) if fb_total else 0,
        "booking_rate": round(len(books) / len(starts), 3) if starts else 0,
        "price_avg": shop["price_avg"],
        "rating": shop["rating"],
    }


def _top_categories(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter = Counter(_style_cat(r.get("style_id")) for r in logs if r.get("event") == "tryon_start")
    return [{"category": cat, "name": CATEGORY_NAMES.get(cat, cat), "count": count} for cat, count in counter.most_common() if cat != "?"]


def _top_styles(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter = Counter(r.get("style_id") for r in logs if r.get("event") == "tryon_start" and r.get("style_id"))
    return [{"style_id": sid, "count": count} for sid, count in counter.most_common(10)]


def _period_actions(metrics: dict[str, Any], shop_id: str) -> list[dict[str, str]]:
    actions = []
    if metrics["shop_books"] >= 3:
        actions.append({"type": "boost_shop_exposure", "target": shop_id, "reason": "shop_bookings_good"})
    if metrics["booking_rate"] < 0.08 and metrics["tryons"]:
        actions.append({"type": "improve_booking_cta", "target": shop_id, "reason": "booking_conversion_low"})
    return actions


def _hot_actions(style_fit: float, metrics: dict[str, Any], trend: dict[str, Any]) -> list[str]:
    actions = ["promote_shop"]
    if style_fit >= 0.8:
        actions.append("promote_homepage")
    if metrics["like_rate"] >= 0.6 or trend["growth_rate"] > 0.06:
        actions.append("generate_variant")
    if metrics["booking_rate"] >= 0.15:
        actions.append("campaign_ready")
    return actions


def _cold_action(risk_score: int) -> str:
    if risk_score >= 70:
        return "retire"
    if risk_score >= 50:
        return "deprioritize"
    if risk_score >= 30:
        return "revise"
    return "observe"


def _styles_for_category(cat: str) -> list[str]:
    return [sid for sid, style_cat in STYLE_CATEGORIES.items() if style_cat == cat]


def _style_cat(style_id: str | None) -> str:
    return STYLE_CATEGORIES.get(style_id or "", "?")


def _category_similarity(a: str, b: str) -> float:
    if a == b:
        return 1.0
    matrix = {
        "A": {"B": 0.55, "C": 0.45, "D": 0.25, "E": 0.35},
        "B": {"A": 0.55, "C": 0.35, "D": 0.25, "E": 0.45},
        "C": {"A": 0.45, "B": 0.35, "D": 0.45, "E": 0.55},
        "D": {"A": 0.25, "B": 0.25, "C": 0.45, "E": 0.55},
        "E": {"A": 0.35, "B": 0.45, "C": 0.55, "D": 0.55},
    }
    return matrix.get(a, {}).get(b, 0.3)


def _shop_public(shop: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": shop["id"],
        "name": shop["name"],
        "style": shop["style"],
        "style_name": CATEGORY_NAMES[shop["style"]],
        "rating": shop["rating"],
        "price_avg": shop["price_avg"],
    }


def _latest_ts(logs: list[dict[str, Any]]) -> datetime | None:
    timestamps = [_parse_ts(r.get("ts")) for r in logs]
    timestamps = [ts for ts in timestamps if ts]
    return max(timestamps) if timestamps else None


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=BJT)
        return parsed.astimezone(BJT)
    except ValueError:
        return None


def _in_range(record: dict[str, Any], start: datetime, end: datetime) -> bool:
    ts = _parse_ts(record.get("ts"))
    return bool(ts and start <= ts <= end)


def _delta(current: float, previous: float) -> dict[str, float | None]:
    if previous == 0:
        return {"absolute": current - previous, "relative": None}
    return {"absolute": current - previous, "relative": round((current - previous) / previous, 3)}


def _avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def _load_generated_shop_snapshot(base_dir: str, shop_id: str, period_days: int) -> dict[str, Any] | None:
    profile = _load_generated_shop_profile(base_dir, shop_id)
    if not profile:
        return None
    db_path = os.path.join(base_dir, "data", "jiaqu.db")
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        catalog_rows = conn.execute(
            """
            SELECT shop_id, style_id, style_name, category, price, cost, duration_minutes, search_volume_30d,
                   click_volume_30d, cart_volume_30d, group_buy_orders_30d, ctr, conversion_rate,
                   refund_orders_30d, favorite_count_30d, share_count_30d, impression_volume_30d,
                   cpc, gmv_30d, inventory_status, launch_stage, trend_signal, title_tags,
                   primary_style, secondary_style, nail_shape, nail_length, primary_color, accent_colors,
                   transparency, texture_finish, base_coat, core_techniques, support_techniques,
                   element_tags, occasion_tags, complexity_tier, merchant_generation_mode,
                   design_prompt, style_image_url, style_image_prompt, style_image_status
            FROM merchant_style_catalog
            WHERE shop_id = ?
            ORDER BY group_buy_orders_30d DESC, click_volume_30d DESC, search_volume_30d DESC
            """,
            (shop_id,),
        ).fetchall()
        daily_rows = conn.execute(
            """
            SELECT date, search_volume, click_volume, consultation_volume, group_buy_orders, revenue,
                   ad_spend, repeat_orders, refund_orders, favorites_added
            FROM merchant_shop_daily_metrics
            WHERE shop_id = ?
            ORDER BY date DESC
            LIMIT ?
            """,
            (shop_id, max(14, period_days * 3)),
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return None

    catalog = []
    for row in catalog_rows:
        item = dict(row)
        for key in ("title_tags", "accent_colors", "core_techniques", "support_techniques", "element_tags", "occasion_tags"):
            raw = item.get(key)
            try:
                parsed = json.loads(raw) if isinstance(raw, str) and raw.strip() else []
            except json.JSONDecodeError:
                parsed = []
            item[key] = parsed if isinstance(parsed, list) else []
        catalog.append(item)

    daily = [dict(row) for row in daily_rows]
    return {
        "profile": profile,
        "shop": _generated_shop_public(profile),
        "catalog": catalog,
        "daily": daily,
    }


def _load_generated_shop_profile(base_dir: str, shop_id: str) -> dict[str, Any] | None:
    db_path = os.path.join(base_dir, "data", "jiaqu.db")
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT shop_id, shop_name, city, district, style, style_name, style_persona_name, style_keywords, target_audiences, rating, review_count, avg_ticket,
                   monthly_revenue, repeat_customer_rate, refund_rate, complaint_rate, store_status,
                   hero_sku_id, hero_sku_name, owner_name
            FROM merchant_profiles
            WHERE shop_id = ?
            """,
            (shop_id,),
        ).fetchone()
        conn.close()
    except sqlite3.Error:
        return None
    return dict(row) if row else None


def _generated_shop_public(profile: dict[str, Any]) -> dict[str, Any]:
    style_code = str(profile.get("style") or "A")
    return {
        "id": profile["shop_id"],
        "name": profile["shop_name"],
        "style": style_code,
        "style_name": profile.get("style_name") or CATEGORY_NAMES.get(style_code, style_code),
        "style_persona_name": profile.get("style_persona_name") or profile.get("style_name") or CATEGORY_NAMES.get(style_code, style_code),
        "rating": profile.get("rating", 0),
        "price_avg": profile.get("avg_ticket", 0),
        "city": profile.get("city", ""),
        "district": profile.get("district", ""),
    }


def _generated_merchant_style_profile(snapshot: dict[str, Any]) -> dict[str, Any]:
    profile = snapshot["profile"]
    catalog = snapshot["catalog"]
    category_counter: dict[str, int] = defaultdict(int)
    for item in catalog:
        category_counter[str(item.get("category") or profile["style"])] += int(item.get("group_buy_orders_30d") or 0) * 3 + int(item.get("click_volume_30d") or 0)
    total = sum(category_counter.values()) or 1
    style_mix = [
        {
            "category": cat,
            "name": _category_display_name(cat),
            "count": score,
            "ratio": round(score / total, 3),
        }
        for cat, score in sorted(category_counter.items(), key=lambda item: item[1], reverse=True)
    ]
    top_related_styles = [_catalog_item_to_style_card(item) for item in catalog[:5]]
    strengths = []
    if float(profile.get("rating") or 0) >= 4.7:
        strengths.append(f"门店评分 {profile['rating']}，口碑基础稳。")
    if float(profile.get("repeat_customer_rate") or 0) >= 0.35:
        strengths.append(f"复购率约 {round(float(profile['repeat_customer_rate']) * 100)}%，老客粘性不错。")
    if profile.get("hero_sku_name"):
        strengths.append(f"主力款「{profile['hero_sku_name']}」已经形成稳定成交。")
    risks = []
    if float(profile.get("refund_rate") or 0) >= 0.05:
        risks.append(f"退款率约 {round(float(profile['refund_rate']) * 100)}%，需要排查服务和定价。")
    if float(profile.get("complaint_rate") or 0) >= 0.015:
        risks.append(f"投诉率约 {round(float(profile['complaint_rate']) * 100)}%，建议回看差评原因。")
    low_conv = [item for item in catalog if float(item.get("conversion_rate") or 0) < 0.06]
    if low_conv:
        risks.append(f"{len(low_conv)} 个款式存在高点击低团购，需要优化卖点和预约链路。")
    recommended_direction = []
    rising = [item for item in catalog if str(item.get("trend_signal") or "") in {"rising", "breakout"}]
    if rising:
        recommended_direction.append(f"优先扩充 {rising[0]['style_name']} 这类上升趋势款的变体。")
    recommended_direction.append(f"继续放大 {_category_display_name(profile['style'])} 这一主风格，保持门店识别度。")
    return {
        "skill": "merchant_style_profile",
        "shop_id": profile["shop_id"],
        "shop": snapshot["shop"],
        "primary_category": profile["style"],
        "primary_category_name": profile.get("style_name") or _category_display_name(profile["style"]),
        "style_summary": f"{profile['shop_name']} 当前以{profile.get('style_name') or _category_display_name(profile['style'])}为主，客单价约 ¥{profile['avg_ticket']}，适合围绕主力款继续做系列化扩展。",
        "style_mix": style_mix,
        "top_related_styles": top_related_styles,
        "strengths": strengths,
        "risks": risks,
        "recommended_direction": recommended_direction,
    }


def _generated_periodic_ops_report(snapshot: dict[str, Any], period_days: int) -> dict[str, Any]:
    daily = snapshot["daily"]
    current_rows = daily[:period_days]
    previous_rows = daily[period_days:period_days * 2]
    current = _aggregate_generated_period(current_rows)
    previous = _aggregate_generated_period(previous_rows)
    alerts = []
    if current["ctr"] < 0.12 and current["search_volume"]:
        alerts.append({"level": "medium", "message": "搜索曝光有了，但点击效率偏低，建议重写标题与首图卖点。"})
    if current["booking_rate"] < 0.09 and current["click_volume"]:
        alerts.append({"level": "high", "message": "点击到团购转化偏低，建议检查套餐描述、团购价和预约引导。"})
    if current["refund_rate"] >= 0.06 and current["group_buy_orders"]:
        alerts.append({"level": "medium", "message": "退款率偏高，建议排查履约和售后说明。"})
    if current["revenue"] > previous["revenue"] * 1.15 and previous["revenue"]:
        alerts.append({"level": "positive", "message": "本期营收明显提升，可继续加码主力风格。"})
    top_styles = [
        {
            "style_id": item["style_id"],
            "name": item["style_name"],
            "count": int(item.get("group_buy_orders_30d") or 0),
            "clicks": int(item.get("click_volume_30d") or 0),
        }
        for item in snapshot["catalog"][:5]
    ]
    top_categories = []
    category_sum: dict[str, int] = defaultdict(int)
    for item in snapshot["catalog"]:
        category_sum[str(item.get("category") or snapshot["profile"]["style"])] += int(item.get("group_buy_orders_30d") or 0)
    for cat, count in sorted(category_sum.items(), key=lambda item: item[1], reverse=True):
        top_categories.append({"category": cat, "name": _category_display_name(cat), "count": count})
    return {
        "skill": "periodic_ops_report",
        "window": {"days": period_days},
        "metrics": current,
        "previous_metrics": previous,
        "deltas": {key: _delta(current.get(key, 0), previous.get(key, 0)) for key in (
            "search_volume", "click_volume", "group_buy_orders", "revenue", "tryons", "likes", "books", "shop_books"
        )},
        "trend_summary": f"近 {period_days} 天搜索 {current['search_volume']}、点击 {current['click_volume']}、团购 {current['group_buy_orders']}、营收 ¥{current['revenue']}。",
        "top_categories": top_categories[:4],
        "top_styles": top_styles,
        "alerts": alerts,
        "actions": _generated_period_actions(current, snapshot["profile"]["shop_id"]),
    }


def _generated_dashboard_overview(snapshot: dict[str, Any], period_days: int) -> dict[str, Any]:
    current_rows_desc = snapshot["daily"][:period_days]
    current_rows = list(reversed(current_rows_desc))
    totals = _aggregate_generated_period(current_rows_desc)
    return {
        "has_chart_data": bool(current_rows),
        "period_days": period_days,
        "daily_series": [
            {
                "date": item.get("date"),
                "search_volume": int(item.get("search_volume") or 0),
                "click_volume": int(item.get("click_volume") or 0),
                "consultation_volume": int(item.get("consultation_volume") or 0),
                "group_buy_orders": int(item.get("group_buy_orders") or 0),
                "revenue": int(item.get("revenue") or 0),
                "ad_spend": int(item.get("ad_spend") or 0),
                "repeat_orders": int(item.get("repeat_orders") or 0),
                "refund_orders": int(item.get("refund_orders") or 0),
                "favorites_added": int(item.get("favorites_added") or 0),
            }
            for item in current_rows
        ],
        "totals": totals,
    }


def _generated_competitor_analysis(base_dir: str, snapshot: dict[str, Any], period_days: int, limit: int = 3) -> dict[str, Any]:
    profile = snapshot["profile"]
    current = _aggregate_generated_period(snapshot["daily"][:period_days])
    peers = _load_generated_peer_group(base_dir, profile["style"], profile["shop_id"], period_days, limit=max(limit, 6))
    peer_group = peers[:limit]
    peer_booking_rates = [item["booking_rate"] for item in peer_group]
    own_booking = current["booking_rate"]
    peer_tryons = [item["tryons"] for item in peer_group]
    own_tryons = current["tryons"]
    advantages = []
    if float(profile.get("rating") or 0) >= _avg([float(item["shop"].get("rating") or 0) for item in peer_group if item.get("shop")]):
        advantages.append("门店评分高于同风格均值，口碑更容易支撑高客单成交。")
    if own_booking >= _avg(peer_booking_rates):
        advantages.append("本店点击转团购效率不低于同风格门店。")
    gaps = []
    if peer_booking_rates and own_booking < _avg(peer_booking_rates):
        gaps.append("当前成交转化率低于同风格门店均值。")
    if peer_tryons and own_tryons < _avg(peer_tryons):
        gaps.append("门店当前流量样本低于同风格门店均值，仍有放量空间。")
    opportunities = []
    if gaps:
        opportunities.append("可参考同风格高转化门店的套餐包装、首页卖点和爆款排序。")
    else:
        opportunities.append("可以用高评分和主风格稳定性继续放大高毛利系列。")
    return {
        "skill": "same_style_competitor_analysis",
        "current_shop": {
            **snapshot["shop"],
            "tryons": current["tryons"],
            "likes": current["likes"],
            "books": current["books"],
            "booking_rate": current["booking_rate"],
        },
        "peer_group": peer_group,
        "competitive_position": "已基于同风格门店样本生成对比视角。",
        "advantages": advantages,
        "gaps": gaps,
        "opportunities": opportunities,
    }


def _generated_hot_style_launch(snapshot: dict[str, Any], limit: int = 6) -> dict[str, Any]:
    candidates = []
    primary_cat = snapshot["profile"]["style"]
    for item in snapshot["catalog"]:
        trend_growth = _trend_growth_from_signal(item.get("trend_signal"))
        score = (
            float(item.get("click_volume_30d") or 0) * 0.08
            + float(item.get("group_buy_orders_30d") or 0) * 2.4
            + float(item.get("favorite_count_30d") or 0) * 0.16
            + float(item.get("ctr") or 0) * 45
            + float(item.get("conversion_rate") or 0) * 70
            + trend_growth * 100
        )
        style_fit = 1.0 if str(item.get("category") or "") == primary_cat else _category_similarity(primary_cat, str(item.get("category") or primary_cat))
        score += style_fit * 12
        candidates.append({
            "style_id": item["style_id"],
            "name": item["style_name"],
            "category": item["category"],
            "score": round(score, 1),
            "reason": "generated_shop_hot_score",
            "metrics": {
                "tryons": int(item.get("click_volume_30d") or 0),
                "likes": int(item.get("favorite_count_30d") or 0),
                "books": int(item.get("group_buy_orders_30d") or 0),
                "like_rate": round(_safe_divide(item.get("favorite_count_30d"), item.get("click_volume_30d")), 3),
                "booking_rate": round(float(item.get("conversion_rate") or 0), 3),
            },
            "external_trend": {
                "growth_rate": trend_growth,
                "signal": item.get("trend_signal") or "stable",
            },
            "plaza": {"posts": int(item.get("share_count_30d") or 0), "likes": int(item.get("favorite_count_30d") or 0)},
            "actions": _generated_hot_actions(item, style_fit, trend_growth),
            "note": f"搜索 {item['search_volume_30d']} / 点击 {item['click_volume_30d']} / 团购 {item['group_buy_orders_30d']}，适合作为近期上新候选。",
        })
    candidates.sort(key=lambda value: value["score"], reverse=True)
    return {"skill": "hot_style_launch", "hot_candidates": candidates[:limit]}


def _generated_cold_style_retire(snapshot: dict[str, Any], limit: int = 6) -> dict[str, Any]:
    candidates = []
    primary_cat = snapshot["profile"]["style"]
    for item in snapshot["catalog"]:
        style_fit = 1.0 if str(item.get("category") or "") == primary_cat else _category_similarity(primary_cat, str(item.get("category") or primary_cat))
        risk = 0
        if int(item.get("search_volume_30d") or 0) <= 80:
            risk += 20
        if float(item.get("ctr") or 0) < 0.09:
            risk += 24
        if float(item.get("conversion_rate") or 0) < 0.05:
            risk += 24
        if int(item.get("refund_orders_30d") or 0) >= 3:
            risk += 18
        if style_fit < 0.5:
            risk += 10
        if risk:
            candidates.append({
                "style_id": item["style_id"],
                "name": item["style_name"],
                "category": item["category"],
                "risk_score": risk,
                "reason": "generated_shop_cold_risk_score",
                "metrics": {
                    "tryons": int(item.get("click_volume_30d") or 0),
                    "likes": int(item.get("favorite_count_30d") or 0),
                    "books": int(item.get("group_buy_orders_30d") or 0),
                    "booking_rate": round(float(item.get("conversion_rate") or 0), 3),
                },
                "external_trend": {"growth_rate": _trend_growth_from_signal(item.get("trend_signal"))},
                "suggested_action": _cold_action(risk),
                "note": f"点击 {item['click_volume_30d']}、团购 {item['group_buy_orders_30d']}、退款 {item['refund_orders_30d']}，需要决定观察、改款或降权。",
            })
    candidates.sort(key=lambda value: value["risk_score"], reverse=True)
    return {"skill": "cold_style_retire", "cold_candidates": candidates[:limit]}


def _load_generated_peer_group(base_dir: str, style: str, exclude_shop_id: str, period_days: int, limit: int = 6) -> list[dict[str, Any]]:
    db_path = os.path.join(base_dir, "data", "jiaqu.db")
    if not os.path.exists(db_path):
        return []
    cutoff = (datetime.now(BJT) - timedelta(days=period_days)).date().isoformat()
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT p.shop_id, p.shop_name, p.city, p.district, p.style, p.style_name, p.rating, p.avg_ticket,
                   COALESCE(SUM(d.search_volume), 0) AS search_volume,
                   COALESCE(SUM(d.click_volume), 0) AS click_volume,
                   COALESCE(SUM(d.group_buy_orders), 0) AS group_buy_orders,
                   COALESCE(SUM(d.revenue), 0) AS revenue
            FROM merchant_profiles p
            LEFT JOIN merchant_shop_daily_metrics d
              ON d.shop_id = p.shop_id AND d.date >= ?
            WHERE p.style = ? AND p.shop_id != ?
            GROUP BY p.shop_id, p.shop_name, p.city, p.district, p.style, p.style_name, p.rating, p.avg_ticket
            ORDER BY group_buy_orders DESC, revenue DESC, p.rating DESC
            LIMIT ?
            """,
            (cutoff, style, exclude_shop_id, max(1, limit)),
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return []
    peers = []
    for row in rows:
        item = dict(row)
        click_volume = int(item.get("click_volume") or 0)
        books = int(item.get("group_buy_orders") or 0)
        peers.append({
            "shop": {
                "id": item["shop_id"],
                "name": item["shop_name"],
                "style": item["style"],
                "style_name": item.get("style_name") or _category_display_name(item["style"]),
                "rating": item["rating"],
                "price_avg": item["avg_ticket"],
                "city": item.get("city", ""),
                "district": item.get("district", ""),
            },
            "style_match": 1.0,
            "tryons": click_volume,
            "likes": 0,
            "books": books,
            "booking_rate": round(books / click_volume, 3) if click_volume else 0.0,
            "revenue": int(item.get("revenue") or 0),
        })
    return peers


def _aggregate_generated_period(rows: list[dict[str, Any]]) -> dict[str, Any]:
    search_volume = sum(int(item.get("search_volume") or 0) for item in rows)
    click_volume = sum(int(item.get("click_volume") or 0) for item in rows)
    consultation_volume = sum(int(item.get("consultation_volume") or 0) for item in rows)
    group_buy_orders = sum(int(item.get("group_buy_orders") or 0) for item in rows)
    revenue = sum(int(item.get("revenue") or 0) for item in rows)
    ad_spend = sum(int(item.get("ad_spend") or 0) for item in rows)
    repeat_orders = sum(int(item.get("repeat_orders") or 0) for item in rows)
    refund_orders = sum(int(item.get("refund_orders") or 0) for item in rows)
    favorites_added = sum(int(item.get("favorites_added") or 0) for item in rows)
    ctr = round(click_volume / search_volume, 3) if search_volume else 0.0
    conversion_rate = round(group_buy_orders / click_volume, 3) if click_volume else 0.0
    refund_rate = round(refund_orders / group_buy_orders, 3) if group_buy_orders else 0.0
    return {
        "search_volume": search_volume,
        "click_volume": click_volume,
        "consultation_volume": consultation_volume,
        "group_buy_orders": group_buy_orders,
        "revenue": revenue,
        "ad_spend": ad_spend,
        "repeat_orders": repeat_orders,
        "refund_orders": refund_orders,
        "favorites_added": favorites_added,
        "tryons": click_volume,
        "likes": favorites_added,
        "books": group_buy_orders,
        "shop_books": group_buy_orders,
        "like_rate": round(favorites_added / click_volume, 3) if click_volume else 0.0,
        "booking_rate": conversion_rate,
        "ctr": ctr,
        "conversion_rate": conversion_rate,
        "refund_rate": refund_rate,
    }


def _generated_period_actions(metrics: dict[str, Any], shop_id: str) -> list[dict[str, str]]:
    actions = []
    if metrics["ctr"] < 0.12 and metrics["search_volume"]:
        actions.append({"type": "boost_shop_exposure", "target": shop_id, "reason": "search_exposure_high_click_rate_low"})
    if metrics["booking_rate"] < 0.09 and metrics["click_volume"]:
        actions.append({"type": "improve_booking_cta", "target": shop_id, "reason": "click_to_group_buy_low"})
    if metrics["refund_rate"] >= 0.06 and metrics["group_buy_orders"]:
        actions.append({"type": "revise", "target": shop_id, "reason": "refund_rate_high"})
    return actions


def _generated_hot_actions(item: dict[str, Any], style_fit: float, trend_growth: float) -> list[str]:
    actions = ["promote_shop"]
    if style_fit >= 0.85:
        actions.append("promote_homepage")
    if trend_growth >= 0.12 or float(item.get("favorite_count_30d") or 0) >= 45:
        actions.append("generate_variant")
    if float(item.get("conversion_rate") or 0) >= 0.14:
        actions.append("campaign_ready")
    return actions


def _catalog_item_to_style_card(item: dict[str, Any]) -> dict[str, Any]:
    clicks = int(item.get("click_volume_30d") or 0)
    favorites = int(item.get("favorite_count_30d") or 0)
    books = int(item.get("group_buy_orders_30d") or 0)
    refunds = int(item.get("refund_orders_30d") or 0)
    return {
        "style_id": item["style_id"],
        "name": item["style_name"],
        "tryons": clicks,
        "likes": favorites,
        "dislikes": refunds,
        "books": books,
        "like_rate": f"{round(_safe_divide(favorites, clicks) * 100)}%",
        "booking_rate": f"{round(_safe_divide(books, clicks) * 100)}%",
        "note": f"售价 ¥{item['price']} · CTR {round(float(item.get('ctr') or 0) * 100)}% · 趋势 {format_trend_signal(item.get('trend_signal'))}",
    }


def _shop_public_for_id(base_dir: str, shop_id: str) -> dict[str, Any]:
    if shop_id in SHOP_BY_ID:
        return _shop_public(SHOP_BY_ID[shop_id])
    profile = _load_generated_shop_profile(base_dir, shop_id)
    if profile:
        return _generated_shop_public(profile)
    raise ValueError(f"Unknown shop_id: {shop_id}")


def _validate_shop(base_dir: str, shop_id: str | None) -> str:
    shop_id = shop_id or SHOPS[0]["id"]
    if shop_id in SHOP_BY_ID:
        return shop_id
    if _load_generated_shop_profile(base_dir, shop_id):
        return shop_id
    raise ValueError(f"Unknown shop_id: {shop_id}")


def _safe_divide(a: Any, b: Any) -> float:
    left = float(a or 0)
    right = float(b or 0)
    return left / right if right else 0.0


def _category_display_name(cat: str) -> str:
    return {
        "A": "简约清透",
        "B": "甜美可爱",
        "C": "闪耀华丽",
        "D": "冷感暗黑",
        "E": "趋势实验",
    }.get(str(cat or ""), str(cat or "未知风格"))


def _trend_growth_from_signal(signal: Any) -> float:
    return {
        "breakout": 0.26,
        "rising": 0.14,
        "stable": 0.04,
        "cooling": -0.05,
        "falling": -0.12,
    }.get(str(signal or "stable"), 0.02)


def format_trend_signal(signal: Any) -> str:
    return {
        "breakout": "爆发中",
        "rising": "上升中",
        "stable": "稳定",
        "cooling": "降温中",
        "falling": "下滑中",
    }.get(str(signal or "stable"), "稳定")
