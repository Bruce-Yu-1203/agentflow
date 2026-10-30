"""Bearer identity and administrator authorization."""

from dataclasses import dataclass
import hmac
import json

from fastapi import HTTPException

from agentflow.config import Settings


@dataclass(frozen=True)
class Identity:
    user_id: str
    role: str


def resolve_identity(settings: Settings, authorization: str | None, requested_user: str = "anonymous") -> Identity:
    if not settings.api_tokens and settings.environment != "production":
        return Identity(requested_user, "admin")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    presented = authorization[7:]
    try:
        tokens = json.loads(settings.api_tokens)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=503, detail="Authentication is misconfigured") from exc
    if not isinstance(tokens, dict):
        raise HTTPException(status_code=503, detail="Authentication is misconfigured")
    for token, record in tokens.items():
        if hmac.compare_digest(str(token), presented):
            if not isinstance(record, dict) or record.get("role") not in {"customer", "admin"} or not record.get("user_id"):
                raise HTTPException(status_code=503, detail="Authentication is misconfigured")
            return Identity(str(record["user_id"]), record["role"])
    raise HTTPException(status_code=401, detail="Invalid bearer token")


def require_admin(identity: Identity) -> None:
    if identity.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
