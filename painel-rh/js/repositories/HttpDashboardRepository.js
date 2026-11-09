import { CONFIG } from "../config.js";
import { Journey } from "../models/Journey.js";
import { Alert } from "../models/Alert.js";

/** Repositório que conversa com o núcleo Python (substitui o antigo MockDashboardRepository). */
export class HttpDashboardRepository {
  async #request(path, { method = "GET", body } = {}) {
    let response;
    try {
      response = await fetch(CONFIG.apiBase + path, {
        method,
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch {
      throw new Error(`Não consegui falar com a API em ${CONFIG.apiBase}. O núcleo Python está rodando?`);
    }
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(typeof payload.detail === "string" ? payload.detail : `Erro ${response.status}`);
    }
    return response.json();
  }

  async getDashboardData() {
    const data = await this.#request("/rh/dashboard");
    return {
      journeys: data.journeys.map((item) => new Journey(item)),
      alerts: data.alerts.map((item) => new Alert(item)),
      summary: data.summary,
      stores: data.stores,
      storeList: data.storeList,
    };
  }

  markReminderSent(alertId) { return this.#request(`/rh/alertas/${alertId}/lembrete`, { method: "POST" }); }
  getPeople() { return this.#request("/rh/colaboradores"); }
  createPerson(data) { return this.#request("/rh/colaboradores", { method: "POST", body: data }); }
  updatePerson(id, data) { return this.#request(`/rh/colaboradores/${id}`, { method: "PATCH", body: data }); }
  getMentorships() { return this.#request("/rh/mentorias"); }
  assignMentor(mentorId, aprendizId) { return this.#request("/rh/mentorias", { method: "POST", body: { mentorId, aprendizId } }); }
  endMentorship(id) { return this.#request(`/rh/mentorias/${id}`, { method: "DELETE" }); }
  getInsights() { return this.#request("/rh/insights"); }
}
