# Diário de Uso de Inteligência Artificial — EventHub

**Disciplina:** Arquitetura de Software  
**Projeto:** EventHub — Sistema Universitário de Eventos (Arquitetura Híbrida SOA + Microsserviços)  
**Ferramenta de IA utilizada:** Antigravity (Orquestração agêntica com planejamento e execução verificada)

---

## 1. Principais Prompts Utilizados

1. **Prompt 1 — Atualização de Governança e Definição da Arquitetura Híbrida:**
   > *"Atualiza a .agents do projeto, em seguida: Uma universidade quer um sistema para gerenciar eventos como semanas acadêmicas, palestras e minicursos... serviços corporativos reutilizáveis (SOA) e serviços de domínio independentes (Microsserviços)... controle de acesso JWT com RBAC (3 perfis), Python + Flask, mínimo 5 serviços independentes, banco próprio por microsserviço, OpenAPI/Swagger, fluxo orquestrado, Docker Compose, testes com pytest, Manual completo e Diário de Uso de IA."*

2. **Prompt 2 — Integração do Repositório de Referência:**
   > *"O repositorio do github: https://github.com/ronaldocrispimsg/gerenciador-de-eventos/tree/main"*

3. **Prompt 3 — Refinamento de Normas Acadêmicas e Documentação Técnica (etapa anterior):**
   > *"Com base nos arquivos e links anexados... Documento digital nas normas da ABNT... deixe nas normas ABNT e refine."*

---

## 2. Registro de Decisões: Aceito, Modificado e Rejeitado

| Sugestão / Artefato da IA | Decisão | Justificativa Técnica |
| :--- | :---: | :--- |
| Separação em 7 serviços independentes (`api-gateway`, `soa-identidade`, `soa-notificacao`, `soa-orquestrador`, `ms-eventos`, `ms-inscricoes`, `ms-certificados`) | **Aceito** | Reflete exatamente o diagrama de referência do projeto e separa os serviços corporativos reutilizáveis (SOA) dos domínios de negócio isolados (Microsserviços). |
| Validação de JWT *Defense-in-Depth* tanto no `api-gateway` quanto via `@require_roles` em cada microsserviço | **Aceito** | Impede que uma chamada direta a uma porta interna (`5004`, `5005`, `5006`) burle as permissões RBAC caso o tráfego ignore o Gateway. |
| Uso de bibliotecas externas pesadas como `flasgger` ou `flask-smorest` para OpenAPI | **Rejeitado / Substituído** | No ambiente isolado sem internet do laboratório, `flasgger` exigiria múltiplas dependências extras (`jsonschema`, `mistune`, `pyyaml`). Optou-se por um registrador leve e compatível com OpenAPI 3.0.3 (`common/openapi.py`) servindo `/openapi.json` e `/apidocs` nativamente em Flask, sem quebrar nenhum contrato formal. |
| Rotear `POST /inscricoes` diretamente do Gateway para `ms-inscricoes` | **Modificado** | Inicialmente uma rota simples de proxy mandaria `POST /inscricoes` direto ao microsserviço, pulando a verificação do evento aprovado e o envio de notificação. Modificou-se o `api-gateway` para encaminhar `POST /inscricoes` ao `soa-orquestrador` (`POST /processos/inscricao`), garantindo que o fluxo completo (`ms-eventos -> ms-inscricoes -> soa-notificacao`) seja executado obrigatoriamente. |
| Propagação da capacidade do evento como parâmetro da requisição para `ms-inscricoes` | **Aceito com ressalva** | Mantém `ms-inscricoes` sem acesso ao banco `eventos.db` (respeitando *Database-per-Service*) sem criar dependência síncrona circular entre `ms-inscricoes` e `ms-eventos`; em contrapartida, assume que `POST /inscricoes` passa pelo Orquestrador. |

---

## 3. Erros e Limitações da IA Identificados e Corrigidos

### Erro 1 — Conflito de Precedência de Rotas no API Gateway (`/eventos/<id>/inscritos`)
* **O que aconteceu:** Em um primeiro desenho do proxy no `api-gateway`, a rota genérica `@app.route("/eventos/<path:subpath>")` capturava todas as requisições iniciadas por `/eventos/`, inclusive `GET /eventos/1/inscritos`, encaminhando-a erroneamente para o `ms-eventos` (que não possui a tabela `inscricoes`) resultando em `404 Not Found`.
* **Como foi corrigido:** Declarou-se a rota específica `@app.get("/eventos/<int:evento_id>/inscritos")` antes das rotas genéricas do `ms-eventos`, roteando explicitamente a consulta de inscritos para o `ms-inscricoes`.

### Erro 2 — Requisito de Tipo `str` para Claim `sub` no PyJWT 2.10+
* **O que aconteceu:** Versões recentes do `PyJWT` (como a `2.15.1` instalada no `.venv`) passaram a validar estritamente o tipo do campo padrão `sub` (*Subject*) segundo a RFC 7519, rejeitando tokens quando `sub` é gravado como inteiro (`1`) em vez de string (`"1"`).
* **Como foi corrigido:** Em `common/auth.py`, `sub` foi padronizado como `str(user["id"])` e adicionou-se a claim `user_id` inteira separadamente, garantindo compatibilidade total na decodificação e comparações numéricas de ownership nos serviços.

### Erro 3 — Execução de `pytest` em Ambiente Virtual Montado Manualmente
* **O que aconteceu:** Ao montar o `.venv` offline a partir do cache local de pacotes (`archive-v0`), o binário wrapper `.venv/bin/pytest` não existia (erro `127: No such file or directory`).
* **Como foi corrigido:** Invocou-se o executor diretamente via módulo Python (`.venv/bin/python -m pytest -v`), executando os 5 testes de integração ponta a ponta com sucesso em 3,52s.
