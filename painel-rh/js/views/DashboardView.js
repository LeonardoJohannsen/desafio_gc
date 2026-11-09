import { escapeHtml } from "../utils/dom.js";

const STATUS_CLASS = {
  "open-alert": "status-warning",
  "no-response": "status-danger",
  attended: "status-dark",
  "on-track": "",
  pending: "status-muted",
  paused: "status-muted",
};

const METRICS = [
  { key: "inJourney", label: "Na jornada", accent: "var(--text)" },
  { key: "openAlerts", label: "Alertas abertos", accent: "var(--yellow)" },
  { key: "noResponse", label: "Sem resposta há 24h", accent: "var(--red)", valueColor: "var(--red)" },
  { key: "attended", label: "Atendidos", accent: "var(--text)" },
];

export class DashboardView {
  renderStoreOptions(stores) {
    const select = document.querySelector("#store-filter");
    const previousValue = select.value;
    select.innerHTML = '<option value="all">Todas</option>' + stores.map((store) =>
      `<option value="${escapeHtml(store)}">${escapeHtml(store)}</option>`).join("");
    select.value = stores.includes(previousValue) ? previousValue : "all";
  }

  renderMetrics(summary) {
    document.querySelector("#metric-grid").innerHTML = METRICS.map((metric) => `
      <article class="metric-card" style="--metric-accent:${metric.accent};${metric.valueColor ? `--metric-value-color:${metric.valueColor};` : ""}">
        <div class="metric-label">${metric.label}</div>
        <div class="metric-value">${Number(summary[metric.key] ?? 0).toLocaleString("pt-BR")}</div>
      </article>`).join("");
    document.querySelector("#sidebar-alert-count").textContent = summary.openAlerts;
  }

  renderJourneys(elementId, emptyId, journeys) {
    const tbody = document.getElementById(elementId);
    tbody.innerHTML = journeys.map((journey) => `
      <tr>
        <td><span class="employee-name">${escapeHtml(journey.employeeName)}</span></td>
        <td><span class="store-name">${escapeHtml(journey.store)}</span></td>
        <td class="progress-cell"><div class="progress-wrap" aria-label="${journey.progress}% concluído">
          <div class="progress-track" role="progressbar" aria-valuenow="${journey.progress}" aria-valuemin="0" aria-valuemax="100" aria-label="Progresso da jornada"><span class="progress-fill" style="width:${journey.progress}%"></span></div>
          <span class="progress-number">${journey.progress}%</span>
        </div></td>
        <td><span class="day-label">Dia ${journey.day}</span></td>
        <td><span class="store-name">${escapeHtml(journey.mentor ?? "—")}</span></td>
        <td><span class="status-pill ${STATUS_CLASS[journey.status] ?? ""}">${escapeHtml(journey.statusLabel)}</span></td>
      </tr>`).join("");
    document.getElementById(emptyId).classList.toggle("hidden", journeys.length > 0);
  }

  setJourneyCount(elementId, journeys, total) {
    const element = document.getElementById(elementId);
    element.textContent = `Exibindo ${journeys.length} de ${total} colaborador(es)`;
  }

  renderRecentAlerts(alerts) {
    const host = document.querySelector("#alerts-list");
    const visibleAlerts = alerts.slice(0, 3);
    host.innerHTML = visibleAlerts.map((alert) => this.#alertMarkup(alert)).join("");
    document.querySelector("#alerts-empty").classList.toggle("hidden", alerts.length > 0);
  }

  renderAlertCenter(alerts) {
    document.querySelector("#alert-center-list").innerHTML = alerts.map((alert) => this.#alertMarkup(alert)).join("");
    document.querySelector("#alert-center-empty").classList.toggle("hidden", alerts.length > 0);
    document.querySelector("#alert-section-total").textContent = `${alerts.filter((item) => item.category !== "attended").length} alertas abertos`;
  }

  #alertMarkup(alert) {
    const styleClass = alert.category === "no-response" ? "alert-danger" : ["open", "not-reached"].includes(alert.category) ? "alert-warning" : "";
    const reminderButton = alert.category !== "attended"
      ? `<button class="button-small" type="button" data-reminder-id="${alert.id}">Reenviar lembrete</button>`
      : "";
    const channel = alert.channel === "RH" ? '<span class="channel-badge">🔒 Canal RH</span>' : "";
    const detail = `Sinal: ${escapeHtml(alert.signal)}${alert.recommendation ? `. Sugestão: ${escapeHtml(alert.recommendation)}` : ""}.`;
    const summary = alert.summary ? `<p class="alert-summary">${escapeHtml(alert.summary)}</p>` : "";
    const owner = alert.owner ? `Com ${escapeHtml(alert.owner)} · ` : "";
    return `<article class="alert-item ${styleClass}" data-alert-id="${alert.id}">
      <div class="alert-item-top"><span class="alert-person">${escapeHtml(alert.employeeName)} <span class="store-name">· ${escapeHtml(alert.store)}</span> ${channel}</span><span class="alert-state">${escapeHtml(alert.state)}</span></div>
      <p class="alert-description">${detail}</p>${summary}
      <div class="alert-actions">${reminderButton}<span class="alert-meta">${owner}${escapeHtml(alert.createdAt)}</span></div>
    </article>`;
  }

  renderStores(stores, journeys, alerts) {
    const markup = stores.map((store) => {
      const journeyCount = journeys.filter((item) => item.store === store).length;
      const alertCount = alerts.filter((item) => item.store === store && item.category !== "attended").length;
      const averageProgress = journeyCount
        ? Math.round(journeys.filter((item) => item.store === store).reduce((sum, item) => sum + item.progress, 0) / journeyCount)
        : 0;
      return `<article class="store-card">
        <div class="store-card-top"><div class="store-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 10 12 3l9 7v11H3z"/><path d="M9 21v-7h6v7"/></svg></div><div><h3>${escapeHtml(store)}</h3><p>Unidade acompanhada</p></div></div>
        <div class="store-stats"><div class="store-stat"><strong>${journeyCount}</strong><span>Jornadas</span></div><div class="store-stat"><strong>${alertCount}</strong><span>Alertas pendentes</span></div><div class="store-stat"><strong>${averageProgress}%</strong><span>Progresso médio</span></div><div class="store-stat"><strong>${journeys.filter((item) => item.store === store && item.status === "no-response").length}</strong><span>Sem resposta 24h</span></div></div>
        <button class="store-card-link" type="button" data-store-shortcut="${escapeHtml(store)}">Ver jornadas desta loja →</button>
      </article>`;
    }).join("");
    document.querySelector("#store-grid").innerHTML = markup;
    document.querySelector("#store-section-total").textContent = `${stores.length} lojas`;
  }

  setPage(page) {
    const pageNames = {
      overview: ["Visão geral das jornadas", "Dados da demonstração · todas as lojas"],
      journeys: ["Jornadas", "Dados da demonstração · acompanhamento dos colaboradores"],
      alerts: ["Alertas", "Só alertas que o colaborador autorizou · sinais que precisam de acompanhamento"],
      stores: ["Lojas", "Dados da demonstração · visão resumida por unidade"],
      colaboradores: ["Colaboradores", "Cadastro de quem recebe as mensagens do Parceiro dos 90 dias"],
      mentoria: ["Mentoria", "Quem ensina quem: vínculos entre mentores e aprendizes"],
      insights: ["Insights", "O que as conversas, alertas e enquetes estão mostrando"],
    };
    document.querySelector("#page-title").textContent = pageNames[page][0];
    document.querySelector("#page-subtitle").textContent = pageNames[page][1];
    for (const name of Object.keys(pageNames)) {
      document.getElementById(`${name}-page`).classList.toggle("hidden", name !== page);
    }
    document.querySelectorAll(".nav-item").forEach((item) => {
      const active = item.dataset.page === page;
      item.classList.toggle("is-active", active);
      if (active) item.setAttribute("aria-current", "page");
      else item.removeAttribute("aria-current");
    });
  }

  showToast(title, message) {
    const region = document.querySelector("#toast-region");
    const toast = document.createElement("div");
    toast.className = "toast";
    const strong = document.createElement("strong");
    strong.textContent = title;
    const text = document.createElement("span");
    text.textContent = message;
    toast.append(strong, text);
    region.append(toast);
    window.setTimeout(() => toast.remove(), 3800);
  }

  setThemeButtonState(theme) {
    document.querySelectorAll("[data-theme-choice]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.themeChoice === theme));
    });
  }
}
