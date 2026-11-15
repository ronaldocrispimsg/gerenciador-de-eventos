"""Geracao, validacao JWT e controle de acesso RBAC para os servicos EventHub."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Callable

import jwt
from flask import g, jsonify, request

VALID_ROLES = ("admin", "organizador", "participante")


def get_jwt_secret() -> str:
    """Retorna a chave secreta JWT definida no ambiente (com fallback apenas para dev)."""
    return os.getenv("JWT_SECRET", "eventhub-dev-secret-alterar-em-producao")


def generate_token(user: dict[str, Any], expires_hours: int | None = None) -> str:
    """Gera um token JWT HS256 contendo identidade e papel (role) do usuario."""
    hours = expires_hours if expires_hours is not None else int(os.getenv("JWT_EXPIRES_HOURS", "8"))
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["id"]),
        "user_id": int(user["id"]),
        "nome": user["nome"],
        "email": user["email"],
        "role": user["role"],
        "iat": now,
        "exp": now + timedelta(hours=hours),
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm="HS256")


def decode_token(token: str) -> dict[str, Any]:
    """Decodifica e valida assinatura e expiracao de um token JWT HS256."""
    return jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])


def extract_bearer_token() -> str | None:
    """Extrai o token do cabecalho Authorization: Bearer <token>."""
    auth_header = request.headers.get("Authorization", "").strip()
    if not auth_header:
        return None
    parts = auth_header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def require_roles(*allowed_roles: str) -> Callable:
    """Decorator Flask para autenticacao JWT e autorizacao RBAC por perfil."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            token = extract_bearer_token()
            if not token:
                return jsonify({"erro": "Token de autenticacao ausente ou malformado"}), 401

            try:
                payload = decode_token(token)
            except jwt.ExpiredSignatureError:
                return jsonify({"erro": "Token expirado"}), 401
            except jwt.InvalidTokenError:
                return jsonify({"erro": "Token invalido"}), 401

            role = payload.get("role")
            if allowed_roles and role not in allowed_roles:
                return (
                    jsonify(
                        {
                            "erro": "Acesso negado para este perfil",
                            "perfil_atual": role,
                            "perfis_permitidos": list(allowed_roles),
                        }
                    ),
                    403,
                )

            g.current_user = payload
            g.raw_token = token
            return func(*args, **kwargs)

        return wrapper

    return decorator
