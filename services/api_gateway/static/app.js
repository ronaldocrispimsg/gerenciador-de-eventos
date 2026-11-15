(() => {
  "use strict";

  const STORAGE_KEYS = {
    token: "eventhub_token",
    user: "eventhub_user",
  };

  const DEMO_ACCOUNTS = {
    participante: {
      email: "participante@universidade.edu.br",
      senha: "Part@123",
    },
    organizador: {
      email: "organizador@universidade.edu.br",
      senha: "Org@123",
    },
    admin: {
      email: "admin@universidade.edu.br",
      senha: "Admin@123",
    },
  };

  const EVENT_TYPE_LABELS = {
    SEMANA_ACADEMICA: "Semana Acadêmica",
    PALESTRA: "Palestra",
    MINICURSO: "Minicurso",
  };

  const ROLE_LABELS = {
    admin: "Admin",
    organizador: "Organizador",
    participante: "Participante",
  };

  const VIEWS_BY_ROLE = {
    participante: [
      { id: "eventos", label: "Eventos disponíveis" },
      { id: "minhas-inscricoes", label: "Minhas inscrições" },
      { id: "meus-certificados", label: "Meus certificados" },
      { id: "notificacoes", label: "Notificações" },
    ],
    organizador: [
      { id: "eventos", label: "Eventos" },
      { id: "inscritos", label: "Inscritos e presença" },
      { id: "notificacoes", label: "Notificações" },
    ],
    admin: [
      { id: "relatorio", label: "Relatório geral" },
      { id: "eventos", label: "Eventos e aprovações" },
      { id: "inscritos", label: "Inscritos e presença" },
      { id: "usuarios", label: "Usuários e perfis" },
      { id: "certificados", label: "Certificados" },
      { id: "notificacoes", label: "Notificações" },
    ],
  };

  const state = {
    token: sessionStorage.getItem(STORAGE_KEYS.token) || "",
    user: readStoredUser(),
    activeView: "",
    selectedEventoId: null,
    filters: {
      eventQuery: "",
      eventStatus: "TODOS",
      eventType: "TODOS",
      certQuery: "",
    },
  };

  const dom = {
    toastRegion: document.getElementById("toast-region"),
    authScreen: document.getElementById("auth-screen"),
    appScreen: document.getElementById("app-screen"),
    loginForm: document.getElementById("login-form"),
    loginError: document.getElementById("login-error"),
    registerForm: document.getElementById("register-form"),
    registerError: document.getElementById("register-error"),
    publicValidateForm: document.getElementById("public-validate-form"),
    publicCertCode: document.getElementById("public-cert-code"),
    publicValidateResult: document.getElementById("public-validate-result"),
    userName: document.getElementById("user-name"),
    userRole: document.getElementById("user-role"),
    refreshViewBtn: document.getElementById("refresh-view-btn"),
    logoutBtn: document.getElementById("logout-btn"),
    sidebarNav: document.getElementById("sidebar-nav"),
    mainContent: document.getElementById("main-content"),
    modal: document.getElementById("app-modal"),
    modalTitle: document.getElementById("modal-title"),
    modalCloseBtn: document.getElementById("modal-close-btn"),
    modalBody: document.getElementById("modal-body"),
  };

  function readStoredUser() {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEYS.user);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }

  function saveSession(token, user) {
    state.token = token;
    state.user = user;
    sessionStorage.setItem(STORAGE_KEYS.token, token);
    sessionStorage.setItem(STORAGE_KEYS.user, JSON.stringify(user));
  }

  function clearSession() {
    state.token = "";
    state.user = null;
    state.activeView = "";
    state.selectedEventoId = null;
    sessionStorage.removeItem(STORAGE_KEYS.token);
    sessionStorage.removeItem(STORAGE_KEYS.user);
  }

  function el(tag, attrs = {}, children = []) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (value === undefined || value === null) continue;
      if (key === "className") {
        node.className = value;
      } else if (key === "dataset") {
        for (const [dKey, dVal] of Object.entries(value)) {
          node.dataset[dKey] = String(dVal);
        }
      } else if (key.startsWith("on") && typeof value === "function") {
        node.addEventListener(key.slice(2).toLowerCase(), value);
      } else if (typeof value === "boolean") {
        if (value) node.setAttribute(key, "");
      } else {
        node.setAttribute(key, String(value));
      }
    }

    const list = Array.isArray(children) ? children : [children];
    for (const item of list) {
      if (item === null || item === undefined || item === false) continue;
      if (typeof item === "string" || typeof item === "number") {
        node.appendChild(document.createTextNode(String(item)));
      } else {
        node.appendChild(item);
      }
    }
    return node;
  }

  function showToast(message, variant = "info") {
    const toast = el("div", {
      className: `toast ${variant === "error" ? "error" : variant === "success" ? "success" : ""}`.trim(),
    }, message);
    dom.toastRegion.appendChild(toast);
    setTimeout(() => {
      toast.remove();
    }, 4500);
  }

  function formatDateTime(value) {
    if (!value) return "-";
    const normalized = value.includes("T") ? value : value.replace(" ", "T");
    const date = new Date(normalized);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function formatDateInput(value) {
    if (!value) return "";
    const normalized = value.includes("T") ? value : value.replace(" ", "T");
    return normalized.slice(0, 16);
  }

  function makeBadge(label, variant = "info") {
    return el("span", { className: `badge badge-${variant}` }, label);
  }

  function statusBadge(status) {
    const map = {
      APROVADO: ["Aprovado", "ok"],
      ATIVA: ["Ativa", "ok"],
      ENVIADO: ["Enviado", "ok"],
      PENDENTE: ["Pendente", "warn"],
      REJEITADO: ["Rejeitado", "bad"],
      CANCELADA: ["Cancelada", "bad"],
    };
    const [text, variant] = map[status] || [status || "-", "info"];
    return makeBadge(text, variant);
  }

  async function apiRequest(path, { method = "GET", body = null, auth = true } = {}) {
    const headers = {};
    if (body !== null) {
      headers["Content-Type"] = "application/json";
    }
    if (auth && state.token) {
      headers.Authorization = `Bearer ${state.token}`;
    }

    const response = await fetch(path, {
      method,
      headers,
      body: body !== null ? JSON.stringify(body) : undefined,
    });

    let data = {};
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      data = await response.json();
    }

    if (response.status === 401 && auth && path !== "/auth/login") {
      clearSession();
      renderShell();
      showToast("Sessão expirada ou inválida. Entre novamente.", "error");
      throw new Error(data.erro || "Não autenticado");
    }

    if (!response.ok) {
      const msg = data.erro || data.message || `Erro HTTP ${response.status}`;
      const error = new Error(msg);
      error.status = response.status;
      error.payload = data;
      throw error;
    }

    return data;
  }

  function setInlineError(box, message) {
    if (!message) {
      box.textContent = "";
      box.classList.add("hidden");
      return;
    }
    box.textContent = message;
    box.classList.remove("hidden");
  }

  function openModal(title, contentNode) {
    dom.modalTitle.textContent = title;
    dom.modalBody.replaceChildren(contentNode);
    if (!dom.modal.open) {
      dom.modal.showModal();
    }
  }

  function closeModal() {
    if (dom.modal.open) {
      dom.modal.close();
    }
    dom.modalBody.replaceChildren();
  }

  function createViewHeader(title, subtitle, rightActions = null) {
    return el("div", { className: "view-header" }, [
      el("div", {}, [
        el("h1", {}, title),
        subtitle ? el("p", {}, subtitle) : null,
      ]),
      rightActions,
    ]);
  }

  function renderLoading(message = "Carregando dados...") {
    dom.mainContent.replaceChildren(
      el("div", { className: "panel" }, el("p", { className: "muted" }, message))
    );
  }

  function renderErrorState(err, retryFn) {
    dom.mainContent.replaceChildren(
      el("div", { className: "panel" }, [
        el("p", { className: "form-error" }, err.message || "Falha ao carregar dados."),
        retryFn
          ? el(
              "button",
              {
                type: "button",
                className: "btn btn-secondary btn-sm",
                style: "margin-top: 12px;",
                onClick: retryFn,
              },
              "Tentar novamente"
            )
          : null,
      ])
    );
  }

  function setupAuthEvents() {
    document.querySelectorAll("[data-auth-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const target = btn.dataset.authTab;
        document.querySelectorAll("[data-auth-tab]").forEach((b) => {
          const active = b.dataset.authTab === target;
          b.classList.toggle("active", active);
          b.setAttribute("aria-selected", String(active));
        });
        dom.loginForm.classList.toggle("hidden", target !== "login");
        dom.registerForm.classList.toggle("hidden", target !== "register");
        setInlineError(dom.loginError, "");
        setInlineError(dom.registerError, "");
      });
    });

    document.querySelectorAll("[data-fill-role]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const creds = DEMO_ACCOUNTS[btn.dataset.fillRole];
        if (!creds) return;
        dom.loginForm.elements.email.value = creds.email;
        dom.loginForm.elements.senha.value = creds.senha;
        setInlineError(dom.loginError, "");
        dom.loginForm.elements.email.focus();
      });
    });

    dom.loginForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      setInlineError(dom.loginError, "");
      const submitBtn = dom.loginForm.querySelector('button[type="submit"]');
      const originalLabel = submitBtn.textContent;
      submitBtn.disabled = true;
      submitBtn.textContent = "Entrando...";

      try {
        const email = dom.loginForm.elements.email.value.trim();
        const senha = dom.loginForm.elements.senha.value;
        const data = await apiRequest("/auth/login", {
          method: "POST",
          body: { email, senha },
          auth: false,
        });
        saveSession(data.access_token, data.usuario);
        dom.loginForm.reset();
        enterAuthenticatedApp();
        showToast(`Bem-vindo(a), ${data.usuario.nome}.`, "success");
      } catch (err) {
        setInlineError(dom.loginError, err.message);
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = originalLabel;
      }
    });

    dom.registerForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      setInlineError(dom.registerError, "");
      const submitBtn = dom.registerForm.querySelector('button[type="submit"]');
      const originalLabel = submitBtn.textContent;
      submitBtn.disabled = true;
      submitBtn.textContent = "Criando conta...";

      const nome = dom.registerForm.elements.nome.value.trim();
      const email = dom.registerForm.elements.email.value.trim();
      const senha = dom.registerForm.elements.senha.value;

      try {
        await apiRequest("/auth/register", {
          method: "POST",
          body: { nome, email, senha },
          auth: false,
        });
        const loginData = await apiRequest("/auth/login", {
          method: "POST",
          body: { email, senha },
          auth: false,
        });
        saveSession(loginData.access_token, loginData.usuario);
        dom.registerForm.reset();
        enterAuthenticatedApp();
        showToast("Conta criada e sessão iniciada.", "success");
      } catch (err) {
        setInlineError(dom.registerError, err.message);
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = originalLabel;
      }
    });

    dom.publicValidateForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const code = dom.publicCertCode.value.trim();
      if (!code) return;

      dom.publicValidateResult.className = "validate-result";
      dom.publicValidateResult.textContent = "Consultando certificado...";

      try {
        const data = await apiRequest(`/certificados/validar/${encodeURIComponent(code)}`, {
          auth: false,
        });
        const cert = data.certificado;
        dom.publicValidateResult.className = "validate-result valid";
        dom.publicValidateResult.replaceChildren(
          el("strong", {}, "Certificado autêntico"),
          el("div", { style: "margin-top: 6px;" }, [
            el("div", {}, `Participante: ${cert.participante_nome}`),
            el("div", {}, `Evento: ${cert.evento_titulo} (${cert.carga_horaria}h)`),
            el("div", {}, `Emitido em: ${formatDateTime(cert.emitido_em)}`),
            el("div", { className: "mono", style: "margin-top: 4px;" }, `Código: ${cert.codigo_verificacao}`),
          ])
        );
      } catch (err) {
        dom.publicValidateResult.className = "validate-result invalid";
        dom.publicValidateResult.textContent = err.message || "Código não encontrado.";
      }
    });

    dom.logoutBtn.addEventListener("click", () => {
      clearSession();
      renderShell();
      showToast("Sessão encerrada.");
    });

    dom.refreshViewBtn.addEventListener("click", () => {
      renderActiveView();
    });

    dom.modalCloseBtn.addEventListener("click", closeModal);
    dom.modal.addEventListener("click", (event) => {
      if (event.target === dom.modal) {
        closeModal();
      }
    });
  }

  function renderSidebar() {
    const role = state.user?.role || "participante";
    const items = VIEWS_BY_ROLE[role] || VIEWS_BY_ROLE.participante;

    if (!items.some((item) => item.id === state.activeView)) {
      state.activeView = items[0].id;
    }

    const navList = el(
      "div",
      { className: "nav-list" },
      items.map((item) =>
        el(
          "button",
          {
            type: "button",
            className: `nav-item ${state.activeView === item.id ? "active" : ""}`.trim(),
            onClick: () => {
              state.activeView = item.id;
              renderSidebar();
              renderActiveView();
            },
          },
          item.label
        )
      )
    );

    dom.sidebarNav.replaceChildren(navList);
  }

  function renderShell() {
    const authenticated = Boolean(state.token && state.user);
    dom.authScreen.classList.toggle("hidden", authenticated);
    dom.appScreen.classList.toggle("hidden", !authenticated);

    if (!authenticated) {
      dom.sidebarNav.replaceChildren();
      dom.mainContent.replaceChildren();
      return;
    }

    dom.userName.textContent = state.user.nome;
    dom.userRole.textContent = ROLE_LABELS[state.user.role] || state.user.role;
    renderSidebar();
  }

  function enterAuthenticatedApp() {
    const role = state.user?.role || "participante";
    state.activeView = (VIEWS_BY_ROLE[role] || VIEWS_BY_ROLE.participante)[0].id;
    renderShell();
    renderActiveView();
  }

  async function renderActiveView() {
    if (!state.user) return;
    switch (state.activeView) {
      case "relatorio":
        await renderRelatorioView();
        break;
      case "eventos":
        await renderEventosView();
        break;
      case "minhas-inscricoes":
        await renderMinhasInscricoesView();
        break;
      case "inscritos":
        await renderInscritosView();
        break;
      case "meus-certificados":
        await renderCertificadosView(false);
        break;
      case "certificados":
        await renderCertificadosView(true);
        break;
      case "usuarios":
        await renderUsuariosView();
        break;
      case "notificacoes":
        await renderNotificacoesView();
        break;
      default:
        await renderEventosView();
    }
  }

  // -------------------- VISÃO: RELATÓRIO GERAL (ADMIN) --------------------

  async function renderRelatorioView() {
    renderLoading("Consolidando métricas dos serviços SOA e microsserviços...");
    try {
      const data = await apiRequest("/relatorios/geral");
      const rel = data.relatorio || {};
      const usuarios = rel.usuarios || {};
      const eventos = rel.eventos || {};
      const inscricoes = rel.inscricoes || {};
      const certificados = rel.certificados || {};
      const notificacoes = rel.notificacoes || {};

      const cards = el("div", { className: "metrics-grid" }, [
        makeMetricBox("Usuários cadastrados", usuarios.total_usuarios ?? 0, formatBreakdown(usuarios.por_perfil)),
        makeMetricBox("Eventos", eventos.total_eventos ?? 0, formatBreakdown(eventos.por_status)),
        makeMetricBox(
          "Inscrições",
          inscricoes.total_inscricoes ?? 0,
          `${inscricoes.presencas_confirmadas ?? 0} presença(s) confirmada(s)`
        ),
        makeMetricBox("Certificados emitidos", certificados.total_certificados ?? 0, "Emitidos em ms-certificados"),
        makeMetricBox("Notificações enviadas", notificacoes.total_notificacoes ?? 0, formatBreakdown(notificacoes.por_canal)),
      ]);

      const corrPanel = el("div", { className: "panel" }, [
        el("h2", { style: "margin: 0 0 8px; font-size: 16px;" }, "Rastreabilidade da agregação"),
        el(
          "p",
          { className: "muted", style: "margin-bottom: 10px;" },
          "O endpoint GET /relatorios/geral é orquestrado pelo SOA Orquestrador consultando os 5 bancos isolados."
        ),
        el("div", { className: "mono" }, `X-Correlation-ID: ${data.correlation_id || "-"}`),
      ]);

      const breakdownPanel = el("div", { className: "panel" }, [
        el("h2", { style: "margin: 0 0 12px; font-size: 16px;" }, "Distribuição por serviço"),
        el("div", { className: "table-wrap" }, [
          el("table", {}, [
            el("thead", {}, el("tr", {}, [
              el("th", {}, "Domínio"),
              el("th", {}, "Detalhamento"),
            ])),
            el("tbody", {}, [
              el("tr", {}, [
                el("td", {}, "SOA Identidade"),
                el("td", {}, formatBreakdown(usuarios.por_perfil) || "Sem dados"),
              ]),
              el("tr", {}, [
                el("td", {}, "ms-eventos (tipos)"),
                el("td", {}, formatBreakdown(eventos.por_tipo) || "Sem dados"),
              ]),
              el("tr", {}, [
                el("td", {}, "ms-eventos (status)"),
                el("td", {}, formatBreakdown(eventos.por_status) || "Sem dados"),
              ]),
              el("tr", {}, [
                el("td", {}, "ms-inscricoes"),
                el("td", {}, formatBreakdown(inscricoes.por_status) || "Sem dados"),
              ]),
              el("tr", {}, [
                el("td", {}, "SOA Notificação"),
                el("td", {}, formatBreakdown(notificacoes.por_canal) || "Sem dados"),
              ]),
            ]),
          ]),
        ]),
      ]);

      dom.mainContent.replaceChildren(
        createViewHeader("Relatório geral", "Visão consolidada do ecossistema EventHub."),
        cards,
        breakdownPanel,
        corrPanel
      );
    } catch (err) {
      renderErrorState(err, renderRelatorioView);
    }
  }

  function makeMetricBox(label, value, detail) {
    return el("div", { className: "metric-box" }, [
      el("div", { className: "metric-label" }, label),
      el("div", { className: "metric-value" }, String(value)),
      el("div", { className: "metric-detail" }, detail || "-"),
    ]);
  }

  function formatBreakdown(obj) {
    if (!obj || typeof obj !== "object") return "-";
    const entries = Object.entries(obj);
    if (!entries.length) return "Nenhum registro";
    return entries.map(([k, v]) => `${k}: ${v}`).join(" · ");
  }

  // -------------------- VISÃO: EVENTOS --------------------

  async function renderEventosView() {
    renderLoading("Carregando eventos...");
    const role = state.user.role;
    const isParticipante = role === "participante";
    const canCreate = role === "organizador" || role === "admin";

    try {
      const promises = [apiRequest("/eventos")];
      if (isParticipante) {
        promises.push(apiRequest("/inscricoes/minhas"));
      }
      const [evtData, insData] = await Promise.all(promises);
      const eventos = evtData.eventos || [];
      const activeInscricoesByEvento = new Set(
        (insData?.inscricoes || [])
          .filter((ins) => ins.status === "ATIVA")
          .map((ins) => ins.evento_id)
      );

      const headerBtn = canCreate
        ? el(
            "button",
            {
              type: "button",
              className: "btn btn-primary",
              onClick: () => openEventModal(null),
            },
            "Novo evento"
          )
        : null;

      const header = createViewHeader(
        role === "admin" ? "Eventos e aprovações" : "Eventos",
        isParticipante
          ? "Consulte eventos aprovados e faça sua inscrição com confirmação automática."
          : "Gerencie eventos acadêmicos, prazos, vagas e aprovações.",
        headerBtn
      );

      const searchInput = el("input", {
        type: "search",
        placeholder: "Buscar por título ou local...",
        value: state.filters.eventQuery,
        "aria-label": "Buscar eventos",
      });

      const typeSelect = el("select", { "aria-label": "Filtrar por tipo" }, [
        el("option", { value: "TODOS" }, "Todos os tipos"),
        el("option", { value: "SEMANA_ACADEMICA" }, "Semana Acadêmica"),
        el("option", { value: "PALESTRA" }, "Palestra"),
        el("option", { value: "MINICURSO" }, "Minicurso"),
      ]);
      typeSelect.value = state.filters.eventType;

      const statusSelect = el("select", { "aria-label": "Filtrar por status" }, [
        el("option", { value: "TODOS" }, "Todos os status"),
        el("option", { value: "APROVADO" }, "Aprovados"),
        el("option", { value: "PENDENTE" }, "Pendentes"),
        el("option", { value: "REJEITADO" }, "Rejeitados"),
      ]);
      statusSelect.value = state.filters.eventStatus;

      const toolbarChildren = [searchInput, typeSelect];
      if (!isParticipante) toolbarChildren.push(statusSelect);
      const toolbar = el("div", { className: "toolbar" }, toolbarChildren);

      const tableHost = el("div");

      const redrawTable = () => {
        const query = state.filters.eventQuery.trim().toLowerCase();
        const filtered = eventos.filter((ev) => {
          if (state.filters.eventType !== "TODOS" && ev.tipo !== state.filters.eventType) return false;
          if (!isParticipante && state.filters.eventStatus !== "TODOS" && ev.status !== state.filters.eventStatus) {
            return false;
          }
          if (!query) return true;
          return (
            (ev.titulo || "").toLowerCase().includes(query) ||
            (ev.local || "").toLowerCase().includes(query) ||
            (ev.organizador_nome || "").toLowerCase().includes(query)
          );
        });

        if (!filtered.length) {
          tableHost.replaceChildren(
            el("div", { className: "empty-state" }, "Nenhum evento encontrado com os filtros atuais.")
          );
          return;
        }

        const rows = filtered.map((ev) => {
          const actions = [];
          const isOwner = ev.organizador_id === state.user.id;

          if (role === "participante" && ev.status === "APROVADO") {
            const alreadyIn = activeInscricoesByEvento.has(ev.id);
            actions.push(
              el(
                "button",
                {
                  type: "button",
                  className: `btn btn-sm ${alreadyIn ? "btn-secondary" : "btn-primary"}`,
                  disabled: alreadyIn,
                  onClick: (e) => handleSubscribe(ev, e.currentTarget),
                },
                alreadyIn ? "Inscrito" : "Inscrever-se"
              )
            );
          }

          if (role === "organizador" || role === "admin") {
            if (role === "admin" || isOwner) {
              actions.push(
                el(
                  "button",
                  {
                    type: "button",
                    className: "btn btn-secondary btn-sm",
                    onClick: () => openEventModal(ev),
                  },
                  "Editar"
                )
              );
            }
            actions.push(
              el(
                "button",
                {
                  type: "button",
                  className: "btn btn-secondary btn-sm",
                  onClick: () => {
                    state.selectedEventoId = ev.id;
                    state.activeView = "inscritos";
                    renderSidebar();
                    renderActiveView();
                  },
                },
                "Inscritos"
              )
            );
          }

          if (role === "admin") {
            if (ev.status !== "APROVADO") {
              actions.push(
                el(
                  "button",
                  {
                    type: "button",
                    className: "btn btn-success btn-sm",
                    onClick: (e) => handleApproveEvent(ev.id, "APROVADO", e.currentTarget),
                  },
                  "Aprovar"
                )
              );
            }
            if (ev.status !== "REJEITADO") {
              actions.push(
                el(
                  "button",
                  {
                    type: "button",
                    className: "btn btn-danger btn-sm",
                    onClick: (e) => handleApproveEvent(ev.id, "REJEITADO", e.currentTarget),
                  },
                  "Rejeitar"
                )
              );
            }
          }

          return el("tr", {}, [
            el("td", {}, [
              el("strong", {}, ev.titulo),
              el("div", { className: "muted", style: "margin: 2px 0 0; font-size: 13px;" }, ev.descricao),
            ]),
            el("td", {}, EVENT_TYPE_LABELS[ev.tipo] || ev.tipo),
            el("td", {}, [
              el("div", {}, formatDateTime(ev.data_evento)),
              el("div", { className: "muted", style: "margin: 2px 0 0; font-size: 12px;" }, ev.local),
            ]),
            el("td", {}, `${ev.capacidade} vagas · ${ev.carga_horaria}h`),
            el("td", {}, ev.organizador_nome || "-"),
            el("td", {}, statusBadge(ev.status)),
            el("td", {}, el("div", { className: "actions-cell" }, actions)),
          ]);
        });

        tableHost.replaceChildren(
          el("div", { className: "table-wrap" }, [
            el("table", {}, [
              el(
                "thead",
                {},
                el("tr", {}, [
                  el("th", {}, "Evento"),
                  el("th", {}, "Tipo"),
                  el("th", {}, "Data e local"),
                  el("th", {}, "Capacidade / CH"),
                  el("th", {}, "Organizador"),
                  el("th", {}, "Status"),
                  el("th", {}, "Ações"),
                ])
              ),
              el("tbody", {}, rows),
            ]),
          ])
        );
      };

      searchInput.addEventListener("input", () => {
        state.filters.eventQuery = searchInput.value;
        redrawTable();
      });
      typeSelect.addEventListener("change", () => {
        state.filters.eventType = typeSelect.value;
        redrawTable();
      });
      statusSelect.addEventListener("change", () => {
        state.filters.eventStatus = statusSelect.value;
        redrawTable();
      });

      redrawTable();
      dom.mainContent.replaceChildren(header, toolbar, tableHost);
    } catch (err) {
      renderErrorState(err, renderEventosView);
    }
  }

  async function handleSubscribe(evento, btn) {
    btn.disabled = true;
    const prev = btn.textContent;
    btn.textContent = "Inscrevendo...";
    try {
      const resp = await apiRequest("/inscricoes", {
        method: "POST",
        body: { evento_id: evento.id },
      });
      const protocolo = resp.notificacao?.protocolo ? ` (Protocolo ${resp.notificacao.protocolo})` : "";
      showToast(`Inscrição confirmada em "${evento.titulo}"${protocolo}.`, "success");
      await renderEventosView();
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
      btn.textContent = prev;
    }
  }

  async function handleApproveEvent(eventoId, status, btn) {
    btn.disabled = true;
    try {
      await apiRequest(`/eventos/${eventoId}/aprovar`, {
        method: "PATCH",
        body: { status },
      });
      showToast(`Evento atualizado para ${status}.`, "success");
      await renderEventosView();
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
    }
  }

  function openEventModal(existing) {
    const isEdit = Boolean(existing);
    const errorBox = el("div", { className: "form-error hidden" });

    const tituloInput = el("input", { type: "text", required: true, value: existing?.titulo || "" });
    const descInput = el("textarea", { required: true }, existing?.descricao || "");
    const tipoSelect = el("select", { required: true }, [
      el("option", { value: "PALESTRA" }, "Palestra"),
      el("option", { value: "MINICURSO" }, "Minicurso"),
      el("option", { value: "SEMANA_ACADEMICA" }, "Semana Acadêmica"),
    ]);
    tipoSelect.value = existing?.tipo || "PALESTRA";

    const dataInput = el("input", {
      type: "datetime-local",
      required: true,
      value: formatDateInput(existing?.data_evento) || "2026-11-25T19:00",
    });
    const localInput = el("input", { type: "text", required: true, value: existing?.local || "" });
    const capInput = el("input", {
      type: "number",
      min: "1",
      required: true,
      value: String(existing?.capacidade ?? 40),
    });
    const chInput = el("input", {
      type: "number",
      min: "1",
      required: true,
      value: String(existing?.carga_horaria ?? 4),
    });

    const submitBtn = el(
      "button",
      { type: "submit", className: "btn btn-primary" },
      isEdit ? "Salvar alterações" : "Criar evento"
    );

    const form = el("form", { className: "stack-form" }, [
      el("div", { className: "field" }, [el("label", {}, "Título"), tituloInput]),
      el("div", { className: "field" }, [el("label", {}, "Descrição"), descInput]),
      el("div", { className: "field-grid" }, [
        el("div", { className: "field" }, [el("label", {}, "Tipo"), tipoSelect]),
        el("div", { className: "field" }, [el("label", {}, "Data e hora"), dataInput]),
      ]),
      el("div", { className: "field" }, [el("label", {}, "Local"), localInput]),
      el("div", { className: "field-grid" }, [
        el("div", { className: "field" }, [el("label", {}, "Capacidade (vagas)"), capInput]),
        el("div", { className: "field" }, [el("label", {}, "Carga horária (horas)"), chInput]),
      ]),
      errorBox,
      el("div", { className: "actions-cell", style: "justify-content: flex-end;" }, [
        el("button", { type: "button", className: "btn btn-secondary", onClick: closeModal }, "Cancelar"),
        submitBtn,
      ]),
    ]);

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      setInlineError(errorBox, "");
      submitBtn.disabled = true;

      const rawDate = dataInput.value;
      const isoDate = rawDate.length === 16 ? `${rawDate}:00` : rawDate;

      const payload = {
        titulo: tituloInput.value.trim(),
        descricao: descInput.value.trim(),
        tipo: tipoSelect.value,
        data_evento: isoDate,
        local: localInput.value.trim(),
        capacidade: Number(capInput.value),
        carga_horaria: Number(chInput.value),
      };

      try {
        if (isEdit) {
          await apiRequest(`/eventos/${existing.id}`, { method: "PUT", body: payload });
          showToast("Evento atualizado com sucesso.", "success");
        } else {
          await apiRequest("/eventos", { method: "POST", body: payload });
          showToast("Evento criado com status PENDENTE.", "success");
        }
        closeModal();
        await renderEventosView();
      } catch (err) {
        setInlineError(errorBox, err.message);
        submitBtn.disabled = false;
      }
    });

    openModal(isEdit ? `Editar evento #${existing.id}` : "Criar novo evento", form);
  }

  // -------------------- VISÃO: MINHAS INSCRIÇÕES (PARTICIPANTE) --------------------

  async function renderMinhasInscricoesView() {
    renderLoading("Carregando suas inscrições e certificados...");
    try {
      const [insData, evtData, certData] = await Promise.all([
        apiRequest("/inscricoes/minhas"),
        apiRequest("/eventos"),
        apiRequest("/certificados/meus"),
      ]);

      const inscricoes = insData.inscricoes || [];
      const eventsMap = new Map((evtData.eventos || []).map((ev) => [ev.id, ev]));
      const certsByInscricao = new Map((certData.certificados || []).map((c) => [c.inscricao_id, c]));

      const header = createViewHeader(
        "Minhas inscrições",
        "Acompanhe presença confirmada, cancele inscrições ou emita certificados."
      );

      if (!inscricoes.length) {
        dom.mainContent.replaceChildren(
          header,
          el("div", { className: "empty-state" }, "Você ainda não possui inscrições em eventos.")
        );
        return;
      }

      const rows = inscricoes.map((ins) => {
        const ev = eventsMap.get(ins.evento_id);
        const cert = certsByInscricao.get(ins.id);
        const actions = [];

        if (ins.status === "ATIVA" && ins.presenca && !cert) {
          actions.push(
            el(
              "button",
              {
                type: "button",
                className: "btn btn-primary btn-sm",
                onClick: (e) => handleIssueCertificate(ins.id, e.currentTarget),
              },
              "Emitir certificado"
            )
          );
        }

        if (cert) {
          actions.push(
            el(
              "button",
              {
                type: "button",
                className: "btn btn-secondary btn-sm",
                onClick: () => {
                  state.activeView = "meus-certificados";
                  renderSidebar();
                  renderActiveView();
                },
              },
              "Ver certificado"
            )
          );
        }

        if (ins.status === "ATIVA" && !ins.presenca) {
          actions.push(
            el(
              "button",
              {
                type: "button",
                className: "btn btn-danger btn-sm",
                onClick: (e) => handleCancelRegistration(ins.id, e.currentTarget),
              },
              "Cancelar"
            )
          );
        }

        return el("tr", {}, [
          el("td", {}, [
            el("strong", {}, ev ? ev.titulo : `Evento #${ins.evento_id}`),
            ev
              ? el("div", { className: "muted", style: "margin: 2px 0 0; font-size: 12px;" }, `${formatDateTime(ev.data_evento)} · ${ev.local}`)
              : null,
          ]),
          el("td", {}, statusBadge(ins.status)),
          el("td", {}, ins.presenca ? makeBadge("Presente", "ok") : makeBadge("Aguardando", "warn")),
          el("td", {}, formatDateTime(ins.criado_em)),
          el("td", {}, el("div", { className: "actions-cell" }, actions.length ? actions : [el("span", { className: "muted" }, "-")])),
        ]);
      });

      dom.mainContent.replaceChildren(
        header,
        el("div", { className: "table-wrap" }, [
          el("table", {}, [
            el(
              "thead",
              {},
              el("tr", {}, [
                el("th", {}, "Evento"),
                el("th", {}, "Inscrição"),
                el("th", {}, "Presença"),
                el("th", {}, "Data da inscrição"),
                el("th", {}, "Ações"),
              ])
            ),
            el("tbody", {}, rows),
          ]),
        ])
      );
    } catch (err) {
      renderErrorState(err, renderMinhasInscricoesView);
    }
  }

  async function handleCancelRegistration(inscricaoId, btn) {
    btn.disabled = true;
    btn.textContent = "Cancelando...";
    try {
      await apiRequest(`/inscricoes/${inscricaoId}/cancelar`, { method: "PATCH" });
      showToast("Inscrição cancelada e notificação registrada.", "success");
      await renderMinhasInscricoesView();
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
      btn.textContent = "Cancelar";
    }
  }

  async function handleIssueCertificate(inscricaoId, btn) {
    btn.disabled = true;
    btn.textContent = "Emitindo...";
    try {
      const data = await apiRequest("/certificados/emitir", {
        method: "POST",
        body: { inscricao_id: inscricaoId },
      });
      const codigo = data.certificado?.codigo_verificacao || "";
      showToast(`Certificado emitido (${codigo}).`, "success");
      await renderMinhasInscricoesView();
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
      btn.textContent = "Emitir certificado";
    }
  }

  // -------------------- VISÃO: INSCRITOS E PRESENÇA (ORG / ADMIN) --------------------

  async function renderInscritosView() {
    renderLoading("Carregando eventos para controle de presença...");
    try {
      const evtData = await apiRequest("/eventos");
      const eventos = evtData.eventos || [];

      const header = createViewHeader(
        "Inscritos e presença",
        "Selecione um evento para consultar inscritos e registrar presença."
      );

      if (!eventos.length) {
        dom.mainContent.replaceChildren(
          header,
          el("div", { className: "empty-state" }, "Nenhum evento cadastrado para exibir inscritos.")
        );
        return;
      }

      if (!state.selectedEventoId || !eventos.some((e) => e.id === state.selectedEventoId)) {
        state.selectedEventoId = eventos[0].id;
      }

      const select = el(
        "select",
        { "aria-label": "Selecionar evento" },
        eventos.map((ev) =>
          el("option", { value: String(ev.id) }, `#${ev.id} · ${ev.titulo} (${ev.status})`)
        )
      );
      select.value = String(state.selectedEventoId);

      const listHost = el("div");

      const loadAttendees = async (eventoId) => {
        listHost.replaceChildren(el("div", { className: "panel" }, el("p", { className: "muted" }, "Carregando inscritos...")));
        try {
          const data = await apiRequest(`/eventos/${eventoId}/inscritos`);
          const inscritos = data.inscritos || [];
          const ativos = inscritos.filter((i) => i.status === "ATIVA").length;
          const presentes = inscritos.filter((i) => i.status === "ATIVA" && i.presenca).length;

          const summary = el("div", { className: "metrics-grid" }, [
            makeMetricBox("Total de registros", inscritos.length, "Inscrições no evento"),
            makeMetricBox("Inscrições ativas", ativos, "Ocupando vaga"),
            makeMetricBox("Presenças confirmadas", presentes, "Aptos para certificado"),
          ]);

          if (!inscritos.length) {
            listHost.replaceChildren(
              summary,
              el("div", { className: "empty-state" }, "Ainda não há inscritos neste evento.")
            );
            return;
          }

          const rows = inscritos.map((ins) => {
            const canToggle = ins.status === "ATIVA";
            const actionBtn = canToggle
              ? el(
                  "button",
                  {
                    type: "button",
                    className: `btn btn-sm ${ins.presenca ? "btn-secondary" : "btn-primary"}`,
                    onClick: async (e) => {
                      const button = e.currentTarget;
                      button.disabled = true;
                      try {
                        await apiRequest(`/inscricoes/${ins.id}/presenca`, {
                          method: "PATCH",
                          body: { presenca: !ins.presenca },
                        });
                        showToast(
                          !ins.presenca
                            ? `Presença confirmada para ${ins.participante_nome}.`
                            : `Presença removida para ${ins.participante_nome}.`,
                          "success"
                        );
                        await loadAttendees(eventoId);
                      } catch (err) {
                        showToast(err.message, "error");
                        button.disabled = false;
                      }
                    },
                  },
                  ins.presenca ? "Desmarcar presença" : "Confirmar presença"
                )
              : el("span", { className: "muted" }, "Cancelada");

            return el("tr", {}, [
              el("td", {}, [
                el("strong", {}, ins.participante_nome),
                el("div", { className: "muted", style: "margin: 2px 0 0; font-size: 12px;" }, ins.participante_email),
              ]),
              el("td", {}, statusBadge(ins.status)),
              el("td", {}, ins.presenca ? makeBadge("Presente", "ok") : makeBadge("Ausente", "warn")),
              el("td", {}, formatDateTime(ins.criado_em)),
              el("td", {}, actionBtn),
            ]);
          });

          listHost.replaceChildren(
            summary,
            el("div", { className: "table-wrap" }, [
              el("table", {}, [
                el(
                  "thead",
                  {},
                  el("tr", {}, [
                    el("th", {}, "Participante"),
                    el("th", {}, "Status"),
                    el("th", {}, "Presença"),
                    el("th", {}, "Inscrito em"),
                    el("th", {}, "Ação"),
                  ])
                ),
                el("tbody", {}, rows),
              ]),
            ])
          );
        } catch (err) {
          listHost.replaceChildren(el("div", { className: "form-error" }, err.message));
        }
      };

      select.addEventListener("change", () => {
        state.selectedEventoId = Number(select.value);
        loadAttendees(state.selectedEventoId);
      });

      const toolbar = el("div", { className: "toolbar" }, [select]);
      dom.mainContent.replaceChildren(header, toolbar, listHost);
      await loadAttendees(state.selectedEventoId);
    } catch (err) {
      renderErrorState(err, renderInscritosView);
    }
  }

  // -------------------- VISÃO: CERTIFICADOS --------------------

  async function renderCertificadosView(isAdminAll) {
    renderLoading("Carregando certificados...");
    try {
      const endpoint = isAdminAll ? "/certificados" : "/certificados/meus";
      const data = await apiRequest(endpoint);
      const certificados = data.certificados || [];

      const header = createViewHeader(
        isAdminAll ? "Certificados emitidos" : "Meus certificados",
        isAdminAll
          ? "Registro completo dos certificados gerados pelo microsserviço ms-certificados."
          : "Certificados digitais emitidos após confirmação de presença."
      );

      if (!certificados.length) {
        dom.mainContent.replaceChildren(
          header,
          el(
            "div",
            { className: "empty-state" },
            isAdminAll
              ? "Nenhum certificado emitido até o momento."
              : "Você ainda não possui certificados emitidos. Confirme presença em um evento e emita na aba Minhas inscrições."
          )
        );
        return;
      }

      const searchInput = el("input", {
        type: "search",
        placeholder: "Filtrar por código, participante ou evento...",
        value: state.filters.certQuery,
        "aria-label": "Filtrar certificados",
      });
      const tableHost = el("div");

      const redraw = () => {
        const q = state.filters.certQuery.trim().toLowerCase();
        const filtered = certificados.filter((c) => {
          if (!q) return true;
          return (
            (c.codigo_verificacao || "").toLowerCase().includes(q) ||
            (c.evento_titulo || "").toLowerCase().includes(q) ||
            (c.participante_nome || "").toLowerCase().includes(q)
          );
        });

        if (!filtered.length) {
          tableHost.replaceChildren(el("div", { className: "empty-state" }, "Nenhum certificado corresponde ao filtro."));
          return;
        }

        const rows = filtered.map((c) =>
          el("tr", {}, [
            el("td", {}, el("span", { className: "mono" }, c.codigo_verificacao)),
            el("td", {}, [
              el("strong", {}, c.evento_titulo),
              el("div", { className: "muted", style: "margin: 2px 0 0; font-size: 12px;" }, `${EVENT_TYPE_LABELS[c.tipo_evento] || c.tipo_evento} · ${c.carga_horaria}h`),
            ]),
            el("td", {}, [
              el("div", {}, c.participante_nome),
              el("div", { className: "muted", style: "margin: 2px 0 0; font-size: 12px;" }, c.participante_email),
            ]),
            el("td", {}, formatDateTime(c.emitido_em)),
            el(
              "td",
              {},
              el(
                "div",
                { className: "actions-cell" },
                [
                  el(
                    "button",
                    {
                      type: "button",
                      className: "btn btn-secondary btn-sm",
                      onClick: () => verifyCertificateModal(c.codigo_verificacao),
                    },
                    "Validar código"
                  ),
                ]
              )
            ),
          ])
        );

        tableHost.replaceChildren(
          el("div", { className: "table-wrap" }, [
            el("table", {}, [
              el(
                "thead",
                {},
                el("tr", {}, [
                  el("th", {}, "Código verificador"),
                  el("th", {}, "Evento / Carga"),
                  el("th", {}, "Participante"),
                  el("th", {}, "Emitido em"),
                  el("th", {}, "Ações"),
                ])
              ),
              el("tbody", {}, rows),
            ]),
          ])
        );
      };

      searchInput.addEventListener("input", () => {
        state.filters.certQuery = searchInput.value;
        redraw();
      });

      redraw();
      dom.mainContent.replaceChildren(header, el("div", { className: "toolbar" }, [searchInput]), tableHost);
    } catch (err) {
      renderErrorState(err, () => renderCertificadosView(isAdminAll));
    }
  }

  async function verifyCertificateModal(code) {
    try {
      const data = await apiRequest(`/certificados/validar/${encodeURIComponent(code)}`, { auth: false });
      const c = data.certificado;
      const box = el("div", { className: "stack-form" }, [
        el("div", { className: "validate-result valid" }, [
          el("strong", {}, "Autenticidade confirmada via GET /certificados/validar"),
          el("div", { style: "margin-top: 8px;" }, [
            el("div", {}, `Titular: ${c.participante_nome} (${c.participante_email})`),
            el("div", {}, `Evento: ${c.evento_titulo}`),
            el("div", {}, `Tipo: ${EVENT_TYPE_LABELS[c.tipo_evento] || c.tipo_evento} · ${c.carga_horaria}h`),
            el("div", {}, `Emissão: ${formatDateTime(c.emitido_em)}`),
            el("div", { className: "mono", style: "margin-top: 6px;" }, c.codigo_verificacao),
          ]),
        ]),
        el("div", { className: "actions-cell", style: "justify-content: flex-end;" }, [
          el("button", { type: "button", className: "btn btn-primary", onClick: closeModal }, "Fechar"),
        ]),
      ]);
      openModal("Validação de certificado", box);
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  // -------------------- VISÃO: USUÁRIOS E PERFIS (ADMIN) --------------------

  async function renderUsuariosView() {
    renderLoading("Carregando usuários...");
    try {
      const data = await apiRequest("/usuarios");
      const usuarios = data.usuarios || [];

      const header = createViewHeader(
        "Usuários e perfis (RBAC)",
        "Crie contas administrativas/organizadoras, altere papéis ou desative acessos.",
        el(
          "button",
          {
            type: "button",
            className: "btn btn-primary",
            onClick: openNewUserModal,
          },
          "Novo usuário"
        )
      );

      const rows = usuarios.map((u) => {
        const isSelf = u.id === state.user.id;
        const roleSelect = el(
          "select",
          { "aria-label": `Papel de ${u.nome}`, disabled: isSelf },
          [
            el("option", { value: "participante" }, "Participante"),
            el("option", { value: "organizador" }, "Organizador"),
            el("option", { value: "admin" }, "Admin"),
          ]
        );
        roleSelect.value = u.role;

        roleSelect.addEventListener("change", async () => {
          roleSelect.disabled = true;
          try {
            await apiRequest(`/usuarios/${u.id}/perfil`, {
              method: "PATCH",
              body: { role: roleSelect.value },
            });
            showToast(`Perfil de ${u.nome} atualizado para ${roleSelect.value}.`, "success");
            await renderUsuariosView();
          } catch (err) {
            showToast(err.message, "error");
            roleSelect.value = u.role;
            roleSelect.disabled = isSelf;
          }
        });

        const toggleBtn = el(
          "button",
          {
            type: "button",
            className: `btn btn-sm ${u.ativo ? "btn-danger" : "btn-success"}`,
            disabled: isSelf,
            onClick: async (e) => {
              const btn = e.currentTarget;
              btn.disabled = true;
              try {
                await apiRequest(`/usuarios/${u.id}/perfil`, {
                  method: "PATCH",
                  body: { ativo: !u.ativo },
                });
                showToast(
                  u.ativo ? `Usuário ${u.nome} desativado.` : `Usuário ${u.nome} reativado.`,
                  "success"
                );
                await renderUsuariosView();
              } catch (err) {
                showToast(err.message, "error");
                btn.disabled = false;
              }
            },
          },
          u.ativo ? "Desativar" : "Reativar"
        );

        return el("tr", {}, [
          el("td", {}, [
            el("strong", {}, u.nome),
            isSelf ? el("span", { className: "muted", style: "margin-left: 6px; font-size: 12px;" }, "(você)") : null,
            el("div", { className: "muted", style: "margin: 2px 0 0; font-size: 12px;" }, u.email),
          ]),
          el("td", {}, roleSelect),
          el("td", {}, u.ativo ? makeBadge("Ativo", "ok") : makeBadge("Inativo", "bad")),
          el("td", {}, formatDateTime(u.criado_em)),
          el("td", {}, toggleBtn),
        ]);
      });

      dom.mainContent.replaceChildren(
        header,
        el("div", { className: "table-wrap" }, [
          el("table", {}, [
            el(
              "thead",
              {},
              el("tr", {}, [
                el("th", {}, "Usuário"),
                el("th", {}, "Papel (RBAC)"),
                el("th", {}, "Situação"),
                el("th", {}, "Criado em"),
                el("th", {}, "Ação"),
              ])
            ),
            el("tbody", {}, rows),
          ]),
        ])
      );
    } catch (err) {
      renderErrorState(err, renderUsuariosView);
    }
  }

  function openNewUserModal() {
    const errorBox = el("div", { className: "form-error hidden" });
    const nomeInput = el("input", { type: "text", required: true });
    const emailInput = el("input", { type: "email", required: true });
    const senhaInput = el("input", { type: "password", minlength: "6", required: true });
    const roleSelect = el("select", { required: true }, [
      el("option", { value: "participante" }, "Participante"),
      el("option", { value: "organizador" }, "Organizador"),
      el("option", { value: "admin" }, "Admin"),
    ]);

    const submitBtn = el("button", { type: "submit", className: "btn btn-primary" }, "Criar usuário");

    const form = el("form", { className: "stack-form" }, [
      el("div", { className: "field" }, [el("label", {}, "Nome completo"), nomeInput]),
      el("div", { className: "field" }, [el("label", {}, "E-mail institucional"), emailInput]),
      el("div", { className: "field-grid" }, [
        el("div", { className: "field" }, [el("label", {}, "Senha"), senhaInput]),
        el("div", { className: "field" }, [el("label", {}, "Papel"), roleSelect]),
      ]),
      errorBox,
      el("div", { className: "actions-cell", style: "justify-content: flex-end;" }, [
        el("button", { type: "button", className: "btn btn-secondary", onClick: closeModal }, "Cancelar"),
        submitBtn,
      ]),
    ]);

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      setInlineError(errorBox, "");
      submitBtn.disabled = true;

      try {
        await apiRequest("/usuarios", {
          method: "POST",
          body: {
            nome: nomeInput.value.trim(),
            email: emailInput.value.trim(),
            senha: senhaInput.value,
            role: roleSelect.value,
          },
        });
        showToast("Usuário cadastrado com sucesso.", "success");
        closeModal();
        await renderUsuariosView();
      } catch (err) {
        setInlineError(errorBox, err.message);
        submitBtn.disabled = false;
      }
    });

    openModal("Novo usuário", form);
  }

  // -------------------- VISÃO: NOTIFICAÇÕES --------------------

  async function renderNotificacoesView() {
    renderLoading("Carregando notificações...");
    try {
      const data = await apiRequest("/notificacoes");
      const notificacoes = data.notificacoes || [];

      const header = createViewHeader(
        "Notificações",
        state.user.role === "admin"
          ? "Log corporativo de notificações disparadas pelo SOA Notificação."
          : "Comunicações enviadas para o seu e-mail institucional."
      );

      if (!notificacoes.length) {
        dom.mainContent.replaceChildren(
          header,
          el("div", { className: "empty-state" }, "Nenhuma notificação registrada até o momento.")
        );
        return;
      }

      const rows = notificacoes.map((n) =>
        el("tr", {}, [
          el("td", {}, el("span", { className: "mono" }, n.protocolo)),
          el("td", {}, [
            el("strong", {}, n.assunto),
            el("div", { className: "muted", style: "margin: 2px 0 0; font-size: 13px;" }, n.mensagem),
          ]),
          el("td", {}, [
            el("div", {}, n.destinatario_nome),
            el("div", { className: "muted", style: "margin: 2px 0 0; font-size: 12px;" }, n.destinatario_email),
          ]),
          el("td", {}, makeBadge(n.canal, "info")),
          el("td", {}, statusBadge(n.status)),
          el("td", {}, formatDateTime(n.enviado_em)),
        ])
      );

      dom.mainContent.replaceChildren(
        header,
        el("div", { className: "table-wrap" }, [
          el("table", {}, [
            el(
              "thead",
              {},
              el("tr", {}, [
                el("th", {}, "Protocolo"),
                el("th", {}, "Assunto / Mensagem"),
                el("th", {}, "Destinatário"),
                el("th", {}, "Canal"),
                el("th", {}, "Status"),
                el("th", {}, "Enviado em"),
              ])
            ),
            el("tbody", {}, rows),
          ]),
        ])
      );
    } catch (err) {
      renderErrorState(err, renderNotificacoesView);
    }
  }

  async function bootstrap() {
    setupAuthEvents();

    if (state.token) {
      try {
        const data = await apiRequest("/auth/validate");
        if (data.valido && data.usuario) {
          saveSession(state.token, data.usuario);
          enterAuthenticatedApp();
          return;
        }
      } catch {
        clearSession();
      }
    }

    renderShell();
  }

  bootstrap();
})();
