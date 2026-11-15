"""Cliente HTTP utilitario com propagacao de JWT e X-Correlation-ID."""

from __future__ import annotations

import uuid
from typing import Any

import requests
from flask import request


def get_correlation_id() -> str:
    """Obtem o X-Correlation-ID da requisicao atual ou gera um novo identificador."""
    corr = request.headers.get("X-Correlation-ID", "").strip()
    return corr or str(uuid.uuid4())


def service_request(
    method: str,
    url: str,
    token: str | None = None,
    correlation_id: str | None = None,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = 5.0,
) -> tuple[dict[str, Any] | list[Any], int]:
    """Executa chamada REST/JSON para outro servico propagando credenciais e rastreamento."""
    headers: dict[str, str] = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id

    try:
        resp = requests.request(
            method=method.upper(),
            url=url,
            headers=headers,
            json=json_body,
            params=params,
            timeout=timeout,
        )
    except requests.exceptions.RequestException as exc:
        return {"erro": "Servico interno indisponivel", "detalhes": str(exc)}, 503

    try:
        data = resp.json()
    except ValueError:
        data = {"mensagem": resp.text}

    return data, resp.status_code
