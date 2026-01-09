import json
from typing import List, Dict, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from fastapi import Header, HTTPException, Request

from app.core.config import config


def _allowed_ips() -> List[str]:
    raw = config.get("ALLOWED_IPS", "*")
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return parts or ["*"]


class IPAllowlistMiddleware:
    def __init__(self, app):
        self.app = app
        self.allowed = _allowed_ips()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 提取客户端 IP
        host = scope.get("client", ["", 0])[0]
        # 检查 X-Forwarded-For 头部
        headers = dict(scope.get("headers", []))
        xff = headers.get(b"x-forwarded-for", b"").decode()
        ip = xff.split(",")[0].strip() if xff else host

        if "*" not in self.allowed and ip not in self.allowed:
            response = JSONResponse({"detail": "IP not allowed"}, status_code=403)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def _get_token_map() -> Dict[str, str]:
    """
    解析多 Token 映射表。支持:
    1. JSON 字符串: {"token1": "role1", "token2": "role2"}
    2. 单一 Token (回退兼容): API_TOKEN 和 API_ROLE
    """
    # 优先尝试从 API_TOKENS 获取 JSON 配置
    tokens_json = config.get("API_TOKENS")
    if tokens_json:
        try:
            # 如果是 JSON 格式，直接解析
            if tokens_json.startswith("{"):
                return json.loads(tokens_json)
            # 如果是逗号分隔的列表，则全部分配为 API_ROLE 或默认 public
            default_role = config.get("API_ROLE", "public")
            return {t.strip(): default_role for t in tokens_json.split(",") if t.strip()}
        except Exception:
            pass

    # 回退到单 Token 模式
    single_token = config.get("API_TOKEN")
    if single_token:
        return {single_token: config.get("API_ROLE", "public")}
    
    return {}


def verify_token(header_val: str | None) -> bool:
    if not header_val:
        return False
    token_map = _get_token_map()
    # 如果没有配置任何 Token，则默认为开放（保持原有逻辑兼容性）
    if not token_map:
        return True
    return header_val in token_map


def resolve_role(token: str | None) -> str:
    if not token:
        return "public"
    token_map = _get_token_map()
    return token_map.get(token, "public")

def require_auth(x_api_token: Optional[str] = Header(None, alias="X-API-Token")):
    """
    FastAPI 依赖注入函数：验证 X-API-Token
    """
    if not verify_token(x_api_token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return x_api_token

def token_dependency(request: Request, x_api_token: Optional[str] = Header(None, alias="X-API-Token")):
    if not verify_token(x_api_token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    ip = request.headers.get("X-Forwarded-For") or request.client.host
    role = resolve_role(x_api_token)
    return {"ip": ip, "token": x_api_token, "role": role}
