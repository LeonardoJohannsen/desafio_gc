# Painel do RH · Parceiro dos 90 dias

HTML, CSS e JavaScript puros (módulos ES), na arquitetura Repository → Service → View → Controller do protótipo original.
O antigo MockDashboardRepository foi trocado pelo HttpDashboardRepository, que usa a API do núcleo Python (/rh/*).

Abra pelo servidor do núcleo: http://localhost:8000/painel/   (uvicorn app.main:app --port 8000, dentro de bot-core)

Telas: Visão geral · Jornadas · Alertas · Lojas · Colaboradores (cadastro) · Mentoria · Insights.
Atualiza sozinho a cada 10 s. O botão "Reenviar lembrete" manda o lembrete de verdade para o WhatsApp do líder.

Privacidade (LGPD): o painel só recebe alertas que o colaborador autorizou, nunca o texto das conversas, e o resumo
de um alerta só aparece quando ele foi para o canal RH. Não há login: é uma demonstração local.
