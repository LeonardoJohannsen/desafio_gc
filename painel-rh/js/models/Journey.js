/** Entidade de domínio para uma jornada de colaborador. */
export class Journey {
  constructor({ id, employeeName, store, day, totalDays = 90, status, statusLabel, mentor = null, manager = null }) {
    this.id = id;
    this.employeeName = employeeName;
    this.store = store;
    this.day = Number(day);
    this.totalDays = Number(totalDays);
    this.status = status;
    this.statusLabel = statusLabel;
    this.mentor = mentor;
    this.manager = manager;
  }

  get progress() {
    if (!this.totalDays) return 0;
    return Math.min(100, Math.max(0, Math.round((this.day / this.totalDays) * 100)));
  }
}
