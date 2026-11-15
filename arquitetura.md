# Arquitetura do Sistema — EventHub

**Repositório:** `gerenciador-de-eventos` (`https://github.com/ronaldocrispimsg/gerenciador-de-eventos/tree/main`)

## Visão Geral
O **EventHub** implementa uma **Arquitetura Híbrida (SOA + Microsserviços)** em Python 3.13 + Flask 3.1, composta por **7 serviços independentes** comunicando-se via REST/JSON com segurança baseada em **JWT (HS256)** e controle de acesso por papéis (**RBAC**: `admin`, `organizador`, `participante`).

## Componentes e Portas

| Camada | Serviço | Porta | Banco SQLite Próprio | Responsabilidade |
| :--- | :--- | :---: | :--- | :--- |
| Entrada | `api-gateway` | `5000` | — | Validação preliminar de JWT, `X-Correlation-ID` e roteamento |
| SOA | `soa-identidade` | `5001` | `data/identidade.db` | Autenticação, emissão/validação JWT e gestão de usuários |
| SOA | `soa-notificacao` | `5002` | `data/notificacoes.db` | Serviço corporativo reutilizável de e-mail/log |
| SOA | `soa-orquestrador` | `5003` | — | Orquestração (inscrição, cancelamento, certificado, relatórios) |
| Microsserviço | `ms-eventos` | `5004` | `data/eventos.db` | Criação, edição e aprovação de eventos |
| Microsserviço | `ms-inscricoes` | `5005` | `data/inscricoes.db` | Gestão de inscrições, vagas, cancelamentos e presença |
| Microsserviço | `ms-certificados` | `5006` | `data/certificados.db` | Emissão de certificados e validação pública por código |

## Infraestrutura Compartilhada (`common/`)
Contém apenas utilitários transversais sem compartilhamento de banco:
- [`common/auth.py`](common/auth.py): `generate_token`, `decode_token`, `@require_roles`.
- [`common/openapi.py`](common/openapi.py): especificação OpenAPI 3.0.3 (`/openapi.json`), Swagger UI (`/apidocs`) e `/health`.
- [`common/http_client.py`](common/http_client.py): cliente HTTP com propagação de Bearer JWT e `X-Correlation-ID`.
- [`common/db.py`](common/db.py): helper de conexão SQLite apontando para o arquivo individual de cada serviço.

Para detalhes aprofundados, diagramas C4/UML e matriz RBAC completa, consulte [`docs/MANUAL_ARQUITETURA_EVENTHUB.md`](docs/MANUAL_ARQUITETURA_EVENTHUB.md).
