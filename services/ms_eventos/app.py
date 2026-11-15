"""Microsservico ms-eventos: catalogo, criacao, edicao e aprovacao de eventos."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

from flask import Flask, g, jsonify, request

from common.auth import require_roles
from common.db import get_connection, resolve_db_path
from common.openapi import build_openapi_spec, register_openapi

VALID_EVENT_TYPES = ("SEMANA_ACADEMICA", "PALESTRA", "MINICURSO")
VALID_EVENT_STATUS = ("PENDENTE", "APROVADO", "REJEITADO")

OPENAPI_PATHS = {
    "/eventos": {
        "get": {
            "summary": "Lista eventos academicos (participantes veem somente APROVADO)",
            "tags": ["Eventos"],
            "security": [{"BearerAuth": []}],
            "responses": {"200": {"description": "Lista de eventos"}, "401": {"description": "Nao autenticado"}},
        },
        "post": {
            "summary": "Cria novo evento com status PENDENTE (organizador ou admin)",
            "tags": ["Eventos"],
            "security": [{"BearerAuth": []}],
            "responses": {
                "201": {"description": "Evento criado"},
                "400": {"description": "Dados invalidos"},
                "403": {"description": "Perfil sem permissao"},
            },
        },
    },
    "/eventos/{evento_id}": {
        "get": {
            "summary": "Consulta detalhes de um evento",
            "tags": ["Eventos"],
            "security": [{"BearerAuth": []}],
            "responses": {"200": {"description": "Evento encontrado"}, "404": {"description": "Evento nao encontrado"}},
        },
        "put": {
            "summary": "Edita evento (organizador dono ou admin)",
            "tags": ["Eventos"],
            "security": [{"BearerAuth": []}],
            "responses": {
                "200": {"description": "Evento atualizado"},
                "403": {"description": "Nao e dono do evento"},
                "404": {"description": "Evento nao encontrado"},
            },
        },
    },
    "/eventos/{evento_id}/aprovar": {
        "patch": {
            "summary": "Aprova ou rejeita evento (exclusivo admin)",
            "tags": ["Eventos"],
            "security": [{"BearerAuth": []}],
            "responses": {
                "200": {"description": "Status do evento atualizado"},
                "403": {"description": "Restrito a admin"},
                "404": {"description": "Evento nao encontrado"},
            },
        }
    },
}


def _row_to_event(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "titulo": row["titulo"],
        "descricao": row["descricao"],
        "tipo": row["tipo"],
        "data_evento": row["data_evento"],
        "local": row["local"],
        "capacidade": row["capacidade"],
        "carga_horaria": row["carga_horaria"],
        "organizador_id": row["organizador_id"],
        "organizador_nome": row["organizador_nome"],
        "status": row["status"],
        "criado_em": row["criado_em"],
    }


def _init_db(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                descricao TEXT NOT NULL,
                tipo TEXT NOT NULL CHECK(tipo IN ('SEMANA_ACADEMICA', 'PALESTRA', 'MINICURSO')),
                data_evento TEXT NOT NULL,
                local TEXT NOT NULL,
                capacidade INTEGER NOT NULL CHECK(capacidade > 0),
                carga_horaria INTEGER NOT NULL CHECK(carga_horaria > 0),
                organizador_id INTEGER NOT NULL,
                organizador_nome TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDENTE'
                    CHECK(status IN ('PENDENTE', 'APROVADO', 'REJEITADO')),
                criado_em TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def create_app(db_path: str | None = None) -> Flask:
    """Cria e configura o aplicativo Flask do microsservico ms-eventos."""
    app = Flask(__name__)
    resolved_db = db_path or resolve_db_path("EVENTOS_DB_PATH", "data/eventos.db")
    app.config["DB_PATH"] = resolved_db
    _init_db(resolved_db)

    spec = build_openapi_spec(
        title="EventHub MS - Eventos",
        version="1.0.0",
        description="Microsservico independente para gerenciamento de eventos academicos (banco proprio).",
        paths=OPENAPI_PATHS,
    )
    register_openapi(app, "ms-eventos", spec)

    @app.get("/eventos")
    @require_roles("admin", "organizador", "participante")
    def list_events() -> tuple[Any, int]:
        current = g.current_user
        status_filter = request.args.get("status", "").strip().upper()
        conn = get_connection(app.config["DB_PATH"])
        try:
            if current["role"] == "participante":
                rows = conn.execute(
                    "SELECT * FROM eventos WHERE status = 'APROVADO' ORDER BY id DESC"
                ).fetchall()
            elif status_filter in VALID_EVENT_STATUS:
                rows = conn.execute(
                    "SELECT * FROM eventos WHERE status = ? ORDER BY id DESC",
                    (status_filter,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM eventos ORDER BY id DESC").fetchall()
        finally:
            conn.close()

        events = [_row_to_event(r) for r in rows]
        return jsonify({"eventos": events, "total": len(events)}), 200

    @app.get("/eventos/<int:evento_id>")
    @require_roles("admin", "organizador", "participante")
    def get_event(evento_id: int) -> tuple[Any, int]:
        conn = get_connection(app.config["DB_PATH"])
        try:
            row = conn.execute("SELECT * FROM eventos WHERE id = ?", (evento_id,)).fetchone()
        finally:
            conn.close()

        if not row:
            return jsonify({"erro": "Evento nao encontrado"}), 404
        return jsonify({"evento": _row_to_event(row)}), 200

    @app.post("/eventos")
    @require_roles("organizador", "admin")
    def create_event() -> tuple[Any, int]:
        data = request.get_json(silent=True) or {}
        titulo = str(data.get("titulo", "")).strip()
        descricao = str(data.get("descricao", "")).strip()
        tipo = str(data.get("tipo", "")).strip().upper()
        data_evento = str(data.get("data_evento", "")).strip()
        local = str(data.get("local", "")).strip()

        try:
            capacidade = int(data.get("capacidade", 0))
            carga_horaria = int(data.get("carga_horaria", 0))
        except (TypeError, ValueError):
            return jsonify({"erro": "Capacidade e carga_horaria devem ser numeros inteiros"}), 400

        if not titulo or not descricao or not data_evento or not local:
            return (
                jsonify(
                    {
                        "erro": "Campos 'titulo', 'descricao', 'tipo', 'data_evento' e 'local' sao obrigatorios"
                    }
                ),
                400,
            )
        if tipo not in VALID_EVENT_TYPES:
            return (
                jsonify({"erro": f"Tipo invalido. Valores aceitos: {', '.join(VALID_EVENT_TYPES)}"}),
                400,
            )
        if capacidade <= 0 or carga_horaria <= 0:
            return jsonify({"erro": "Capacidade e carga_horaria devem ser maiores que zero"}), 400

        current = g.current_user
        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection(app.config["DB_PATH"])
        try:
            cursor = conn.execute(
                """
                INSERT INTO eventos (
                    titulo, descricao, tipo, data_evento, local, capacidade, carga_horaria,
                    organizador_id, organizador_nome, status, criado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDENTE', ?)
                """,
                (
                    titulo,
                    descricao,
                    tipo,
                    data_evento,
                    local,
                    capacidade,
                    carga_horaria,
                    int(current["user_id"]),
                    current["nome"],
                    now,
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM eventos WHERE id = ?", (cursor.lastrowid,)).fetchone()
        finally:
            conn.close()

        return jsonify({"evento": _row_to_event(row)}), 201

    @app.put("/eventos/<int:evento_id>")
    @require_roles("organizador", "admin")
    def update_event(evento_id: int) -> tuple[Any, int]:
        current = g.current_user
        data = request.get_json(silent=True) or {}

        conn = get_connection(app.config["DB_PATH"])
        try:
            existing = conn.execute("SELECT * FROM eventos WHERE id = ?", (evento_id,)).fetchone()
            if not existing:
                return jsonify({"erro": "Evento nao encontrado"}), 404

            if current["role"] == "organizador" and int(existing["organizador_id"]) != int(
                current["user_id"]
            ):
                return jsonify({"erro": "Organizador so pode editar os proprios eventos"}), 403

            titulo = str(data.get("titulo", existing["titulo"])).strip()
            descricao = str(data.get("descricao", existing["descricao"])).strip()
            tipo = str(data.get("tipo", existing["tipo"])).strip().upper()
            data_evento = str(data.get("data_evento", existing["data_evento"])).strip()
            local = str(data.get("local", existing["local"])).strip()

            try:
                capacidade = int(data.get("capacidade", existing["capacidade"]))
                carga_horaria = int(data.get("carga_horaria", existing["carga_horaria"]))
            except (TypeError, ValueError):
                return jsonify({"erro": "Capacidade e carga_horaria devem ser inteiros"}), 400

            if tipo not in VALID_EVENT_TYPES or capacidade <= 0 or carga_horaria <= 0:
                return jsonify({"erro": "Dados do evento invalidos"}), 400

            conn.execute(
                """
                UPDATE eventos
                SET titulo = ?, descricao = ?, tipo = ?, data_evento = ?, local = ?,
                    capacidade = ?, carga_horaria = ?
                WHERE id = ?
                """,
                (titulo, descricao, tipo, data_evento, local, capacidade, carga_horaria, evento_id),
            )
            conn.commit()
            updated = conn.execute("SELECT * FROM eventos WHERE id = ?", (evento_id,)).fetchone()
        finally:
            conn.close()

        return jsonify({"evento": _row_to_event(updated)}), 200

    @app.patch("/eventos/<int:evento_id>/aprovar")
    @require_roles("admin")
    def approve_event(evento_id: int) -> tuple[Any, int]:
        data = request.get_json(silent=True) or {}
        new_status = str(data.get("status", "APROVADO")).strip().upper()
        if new_status not in ("APROVADO", "REJEITADO"):
            return jsonify({"erro": "Status deve ser APROVADO ou REJEITADO"}), 400

        conn = get_connection(app.config["DB_PATH"])
        try:
            existing = conn.execute("SELECT * FROM eventos WHERE id = ?", (evento_id,)).fetchone()
            if not existing:
                return jsonify({"erro": "Evento nao encontrado"}), 404

            conn.execute("UPDATE eventos SET status = ? WHERE id = ?", (new_status, evento_id))
            conn.commit()
            updated = conn.execute("SELECT * FROM eventos WHERE id = ?", (evento_id,)).fetchone()
        finally:
            conn.close()

        return jsonify({"evento": _row_to_event(updated)}), 200

    @app.get("/eventos/estatisticas")
    @require_roles("admin")
    def event_stats() -> tuple[Any, int]:
        conn = get_connection(app.config["DB_PATH"])
        try:
            total = conn.execute("SELECT COUNT(*) as total FROM eventos").fetchone()["total"]
            por_status = conn.execute(
                "SELECT status, COUNT(*) as qtd FROM eventos GROUP BY status"
            ).fetchall()
            por_tipo = conn.execute(
                "SELECT tipo, COUNT(*) as qtd FROM eventos GROUP BY tipo"
            ).fetchall()
        finally:
            conn.close()

        return (
            jsonify(
                {
                    "total_eventos": total,
                    "por_status": {r["status"]: r["qtd"] for r in por_status},
                    "por_tipo": {r["tipo"]: r["qtd"] for r in por_tipo},
                }
            ),
            200,
        )

    return app


if __name__ == "__main__":
    port = int(os.getenv("EVENTOS_PORT", "5004"))
    create_app().run(host="0.0.0.0", port=port)
