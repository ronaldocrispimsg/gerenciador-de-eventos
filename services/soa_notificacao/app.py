"""SOA Notificacao: servico corporativo reutilizavel de envio e auditoria de mensagens."""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from flask import Flask, g, jsonify, request

from common.auth import require_roles
from common.db import get_connection, resolve_db_path
from common.openapi import build_openapi_spec, register_openapi

VALID_CHANNELS = ("EMAIL", "SISTEMA", "SMS")

OPENAPI_PATHS = {
    "/notificacoes/enviar": {
        "post": {
            "summary": "Envia e registra uma notificacao corporativa",
            "tags": ["Notificacoes"],
            "security": [{"BearerAuth": []}],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "required": ["destinatario_email", "assunto", "mensagem"],
                            "properties": {
                                "destinatario_email": {"type": "string"},
                                "destinatario_nome": {"type": "string"},
                                "assunto": {"type": "string"},
                                "mensagem": {"type": "string"},
                                "canal": {"type": "string", "enum": ["EMAIL", "SISTEMA", "SMS"]},
                                "sistema_origem": {"type": "string"},
                                "referencia_externa": {"type": "string"},
                            },
                        }
                    }
                },
            },
            "responses": {
                "201": {"description": "Notificacao registrada e enviada"},
                "400": {"description": "Campos obrigatorios ausentes ou canal invalido"},
                "401": {"description": "Nao autenticado"},
            },
        }
    },
    "/notificacoes": {
        "get": {
            "summary": "Lista historico de notificacoes (admin ve todas; demais veem as proprias)",
            "tags": ["Notificacoes"],
            "security": [{"BearerAuth": []}],
            "responses": {
                "200": {"description": "Historico de notificacoes"},
                "401": {"description": "Nao autenticado"},
            },
        }
    },
    "/notificacoes/{notif_id}": {
        "get": {
            "summary": "Consulta detalhes de uma notificacao",
            "tags": ["Notificacoes"],
            "security": [{"BearerAuth": []}],
            "parameters": [
                {"name": "notif_id", "in": "path", "required": True, "schema": {"type": "integer"}}
            ],
            "responses": {
                "200": {"description": "Detalhes da notificacao"},
                "403": {"description": "Acesso negado"},
                "404": {"description": "Notificacao nao encontrada"},
            },
        }
    },
}


def _row_to_notif(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "protocolo": row["protocolo"],
        "destinatario_email": row["destinatario_email"],
        "destinatario_nome": row["destinatario_nome"],
        "assunto": row["assunto"],
        "mensagem": row["mensagem"],
        "canal": row["canal"],
        "sistema_origem": row["sistema_origem"],
        "referencia_externa": row["referencia_externa"],
        "status": row["status"],
        "enviado_em": row["enviado_em"],
    }


def _init_db(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notificacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                protocolo TEXT UNIQUE NOT NULL,
                destinatario_email TEXT NOT NULL,
                destinatario_nome TEXT NOT NULL,
                assunto TEXT NOT NULL,
                mensagem TEXT NOT NULL,
                canal TEXT NOT NULL DEFAULT 'EMAIL',
                sistema_origem TEXT NOT NULL DEFAULT 'EventHub',
                referencia_externa TEXT,
                status TEXT NOT NULL DEFAULT 'ENVIADO',
                enviado_em TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def create_app(db_path: str | None = None) -> Flask:
    """Cria e configura o aplicativo Flask do servico SOA Notificacao."""
    app = Flask(__name__)
    resolved_db = db_path or resolve_db_path("NOTIFICACAO_DB_PATH", "data/notificacoes.db")
    app.config["DB_PATH"] = resolved_db
    _init_db(resolved_db)

    spec = build_openapi_spec(
        title="EventHub SOA - Servico de Notificacao",
        version="1.0.0",
        description="Servico corporativo reutilizavel de envio de notificacoes (e-mail/log) para sistemas da universidade.",
        paths=OPENAPI_PATHS,
    )
    register_openapi(app, "soa-notificacao", spec)

    @app.post("/notificacoes/enviar")
    @require_roles("admin", "organizador", "participante")
    def send_notification() -> tuple[Any, int]:
        data = request.get_json(silent=True) or {}
        dest_email = str(data.get("destinatario_email", "")).strip().lower()
        dest_nome = str(data.get("destinatario_nome", "Usuario")).strip() or "Usuario"
        assunto = str(data.get("assunto", "")).strip()
        mensagem = str(data.get("mensagem", "")).strip()
        canal = str(data.get("canal", "EMAIL")).strip().upper()
        sistema_origem = str(data.get("sistema_origem", "EventHub")).strip() or "EventHub"
        referencia_externa = data.get("referencia_externa")

        if not dest_email or not assunto or not mensagem:
            return (
                jsonify(
                    {
                        "erro": "Campos 'destinatario_email', 'assunto' e 'mensagem' sao obrigatorios"
                    }
                ),
                400,
            )
        if canal not in VALID_CHANNELS:
            return (
                jsonify({"erro": f"Canal invalido. Valores aceitos: {', '.join(VALID_CHANNELS)}"}),
                400,
            )

        protocolo = f"NOTIF-{uuid.uuid4().hex[:10].upper()}"
        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection(app.config["DB_PATH"])
        try:
            cursor = conn.execute(
                """
                INSERT INTO notificacoes (
                    protocolo, destinatario_email, destinatario_nome, assunto, mensagem,
                    canal, sistema_origem, referencia_externa, status, enviado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ENVIADO', ?)
                """,
                (
                    protocolo,
                    dest_email,
                    dest_nome,
                    assunto,
                    mensagem,
                    canal,
                    sistema_origem,
                    str(referencia_externa) if referencia_externa is not None else None,
                    now,
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM notificacoes WHERE id = ?", (cursor.lastrowid,)).fetchone()
        finally:
            conn.close()

        app.logger.info(
            "[%s] Notificacao %s enviada via %s para %s (%s)",
            sistema_origem,
            protocolo,
            canal,
            dest_email,
            assunto,
        )
        return jsonify({"notificacao": _row_to_notif(row)}), 201

    @app.get("/notificacoes")
    @require_roles("admin", "organizador", "participante")
    def list_notifications() -> tuple[Any, int]:
        current = g.current_user
        sistema = request.args.get("sistema_origem", "").strip()
        conn = get_connection(app.config["DB_PATH"])
        try:
            if current["role"] == "admin":
                if sistema:
                    rows = conn.execute(
                        "SELECT * FROM notificacoes WHERE sistema_origem = ? ORDER BY id DESC",
                        (sistema,),
                    ).fetchall()
                else:
                    rows = conn.execute("SELECT * FROM notificacoes ORDER BY id DESC").fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM notificacoes WHERE destinatario_email = ? ORDER BY id DESC",
                    (current["email"].lower(),),
                ).fetchall()
        finally:
            conn.close()

        items = [_row_to_notif(r) for r in rows]
        return jsonify({"notificacoes": items, "total": len(items)}), 200

    @app.get("/notificacoes/<int:notif_id>")
    @require_roles("admin", "organizador", "participante")
    def get_notification(notif_id: int) -> tuple[Any, int]:
        current = g.current_user
        conn = get_connection(app.config["DB_PATH"])
        try:
            row = conn.execute("SELECT * FROM notificacoes WHERE id = ?", (notif_id,)).fetchone()
        finally:
            conn.close()

        if not row:
            return jsonify({"erro": "Notificacao nao encontrada"}), 404
        if current["role"] != "admin" and row["destinatario_email"] != current["email"].lower():
            return jsonify({"erro": "Sem permissao para visualizar esta notificacao"}), 403

        return jsonify({"notificacao": _row_to_notif(row)}), 200

    @app.get("/notificacoes/estatisticas")
    @require_roles("admin")
    def notif_stats() -> tuple[Any, int]:
        conn = get_connection(app.config["DB_PATH"])
        try:
            total = conn.execute("SELECT COUNT(*) as total FROM notificacoes").fetchone()["total"]
            por_canal_rows = conn.execute(
                "SELECT canal, COUNT(*) as qtd FROM notificacoes GROUP BY canal"
            ).fetchall()
        finally:
            conn.close()

        return (
            jsonify(
                {
                    "total_notificacoes": total,
                    "por_canal": {r["canal"]: r["qtd"] for r in por_canal_rows},
                }
            ),
            200,
        )

    return app


if __name__ == "__main__":
    port = int(os.getenv("NOTIFICACAO_PORT", "5002"))
    create_app().run(host="0.0.0.0", port=port)
