// modo "mock": o bot é simulado no próprio navegador (não precisa de servidor).
// modo "api" : fala com o núcleo Python. Use  index.html?modo=api
const params = new URLSearchParams(location.search);

export const CONFIG = {
  modo: params.get("modo") === "api" ? "api" : "mock",
  // Servido pelo próprio núcleo Python (porta 8000)? Usa a mesma origem. Senão, localhost:8000.
  apiBase: location.port === "8000" ? location.origin : "http://localhost:8000",
  wsBase: location.port === "8000" ? location.origin.replace("http", "ws") : "ws://localhost:8000",
};

export const PERSONAS = {
  colaborador: { id: "colaborador", nome: "Ana (colaboradora)", telefone: "5551999990001" },
  gerente: { id: "gerente", nome: "Marcos (gerente)", telefone: "5551999990002" },
  mentor: { id: "mentor", nome: "Rafael (mentor)", telefone: "5551999990003" },
};

// Link do painel do RH: ?tel=5551999990099&nome=Fulano abre o celular de quem foi cadastrado lá.
const tel = params.get("tel");
const conhecido = Object.values(PERSONAS).find((p) => p.telefone === tel);
if (tel && !conhecido) PERSONAS.extra = { id: "extra", nome: params.get("nome") || "Novo número", telefone: tel };
export const PERSONA_INICIAL = conhecido ? conhecido.id : tel ? "extra" : params.get("p");
