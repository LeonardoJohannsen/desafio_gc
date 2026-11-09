import { escapeHtml } from "../utils/dom.js";

const pct = (n, total) => (total ? Math.round((100 * n) / total) : 0);

function metricCard(label, value, note, accent, valueColor) {
  return `<article class="metric-card" style="--metric-accent:${accent};${valueColor ? `--metric-value-color:${valueColor};` : ""}">
    <div class="metric-label">${label}</div><div class="metric-value">${value}</div><div class="metric-note">${note}</div></article>`;
}

const barRow = (label, n, value, text) => `<div class="bar-row"><span class="bar-label">${escapeHtml(label)}</span>
  <span class="bar-track"><span class="bar-fill" style="width:${value}%"></span></span><span class="bar-value">${text ?? n}</span></div>`;

export function insightsHtml(i) {
  const rate = i.taxaResposta10Dias;
  const rateOk = rate.valor !== null && rate.valor > rate.meta;
  const metrics = [
    metricCard("Resposta nos 10 primeiros dias", rate.valor === null ? "—" : `${rate.valor}%`,
      `Meta: acima de ${rate.meta}% · base: ${rate.base} pessoa(s)`, rateOk ? "var(--green)" : "var(--red)", rate.valor === null ? "" : (rateOk ? "var(--green)" : "var(--red)")),
    metricCard("Tempo médio até o retorno do líder", i.tempoMedioRetornoHoras === null ? "—" : `${String(i.tempoMedioRetornoHoras).replace(".", ",")} h`,
      "Do aviso ao toque em “conversei” ou “não consegui”", "var(--text)"),
    metricCard("Retornos em até 24 h", i.atendidosEm24hPct === null ? "—" : `${i.atendidosEm24hPct}%`, "Dos alertas que já tiveram retorno", "var(--yellow)"),
    metricCard("Alertas confirmados", i.totalAlertas, "Só entram os que o colaborador autorizou", "var(--text)"),
  ].join("");

  const maxWeek = Math.max(1, ...i.alertasPorSemana.map((w) => w.total));
  const weekly = `<div class="column-chart" role="img" aria-label="Alertas por semana">${i.alertasPorSemana.map((w) =>
    `<div class="col"><span class="col-value">${w.total}</span><span class="col-bar" style="height:${Math.max(3, pct(w.total, maxWeek))}%"></span><span class="col-label">${escapeHtml(w.semana)}</span></div>`).join("")}</div>
    <p class="panel-description">Semanas começando na data indicada (segunda-feira).</p>`;

  const maxSignal = Math.max(1, ...i.sinais.map((s) => s.n));
  const signals = i.sinais.length ? i.sinais.map((s) => barRow(s.rotulo, s.n, pct(s.n, maxSignal))).join("") : '<div class="empty-state">Ainda sem alertas.</div>';

  const t = i.treinamento;
  const withCourse = t.total - t.semCurso;
  const different = t.emParte + t.diferente;
  const training = t.total === 0 ? '<div class="empty-state">Ainda sem respostas da enquete sobre o curso online.</div>' : `
    <div class="stack-bar" role="img" aria-label="Curso online comparado com a prática na loja">
      ${[["bate", t.bate, "seg-green"], ["em parte", t.emParte, "seg-yellow"], ["diferente", t.diferente, "seg-red"], ["sem curso", t.semCurso, "seg-gray"]]
        .filter(([, n]) => n > 0).map(([rotulo, n, cls]) => `<span class="seg ${cls}" style="flex:${n}" title="${rotulo}: ${n}">${pct(n, t.total)}%</span>`).join("")}
    </div>
    <div class="legend"><span><i class="seg-green"></i>Bate certinho (${t.bate})</span><span><i class="seg-yellow"></i>Em parte (${t.emParte})</span>
      <span><i class="seg-red"></i>É bem diferente (${t.diferente})</span><span><i class="seg-gray"></i>Não fez curso (${t.semCurso})</span></div>
    <p class="insight-text">${withCourse ? `<strong>${pct(different, withCourse)}%</strong> de quem fez o curso online diz que a prática na loja bate só em parte ou é bem diferente do que aprendeu.` : "Ninguém dos que responderam fez o curso online."}
    Vale conversar com treinadores e mentores sobre quais procedimentos estão sendo ensinados de formas diferentes.</p>`;

  const polls = i.enquetes.length ? i.enquetes.map((e) => `<section class="poll"><h3>${escapeHtml(e.pergunta)}</h3>
    <p class="panel-description">${e.total} resposta(s)</p>${e.opcoes.map((o) => barRow(o.rotulo, o.n, o.pct, `${o.pct}% (${o.n})`)).join("")}</section>`).join("")
    : '<div class="empty-state">As enquetes aparecem aqui conforme os colaboradores respondem.</div>';

  const m = i.mentoria;
  return { metrics, weekly, signals, training, polls,
           mentorship: `${m.comMentor} aprendiz(es) com mentor · ${m.semMentor} sem mentor` };
}

export class InsightsView {
  render(insights) {
    const html = insightsHtml(insights);
    document.querySelector("#insights-metrics").innerHTML = html.metrics;
    document.querySelector("#insights-weekly").innerHTML = html.weekly;
    document.querySelector("#insights-signals").innerHTML = html.signals;
    document.querySelector("#insights-training").innerHTML = html.training;
    document.querySelector("#insights-polls").innerHTML = html.polls;
    document.querySelector("#insights-mentorship-tag").textContent = html.mentorship;
  }
}
