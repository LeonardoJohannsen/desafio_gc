import { CONFIG, PERSONAS, PERSONA_INICIAL } from "./config.js";
import { createTransport } from "./transport.js";
import { Recorder, audioBubble, fmt } from "./audio.js";

const $ = (s) => document.querySelector(s);
const ICON = {
  mic: '<svg viewBox="0 0 24 24"><path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v5a3 3 0 0 0 3 3Z"/><path d="M19 11a7 7 0 0 1-14 0M12 18v3"/></svg>',
  send: '<svg viewBox="0 0 24 24"><path d="m4 12 16-8-6 16-2-7z"/></svg>',
  trash: '<svg viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg>',
};
const hhmm = (d) => d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });

const chats = {};
let active = PERSONAS[PERSONA_INICIAL] ? PERSONA_INICIAL : "colaborador";
const recorder = new Recorder();

/* ---------- mensagens ---------- */
function add(pid, msg) {
  msg.time = new Date();
  chats[pid].msgs.push(msg);
  if (pid === active) { $("#messages").append(renderMsg(pid, msg)); scrollDown(); }
  else { chats[pid].unread++; renderTabs(); }
}
const scrollDown = () => { const m = $("#messages"); m.scrollTop = m.scrollHeight; };
const system = (pid, text) => add(pid, { dir: "system", kind: "text", text });

function renderMsg(pid, msg) {
  const row = document.createElement("div");
  row.className = `row ${msg.dir}`;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (msg.kind === "audio") bubble.append(audioBubble(msg.url, msg.secs));
  else bubble.append(document.createTextNode(msg.text));
  if (msg.dir !== "system") {
    const meta = document.createElement("span");
    meta.className = "meta";
    meta.textContent = hhmm(msg.time) + (msg.dir === "out" ? " ✓" : "");
    if (msg.dir === "out") setTimeout(() => { meta.textContent = hhmm(msg.time) + " ✓✓"; }, 700);
    bubble.append(meta);
  }
  row.append(bubble);
  if (msg.kind === "buttons") {
    const quick = document.createElement("div");
    quick.className = "quick";
    msg.options.forEach((opt) => {
      const b = document.createElement("button");
      b.type = "button"; b.textContent = opt.rotulo;
      if (msg.chosen) { b.disabled = true; b.classList.toggle("chosen", msg.chosen === opt.id); }
      b.addEventListener("click", () => choose(pid, msg, opt, quick));
      quick.append(b);
    });
    row.append(quick);
  }
  return row;
}

async function choose(pid, msg, opt, quick) {
  if (msg.chosen) return;
  msg.chosen = opt.id;
  quick.querySelectorAll("button").forEach((b) => { b.disabled = true; b.classList.toggle("chosen", b.textContent === opt.rotulo); });
  add(pid, { dir: "out", kind: "text", text: opt.rotulo });
  await safe(pid, () => chats[pid].transport.choice(msg, opt));
}

async function safe(pid, fn) {
  try { await fn(); }
  catch (err) {
    console.error(err);
    system(pid, CONFIG.modo === "api" ? "Não consegui enviar. Confira se o núcleo Python está ligado em " + CONFIG.apiBase + "." : "Não consegui enviar.");
  }
}

function onIncoming(pid, ev) {
  if (ev.tipo === "digitando") { chats[pid].typing = !!ev.ativo; if (pid === active) setStatus(); return; }
  chats[pid].typing = false;
  if (pid === active) setStatus();
  add(pid, ev.tipo === "botoes"
    ? { dir: "in", kind: "buttons", text: ev.texto, options: ev.opcoes || [], alertaId: ev.alertaId }
    : { dir: "in", kind: "text", text: ev.texto });
}

/* ---------- UI ---------- */
const setStatus = () => { $("#bot-status").textContent = chats[active].typing ? "digitando…" : "online"; };

function renderTabs() {
  const nav = $("#tabs");
  nav.replaceChildren(...Object.values(PERSONAS).map((p) => {
    const b = document.createElement("button");
    b.type = "button"; b.setAttribute("aria-selected", String(p.id === active)); b.textContent = p.nome;
    if (chats[p.id]?.unread) { const s = document.createElement("span"); s.className = "badge"; s.textContent = chats[p.id].unread; b.append(s); }
    b.addEventListener("click", () => switchTo(p.id));
    return b;
  }));
}

function switchTo(pid) {
  if (recording) cancelRec();
  active = pid;
  chats[pid].unread = 0;
  const query = new URLSearchParams(location.search);  // preserva modo, tel e nome
  query.set("p", pid);
  history.replaceState(null, "", `?${query}`);
  renderTabs(); setStatus();
  $("#messages").replaceChildren(...chats[pid].msgs.map((m) => renderMsg(pid, m)));
  scrollDown();
}

/* ---------- composer ---------- */
const input = $("#text-input"), action = $("#action-btn");
const syncAction = () => {
  const hasText = input.value.trim().length > 0;
  action.innerHTML = hasText ? ICON.send : ICON.mic;
  action.setAttribute("aria-label", hasText ? "Enviar mensagem" : "Gravar áudio");
};

async function sendText() {
  const text = input.value.trim();
  if (!text) return;
  input.value = ""; syncAction();
  const pid = active;
  add(pid, { dir: "out", kind: "text", text });
  await safe(pid, () => chats[pid].transport.sendText(text));
}

let recording = false;
const showRec = (on) => { recording = on; $("#row-text").classList.toggle("hidden", on); $("#row-rec").classList.toggle("hidden", !on); };

async function startRec() {
  try {
    await recorder.start((s) => { $("#rec-time").textContent = fmt(s); }, sendRec);
    $("#rec-time").textContent = "0:00";
    showRec(true);
  } catch (err) {
    console.error(err);
    system(active, "Não consegui usar o microfone. Permita o acesso no navegador e abra a página por http://localhost (não por file://).");
  }
}
function cancelRec() { recorder.cancel(); showRec(false); }
async function sendRec() {
  if (!recording) return;
  const pid = active;
  showRec(false);
  const result = await recorder.stop();
  if (result.secs < 1) return system(pid, "Áudio muito curto. Segure um pouco mais.");
  add(pid, { dir: "out", kind: "audio", url: URL.createObjectURL(result.blob), secs: result.secs });
  await safe(pid, () => chats[pid].transport.sendAudio(result));
}

action.addEventListener("click", () => (input.value.trim() ? sendText() : startRec()));
input.addEventListener("input", syncAction);
input.addEventListener("keydown", (e) => { if (e.key === "Enter") sendText(); });
$("#rec-cancel").innerHTML = ICON.trash;
$("#rec-send").innerHTML = ICON.send;
$("#rec-cancel").addEventListener("click", cancelRec);
$("#rec-send").addEventListener("click", sendRec);

/* ---------- início ---------- */
$("#clock").textContent = hhmm(new Date());
$("#mode-hint").textContent = CONFIG.modo === "api"
  ? `Conectado ao núcleo Python em ${CONFIG.apiBase}.`
  : "Modo demonstração: o bot é simulado aqui mesmo. Use ?modo=api para ligar no núcleo Python. Dica: escreva “estou cansado” no celular da Ana.";
for (const p of Object.values(PERSONAS)) {
  chats[p.id] = { msgs: [], unread: 0, typing: false };
  chats[p.id].transport = createTransport(p, (ev) => onIncoming(p.id, ev));
}
syncAction(); switchTo(active);
