/** Entidade de domínio para um alerta de acompanhamento (só alertas que o colaborador confirmou). */
export class Alert {
  constructor({ id, colaboradorId = null, employeeName, store, signal, recommendation = "", state, category, createdAt,
                channel = "GERENTE", owner = null, summary = null, severity = null }) {
    this.id = id;
    this.colaboradorId = colaboradorId;
    this.employeeName = employeeName;
    this.store = store;
    this.signal = signal;
    this.recommendation = recommendation;
    this.state = state;
    this.category = category;
    this.createdAt = createdAt;
    this.channel = channel;   // GERENTE ou RH
    this.owner = owner;       // quem recebeu o alerta
    this.summary = summary;   // só vem preenchido no canal RH
    this.severity = severity;
  }
}
