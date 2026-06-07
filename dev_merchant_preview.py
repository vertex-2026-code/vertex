import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"


SKILL_REGISTRY = {
    "skill_ids": [
        "merchant_style_profile",
        "periodic_ops_report",
        "same_style_competitor_analysis",
        "hot_style_launch",
        "cold_style_retire",
        "automation_queue",
    ],
    "skills": {
        "merchant_style_profile": {"name": "Merchant style profile"},
        "periodic_ops_report": {"name": "Periodic operations report"},
        "same_style_competitor_analysis": {"name": "Same-style competitor analysis"},
        "hot_style_launch": {"name": "Hot style launch"},
        "cold_style_retire": {"name": "Cold style retire"},
        "automation_queue": {"name": "Automation queue"},
    },
}


def mock_fallback(skill_id: str) -> dict:
    if skill_id == "cold_style_retire":
        return {
            "skill": skill_id,
            "cold_candidates": [
                {
                    "style_id": "nail_12",
                    "risk_score": 78,
                    "suggested_action": "deprioritize",
                    "reason": "low tryons, weak booking, trend down",
                },
                {
                    "style_id": "nail_08",
                    "risk_score": 64,
                    "suggested_action": "revise",
                    "reason": "low like rate, revise color palette",
                },
            ],
        }
    if skill_id == "automation_queue":
        return {
            "skill": skill_id,
            "items": [
                {
                    "type": "launch_hot_style",
                    "target": "nail_05",
                    "priority": "high",
                    "status": "ready",
                    "reason": "sweet style converts well",
                },
                {
                    "type": "retire_or_revise_cold_style",
                    "target": "nail_12",
                    "priority": "medium",
                    "status": "pending_review",
                    "reason": "watch low conversion style",
                },
            ],
        }
    return {
        "skill": skill_id,
        "hot_candidates": [
            {
                "style_id": "nail_05",
                "score": 86,
                "reason": "high tryons, high likes, good shop fit",
                "actions": ["promote_shop", "generate_variant"],
            },
            {
                "style_id": "nail_16",
                "score": 78,
                "reason": "same-style supporting candidate",
                "actions": ["promote_shop"],
            },
        ],
    }


class MerchantPreviewHandler(BaseHTTPRequestHandler):
    server_version = "MerchantPreview/1.0"

    def do_GET(self):
        path = urlparse(self.path).path
        if path in {"/", "/merchant"}:
            return self._serve_html("merchant.html")
        if path == "/api/merchant/skills/registry":
            return self._send_json(200, SKILL_REGISTRY)
        if path == "/api/merchant/skills":
            return self._send_json(
                200,
                {
                    "mode": "preview_local_fallback",
                    "shop": {"id": "shop_002", "name": "Fleur Rose - Wudaokou"},
                    "period_days": 14,
                    "skills": {
                        "hot_style_launch": mock_fallback("hot_style_launch"),
                        "cold_style_retire": mock_fallback("cold_style_retire"),
                        "automation_queue": mock_fallback("automation_queue"),
                    },
                },
            )
        return self._send_json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_json_body()
        if path == "/api/merchant/agent/run-skill":
            skill_id = str(body.get("skill_id") or "hot_style_launch")
            return self._send_json(
                200,
                {
                    "mode": "preview_openclaw_skill",
                    "skill_id": skill_id,
                    "shop": {"id": body.get("shop_id"), "name": "Fleur Rose - Wudaokou"},
                    "period_days": body.get("period_days"),
                    "openclaw": {
                        "used": False,
                        "reply": {"ui_summary": f"Preview mode ran skill {skill_id}"},
                        "error": None,
                    },
                    "local_fallback": mock_fallback(skill_id),
                },
            )
        if path == "/api/merchant/agent/chat":
            return self._send_json(
                200,
                {
                    "mode": "preview_openclaw_agent_dispatch",
                    "shop": {"id": body.get("shop_id"), "name": "Fleur Rose - Wudaokou"},
                    "period_days": body.get("period_days"),
                    "openclaw": {
                        "used": False,
                        "reply": {
                            "intent": body.get("message", ""),
                            "selected_skills": ["hot_style_launch", "cold_style_retire"],
                            "ui_summary": "Preview mode selected hot launch and cold retire skills.",
                        },
                        "error": None,
                    },
                    "local_fallback": {
                        "skills": {"automation_queue": mock_fallback("automation_queue")}
                    },
                },
            )
        return self._send_json(404, {"error": "not found"})

    def log_message(self, format, *args):
        return

    def _serve_html(self, filename: str):
        path = STATIC_DIR / filename
        if not path.exists():
            return self._send_json(404, {"error": f"{filename} not found"})
        content = path.read_text(encoding="utf-8")
        data = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _send_json(self, status: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    host = "127.0.0.1"
    port = 5000
    print(f"Merchant preview started at http://{host}:{port}/merchant")
    ThreadingHTTPServer((host, port), MerchantPreviewHandler).serve_forever()
