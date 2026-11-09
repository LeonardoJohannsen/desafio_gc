/** Telas de Colaboradores, Mentoria e Insights. */
export class PeopleController {
  constructor({ service, view, peopleView, insightsView, getStores, refresh }) {
    Object.assign(this, { service, view, peopleView, insightsView, getStores, refresh });
    this.people = [];
  }

  bind() {
    document.querySelector("#person-form").addEventListener("submit", (event) => this.submitPerson(event));
    document.querySelector("#person-role").addEventListener("change", () => this.toggleFields());
    document.querySelector("#mentorship-form").addEventListener("submit", (event) => this.submitMentorship(event));
    document.addEventListener("click", (event) => {
      const off = event.target.closest("[data-person-deactivate]");
      if (off) this.deactivate(Number(off.dataset.personDeactivate));
      const end = event.target.closest("[data-mentorship-end]");
      if (end) this.endMentorship(Number(end.dataset.mentorshipEnd));
    });
    document.querySelector("#person-date").value = new Date().toLocaleDateString("sv-SE"); // AAAA-MM-DD local
    this.toggleFields();
  }

  toggleFields() {
    const role = document.querySelector("#person-role").value;
    document.querySelector("#field-date").classList.toggle("hidden", role !== "COLABORADOR");
    document.querySelector("#field-manager").classList.toggle("hidden", role !== "COLABORADOR");
    document.querySelector("#field-store").classList.toggle("hidden", role === "RH");
  }

  async showPeople() {
    this.people = await this.service.loadPeople();
    this.peopleView.fillStores(this.getStores());
    this.peopleView.fillManagers(this.people);
    this.peopleView.renderPeople(this.people);
  }

  async showMentorships() {
    const [people, data] = await Promise.all([this.service.loadPeople(), this.service.loadMentorships()]);
    this.people = people;
    this.peopleView.renderMentorships(data, people);
  }

  async showInsights() {
    this.insightsView.render(await this.service.loadInsights());
  }

  async submitPerson(event) {
    event.preventDefault();
    const value = (id) => document.querySelector(id).value.trim();
    const number = (id) => (value(id) ? Number(value(id)) : null);
    const role = value("#person-role");
    const payload = {
      nome: value("#person-name"), telefone: value("#person-phone"), papel: role,
      lojaId: role === "RH" ? null : number("#person-store"),
      dataEntrada: role === "COLABORADOR" ? value("#person-date") : null,
      gerenteId: role === "COLABORADOR" ? number("#person-manager") : null,
    };
    try {
      const created = await this.service.createPerson(payload);
      this.peopleView.showError("person-form-error", "");
      document.querySelector("#person-name").value = "";
      document.querySelector("#person-phone").value = "";
      this.view.showToast("Cadastro criado", `${created.nome} recebe as boas-vindas assim que abrir o WhatsApp.`);
      await Promise.all([this.showPeople(), this.refresh()]);
    } catch (error) {
      this.peopleView.showError("person-form-error", error.message);
    }
  }

  async deactivate(id) {
    if (!window.confirm("Desativar esta pessoa? Ela sai da jornada e os vínculos de mentoria dela são encerrados.")) return;
    try {
      await this.service.updatePerson(id, { ativo: false });
      await Promise.all([this.showPeople(), this.refresh()]);
      this.view.showToast("Pessoa desativada", "Ela não recebe mais mensagens do assistente.");
    } catch (error) {
      this.view.showToast("Não foi possível desativar", error.message);
    }
  }

  async submitMentorship(event) {
    event.preventDefault();
    const mentorId = Number(document.querySelector("#mentorship-mentor").value);
    const aprendizId = Number(document.querySelector("#mentorship-apprentice").value);
    if (!mentorId || !aprendizId) {
      this.peopleView.showError("mentorship-form-error", "Escolha o mentor e o aprendiz.");
      return;
    }
    try {
      await this.service.assignMentor(mentorId, aprendizId);
      this.peopleView.showError("mentorship-form-error", "");
      this.view.showToast("Mentoria vinculada", "O vínculo já aparece na tabela de jornadas.");
      await Promise.all([this.showMentorships(), this.refresh()]);
    } catch (error) {
      this.peopleView.showError("mentorship-form-error", error.message);
    }
  }

  async endMentorship(id) {
    try {
      await this.service.endMentorship(id);
      await Promise.all([this.showMentorships(), this.refresh()]);
      this.view.showToast("Vínculo encerrado", "O aprendiz voltou para a lista de quem está sem mentor.");
    } catch (error) {
      this.view.showToast("Não foi possível encerrar", error.message);
    }
  }
}
