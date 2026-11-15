"""SOA Orquestrador: coordena fluxos compostos (inscricao, cancelamento, certificado e relatorios)."""

from __future__ import annotations

import os
from typing import Any

from flask import Flask, g, jsonify, request

from common.auth import require_roles
from common.http_client import get_correlation_id, service_request
from common.openapi import build_openapi_spec, register_openapi

OPENAPI_PATHS = {
    "/processos/inscricao": {
        "post": {
            "summary": "Orquestra inscricao: valida evento aprovado -> registra inscricao -> envia notificacao",
            "tags": ["Processos Orquestrados"],
            "security": [{"BearerAuth": []}],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "required": ["evento_id"],
                            "properties": {"evento_id": {"type": "integer"}},
                        }
                    }
                },
            },
            "responses": {
                "201": {"description": "Inscricao realizada e notificada"},
                "400": {"description": "Evento nao aprovado ou dados invalidos"},
                "404": {"description": "Evento nao encontrado"},
                "409": {"description": "Inscricao duplicada ou vagas esgotadas"},
            },
        }
    },
    "/processos/cancelamento/{inscricao_id}": {
        "post": {
            "summary": "Orquestra cancelamento de inscricao e envia notificacao",
            "tags": ["Processos Orquestrados"],
            "security": [{"BearerAuth": []}],
            "responses": {
                "200": {"description": "Cancelamento realizado e notificado"},
                "403": {"description": "Sem permissao"},
                "404": {"description": "Inscricao nao encontrada"},
            },
        }
    },
    "/processos/certificado": {
        "post": {
            "summary": "Orquestra emissao de certificado verificando presenca e notificando participante",
            "tags": ["Processos Orquestrados"],
            "security": [{"BearerAuth": []}],
            "responses": {
                "201": {"description": "Certificado emitido e notificado"},
                "400": {"description": "Presenca nao registrada ou inscricao cancelada"},
                "409": {"description": "Certificado ja emitido"},
            },
        }
    },
    "/relatorios/geral": {
        "get": {
            "summary": "Consolida relatorio gerencial da universidade (exclusivo admin)",
            "tags": ["Relatorios"],
            "security": [{"BearerAuth": []}],
            "responses": {
                "200": {"description": "Relatorio consolidado"},
                "403": {"description": "Acesso restrito ao perfil admin"},
            },
        }
    },
}


def _default_urls() -> dict[str, str]:
    return {
        "identidade": os.getenv("IDENTIDADE_URL", "http://127.0.0.1:5001"),
        "notificacao": os.getenv("NOTIFICACAO_URL", "http://127.0.0.1:5002"),
        "eventos": os.getenv("EVENTOS_URL", "http://127.0.0.1:5004"),
        "inscricoes": os.getenv("INSCRICOES_URL", "http://127.0.0.1:5005"),
        "certificados": os.getenv("CERTIFICADOS_URL", "http://127.0.0.1:5006"),
    }


def create_app(service_urls: dict[str, str] | None = None) -> Flask:
    """Cria e configura o aplicativo Flask do servico SOA Orquestrador."""
    app = Flask(__name__)
    urls = {**_default_urls(), **(service_urls or {})}
    app.config["SERVICE_URLS"] = urls

    spec = build_openapi_spec(
        title="EventHub SOA - Orquestrador de Processos",
        version="1.0.0",
        description="Servico SOA responsavel por orquestrar fluxos de negocio entre microsservicos e servicos corporativos.",
        paths=OPENAPI_PATHS,
    )
    register_openapi(app, "soa-orquestrador", spec)

    @app.post("/processos/inscricao")
    @require_roles("participante", "admin")
    def orchestrate_registration() -> tuple[Any, int]:
        data = request.get_json(silent=True) or {}
        try:
            evento_id = int(data.get("evento_id", 0))
        except (TypeError, ValueError):
            return jsonify({"erro": "Campo 'evento_id' invalido"}), 400
        if evento_id <= 0:
            return jsonify({"erro": "Campo 'evento_id' e obrigatorio"}), 400

        token = g.raw_token
        corr_id = get_correlation_id()
        current = g.current_user
        svc = app.config["SERVICE_URLS"]

        # 1. Consultar evento no ms-eventos
        evt_resp, evt_status = service_request(
            "GET", f"{svc['eventos']}/eventos/{evento_id}", token=token, correlation_id=corr_id
        )
        if evt_status != 200:
            return jsonify(evt_resp), evt_status

        evento = evt_resp["evento"]
        if evento["status"] != "APROVADO":
            return (
                jsonify(
                    {
                        "erro": "Inscricao permitida apenas para eventos com status APROVADO",
                        "status_evento": evento["status"],
                    }
                ),
                400,
            )

        # 2. Registrar inscricao no ms-inscricoes validando vagas e duplicidade
        ins_resp, ins_status = service_request(
            "POST",
            f"{svc['inscricoes']}/inscricoes",
            token=token,
            correlation_id=corr_id,
            json_body={"evento_id": evento_id, "capacidade_maxima": evento["capacidade"]},
        )
        if ins_status != 201:
            return jsonify(ins_resp), ins_status

        inscricao = ins_resp["inscricao"]

        # 3. Enviar notificacao corporativa via soa-notificacao
        notif_resp, notif_status = service_request(
            "POST",
            f"{svc['notificacao']}/notificacoes/enviar",
            token=token,
            correlation_id=corr_id,
            json_body={
                "destinatario_email": current["email"],
                "destinatario_nome": current["nome"],
                "assunto": f"Confirmacao de inscricao: {evento['titulo']}",
                "mensagem": (
                    f"Ola {current['nome']}, sua inscricao #{inscricao['id']} no evento "
                    f"'{evento['titulo']}' ({evento['data_evento']} - {evento['local']}) foi confirmada."
                ),
                "canal": "EMAIL",
                "sistema_origem": "EventHub",
                "referencia_externa": f"inscricao:{inscricao['id']}",
            },
        )
        notificacao = notif_resp.get("notificacao") if notif_status == 201 else notif_resp

        return (
            jsonify(
                {
                    "mensagem": "Inscricao realizada e confirmada com sucesso",
                    "correlation_id": corr_id,
                    "evento": evento,
                    "inscricao": inscricao,
                    "notificacao": notificacao,
                }
            ),
            201,
        )

    @app.post("/processos/cancelamento/<int:inscricao_id>")
    @require_roles("participante", "admin")
    def orchestrate_cancellation(inscricao_id: int) -> tuple[Any, int]:
        token = g.raw_token
        corr_id = get_correlation_id()
        current = g.current_user
        svc = app.config["SERVICE_URLS"]

        ins_resp, ins_status = service_request(
            "PATCH",
            f"{svc['inscricoes']}/inscricoes/{inscricao_id}/cancelar",
            token=token,
            correlation_id=corr_id,
        )
        if ins_status != 200:
            return jsonify(ins_resp), ins_status

        inscricao = ins_resp["inscricao"]
        notif_resp, notif_status = service_request(
            "POST",
            f"{svc['notificacao']}/notificacoes/enviar",
            token=token,
            correlation_id=corr_id,
            json_body={
                "destinatario_email": inscricao["participante_email"],
                "destinatario_nome": inscricao["participante_nome"],
                "assunto": f"Cancelamento de inscricao #{inscricao['id']}",
                "mensagem": (
                    f"Sua inscricao #{inscricao['id']} no evento #{inscricao['evento_id']} "
                    f"foi cancelada conforme solicitado por {current['nome']}."
                ),
                "canal": "EMAIL",
                "sistema_origem": "EventHub",
                "referencia_externa": f"cancelamento:{inscricao['id']}",
            },
        )
        notificacao = notif_resp.get("notificacao") if notif_status == 201 else notif_resp

        return (
            jsonify(
                {
                    "mensagem": "Inscricao cancelada e notificada com sucesso",
                    "correlation_id": corr_id,
                    "inscricao": inscricao,
                    "notificacao": notificacao,
                }
            ),
            200,
        )

    @app.post("/processos/certificado")
    @require_roles("participante", "admin")
    def orchestrate_certificate() -> tuple[Any, int]:
        data = request.get_json(silent=True) or {}
        try:
            inscricao_id = int(data.get("inscricao_id", 0))
        except (TypeError, ValueError):
            return jsonify({"erro": "Campo 'inscricao_id' invalido"}), 400
        if inscricao_id <= 0:
            return jsonify({"erro": "Campo 'inscricao_id' e obrigatorio"}), 400

        token = g.raw_token
        corr_id = get_correlation_id()
        svc = app.config["SERVICE_URLS"]

        ins_resp, ins_status = service_request(
            "GET",
            f"{svc['inscricoes']}/inscricoes/{inscricao_id}",
            token=token,
            correlation_id=corr_id,
        )
        if ins_status != 200:
            return jsonify(ins_resp), ins_status

        inscricao = ins_resp["inscricao"]
        if inscricao["status"] != "ATIVA" or not inscricao["presenca"]:
            return (
                jsonify(
                    {
                        "erro": "Certificado disponivel apenas para inscricoes ativas com presenca confirmada"
                    }
                ),
                400,
            )

        evt_resp, evt_status = service_request(
            "GET",
            f"{svc['eventos']}/eventos/{inscricao['evento_id']}",
            token=token,
            correlation_id=corr_id,
        )
        if evt_status != 200:
            return jsonify(evt_resp), evt_status
        evento = evt_resp["evento"]

        cert_resp, cert_status = service_request(
            "POST",
            f"{svc['certificados']}/certificados",
            token=token,
            correlation_id=corr_id,
            json_body={
                "inscricao_id": inscricao["id"],
                "evento_id": evento["id"],
                "evento_titulo": evento["titulo"],
                "tipo_evento": evento["tipo"],
                "carga_horaria": evento["carga_horaria"],
                "participante_id": inscricao["participante_id"],
                "participante_nome": inscricao["participante_nome"],
                "participante_email": inscricao["participante_email"],
            },
        )
        if cert_status != 201:
            return jsonify(cert_resp), cert_status

        certificado = cert_resp["certificado"]
        notif_resp, notif_status = service_request(
            "POST",
            f"{svc['notificacao']}/notificacoes/enviar",
            token=token,
            correlation_id=corr_id,
            json_body={
                "destinatario_email": inscricao["participante_email"],
                "destinatario_nome": inscricao["participante_nome"],
                "assunto": f"Certificado emitido: {evento['titulo']}",
                "mensagem": (
                    f"Seu certificado do evento '{evento['titulo']}' ({evento['carga_horaria']}h) "
                    f"foi emitido com codigo de verificacao {certificado['codigo_verificacao']}."
                ),
                "canal": "EMAIL",
                "sistema_origem": "EventHub",
                "referencia_externa": f"certificado:{certificado['codigo_verificacao']}",
            },
        )
        notificacao = notif_resp.get("notificacao") if notif_status == 201 else notif_resp

        return (
            jsonify(
                {
                    "mensagem": "Certificado emitido com sucesso",
                    "correlation_id": corr_id,
                    "certificado": certificado,
                    "notificacao": notificacao,
                }
            ),
            201,
        )

    @app.get("/relatorios/geral")
    @require_roles("admin")
    def general_report() -> tuple[Any, int]:
        token = g.raw_token
        corr_id = get_correlation_id()
        svc = app.config["SERVICE_URLS"]

        usuarios, _ = service_request(
            "GET", f"{svc['identidade']}/usuarios/estatisticas", token=token, correlation_id=corr_id
        )
        eventos, _ = service_request(
            "GET", f"{svc['eventos']}/eventos/estatisticas", token=token, correlation_id=corr_id
        )
        inscricoes, _ = service_request(
            "GET", f"{svc['inscricoes']}/inscricoes/estatisticas", token=token, correlation_id=corr_id
        )
        certificados, _ = service_request(
            "GET",
            f"{svc['certificados']}/certificados/estatisticas",
            token=token,
            correlation_id=corr_id,
        )
        notificacoes, _ = service_request(
            "GET",
            f"{svc['notificacao']}/notificacoes/estatisticas",
            token=token,
            correlation_id=corr_id,
        )

        return (
            jsonify(
                {
                    "relatorio": {
                        "usuarios": usuarios,
                        "eventos": eventos,
                        "inscricoes": inscricoes,
                        "certificados": certificados,
                        "notificacoes": notificacoes,
                    },
                    "correlation_id": corr_id,
                }
            ),
            200,
        )

    return app


if __name__ == "__main__":
    port = int(os.getenv("ORQUESTRADOR_PORT", "5003"))
    create_app().run(host="0.0.0.0", port=port)
