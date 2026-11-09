// Servido pelo núcleo Python (porta 8000)? Usa a mesma origem. Senão, localhost:8000.
export const CONFIG = {
  apiBase: location.port === "8000" ? location.origin : "http://localhost:8000",
  refreshMs: 10000, // atualiza alertas e jornadas sozinho a cada 10 s
};
