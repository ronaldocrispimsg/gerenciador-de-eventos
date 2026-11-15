"""Microsservico ms-certificados: emissao e validacao publica de certificados."""

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

OPENAPI_PATHS = {
    "/certificados": {
        "post": {
            "summary": "Emite certificado para uma inscricao com presenca confirmada",
            "tags": ["Certificados"],
            "security": [{"BearerAuth": []}],
            "responses": {
                "201": {"description": "Certificado emitido"},
                "400": {"description": "Dados obrigatorios ausentes"},
                "409": {"description": "Certificado ja emitido para esta inscricao"},
            },
        },
        "get": {
            "summary": "Lista todos os certificados emitidos (somente admin)",
            "tags": ["Certificados"],
            "security": [{"BearerAuth": []}],
            "responses": {"200": {"description": "Lista de certificados"}, "403": {"description": "Restrito a admin"}},
        },
    },
    "/certificados/meus": {
        "get": {
            "summary": "Lista certificados do participante autenticado",
            "tags": ["Certificados"],
            "security": [{"BearerAuth": []}],
            "responses": {"200": {"description": "Lista de certificados"}},
        }
    },
    "/certificados/validar/{codigo}": {
        "get": {
            "summary": "Valida autenticidade de um certificado pelo codigo verificador",
            "tags": ["Certificados"],
            "parameters": [
                {"name": "codigo", "in": "path", "required": True, "schema": {"type": "string"}}
            ],
            "responses": {"200": {"description": "Certificado valido"}, "404": {"description": "Codigo nao encontrado"}},
        }
    },
}


def _row_to_cert(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "codigo_verificacao": row["codigo_verificacao"],
        "inscricao_id": row["inscricao_id"],
        "evento_id": row["evento_id"],
        "evento_titulo": row["evento_titulo"],
        "tipo_evento": row["tipo_evento"],
        "carga_horaria": row["carga_horaria"],
        "participante_id": row["participante_id"],
        "participante_nome": row["participante_nome"],
        "participante_email": row["participante_email"],
        "emitido_em": row["emitido_em"],
    }


def _init_db(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS certificados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_verificacao TEXT UNIQUE NOT NULL,
                inscricao_id INTEGER UNIQUE NOT NULL,
                evento_id INTEGER NOT NULL,
                evento_titulo TEXT NOT NULL,
                tipo_evento TEXT NOT NULL,
                carga_horaria INTEGER NOT NULL,
                participante_id INTEGER NOT NULL,
                participante_nome TEXT NOT NULL,
                participante_email TEXT NOT NULL,
                emitido_em TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def create_app(db_path: str | None = None) -> Flask:
    """Cria e configura o aplicativo Flask do microsservico ms-certificados."""
    app = Flask(__name__)
    resolved_db = db_path or resolve_db_path("CERTIFICADOS_DB_PATH", "data/certificados.db")
    app.config["DB_PATH"] = resolved_db
    _init_db(resolved_db)

    spec = build_openapi_spec(
        title="EventHub MS - Certificados",
        version="1.0.0",
        description="Microsservico independente para emissao e validacao de certificados (banco proprio).",
        paths=OPENAPI_PATHS,
    )
    register_openapi(app, "ms-certificados", spec)

    @app.post("/certificados")
    @require_roles("participante", "admin")
    def issue_certificate() -> tuple[Any, int]:
        data = request.get_json(silent=True) or {}
        try:
            inscricao_id = int(data.get("inscricao_id", 0))
            evento_id = int(data.get("evento_id", 0))
            carga_horaria = int(data.get("carga_horaria", 0))
        except (TypeError, ValueError):
            return jsonify({"erro": "Campos numericos invalidos"}), 400

        evento_titulo = str(data.get("evento_titulo", "")).strip()
        tipo_evento = str(data.get("tipo_evento", "")).strip()

        if inscricao_id <= 0 or evento_id <= 0 or carga_horaria <= 0 or not evento_titulo or not tipo_evento:
            return jsonify({"erro": "Campos obrigatorios do certificado ausentes ou invalidos"}), 400

        current = g.current_user
        participante_id = int(data.get("participante_id", current["user_id"]))
        participante_nome = str(data.get("participante_nome", current["nome"])).strip()
        participante_email = str(data.get("participante_email", current["email"])).strip().lower()

        codigo = f"EVTHUB-{datetime.now(timezone.utc).year}-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc).isoformat()

        conn = get_connection(app.config["DB_PATH"])
        try:
            existing = conn.execute(
                "SELECT * FROM certificados WHERE inscricao_id = ?", (inscricao_id,)
            ).fetchone()
            if existing:
                return (
                    jsonify(
                        {
                            "erro": "Certificado ja emitido para esta inscricao",
                            "certificado": _row_to_cert(existing),
                        }
                    ),
                    409,
                )

            cursor = conn.execute(
                """
                INSERT INTO certificados (
                    codigo_verificacao, inscricao_id, evento_id, evento_titulo, tipo_evento,
                    carga_horaria, participante_id, participante_nome, participante_email, emitido_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    codigo,
                    inscricao_id,
                    evento_id,
                    evento_titulo,
                    tipo_evento,
                    carga_horaria,
                    participante_id,
                    participante_nome,
                    participante_email,
                    now,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM certificados WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        finally:
            conn.close()

        return jsonify({"certificado": _row_to_cert(row)}), 201

    @app.get("/certificados/meus")
    @require_roles("participante", "admin")
    def my_certificates() -> tuple[Any, int]:
        current = g.current_user
        conn = get_connection(app.config["DB_PATH"])
        try:
            rows = conn.execute(
                "SELECT * FROM certificados WHERE participante_id = ? ORDER BY id DESC",
                (int(current["user_id"]),),
            ).fetchall()
        finally:
            conn.close()

        items = [_row_to_cert(r) for r in rows]
        return jsonify({"certificados": items, "total": len(items)}), 200

    @app.get("/certificados/validar/<string:codigo>")
    def validate_certificate(codigo: str) -> tuple[Any, int]:
        conn = get_connection(app.config["DB_PATH"])
        try:
            row = conn.execute(
                "SELECT * FROM certificados WHERE codigo_verificacao = ?",
                (codigo.strip().upper(),),
            ).fetchone()
        finally:
            conn.close()

        if not row:
            return jsonify({"valido": False, "erro": "Certificado nao encontrado"}), 404
        return jsonify({"valido": True, "certificado": _row_to_cert(row)}), 200

    @app.get("/certificados")
    @require_roles("admin")
    def list_all_certificates() -> tuple[Any, int]:
        conn = get_connection(app.config["DB_PATH"])
        try:
            rows = conn.execute("SELECT * FROM certificados ORDER BY id DESC").fetchall()
        finally:
            conn.close()

        items = [_row_to_cert(r) for r in rows]
        return jsonify({"certificados": items, "total": len(items)}), 200

    @app.get("/certificados/estatisticas")
    @require_roles("admin")
    def certificate_stats() -> tuple[Any, int]:
        conn = get_connection(app.config["DB_PATH"])
        try:
            total = conn.execute("SELECT COUNT(*) as total FROM certificados").fetchone()["total"]
        finally:
            conn.close()

        return jsonify({"total_certificados": total}), 200

    return app


if __name__ == "__main__":
    port = int(os.getenv("CERTIFICADOS_PORT", "5006"))
    create_app().run(host="0.0.0.0", port=port)
