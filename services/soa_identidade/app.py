"""SOA Identidade: autenticacao JWT, gestao de usuarios e controle RBAC."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

from flask import Flask, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from common.auth import VALID_ROLES, generate_token, require_roles
from common.db import get_connection, resolve_db_path
from common.openapi import build_openapi_spec, register_openapi

OPENAPI_PATHS = {
    "/auth/login": {
        "post": {
            "summary": "Autentica usuario e emite token JWT",
            "tags": ["Autenticacao"],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "required": ["email", "senha"],
                            "properties": {
                                "email": {"type": "string", "format": "email"},
                                "senha": {"type": "string"},
                            },
                        }
                    }
                },
            },
            "responses": {
                "200": {"description": "Login realizado com sucesso"},
                "400": {"description": "Campos obrigatorios ausentes"},
                "401": {"description": "Credenciais invalidas ou conta inativa"},
            },
        }
    },
    "/auth/register": {
        "post": {
            "summary": "Auto-cadastro publico de participante",
            "tags": ["Autenticacao"],
            "responses": {
                "201": {"description": "Participante criado"},
                "400": {"description": "Dados invalidos"},
                "409": {"description": "E-mail ja cadastrado"},
            },
        }
    },
    "/auth/validate": {
        "get": {
            "summary": "Valida token JWT para outros sistemas da universidade",
            "tags": ["Autenticacao"],
            "security": [{"BearerAuth": []}],
            "responses": {
                "200": {"description": "Token valido e claims retornadas"},
                "401": {"description": "Token ausente, invalido ou expirado"},
            },
        }
    },
    "/usuarios": {
        "get": {
            "summary": "Lista todos os usuarios (somente admin)",
            "tags": ["Usuarios"],
            "security": [{"BearerAuth": []}],
            "responses": {
                "200": {"description": "Lista de usuarios"},
                "401": {"description": "Nao autenticado"},
                "403": {"description": "Acesso restrito ao perfil admin"},
            },
        },
        "post": {
            "summary": "Cria usuario com papel especifico (somente admin)",
            "tags": ["Usuarios"],
            "security": [{"BearerAuth": []}],
            "responses": {
                "201": {"description": "Usuario criado"},
                "400": {"description": "Dados ou perfil invalidos"},
                "403": {"description": "Acesso restrito ao perfil admin"},
                "409": {"description": "E-mail ja cadastrado"},
            },
        },
    },
    "/usuarios/{user_id}": {
        "get": {
            "summary": "Consulta um usuario especifico (admin ou proprio usuario)",
            "tags": ["Usuarios"],
            "security": [{"BearerAuth": []}],
            "parameters": [
                {"name": "user_id", "in": "path", "required": True, "schema": {"type": "integer"}}
            ],
            "responses": {
                "200": {"description": "Dados do usuario"},
                "403": {"description": "Sem permissao para consultar outro usuario"},
                "404": {"description": "Usuario nao encontrado"},
            },
        }
    },
    "/usuarios/{user_id}/perfil": {
        "patch": {
            "summary": "Altera perfil (role) ou status ativo de um usuario (somente admin)",
            "tags": ["Usuarios"],
            "security": [{"BearerAuth": []}],
            "parameters": [
                {"name": "user_id", "in": "path", "required": True, "schema": {"type": "integer"}}
            ],
            "responses": {
                "200": {"description": "Perfil atualizado"},
                "400": {"description": "Dados invalidos"},
                "403": {"description": "Acesso restrito ao perfil admin"},
                "404": {"description": "Usuario nao encontrado"},
            },
        }
    },
}


def _row_to_user(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "nome": row["nome"],
        "email": row["email"],
        "role": row["role"],
        "ativo": bool(row["ativo"]),
        "criado_em": row["criado_em"],
    }


def _init_db(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                senha_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'organizador', 'participante')),
                ativo INTEGER NOT NULL DEFAULT 1,
                criado_em TEXT NOT NULL
            )
            """
        )
        now = datetime.now(timezone.utc).isoformat()
        seeds = [
            (
                "Administrador Universidade",
                "admin@universidade.edu.br",
                os.getenv("SEED_ADMIN_PASSWORD", "Admin@123"),
                "admin",
            ),
            (
                "Organizador Academico",
                "organizador@universidade.edu.br",
                os.getenv("SEED_ORG_PASSWORD", "Org@123"),
                "organizador",
            ),
            (
                "Participante Discente",
                "participante@universidade.edu.br",
                os.getenv("SEED_PART_PASSWORD", "Part@123"),
                "participante",
            ),
        ]
        for nome, email, senha, role in seeds:
            existing = conn.execute("SELECT id FROM usuarios WHERE email = ?", (email,)).fetchone()
            if not existing:
                conn.execute(
                    """
                    INSERT INTO usuarios (nome, email, senha_hash, role, ativo, criado_em)
                    VALUES (?, ?, ?, ?, 1, ?)
                    """,
                    (nome, email, generate_password_hash(senha), role, now),
                )
        conn.commit()
    finally:
        conn.close()


def create_app(db_path: str | None = None) -> Flask:
    """Cria e configura o aplicativo Flask do servico SOA Identidade."""
    app = Flask(__name__)
    resolved_db = db_path or resolve_db_path("IDENTIDADE_DB_PATH", "data/identidade.db")
    app.config["DB_PATH"] = resolved_db
    _init_db(resolved_db)

    spec = build_openapi_spec(
        title="EventHub SOA - Servico de Identidade",
        version="1.0.0",
        description="Servico corporativo reutilizavel para autenticacao JWT, gestao de usuarios e RBAC.",
        paths=OPENAPI_PATHS,
    )
    register_openapi(app, "soa-identidade", spec)

    @app.post("/auth/login")
    def login() -> tuple[Any, int]:
        data = request.get_json(silent=True) or {}
        email = str(data.get("email", "")).strip().lower()
        senha = str(data.get("senha", ""))
        if not email or not senha:
            return jsonify({"erro": "Campos 'email' e 'senha' sao obrigatorios"}), 400

        conn = get_connection(app.config["DB_PATH"])
        try:
            row = conn.execute("SELECT * FROM usuarios WHERE email = ?", (email,)).fetchone()
        finally:
            conn.close()

        if not row or not check_password_hash(row["senha_hash"], senha):
            return jsonify({"erro": "Credenciais invalidas"}), 401
        if not row["ativo"]:
            return jsonify({"erro": "Usuario inativo"}), 401

        user = _row_to_user(row)
        token = generate_token(user)
        return jsonify({"access_token": token, "token_type": "Bearer", "usuario": user}), 200

    @app.post("/auth/register")
    def register() -> tuple[Any, int]:
        data = request.get_json(silent=True) or {}
        nome = str(data.get("nome", "")).strip()
        email = str(data.get("email", "")).strip().lower()
        senha = str(data.get("senha", ""))

        if not nome or not email or not senha:
            return jsonify({"erro": "Campos 'nome', 'email' e 'senha' sao obrigatorios"}), 400
        if len(senha) < 6:
            return jsonify({"erro": "A senha deve possuir ao menos 6 caracteres"}), 400

        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection(app.config["DB_PATH"])
        try:
            cursor = conn.execute(
                """
                INSERT INTO usuarios (nome, email, senha_hash, role, ativo, criado_em)
                VALUES (?, ?, ?, 'participante', 1, ?)
                """,
                (nome, email, generate_password_hash(senha), now),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM usuarios WHERE id = ?", (cursor.lastrowid,)).fetchone()
        except sqlite3.IntegrityError:
            return jsonify({"erro": "E-mail ja cadastrado"}), 409
        finally:
            conn.close()

        return jsonify({"usuario": _row_to_user(row)}), 201

    @app.get("/auth/validate")
    @require_roles()
    def validate_token() -> tuple[Any, int]:
        return jsonify({"valido": True, "usuario": g.current_user}), 200

    @app.get("/usuarios")
    @require_roles("admin")
    def list_users() -> tuple[Any, int]:
        conn = get_connection(app.config["DB_PATH"])
        try:
            rows = conn.execute("SELECT * FROM usuarios ORDER BY id ASC").fetchall()
        finally:
            conn.close()
        users = [_row_to_user(r) for r in rows]
        return jsonify({"usuarios": users, "total": len(users)}), 200

    @app.post("/usuarios")
    @require_roles("admin")
    def create_user() -> tuple[Any, int]:
        data = request.get_json(silent=True) or {}
        nome = str(data.get("nome", "")).strip()
        email = str(data.get("email", "")).strip().lower()
        senha = str(data.get("senha", ""))
        role = str(data.get("role", "participante")).strip().lower()

        if not nome or not email or not senha:
            return jsonify({"erro": "Campos 'nome', 'email' e 'senha' sao obrigatorios"}), 400
        if role not in VALID_ROLES:
            return jsonify({"erro": f"Perfil invalido. Valores aceitos: {', '.join(VALID_ROLES)}"}), 400

        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection(app.config["DB_PATH"])
        try:
            cursor = conn.execute(
                """
                INSERT INTO usuarios (nome, email, senha_hash, role, ativo, criado_em)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (nome, email, generate_password_hash(senha), role, now),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM usuarios WHERE id = ?", (cursor.lastrowid,)).fetchone()
        except sqlite3.IntegrityError:
            return jsonify({"erro": "E-mail ja cadastrado"}), 409
        finally:
            conn.close()

        return jsonify({"usuario": _row_to_user(row)}), 201

    @app.get("/usuarios/<int:user_id>")
    @require_roles("admin", "organizador", "participante")
    def get_user(user_id: int) -> tuple[Any, int]:
        current = g.current_user
        if current["role"] != "admin" and int(current["user_id"]) != user_id:
            return jsonify({"erro": "Sem permissao para consultar dados de outro usuario"}), 403

        conn = get_connection(app.config["DB_PATH"])
        try:
            row = conn.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,)).fetchone()
        finally:
            conn.close()

        if not row:
            return jsonify({"erro": "Usuario nao encontrado"}), 404
        return jsonify({"usuario": _row_to_user(row)}), 200

    @app.patch("/usuarios/<int:user_id>/perfil")
    @require_roles("admin")
    def update_user_profile(user_id: int) -> tuple[Any, int]:
        data = request.get_json(silent=True) or {}
        if "role" not in data and "ativo" not in data:
            return jsonify({"erro": "Informe 'role' e/ou 'ativo' para atualizar"}), 400

        conn = get_connection(app.config["DB_PATH"])
        try:
            existing = conn.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,)).fetchone()
            if not existing:
                return jsonify({"erro": "Usuario nao encontrado"}), 404

            new_role = str(data.get("role", existing["role"])).strip().lower()
            if new_role not in VALID_ROLES:
                return jsonify({"erro": f"Perfil invalido. Valores aceitos: {', '.join(VALID_ROLES)}"}), 400

            new_ativo = 1 if bool(data.get("ativo", existing["ativo"])) else 0
            conn.execute(
                "UPDATE usuarios SET role = ?, ativo = ? WHERE id = ?",
                (new_role, new_ativo, user_id),
            )
            conn.commit()
            updated = conn.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,)).fetchone()
        finally:
            conn.close()

        return jsonify({"usuario": _row_to_user(updated)}), 200

    @app.get("/usuarios/estatisticas")
    @require_roles("admin")
    def user_stats() -> tuple[Any, int]:
        conn = get_connection(app.config["DB_PATH"])
        try:
            rows = conn.execute("SELECT role, COUNT(*) as qtd FROM usuarios GROUP BY role").fetchall()
            total = conn.execute("SELECT COUNT(*) as total FROM usuarios").fetchone()["total"]
        finally:
            conn.close()
        por_perfil = {r["role"]: r["qtd"] for r in rows}
        return jsonify({"total_usuarios": total, "por_perfil": por_perfil}), 200

    return app


if __name__ == "__main__":
    port = int(os.getenv("IDENTIDADE_PORT", "5001"))
    create_app().run(host="0.0.0.0", port=port)
