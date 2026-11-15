"""Microsservico ms-inscricoes: gestao de inscricoes, cancelamentos e registro de presenca."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

from flask import Flask, g, jsonify, request

from common.auth import require_roles
from common.db import get_connection, resolve_db_path
from common.openapi import build_openapi_spec, register_openapi

OPENAPI_PATHS = {
    "/inscricoes": {
        "post": {
            "summary": "Registra inscricao em evento (validando duplicidade e capacidade)",
            "tags": ["Inscricoes"],
            "security": [{"BearerAuth": []}],
            "responses": {
                "201": {"description": "Inscricao criada"},
                "400": {"description": "Dados invalidos"},
                "409": {"description": "Inscricao duplicada ou vagas esgotadas"},
            },
        }
    },
    "/inscricoes/minhas": {
        "get": {
            "summary": "Lista inscricoes do participante autenticado",
            "tags": ["Inscricoes"],
            "security": [{"BearerAuth": []}],
            "responses": {"200": {"description": "Lista de inscricoes"}},
        }
    },
    "/eventos/{evento_id}/inscritos": {
        "get": {
            "summary": "Lista inscritos de um evento (organizador ou admin)",
            "tags": ["Inscricoes"],
            "security": [{"BearerAuth": []}],
            "responses": {"200": {"description": "Lista de inscritos"}, "403": {"description": "Acesso negado"}},
        }
    },
    "/inscricoes/{inscricao_id}/cancelar": {
        "patch": {
            "summary": "Cancela uma inscricao ativa",
            "tags": ["Inscricoes"],
            "security": [{"BearerAuth": []}],
            "responses": {"200": {"description": "Inscricao cancelada"}, "403": {"description": "Acesso negado"}, "404": {"description": "Nao encontrada"}},
        }
    },
    "/inscricoes/{inscricao_id}/presenca": {
        "patch": {
            "summary": "Registra presenca do participante (organizador ou admin)",
            "tags": ["Inscricoes"],
            "security": [{"BearerAuth": []}],
            "responses": {"200": {"description": "Presenca registrada"}, "403": {"description": "Acesso negado"}, "404": {"description": "Nao encontrada"}},
        }
    },
}


def _row_to_registration(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "evento_id": row["evento_id"],
        "participante_id": row["participante_id"],
        "participante_nome": row["participante_nome"],
        "participante_email": row["participante_email"],
        "status": row["status"],
        "presenca": bool(row["presenca"]),
        "criado_em": row["criado_em"],
    }


def _init_db(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS inscricoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evento_id INTEGER NOT NULL,
                participante_id INTEGER NOT NULL,
                participante_nome TEXT NOT NULL,
                participante_email TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ATIVA' CHECK(status IN ('ATIVA', 'CANCELADA')),
                presenca INTEGER NOT NULL DEFAULT 0,
                criado_em TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def create_app(db_path: str | None = None) -> Flask:
    """Cria e configura o aplicativo Flask do microsservico ms-inscricoes."""
    app = Flask(__name__)
    resolved_db = db_path or resolve_db_path("INSCRICOES_DB_PATH", "data/inscricoes.db")
    app.config["DB_PATH"] = resolved_db
    _init_db(resolved_db)

    spec = build_openapi_spec(
        title="EventHub MS - Inscricoes",
        version="1.0.0",
        description="Microsservico independente para gerenciamento de inscricoes e presenca (banco proprio).",
        paths=OPENAPI_PATHS,
    )
    register_openapi(app, "ms-inscricoes", spec)

    @app.post("/inscricoes")
    @require_roles("participante", "admin")
    def create_registration() -> tuple[Any, int]:
        data = request.get_json(silent=True) or {}
        try:
            evento_id = int(data.get("evento_id", 0))
        except (TypeError, ValueError):
            return jsonify({"erro": "Campo 'evento_id' invalido"}), 400

        if evento_id <= 0:
            return jsonify({"erro": "Campo 'evento_id' e obrigatorio e deve ser positivo"}), 400

        capacidade_maxima = data.get("capacidade_maxima")
        if capacidade_maxima is not None:
            try:
                capacidade_maxima = int(capacidade_maxima)
            except (TypeError, ValueError):
                return jsonify({"erro": "Campo 'capacidade_maxima' invalido"}), 400

        current = g.current_user
        participante_id = int(current["user_id"])
        now = datetime.now(timezone.utc).isoformat()

        conn = get_connection(app.config["DB_PATH"])
        try:
            existing = conn.execute(
                """
                SELECT id FROM inscricoes
                WHERE evento_id = ? AND participante_id = ? AND status = 'ATIVA'
                """,
                (evento_id, participante_id),
            ).fetchone()
            if existing:
                return jsonify({"erro": "Participante ja possui inscricao ativa neste evento"}), 409

            if capacidade_maxima is not None:
                ativas = conn.execute(
                    "SELECT COUNT(*) as qtd FROM inscricoes WHERE evento_id = ? AND status = 'ATIVA'",
                    (evento_id,),
                ).fetchone()["qtd"]
                if ativas >= capacidade_maxima:
                    return jsonify({"erro": "Capacidade maxima do evento atingida"}), 409

            cursor = conn.execute(
                """
                INSERT INTO inscricoes (
                    evento_id, participante_id, participante_nome, participante_email,
                    status, presenca, criado_em
                ) VALUES (?, ?, ?, ?, 'ATIVA', 0, ?)
                """,
                (evento_id, participante_id, current["nome"], current["email"], now),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM inscricoes WHERE id = ?", (cursor.lastrowid,)).fetchone()
        finally:
            conn.close()

        return jsonify({"inscricao": _row_to_registration(row)}), 201

    @app.get("/inscricoes/minhas")
    @require_roles("participante", "admin")
    def my_registrations() -> tuple[Any, int]:
        current = g.current_user
        conn = get_connection(app.config["DB_PATH"])
        try:
            rows = conn.execute(
                "SELECT * FROM inscricoes WHERE participante_id = ? ORDER BY id DESC",
                (int(current["user_id"]),),
            ).fetchall()
        finally:
            conn.close()

        items = [_row_to_registration(r) for r in rows]
        return jsonify({"inscricoes": items, "total": len(items)}), 200

    @app.get("/inscricoes/<int:inscricao_id>")
    @require_roles("admin", "organizador", "participante")
    def get_registration(inscricao_id: int) -> tuple[Any, int]:
        current = g.current_user
        conn = get_connection(app.config["DB_PATH"])
        try:
            row = conn.execute("SELECT * FROM inscricoes WHERE id = ?", (inscricao_id,)).fetchone()
        finally:
            conn.close()

        if not row:
            return jsonify({"erro": "Inscricao nao encontrada"}), 404
        if current["role"] == "participante" and int(row["participante_id"]) != int(
            current["user_id"]
        ):
            return jsonify({"erro": "Sem permissao para consultar inscricao de outro usuario"}), 403

        return jsonify({"inscricao": _row_to_registration(row)}), 200

    @app.get("/eventos/<int:evento_id>/inscritos")
    @require_roles("organizador", "admin")
    def list_event_registrations(evento_id: int) -> tuple[Any, int]:
        conn = get_connection(app.config["DB_PATH"])
        try:
            rows = conn.execute(
                "SELECT * FROM inscricoes WHERE evento_id = ? ORDER BY id ASC",
                (evento_id,),
            ).fetchall()
        finally:
            conn.close()

        items = [_row_to_registration(r) for r in rows]
        return jsonify({"evento_id": evento_id, "inscritos": items, "total": len(items)}), 200

    @app.patch("/inscricoes/<int:inscricao_id>/cancelar")
    @require_roles("participante", "admin")
    def cancel_registration(inscricao_id: int) -> tuple[Any, int]:
        current = g.current_user
        conn = get_connection(app.config["DB_PATH"])
        try:
            row = conn.execute("SELECT * FROM inscricoes WHERE id = ?", (inscricao_id,)).fetchone()
            if not row:
                return jsonify({"erro": "Inscricao nao encontrada"}), 404
            if current["role"] == "participante" and int(row["participante_id"]) != int(
                current["user_id"]
            ):
                return jsonify({"erro": "Participante so pode cancelar a propria inscricao"}), 403
            if row["status"] == "CANCELADA":
                return jsonify({"erro": "Inscricao ja esta cancelada"}), 400

            conn.execute("UPDATE inscricoes SET status = 'CANCELADA' WHERE id = ?", (inscricao_id,))
            conn.commit()
            updated = conn.execute(
                "SELECT * FROM inscricoes WHERE id = ?", (inscricao_id,)
            ).fetchone()
        finally:
            conn.close()

        return jsonify({"inscricao": _row_to_registration(updated)}), 200

    @app.patch("/inscricoes/<int:inscricao_id>/presenca")
    @require_roles("organizador", "admin")
    def mark_attendance(inscricao_id: int) -> tuple[Any, int]:
        data = request.get_json(silent=True) or {}
        presenca = bool(data.get("presenca", True))

        conn = get_connection(app.config["DB_PATH"])
        try:
            row = conn.execute("SELECT * FROM inscricoes WHERE id = ?", (inscricao_id,)).fetchone()
            if not row:
                return jsonify({"erro": "Inscricao nao encontrada"}), 404
            if row["status"] != "ATIVA":
                return jsonify({"erro": "Nao e possivel registrar presenca em inscricao cancelada"}), 400

            conn.execute(
                "UPDATE inscricoes SET presenca = ? WHERE id = ?",
                (1 if presenca else 0, inscricao_id),
            )
            conn.commit()
            updated = conn.execute(
                "SELECT * FROM inscricoes WHERE id = ?", (inscricao_id,)
            ).fetchone()
        finally:
            conn.close()

        return jsonify({"inscricao": _row_to_registration(updated)}), 200

    @app.get("/inscricoes/estatisticas")
    @require_roles("admin")
    def registration_stats() -> tuple[Any, int]:
        conn = get_connection(app.config["DB_PATH"])
        try:
            total = conn.execute("SELECT COUNT(*) as total FROM inscricoes").fetchone()["total"]
            por_status = conn.execute(
                "SELECT status, COUNT(*) as qtd FROM inscricoes GROUP BY status"
            ).fetchall()
            presentes = conn.execute(
                "SELECT COUNT(*) as qtd FROM inscricoes WHERE presenca = 1 AND status = 'ATIVA'"
            ).fetchone()["qtd"]
        finally:
            conn.close()

        return (
            jsonify(
                {
                    "total_inscricoes": total,
                    "por_status": {r["status"]: r["qtd"] for r in por_status},
                    "presencas_confirmadas": presentes,
                }
            ),
            200,
        )

    return app


if __name__ == "__main__":
    port = int(os.getenv("INSCRICOES_PORT", "5005"))
    create_app().run(host="0.0.0.0", port=port)
