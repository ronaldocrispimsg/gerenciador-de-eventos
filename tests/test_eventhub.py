"""Testes de integracao ponta a ponta dos 7 servicos EventHub (SOA + Microsservicos)."""

from __future__ import annotations

import sqlite3
import sys
import threading
from pathlib import Path

import pytest
import requests
from werkzeug.serving import make_server

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.api_gateway.app import create_app as create_gateway_app
from services.ms_certificados.app import create_app as create_certificados_app
from services.ms_eventos.app import create_app as create_eventos_app
from services.ms_inscricoes.app import create_app as create_inscricoes_app
from services.soa_identidade.app import create_app as create_identidade_app
from services.soa_notificacao.app import create_app as create_notificacao_app
from services.soa_orquestrador.app import create_app as create_orquestrador_app


class _ServiceHandle:
    def __init__(self, app, name: str) -> None:
        self.name = name
        self.server = make_server("127.0.0.1", 0, app, threaded=True)
        self.port = self.server.server_port
        self.url = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)


@pytest.fixture(scope="module")
def cluster(tmp_path_factory: pytest.TempPathFactory):
    """Sobe os 7 servicos reais em portas dinamicas e bancos SQLite isolados."""
    db_dir = tmp_path_factory.mktemp("eventhub_dbs")
    db_paths = {
        "identidade": str(db_dir / "identidade.db"),
        "notificacao": str(db_dir / "notificacoes.db"),
        "eventos": str(db_dir / "eventos.db"),
        "inscricoes": str(db_dir / "inscricoes.db"),
        "certificados": str(db_dir / "certificados.db"),
    }

    identidade = _ServiceHandle(create_identidade_app(db_paths["identidade"]), "soa-identidade")
    notificacao = _ServiceHandle(create_notificacao_app(db_paths["notificacao"]), "soa-notificacao")
    eventos = _ServiceHandle(create_eventos_app(db_paths["eventos"]), "ms-eventos")
    inscricoes = _ServiceHandle(create_inscricoes_app(db_paths["inscricoes"]), "ms-inscricoes")
    certificados = _ServiceHandle(create_certificados_app(db_paths["certificados"]), "ms-certificados")

    urls = {
        "identidade": identidade.url,
        "notificacao": notificacao.url,
        "eventos": eventos.url,
        "inscricoes": inscricoes.url,
        "certificados": certificados.url,
    }
    orquestrador = _ServiceHandle(create_orquestrador_app(urls), "soa-orquestrador")
    gateway = _ServiceHandle(
        create_gateway_app({**urls, "orquestrador": orquestrador.url}),
        "api-gateway",
    )

    handles = [
        gateway,
        orquestrador,
        certificados,
        inscricoes,
        eventos,
        notificacao,
        identidade,
    ]
    yield {
        "gateway": gateway.url,
        "services": {h.name: h.url for h in handles},
        "db_paths": db_paths,
    }

    for handle in handles:
        handle.stop()


def _login(gw: str, email: str, senha: str) -> str:
    resp = requests.post(f"{gw}/auth/login", json={"email": email, "senha": senha}, timeout=5)
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_health_and_openapi_contracts(cluster) -> None:
    """Verifica /health e contratos OpenAPI/Swagger em todos os servicos."""
    for name, url in cluster["services"].items():
        health = requests.get(f"{url}/health", timeout=5)
        assert health.status_code == 200
        assert health.json()["status"] == "healthy"
        assert health.json()["service"] == name

        spec = requests.get(f"{url}/openapi.json", timeout=5)
        assert spec.status_code == 200
        assert spec.json()["openapi"] == "3.0.3"

        docs = requests.get(f"{url}/apidocs", timeout=5)
        assert docs.status_code == 200
        assert "swagger-ui" in docs.text


def test_authentication_and_http_status_codes(cluster) -> None:
    """Valida login, registro de participante e codigos 400/401/409."""
    gw = cluster["gateway"]

    bad_req = requests.post(f"{gw}/auth/login", json={"email": "admin@universidade.edu.br"}, timeout=5)
    assert bad_req.status_code == 400

    wrong_pw = requests.post(
        f"{gw}/auth/login",
        json={"email": "admin@universidade.edu.br", "senha": "errada"},
        timeout=5,
    )
    assert wrong_pw.status_code == 401

    no_token = requests.get(f"{gw}/eventos", timeout=5)
    assert no_token.status_code == 401

    bad_token = requests.get(f"{gw}/eventos", headers=_headers("token.falso.123"), timeout=5)
    assert bad_token.status_code == 401

    reg = requests.post(
        f"{gw}/auth/register",
        json={"nome": "Aluno Novo", "email": "aluno.novo@universidade.edu.br", "senha": "Aluno@123"},
        timeout=5,
    )
    assert reg.status_code == 201
    assert reg.json()["usuario"]["role"] == "participante"

    dup = requests.post(
        f"{gw}/auth/register",
        json={"nome": "Aluno Novo", "email": "aluno.novo@universidade.edu.br", "senha": "Aluno@123"},
        timeout=5,
    )
    assert dup.status_code == 409


def test_rbac_enforcement_across_roles(cluster) -> None:
    """Garante que cada perfil respeita as restricoes RBAC (403 Forbidden)."""
    gw = cluster["gateway"]
    token_part = _login(gw, "participante@universidade.edu.br", "Part@123")
    token_org = _login(gw, "organizador@universidade.edu.br", "Org@123")

    # Participante nao pode listar usuarios, criar eventos nem aprovar eventos
    assert requests.get(f"{gw}/usuarios", headers=_headers(token_part), timeout=5).status_code == 403
    assert (
        requests.post(
            f"{gw}/eventos",
            headers=_headers(token_part),
            json={
                "titulo": "Evento Indevido",
                "descricao": "Teste",
                "tipo": "PALESTRA",
                "data_evento": "2026-12-01",
                "local": "Auditorio",
                "capacidade": 10,
                "carga_horaria": 2,
            },
            timeout=5,
        ).status_code
        == 403
    )
    assert requests.get(f"{gw}/relatorios/geral", headers=_headers(token_part), timeout=5).status_code == 403

    # Organizador nao pode listar todos usuarios, aprovar eventos nem ver relatorio geral
    assert requests.get(f"{gw}/usuarios", headers=_headers(token_org), timeout=5).status_code == 403
    assert requests.patch(f"{gw}/eventos/1/aprovar", headers=_headers(token_org), timeout=5).status_code == 403
    assert requests.get(f"{gw}/relatorios/geral", headers=_headers(token_org), timeout=5).status_code == 403


def test_end_to_end_orchestrated_eventhub_flow(cluster) -> None:
    """Testa fluxo completo: criar evento -> aprovar -> inscrever (orquestrado) -> presenca -> certificado -> relatorio."""
    gw = cluster["gateway"]
    token_admin = _login(gw, "admin@universidade.edu.br", "Admin@123")
    token_org = _login(gw, "organizador@universidade.edu.br", "Org@123")
    token_part = _login(gw, "participante@universidade.edu.br", "Part@123")
    token_part2 = _login(gw, "aluno.novo@universidade.edu.br", "Aluno@123")

    # 1. Admin cria segundo organizador para testar isolamento de edicao
    r_org2 = requests.post(
        f"{gw}/usuarios",
        headers=_headers(token_admin),
        json={
            "nome": "Outro Organizador",
            "email": "org2@universidade.edu.br",
            "senha": "Org2@123",
            "role": "organizador",
        },
        timeout=5,
    )
    assert r_org2.status_code == 201
    token_org2 = _login(gw, "org2@universidade.edu.br", "Org2@123")

    # 2. Organizador cria minicurso com capacidade = 1 (inicialmente PENDENTE)
    r_evt = requests.post(
        f"{gw}/eventos",
        headers=_headers(token_org),
        json={
            "titulo": "Minicurso de Arquitetura Hibrida",
            "descricao": "SOA e Microsservicos na pratica com Python",
            "tipo": "MINICURSO",
            "data_evento": "2026-11-25",
            "local": "Lab 02",
            "capacidade": 1,
            "carga_horaria": 8,
        },
        timeout=5,
    )
    assert r_evt.status_code == 201
    evento = r_evt.json()["evento"]
    assert evento["status"] == "PENDENTE"
    evento_id = evento["id"]

    # Outro organizador nao pode editar este evento
    r_edit_other = requests.put(
        f"{gw}/eventos/{evento_id}",
        headers=_headers(token_org2),
        json={"local": "Outro Local"},
        timeout=5,
    )
    assert r_edit_other.status_code == 403

    # Organizador dono edita o evento
    r_edit = requests.put(
        f"{gw}/eventos/{evento_id}",
        headers=_headers(token_org),
        json={"local": "Auditorio Central"},
        timeout=5,
    )
    assert r_edit.status_code == 200
    assert r_edit.json()["evento"]["local"] == "Auditorio Central"

    # Participante nao pode se inscrever enquanto evento esta PENDENTE (400)
    r_ins_pending = requests.post(
        f"{gw}/inscricoes",
        headers=_headers(token_part),
        json={"evento_id": evento_id},
        timeout=5,
    )
    assert r_ins_pending.status_code == 400

    # 3. Admin aprova o evento
    r_aprov = requests.patch(
        f"{gw}/eventos/{evento_id}/aprovar",
        headers=_headers(token_admin),
        json={"status": "APROVADO"},
        timeout=5,
    )
    assert r_aprov.status_code == 200
    assert r_aprov.json()["evento"]["status"] == "APROVADO"

    # 4. Participante realiza inscricao via fluxo orquestrado (Gateway -> Orquestrador -> Eventos + Inscricoes + Notificacao)
    r_ins = requests.post(
        f"{gw}/inscricoes",
        headers=_headers(token_part),
        json={"evento_id": evento_id},
        timeout=5,
    )
    assert r_ins.status_code == 201
    ins_body = r_ins.json()
    inscricao_id = ins_body["inscricao"]["id"]
    assert ins_body["notificacao"]["protocolo"].startswith("NOTIF-")

    # Inscricao duplicada retorna 409
    r_dup_ins = requests.post(
        f"{gw}/inscricoes",
        headers=_headers(token_part),
        json={"evento_id": evento_id},
        timeout=5,
    )
    assert r_dup_ins.status_code == 409

    # Segundo participante tentando inscrever em evento lotado (capacidade=1) retorna 409
    r_full = requests.post(
        f"{gw}/inscricoes",
        headers=_headers(token_part2),
        json={"evento_id": evento_id},
        timeout=5,
    )
    assert r_full.status_code == 409

    # 5. Participante tenta emitir certificado antes da presenca -> 400
    r_cert_early = requests.post(
        f"{gw}/certificados/emitir",
        headers=_headers(token_part),
        json={"inscricao_id": inscricao_id},
        timeout=5,
    )
    assert r_cert_early.status_code == 400

    # 6. Organizador ve inscritos e registra presenca
    r_list_ins = requests.get(
        f"{gw}/eventos/{evento_id}/inscritos", headers=_headers(token_org), timeout=5
    )
    assert r_list_ins.status_code == 200
    assert r_list_ins.json()["total"] == 1

    r_pres = requests.patch(
        f"{gw}/inscricoes/{inscricao_id}/presenca",
        headers=_headers(token_org),
        json={"presenca": True},
        timeout=5,
    )
    assert r_pres.status_code == 200
    assert r_pres.json()["inscricao"]["presenca"] is True

    # 7. Participante emite certificado e valida codigo publico
    r_cert = requests.post(
        f"{gw}/certificados/emitir",
        headers=_headers(token_part),
        json={"inscricao_id": inscricao_id},
        timeout=5,
    )
    assert r_cert.status_code == 201
    codigo = r_cert.json()["certificado"]["codigo_verificacao"]
    assert codigo.startswith("EVTHUB-")

    r_val = requests.get(f"{gw}/certificados/validar/{codigo}", timeout=5)
    assert r_val.status_code == 200
    assert r_val.json()["valido"] is True

    assert requests.get(f"{gw}/certificados/validar/INEXISTENTE", timeout=5).status_code == 404

    # 8. Participante cancela uma inscricao em outro evento aprovado
    r_evt2 = requests.post(
        f"{gw}/eventos",
        headers=_headers(token_org),
        json={
            "titulo": "Semana Academica de Computacao",
            "descricao": "Palestras e paineis",
            "tipo": "SEMANA_ACADEMICA",
            "data_evento": "2026-12-10",
            "local": "Campus Central",
            "capacidade": 100,
            "carga_horaria": 20,
        },
        timeout=5,
    )
    evt2_id = r_evt2.json()["evento"]["id"]
    requests.patch(
        f"{gw}/eventos/{evt2_id}/aprovar",
        headers=_headers(token_admin),
        json={"status": "APROVADO"},
        timeout=5,
    )
    r_ins2 = requests.post(
        f"{gw}/inscricoes",
        headers=_headers(token_part),
        json={"evento_id": evt2_id},
        timeout=5,
    )
    assert r_ins2.status_code == 201
    ins2_id = r_ins2.json()["inscricao"]["id"]

    r_cancel = requests.patch(
        f"{gw}/inscricoes/{ins2_id}/cancelar", headers=_headers(token_part), timeout=5
    )
    assert r_cancel.status_code == 200
    assert r_cancel.json()["inscricao"]["status"] == "CANCELADA"

    # 9. Admin consulta relatorio geral consolidado
    r_rep = requests.get(f"{gw}/relatorios/geral", headers=_headers(token_admin), timeout=5)
    assert r_rep.status_code == 200
    rel = r_rep.json()["relatorio"]
    assert rel["eventos"]["total_eventos"] >= 2
    assert rel["inscricoes"]["total_inscricoes"] >= 2
    assert rel["certificados"]["total_certificados"] >= 1
    assert rel["notificacoes"]["total_notificacoes"] >= 3


def test_database_isolation_per_service(cluster) -> None:
    """Comprova fisicamente que cada servico possui seu proprio banco SQLite isolado."""
    expected_tables = {
        "identidade": {"usuarios"},
        "notificacao": {"notificacoes"},
        "eventos": {"eventos"},
        "inscricoes": {"inscricoes"},
        "certificados": {"certificados"},
    }
    for key, tables in expected_tables.items():
        db_file = Path(cluster["db_paths"][key])
        assert db_file.exists()
        conn = sqlite3.connect(str(db_file))
        try:
            found = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'"
                ).fetchall()
            }
        finally:
            conn.close()
        assert found == tables


def test_frontend_assets_served(cluster) -> None:
    """Garante que o portal web SPA e seus assets estaticos sao servidos pelo API Gateway."""
    gw = cluster["gateway"]

    r_index = requests.get(f"{gw}/", timeout=5)
    assert r_index.status_code == 200
    assert "text/html" in r_index.headers.get("Content-Type", "")
    assert "no-store" in r_index.headers.get("Cache-Control", "")
    assert "EventHub" in r_index.text
    assert 'src="/static/app.js"' in r_index.text

    r_css = requests.get(f"{gw}/static/styles.css", timeout=5)
    assert r_css.status_code == 200
    assert "text/css" in r_css.headers.get("Content-Type", "")

    r_js = requests.get(f"{gw}/static/app.js", timeout=5)
    assert r_js.status_code == 200
    assert "javascript" in r_js.headers.get("Content-Type", "")
    assert "/auth/login" in r_js.text

