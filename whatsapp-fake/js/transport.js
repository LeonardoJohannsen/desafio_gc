import { CONFIG } from "./config.js";
import { extFromMime } from "./audio.js";

/* Eventos que chegam ao celular (iguais no mock e na API):
   {tipo:"digitando", ativo:true}
   {tipo:"texto",  texto}
   {tipo:"botoes", texto, opcoes:[{id,rotulo}], alertaId?}            */

// ---------- MODO MOCK: bot simulado no navegador ----------
const hub = {};
const deliver = (pid, ev, ms = 0) => setTimeout(() => hub[pid]?.(ev), ms);
const reply = (pid, ev) => { deliver(pid, { tipo: "digitando", ativo: true }, 250); deliver(pid, ev, 1200); };
const GENERICAS = [
  "Entendi! Obrigado por contar. 😊 Como foi o resto do seu dia?",
  "Boa! Quer uma pílula de 30 segundos sobre atendimento no balcão?",
  "Que legal! Se aparecer alguma dúvida do treinamento, é só me chamar.",
];
let n = 0;

function mockTransport(persona, onIncoming) {
  hub[persona.id] = onIncoming;
  if (persona.id === "colaborador") {
    reply("colaborador", {
      tipo: "botoes",
      texto: "Oi, Ana! Eu sou o Parceiro dos 90 dias 👋\nVou te mandar mensagens curtas, dicas e tirar dúvidas.\n\nTransparência: se você contar algo que merece atenção, eu aviso o seu gerente (ou o RH, se for algo mais sensível) e SEMPRE te conto antes. A participação é opcional e você pode escrever “parar” quando quiser.",
      opcoes: [{ id: "ACEITO", rotulo: "Quero participar" }, { id: "AGORA_NAO", rotulo: "Agora não" }],
    });
  }
  const sinal = (t) => /cansad|sobrecarreg|desmotiv|quero sair|puxad/i.test(t);
  return {
    async sendText(texto) {
      if (persona.id !== "colaborador") return reply(persona.id, { tipo: "texto", texto: "Esse celular só recebe alertas no modo demonstração. 🙂" });
      if (sinal(texto)) {
        reply("colaborador", { tipo: "botoes", texto: "Poxa, parece que o dia foi puxado. Posso avisar o seu gerente para vocês conversarem? Ele recebe só um resumo, e eu te aviso sempre que isso acontecer.", opcoes: [{ id: "AVISAR", rotulo: "Pode avisar" }, { id: "NAO_AVISAR", rotulo: "Prefiro que não" }] });
      } else reply("colaborador", { tipo: "texto", texto: GENERICAS[n++ % GENERICAS.length] });
    },
    async sendAudio({ secs }) {
      reply(persona.id, { tipo: "texto", texto: `🎧 Recebi seu áudio de ${Math.round(secs)}s. No modo API, o Gemini transcreve e analisa a fala.` });
    },
    async choice(msg, opt) {
      if (opt.id === "AVISAR") {
        reply("colaborador", { tipo: "texto", texto: "Combinado! Avisei o seu gerente. 💬 Se ele te procurar, é por causa disso." });
        deliver("gerente", { tipo: "botoes", alertaId: 1, texto: "🔔 Ana Pereira (dia 10) comentou sobre cansaço.\nSugestão: vale uma conversa ainda hoje.", opcoes: [{ id: "CONVERSEI", rotulo: "Conversei" }, { id: "NAO_CONSEGUIU", rotulo: "Não consegui" }] }, 1500);
      } else if (opt.id === "CONVERSEI" || opt.id === "NAO_CONSEGUIU") {
        reply("gerente", { tipo: "texto", texto: "Registrado ✅ O RH já vê o retorno no painel." });
      } else {
        reply(persona.id, { tipo: "texto", texto: opt.id === "ACEITO" ? "Show! Amanhã eu te chamo. Como foi o seu dia hoje?" : "Tudo bem! Se mudar de ideia, é só me escrever." });
      }
    },
    close() { delete hub[persona.id]; },
  };
}

// ---------- MODO API: núcleo Python ----------
function apiTransport(persona, onIncoming) {
  let ws, closed = false;
  const connect = () => {
    ws = new WebSocket(`${CONFIG.wsBase}/ws/${persona.telefone}`);
    ws.onmessage = (e) => { try { onIncoming(JSON.parse(e.data)); } catch { /* ignora lixo */ } };
    ws.onclose = () => { if (!closed) setTimeout(connect, 2000); };
  };
  connect();
  const post = async (path, init) => {
    const res = await fetch(CONFIG.apiBase + path, { method: "POST", ...init });
    if (!res.ok) throw new Error(`${path} respondeu ${res.status}`);
  };
  const json = (body) => ({ headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  return {
    sendText: (texto) => post("/mensagens", json({ telefone: persona.telefone, texto })),
    sendAudio({ blob, secs, mime }) {
      const fd = new FormData();
      fd.append("telefone", persona.telefone);
      fd.append("duracao", secs.toFixed(1));
      fd.append("audio", blob, `audio.${extFromMime(mime)}`);
      return post("/mensagens/audio", { body: fd });
    },
    choice(msg, opt) {
      if (msg.alertaId) return post(`/alertas/${msg.alertaId}/retorno`, json({ telefone: persona.telefone, resultado: opt.id }));
      return post("/mensagens", json({ telefone: persona.telefone, texto: opt.rotulo, opcaoId: opt.id }));
    },
    close() { closed = true; ws?.close(); },
  };
}

export const createTransport = (persona, onIncoming) =>
  (CONFIG.modo === "api" ? apiTransport : mockTransport)(persona, onIncoming);
