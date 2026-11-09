"""Dados fictícios da loja piloto. Os telefones 01, 02 e 03 são os 3 celulares do app fake."""
from datetime import date, timedelta

from app.services.conteudo import Conteudo


def popular(repo, relogio):
    hoje = relogio.agora()
    ts = hoje.strftime("%Y-%m-%d %H:%M:%S")

    def entrada(dia):
        return (hoje - timedelta(days=dia - 1)).strftime("%Y-%m-%d")

    lojas = {n: repo.criar_loja(n) for n in ("Porto Alegre", "Tramandaí", "Capão da Canoa")}
    pa, tr, cc = lojas["Porto Alegre"], lojas["Tramandaí"], lojas["Capão da Canoa"]

    marcos = repo.criar_colaborador("Marcos Lima", "5551999990002", pa, "GERENTE", "2025-01-10")
    repo.criar_colaborador("Rafael Mendes", "5551999990003", pa, "MENTOR", "2025-03-01", marcos)
    repo.criar_colaborador("Helena Prado", "5551999990004", None, "RH", "2024-08-01")
    juliana = repo.criar_colaborador("Juliana Nunes", "5551999990005", tr, "GERENTE", "2025-02-01")
    roberto = repo.criar_colaborador("Roberto Faria", "5551999990006", cc, "GERENTE", "2025-02-15")

    # Ana (dia 6) ainda não aceitou: serve para demonstrar boas-vindas e aceite.
    # Avançando o relógio: dia 7 = marco, 8 = pílula, 10 = enquete.
    repo.criar_colaborador("Ana Pereira", "5551999990001", pa, "COLABORADOR", entrada(6), marcos, None)
    equipe = [
        ("João Silva", "5551999990011", pa, marcos, 10), ("Lucas Martins", "5551999990012", cc, roberto, 34),
        ("Bianca Rocha", "5551999990013", pa, marcos, 52), ("Pedro Alves", "5551999990014", pa, marcos, 21),
        ("Carla Dias", "5551999990015", tr, juliana, 78), ("Marina Costa", "5551999990016", cc, roberto, 43),
        ("Rafael Souza", "5551999990017", tr, juliana, 16),
    ]
    for nome, tel, loja, ger, dia in equipe:
        repo.criar_colaborador(nome, tel, loja, "COLABORADOR", entrada(dia), ger, ts)


def popular_demo(repo, relogio):
    """Histórico fictício (alertas, mensagens, enquetes e mentorias) para o painel do RH não nascer vazio.
    Os alertas aqui já passaram pela confirmação do colaborador."""
    from app.services.relogio import FORMATO
    agora = relogio.agora()

    def t(horas):
        return (agora - timedelta(hours=horas)).strftime(FORMATO)

    def pessoa(nome):
        return repo.colaborador_por_telefone(repo.b.um("SELECT telefone FROM colaborador WHERE nome=?", (nome,))["telefone"])

    camila = repo.criar_colaborador("Camila Torres", "5551999990007", repo.criar_loja("Tramandaí"), "MENTOR", "2025-02-20",
                                    pessoa("Juliana Nunes").id)
    for mentor, aprendiz in (("Rafael Mendes", "João Silva"), ("Rafael Mendes", "Pedro Alves"),
                             ("Camila Torres", "Carla Dias"), ("Camila Torres", "Rafael Souza")):
        repo.b.exec("INSERT INTO mentoria(mentor_id, aprendiz_id, inicio) VALUES (?,?,?)", (pessoa(mentor).id, pessoa(aprendiz).id, t(24 * 9)))

    for nome in ("João Silva", "Lucas Martins", "Bianca Rocha", "Marina Costa", "Rafael Souza"):  # Pedro e Carla ainda não responderam
        p = pessoa(nome)
        for dia, texto in ((2, "tudo certo por aqui"), (5, "to aprendendo aos poucos")):
            repo.salvar_mensagem(p.id, "ENTRADA", "TEXTO", texto, None, dia, t(24 * 3))

    def alerta(nome, canal, sinal, grav, sugestao, resumo, estado, criado_h, retorno_h=None):
        p = pessoa(nome)
        dest = repo.rh() if canal == "RH" else repo.gerente_de(p)
        id_ = repo.criar_alerta(p.id, None, canal, sinal, grav, sugestao, resumo, estado, t(criado_h))
        campos = {"destinatario_id": dest.id if dest else None, "confirmado_em": t(criado_h)}
        if estado == "ABERTO":
            campos["lembrete_em"] = (agora - timedelta(hours=criado_h) + timedelta(hours=24)).strftime(FORMATO)
        if estado == "SEM_RESPOSTA_24H":
            campos["lembrado_em"] = t(criado_h - 24)
        if retorno_h is not None:
            campos["retorno_em"] = t(criado_h - retorno_h)
        repo.atualizar_alerta(id_, estado=estado, **campos)

    g = "GERENTE"
    alerta("João Silva", g, "CANSACO", "MEDIA", "vale uma conversa ainda hoje", "A pessoa comentou estar cansada depois de turnos seguidos.", "ABERTO", 3)
    alerta("Lucas Martins", g, "DESMOTIVACAO", "MEDIA", "vale um contato nos próximos 3 dias", "A pessoa disse estar sem vontade de ir ao trabalho.", "SEM_RESPOSTA_24H", 30)
    alerta("Bianca Rocha", g, "CONFLITO", "MEDIA", "vale uma conversa ainda hoje", "Atrito com um colega de turno.", "ATENDIDO", 26, retorno_h=6)
    alerta("Marina Costa", g, "VONTADE_DE_SAIR", "ALTA", "vale uma conversa ainda hoje", "A pessoa mencionou que pensa em sair.", "ABERTO", 5)
    alerta("Rafael Souza", g, "CONFLITO", "MEDIA", "vale um contato nos próximos 3 dias", "Dificuldade de convivência com a equipe.", "ABERTO", 10)
    alerta("Carla Dias", "RH", "SITUACAO_GRAVE", "ALTA", "tratar com sigilo e conversar em até 24h",
           "Relato de tratamento humilhante por parte da chefia de turno.", "ABERTO", 2)
    for nome, sinal, dias, ret in (("Pedro Alves", "CANSACO", 8, 5), ("João Silva", "SOBRECARGA", 15, 20),
                                   ("Lucas Martins", "CONFLITO", 16, 3), ("Bianca Rocha", "DESMOTIVACAO", 23, 10)):
        alerta(nome, g, sinal, "MEDIA", "vale uma conversa", "Histórico de acompanhamento.", "ATENDIDO", 24 * dias, retorno_h=ret)

    respostas = {
        "bem-estar": {"João Silva": "mais-ou-menos", "Lucas Martins": "dificil", "Bianca Rocha": "bem", "Pedro Alves": "bem",
                      "Carla Dias": "bem", "Marina Costa": "mais-ou-menos", "Rafael Souza": "bem"},
        "curso-x-loja": {"João Silva": "diferente", "Lucas Martins": "diferente", "Bianca Rocha": "parte", "Pedro Alves": "parte",
                         "Carla Dias": "igual", "Marina Costa": "diferente", "Rafael Souza": "sem-curso"},
        "carga": {"João Silva": "pesada", "Lucas Martins": "pesada-demais", "Bianca Rocha": "boa", "Pedro Alves": "leve", "Marina Costa": "pesada"},
        "apoio-equipe": {"João Silva": "muito", "Lucas Martins": "quase-nada", "Bianca Rocha": "as-vezes", "Pedro Alves": "muito",
                         "Marina Costa": "quase-nada", "Rafael Souza": "as-vezes"},
    }
    rotulos = {(e["id"], o["id"]): o["rotulo"] for e in Conteudo.carregar().enquetes for o in e["opcoes"]}
    for enquete, por_pessoa in respostas.items():
        for nome, opcao in por_pessoa.items():
            p = pessoa(nome)
            dia = max(1, (agora.date() - date.fromisoformat(p.data_entrada)).days + 1 - 2)
            repo.salvar_resposta_enquete(enquete, p.id, opcao, rotulos[(enquete, opcao)], dia, t(24 * 2))
