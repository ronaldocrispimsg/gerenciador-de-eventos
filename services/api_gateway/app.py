"""API Gateway: ponto unico de entrada, validacao preliminar de JWT e roteamento REST."""

from __future__ import annotations

import os
from typing import Any

import jwt
from flask import Flask, jsonify, request

from common.auth import decode_token, extract_bearer_token
from common.http_client import get_correlation_id, service_request
from common.openapi import build_openapi_spec, register_openapi

OPENAPI_PATHS = {
    "/auth/login": {"post": {"summary": "Login e obtencao de JWT (proxy soa-identidade)", "tags": ["Gateway"]}},
    "/auth/register": {"post": {"summary": "Auto-cadastro de participante (proxy soa-identidade)", "tags": ["Gateway"]}},
    "/usuarios": {"get": {"summary": "Lista usuarios (admin)", "tags": ["Gateway"]}, "post": {"summary": "Cria usuario (admin)", "tags": ["Gateway"]}},
    "/eventos": {"get": {"summary": "Lista eventos", "tags": ["Gateway"]}, "post": {"summary": "Cria evento (organizador/admin)", "tags": ["Gateway"]}},
    "/eventos/{evento_id}/aprovar": {"patch": {"summary": "Aprova/rejeita evento (admin)", "tags": ["Gateway"]}},
    "/inscricoes": {"post": {"summary": "Realiza inscricao via fluxo orquestrado (soa-orquestrador)", "tags": ["Gateway"]}},
    "/inscricoes/{inscricao_id}/cancelar": {"patch": {"summary": "Cancela inscricao via fluxo orquestrado", "tags": ["Gateway"]}},
    "/inscricoes/{inscricao_id}/presenca": {"patch": {"summary": "Registra presenca (organizador/admin)", "tags": ["Gateway"]}},
    "/certificados/emitir": {"post": {"summary": "Emite certificado via fluxo orquestrado", "tags": ["Gateway"]}},
    "/certificados/validar/{codigo}": {"get": {"summary": "Valida certificado publicamente", "tags": ["Gateway"]}},
    "/relatorios/geral": {"get": {"summary": "Relatorio consolidado da universidade (admin)", "tags": ["Gateway"]}},
}


def _default_urls() -> dict[str, str]:
    return {
        "identidade": os.getenv("IDENTIDADE_URL", "http://127.0.0.1:5001"),
        "notificacao": os.getenv("NOTIFICACAO_URL", "http://127.0.0.1:5002"),
        "orquestrador": os.getenv("ORQUESTRADOR_URL", "http://127.0.0.1:5003"),
        "eventos": os.getenv("EVENTOS_URL", "http://127.0.0.1:5004"),
        "inscricoes": os.getenv("INSCRICOES_URL", "http://127.0.0.1:5005"),
        "certificados": os.getenv("CERTIFICADOS_URL", "http://127.0.0.1:5006"),
    }


def create_app(service_urls: dict[str, str] | None = None) -> Flask:
    """Cria e configura o aplicativo Flask do API Gateway."""
    app = Flask(__name__)
    urls = {**_default_urls(), **(service_urls or {})}
    app.config["SERVICE_URLS"] = urls

    spec = build_openapi_spec(
        title="EventHub - API Gateway",
        version="1.0.0",
        description="Gateway central com validacao JWT e roteamento para camada SOA e Microsservicos.",
        paths=OPENAPI_PATHS,
    )
    register_openapi(app, "api-gateway", spec)

    def _forward(
        service_key: str,
        target_path: str,
        require_auth: bool = True,
        method_override: str | None = None,
    ) -> tuple[Any, int]:
        token = extract_bearer_token()
        if require_auth:
            if not token:
                return jsonify({"erro": "Token de autenticacao ausente ou malformado"}), 401
            try:
                decode_token(token)
            except jwt.ExpiredSignatureError:
                return jsonify({"erro": "Token expirado"}), 401
            except jwt.InvalidTokenError:
                return jsonify({"erro": "Token invalido"}), 401

        target_url = f"{app.config['SERVICE_URLS'][service_key]}{target_path}"
        method = method_override or request.method
        body = request.get_json(silent=True) if method in ("POST", "PUT", "PATCH") else None
        params = request.args.to_dict() if request.args else None
        corr_id = get_correlation_id()

        data, status_code = service_request(
            method=method,
            url=target_url,
            token=token,
            correlation_id=corr_id,
            json_body=body,
            params=params,
        )
        return jsonify(data), status_code

    # --- Rotas de Identidade (SOA) ---
    @app.post("/auth/login")
    def gw_login() -> tuple[Any, int]:
        return _forward("identidade", "/auth/login", require_auth=False)

    @app.post("/auth/register")
    def gw_register() -> tuple[Any, int]:
        return _forward("identidade", "/auth/register", require_auth=False)

    @app.get("/auth/validate")
    def gw_validate() -> tuple[Any, int]:
        return _forward("identidade", "/auth/validate")

    @app.route("/usuarios", methods=["GET", "POST"])
    def gw_users() -> tuple[Any, int]:
        return _forward("identidade", "/usuarios")

    @app.route("/usuarios/<path:subpath>", methods=["GET", "PATCH"])
    def gw_users_sub(subpath: str) -> tuple[Any, int]:
        return _forward("identidade", f"/usuarios/{subpath}")

    # --- Rotas de Notificacao (SOA) ---
    @app.route("/notificacoes", methods=["GET"])
    @app.route("/notificacoes/<path:subpath>", methods=["GET", "POST"])
    def gw_notifications(subpath: str | None = None) -> tuple[Any, int]:
        path = f"/notificacoes/{subpath}" if subpath else "/notificacoes"
        return _forward("notificacao", path)

    # --- Rotas de Eventos e Inscritos ---
    @app.get("/eventos/<int:evento_id>/inscritos")
    def gw_event_subscribers(evento_id: int) -> tuple[Any, int]:
        return _forward("inscricoes", f"/eventos/{evento_id}/inscritos")

    @app.route("/eventos", methods=["GET", "POST"])
    def gw_events() -> tuple[Any, int]:
        return _forward("eventos", "/eventos")

    @app.route("/eventos/<path:subpath>", methods=["GET", "PUT", "PATCH"])
    def gw_events_sub(subpath: str) -> tuple[Any, int]:
        return _forward("eventos", f"/eventos/{subpath}")

    # --- Rotas de Inscricoes (POST roteado para Orquestrador) ---
    @app.post("/inscricoes")
    def gw_create_registration() -> tuple[Any, int]:
        return _forward("orquestrador", "/processos/inscricao")

    @app.patch("/inscricoes/<int:inscricao_id>/cancelar")
    def gw_cancel_registration(inscricao_id: int) -> tuple[Any, int]:
        return _forward(
            "orquestrador",
            f"/processos/cancelamento/{inscricao_id}",
            method_override="POST",
        )

    @app.route("/inscricoes/<path:subpath>", methods=["GET", "PATCH"])
    def gw_registrations_sub(subpath: str) -> tuple[Any, int]:
        return _forward("inscricoes", f"/inscricoes/{subpath}")

    # --- Rotas de Certificados (Emissao via Orquestrador) ---
    @app.post("/certificados/emitir")
    def gw_issue_certificate() -> tuple[Any, int]:
        return _forward("orquestrador", "/processos/certificado")

    @app.get("/certificados/validar/<string:codigo>")
    def gw_validate_certificate(codigo: str) -> tuple[Any, int]:
        return _forward("certificados", f"/certificados/validar/{codigo}", require_auth=False)

    @app.route("/certificados", methods=["GET"])
    @app.route("/certificados/<path:subpath>", methods=["GET"])
    def gw_certificates(subpath: str | None = None) -> tuple[Any, int]:
        path = f"/certificados/{subpath}" if subpath else "/certificados"
        return _forward("certificados", path)

    # --- Rotas Diretas do Orquestrador ---
    @app.route("/processos/<path:subpath>", methods=["POST"])
    def gw_processes(subpath: str) -> tuple[Any, int]:
        return _forward("orquestrador", f"/processos/{subpath}")

    @app.get("/relatorios/geral")
    def gw_general_report() -> tuple[Any, int]:
        return _forward("orquestrador", "/relatorios/geral")

    return app


if __name__ == "__main__":
    port = int(os.getenv("GATEWAY_PORT", "5000"))
    create_app().run(host="0.0.0.0", port=port)
