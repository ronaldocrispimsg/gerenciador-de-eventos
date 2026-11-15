# EventHub — Sistema Universitário de Gerenciamento de Eventos

**Repositório:** [`ronaldocrispimsg/gerenciador-de-eventos`](https://github.com/ronaldocrispimsg/gerenciador-de-eventos/tree/main)

Sistema distribuído desenvolvido em **Python + Flask** aplicando uma **Arquitetura Híbrida (SOA + Microsserviços)** para gerenciar semanas acadêmicas, palestras e minicursos universitários com autenticação **JWT + RBAC** (perfis `admin`, `organizador` e `participante`).

---

## Estrutura Arquitetural (7 Serviços Independentes)

1. **`api-gateway` (`:5000`)**: Ponto de entrada único, validação preliminar de JWT, roteamento REST e interface web (`http://127.0.0.1:5000/`).
2. **Camada SOA (Contratos OpenAPI 3.0.3 em `/openapi.json` e `/apidocs`):**
   - `soa-identidade` (`:5001`, `identidade.db`): Login, emissão/validação JWT e administração de usuários.
   - `soa-notificacao` (`:5002`, `notificacoes.db`): Envio e auditoria de notificações reutilizável por outros sistemas.
   - `soa-orquestrador` (`:5003`): Coordena o fluxo composto de inscrição (`ms-eventos -> ms-inscricoes -> soa-notificacao`), cancelamento, emissão de certificados e relatórios gerenciais.
3. **Camada de Microsserviços de Domínio (*Database-per-Service*):**
   - `ms-eventos` (`:5004`, `eventos.db`): Criação, edição e aprovação de eventos.
   - `ms-inscricoes` (`:5005`, `inscricoes.db`): Vagas, duplicidade, cancelamentos e registro de presença.
   - `ms-certificados` (`:5006`, `certificados.db`): Emissão de certificados e validação pública de autenticidade.

---

## Como Executar

### 1. Docker Compose (Recomendado)
```bash
cp .env.example .env
docker compose up --build
```

### 2. Localmente via Python (`.venv`)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/run_all.py
```

### 3. Acessar o Portal Web e Documentação OpenAPI
Com os serviços em execução (via Docker Compose ou `scripts/run_all.py`):
- **Portal Web EventHub (Frontend RBAC):** `http://127.0.0.1:5000/`
- **Swagger UI (`api-gateway`):** `http://127.0.0.1:5000/apidocs`

### 4. Executar Testes Automatizados (`pytest`)
```bash
.venv/bin/python -m pytest -v
```

---

## Documentação e Artefatos Obrigatórios

- **Manual Técnico e Arquitetural Completo:** [`docs/MANUAL_ARQUITETURA_EVENTHUB.md`](docs/MANUAL_ARQUITETURA_EVENTHUB.md)
- **Diário de Uso de IA:** [`docs/DIARIO_USO_IA.md`](docs/DIARIO_USO_IA.md)
- **Diagrama Editável Draw.io:** [`docs/arquitetura_eventhub.drawio`](docs/arquitetura_eventhub.drawio)
- **Coleção Postman:** [`docs/EventHub.postman_collection.json`](docs/EventHub.postman_collection.json)
- **Resumo Arquitetural:** [`arquitetura.md`](arquitetura.md)
