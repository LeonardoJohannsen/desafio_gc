# bot-core · Parceiro dos 90 dias

Núcleo em Python: classificador de IA (Gemini), fluxo de conversa (aceite, confirmação, alerta,
retorno e lembrete de 24h), banco SQLite e API que liga o app fake de WhatsApp.

## Instalar (Windows, PowerShell, dentro de bot-core)
    python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    copy .env.example .env        # abra o .env e cole a GEMINI_API_KEY

## Testar o classificador no terminal
    python cli.py "Estou exausto, dobrei turno a semana toda"
    python cli.py --audio C:\caminho\audio.wav
    python cli.py --chat --nome Ana --dia 10
    python cli.py --casos tests/casos_rotulados.json
    python -m unittest discover -s tests          # 106 testes, sem internet

## Subir o servidor + app fake
    uvicorn app.main:app --port 8000
    # abra: http://localhost:8000/whatsapp/?modo=api

Para ver o fluxo inteiro, abra em abas separadas (ou use as abas do próprio app fake):
Ana (colaboradora), Marcos (gerente) e Rafael (mentor). Ana começa sem ter aceitado, então
recebe as boas-vindas. Depois do aceite: "estou muito cansado" -> bot pergunta -> "Pode avisar"
-> alerta chega no Marcos com os botões "Conversei" / "Não consegui".

## Cadência dos 90 dias (app/services/jornada.py)
    dias 1-10: todo dia | 11-30: a cada 3 dias | 31-60: semanal | 61-90: a cada 10 dias
    marcos 7, 15, 30, 45, 60, 90: mensagem comemorativa + aviso ao gerente (conversa presencial prevista)
    tipos: acompanhamento (conversa), pílula (poucas, sempre terminam em pergunta), enquete (5, no content/enquetes.json)
    o bot só puxa conversa entre HORARIO_INICIO e HORARIO_FIM (padrão 9h-20h, relógio da demo)
Roteiro de demo com a Ana (começa no dia 6): aceite -> POST avancar 24h (dia 7, marco) -> avancar (dia 8, pílula)
-> avancar 2x (dia 10, enquete; "Está difícil" abre o fluxo de aviso ao gerente).

## Ferramentas da demo (Swagger em http://localhost:8000/docs)
    POST /simulador/relogio/avancar   {"horas": 25}   dispara o lembrete de 24h
    POST /simulador/cadencia/executar                  roda agora a cadência do dia (ignora a janela de horário)
    POST /simulador/reset                              recria os dados fictícios (depois recarregue o app)
    GET  /simulador/estado                             hora simulada, alertas por estado, modo da IA

O banco fica em data/parceiro.sqlite3 (apague o arquivo para recomeçar). Sem GEMINI_API_KEY,
ou se o Gemini falhar, o plano B por palavras-chave assume (campo "origem_analise").

## Limites do Gemini (erro 429)
O bot espaça as chamadas (GEMINI_MAX_RPM), espera o tempo que a API pede ("tente de novo em X s") e,
se falhar, repete com espera crescente (1s, 2s, 4s, 8s...). Se a espera passar de GEMINI_ESPERA_MAXIMA_S,
tenta o GEMINI_MODEL_RESERVA (cada modelo costuma ter a sua cota). Só depois disso entra o plano B.
Cota DIÁRIA esgotada: não insiste, usa o modelo de reserva ou o plano B até o dia seguinte.
Veja o estado em GET /simulador/estado (campo "ia") e os avisos no terminal do uvicorn.
Se ainda aparecer 429, diminua GEMINI_MAX_RPM para o limite que o AI Studio mostra para o seu modelo.

## Economizando cota do Gemini
- 1 mensagem = 1 chamada. Clique em botão, "sim/não" de confirmação e cadência NÃO chamam a IA.
- python cli.py --casos ... roda por padrão só 5 casos essenciais e guarda o resultado em cache (repetir não gasta chamada).
  Use --todos para os 17, --max N para os N primeiros e --sem-cache para forçar chamadas novas.
- GEMINI_LIMITE_DIARIO trava o bot ao atingir N chamadas por modelo no dia (guarda cota para a demo).
  python cli.py --uso mostra a contagem de hoje; o servidor mostra o mesmo em GET /simulador/estado.
- GEMINI_THINKING=minimal (padrão): o Gemini 3.x raciocina "medium" por padrão, o que só atrasa a resposta.
- Para ver o motivo exato de um 429 (por minuto ou por dia), rode: python cli.py "oi" e leia o campo "aviso".
- Veja seus limites reais por modelo em https://aistudio.google.com/rate-limit
- Atualize o SDK se aparecer aviso sobre thinking_level: pip install -U google-genai

## Painel do RH
    http://localhost:8000/painel/        (a pasta ../painel-rh é servida pelo próprio núcleo)
Telas: visão geral, jornadas, alertas, lojas, colaboradores (cadastro), mentoria e insights.
Dados de demonstração (alertas, enquetes e mentorias fictícias) vêm de DEMO_DADOS=1 no .env; use 0 para começar só com o cadastro.
Em "Colaboradores", o link "Abrir no WhatsApp fake" abre o celular de quem foi cadastrado (?tel=...&nome=...).
API: GET /rh/dashboard, /rh/colaboradores, /rh/mentorias, /rh/insights; POST /rh/colaboradores, /rh/mentorias,
/rh/alertas/{id}/lembrete; PATCH /rh/colaboradores/{id}; DELETE /rh/mentorias/{id}. Sem login (demo local).
Privacidade: o painel só recebe alertas que o colaborador autorizou, nunca o texto das conversas, e o resumo de um
alerta só aparece no canal RH.

## Estrutura
    app/api/        rotas HTTP/WebSocket (finas)
    app/services/   conversa.py (regras do fluxo), cadencia.py, painel.py (consultas do RH), relogio.py, jornada.py
    app/pipeline/   analisador.py (IA) e seguranca.py (rede de proteção)
    app/llm/        gemini.py, fallback.py, prompts/analisador.md
    app/storage/    db.py (SQLite) e repositorio.py (consultas)
    content/        faq_kallopolli.md, pilulas.json, enquetes.json, mensagens.json (fictícios)
