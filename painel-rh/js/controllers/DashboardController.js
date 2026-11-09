import { CONFIG } from "../config.js";
import { downloadCsv } from "../utils/dom.js";

/** Controla interações e coordena o serviço e a camada de apresentação. */
export class DashboardController {
  constructor(service, view) {
    this.service = service;
    this.view = view;
    this.data = { journeys: [], alerts: [], summary: {}, stores: [], storeList: [] };
    this.currentPage = "overview";
    this.pages = {}; // páginas extras (colaboradores, mentoria, insights), registradas no main.js
  }

  registerPage(name, handler) {
    this.pages[name] = handler;
  }

  /** Recarrega os dados e redesenha, sem mexer em filtros e buscas. */
  async refresh() {
    this.data = await this.service.loadDashboard();
    this.renderAll();
  }

  startAutoRefresh() {
    window.setInterval(() => {
      if (!document.hidden) this.refresh().catch(() => {});
    }, CONFIG.refreshMs);
  }

  async init() {
    this.data = await this.service.loadDashboard();
    this.view.renderStoreOptions(this.data.stores);
    this.renderAll();
    this.bindEvents();
    this.applyTheme(localStorage.getItem("kallopalli-theme") || "light");
    this.startAutoRefresh();
  }

  renderAll() {
    const store = document.querySelector("#store-filter").value;
    const search = document.querySelector("#journey-search").value;
    const filteredJourneys = this.service.filterJourneys(this.data.journeys, { store, search });
    const filteredAlerts = this.service.filterAlerts(this.data.alerts, { store });

    this.view.renderMetrics(this.data.summary);
    this.view.renderJourneys("journey-table-body", "journey-empty", filteredJourneys.slice(0, 6));
    this.view.setJourneyCount("journey-result-count", filteredJourneys.slice(0, 6), filteredJourneys.length);
    this.view.renderJourneys("all-journeys-table-body", "all-journeys-empty", filteredJourneys);
    this.view.setJourneyCount("all-journeys-result-count", filteredJourneys, filteredJourneys.length);
    this.view.renderRecentAlerts(filteredAlerts);
    this.renderAlertCenter();
    this.view.renderStores(this.data.stores, this.data.journeys, this.data.alerts);
  }

  renderAlertCenter() {
    const store = document.querySelector("#store-filter").value;
    const category = document.querySelector("#alert-status-filter").value;
    this.view.renderAlertCenter(this.service.filterAlerts(this.data.alerts, { store, category }));
  }

  bindEvents() {
    document.querySelector("#store-filter").addEventListener("change", () => this.renderAll());
    document.querySelector("#journey-search").addEventListener("input", () => this.renderAll());
    document.querySelector("#alert-status-filter").addEventListener("change", () => this.renderAlertCenter());
    document.querySelector("#export-button").addEventListener("click", () => this.exportJourneys());

    document.querySelectorAll("[data-page]").forEach((button) => button.addEventListener("click", () => this.navigate(button.dataset.page)));
    document.querySelectorAll("[data-page-link]").forEach((button) => button.addEventListener("click", () => this.navigate(button.dataset.pageLink)));
    document.querySelectorAll("[data-theme-choice]").forEach((button) => button.addEventListener("click", () => this.applyTheme(button.dataset.themeChoice)));

    document.addEventListener("click", async (event) => {
      const reminderButton = event.target.closest("[data-reminder-id]");
      if (reminderButton) await this.handleReminder(Number(reminderButton.dataset.reminderId));
      const storeButton = event.target.closest("[data-store-shortcut]");
      if (storeButton) {
        document.querySelector("#store-filter").value = storeButton.dataset.storeShortcut;
        this.renderAll();
        this.navigate("journeys");
      }
    });

    const sidebar = document.querySelector("#sidebar");
    const backdrop = document.querySelector("#sidebar-backdrop");
    const closeMobileMenu = () => {
      sidebar.classList.remove("is-open");
      backdrop.classList.add("hidden");
    };
    document.querySelector("#menu-toggle").addEventListener("click", () => {
      sidebar.classList.add("is-open");
      backdrop.classList.remove("hidden");
    });
    backdrop.addEventListener("click", closeMobileMenu);
    document.querySelectorAll("[data-page]").forEach((button) => button.addEventListener("click", closeMobileMenu));
  }

  navigate(page) {
    this.currentPage = page;
    this.view.setPage(page);
    if (page === "alerts") this.renderAlertCenter();
    Promise.resolve(this.pages[page]?.()).catch((error) => this.view.showToast("Não foi possível carregar", error.message));
  }

  applyTheme(theme) {
    const validTheme = theme === "dark" ? "dark" : "light";
    document.documentElement.dataset.theme = validTheme;
    localStorage.setItem("kallopalli-theme", validTheme);
    this.view.setThemeButtonState(validTheme);
  }

  async handleReminder(alertId) {
    try {
      await this.service.resendReminder(alertId);
      await this.refresh();
      this.view.showToast("Lembrete enviado", "O líder recebeu o lembrete no WhatsApp.");
    } catch (error) {
      this.view.showToast("Não foi possível reenviar", error.message || "Tente novamente.");
    }
  }

  exportJourneys() {
    const store = document.querySelector("#store-filter").value;
    const search = document.querySelector("#journey-search").value;
    const journeys = this.service.filterJourneys(this.data.journeys, { store, search });
    const rows = [
      ["Colaborador", "Loja", "Dia", "Total de dias", "Progresso (%)", "Situação", "Mentor", "Gerente"],
      ...journeys.map((item) => [item.employeeName, item.store, item.day, item.totalDays, item.progress, item.statusLabel, item.mentor ?? "", item.manager ?? ""]),
    ];
    downloadCsv("jornadas-kallopalli.csv", rows);
    this.view.showToast("Exportação iniciada", `${journeys.length} jornada(s) preparada(s) em CSV.`);
  }
}
