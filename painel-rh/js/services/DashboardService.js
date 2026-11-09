/** Camada de aplicação: consulta e prepara os dados para as telas. */
export class DashboardService {
  constructor(repository) {
    this.repository = repository;
  }

  async loadDashboard() { return this.repository.getDashboardData(); }
  async resendReminder(alertId) { return this.repository.markReminderSent(alertId); }
  loadPeople() { return this.repository.getPeople(); }
  createPerson(data) { return this.repository.createPerson(data); }
  updatePerson(id, data) { return this.repository.updatePerson(id, data); }
  loadMentorships() { return this.repository.getMentorships(); }
  assignMentor(mentorId, aprendizId) { return this.repository.assignMentor(mentorId, aprendizId); }
  endMentorship(id) { return this.repository.endMentorship(id); }
  loadInsights() { return this.repository.getInsights(); }

  filterJourneys(journeys, { store = "all", search = "" } = {}) {
    const query = search.trim().toLocaleLowerCase("pt-BR");
    return journeys.filter((journey) => {
      const matchesStore = store === "all" || journey.store === store;
      const matchesSearch = !query || journey.employeeName.toLocaleLowerCase("pt-BR").includes(query);
      return matchesStore && matchesSearch;
    });
  }

  filterAlerts(alerts, { store = "all", category = "all" } = {}) {
    return alerts.filter((alert) => {
      const matchesStore = store === "all" || alert.store === store;
      const matchesCategory = category === "all" || alert.category === category;
      return matchesStore && matchesCategory;
    });
  }
}
