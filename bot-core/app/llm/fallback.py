import re

from app.llm.base import LLM
from app.models.schemas import ArquivoAudio

_SINAIS = [  # (sinal, padrão, destinatário)
    ("VONTADE_DE_SAIR", r"pedir demiss|quero sair|vou sair|largar (o )?(emprego|trabalho)|n[aã]o volto", "GERENTE"),
    ("SOBRECARGA", r"sobrecarreg|dobr(ei|ando|ar) turno|sem folga|sobra tudo|trabalhando demais", "GERENTE"),
    ("CONFLITO", r"briga|brigu|discuti|n[aã]o me ajuda|conflito|desentend", "GERENTE"),
    ("DESMOTIVACAO", r"desmotiv|sem vontade|n[aã]o sei se (isso|esse|este)|n[aã]o aguento mais|desanim", "GERENTE"),
    ("CANSACO", r"cansad|exaust|esgotad|morto de cansa", "GERENTE"),
]
_DUVIDA = re.compile(r"\?|\b(como|quando|onde|qual|quais|quanto|posso|preciso)\b", re.I)


class FallbackLLM(LLM):
    """Plano B sem IA: regras simples. Serve para a demo não parar e como linha de base."""
    nome = "fallback"

    def analisar(self, prompt_sistema: str, texto: str | None, audio: ArquivoAudio | None) -> dict:
        if not texto:
            return {"intencao": "CONVERSA", "resposta": "Recebi seu áudio, mas não consegui ouvir agora. Pode me escrever?",
                    "confianca": 0.0}
        for sinal, padrao, dest in _SINAIS:
            if re.search(padrao, texto, re.I):
                return {"intencao": "RECLAMACAO", "categoria": "SAUDE_BEM_ESTAR", "sinal": sinal,
                        "gravidade": "MEDIA", "destinatario": dest, "confianca": 0.4,
                        "resposta": "Poxa, obrigado por contar. Posso avisar o seu gerente para vocês conversarem? Só aviso com o seu ok."}
        if _DUVIDA.search(texto):
            return {"intencao": "DUVIDA", "confianca": 0.3,
                    "resposta": "Boa pergunta! Agora não consegui consultar o material, mas posso pedir para o seu gerente te ajudar."}
        return {"intencao": "CONVERSA", "confianca": 0.3, "resposta": "Recebi sua mensagem! Agora estou no modo simples, sem IA, então não consigo conversar direito. Tenta de novo daqui a pouco? 🙂"}
