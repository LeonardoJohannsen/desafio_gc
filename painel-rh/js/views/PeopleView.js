import { CONFIG } from "../config.js";
import { escapeHtml } from "../utils/dom.js";

const ROLE = { COLABORADOR: "Colaborador", GERENTE: "Gerente", MENTOR: "Mentor", RH: "RH" };

export const whatsappUrl = (person) =>
  `${CONFIG.apiBase}/whatsapp/?${new URLSearchParams({ modo: "api", tel: person.telefone, nome: person.nome.split(" ")[0] })}`;

const phoneLabel = (digits) => digits.replace(/^55(\d{2})(\d{4,5})(\d{4})$/, "($1) $2-$3");

function accessPill(person) {
  if (person.papel !== "COLABORADOR") return '<span class="status-pill status-muted">—</span>';
  if (!person.aceitou) return '<span class="status-pill status-warning">Aguardando aceite</span>';
  if (person.pausado) return '<span class="status-pill status-muted">Pausado</span>';
  return '<span class="status-pill status-success">Ativo</span>';
}

export function peopleRowsHtml(people) {
  return people.map((p) => `
    <tr>
      <td><span class="employee-name">${escapeHtml(p.nome)}</span><br><span class="store-name">${escapeHtml(phoneLabel(p.telefone))}</span></td>
      <td>${escapeHtml(ROLE[p.papel] ?? p.papel)}</td>
      <td><span class="store-name">${escapeHtml(p.loja ?? "—")}</span></td>
      <td>${p.dia ? `<span class="day-label">Dia ${p.dia}</span>` : "—"}</td>
      <td><span class="store-name">${escapeHtml(p.gerente ?? "—")}</span></td>
      <td><span class="store-name">${escapeHtml(p.mentor ?? "—")}</span></td>
      <td>${accessPill(p)}<br><a class="link-button" href="${escapeHtml(whatsappUrl(p))}" target="_blank" rel="noopener">Abrir no WhatsApp fake</a></td>
      <td><button class="button-small button-ghost" type="button" data-person-deactivate="${p.id}">Desativar</button></td>
    </tr>`).join("");
}

export function mentorshipRowsHtml(vinculos) {
  return vinculos.map((v) => `
    <tr>
      <td><span class="employee-name">${escapeHtml(v.mentor)}</span></td>
      <td>${escapeHtml(v.aprendiz)}</td>
      <td><span class="store-name">${escapeHtml(v.loja ?? "—")}</span></td>
      <td><span class="day-label">Dia ${v.dia}</span></td>
      <td><span class="store-name">${escapeHtml(v.desde)}</span></td>
      <td><button class="button-small button-ghost" type="button" data-mentorship-end="${v.id}">Encerrar</button></td>
    </tr>`).join("");
}

export class PeopleView {
  fillStores(storeList) {
    document.querySelector("#person-store").innerHTML = '<option value="">Selecione</option>' +
      storeList.map((s) => `<option value="${s.id}">${escapeHtml(s.nome)}</option>`).join("");
  }

  fillManagers(people) {
    document.querySelector("#person-manager").innerHTML = '<option value="">Gerente da loja (automático)</option>' +
      people.filter((p) => p.papel === "GERENTE").map((p) => `<option value="${p.id}">${escapeHtml(p.nome)} · ${escapeHtml(p.loja ?? "")}</option>`).join("");
  }

  renderPeople(people) {
    document.querySelector("#people-table-body").innerHTML = peopleRowsHtml(people);
    document.querySelector("#people-empty").classList.toggle("hidden", people.length > 0);
    document.querySelector("#people-total").textContent = `${people.length} pessoa(s)`;
  }

  renderMentorships(data, people) {
    document.querySelector("#mentorship-table-body").innerHTML = mentorshipRowsHtml(data.vinculos);
    document.querySelector("#mentorship-empty").classList.toggle("hidden", data.vinculos.length > 0);
    document.querySelector("#mentorship-total").textContent = `${data.vinculos.length} vínculo(s)`;

    document.querySelector("#mentorship-mentor").innerHTML = '<option value="">Escolha o mentor</option>' +
      data.mentores.map((m) => `<option value="${m.id}">${escapeHtml(m.nome)} (${m.aprendizes} aprendiz${m.aprendizes === 1 ? "" : "es"})</option>`).join("");

    const withMentor = new Map(data.vinculos.map((v) => [v.aprendizId, v.mentor]));
    document.querySelector("#mentorship-apprentice").innerHTML = '<option value="">Escolha o aprendiz</option>' +
      people.filter((p) => p.papel === "COLABORADOR" && p.dia && p.dia <= 90).map((p) =>
        `<option value="${p.id}">${escapeHtml(p.nome)} · dia ${p.dia}${withMentor.has(p.id) ? ` (hoje com ${escapeHtml(withMentor.get(p.id))})` : " (sem mentor)"}</option>`).join("");

    document.querySelector("#no-mentor-list").innerHTML = data.semMentor.length
      ? data.semMentor.map((p) => `<span class="chip">${escapeHtml(p.nome)} · dia ${p.dia}</span>`).join("")
      : '<span class="empty-state">Todos os aprendizes têm mentor.</span>';
    document.querySelector("#no-mentor-total").textContent = `${data.semMentor.length} sem mentor`;
  }

  showError(elementId, message) {
    const el = document.getElementById(elementId);
    el.textContent = message ?? "";
    el.classList.toggle("hidden", !message);
  }
}
