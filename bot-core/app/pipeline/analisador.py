import logging
from pathlib import Path

from app.config import BASE_DIR, Config
from app.llm.base import LLM, LLMErro
from app.llm.fallback import FallbackLLM
from app.llm.gemini import GeminiLLM
from app.llm.uso import UsoDiario
from app.models.schemas import Analise, ArquivoAudio, Contexto
from app.pipeline import seguranca

log = logging.getLogger("parceiro.analisador")
PROMPT_PATH = Path(__file__).resolve().parent.parent / "llm" / "prompts" / "analisador.md"


class Analisador:
    def __init__(self, llm: LLM, faq: str, template: str, fallback: LLM | None = None):
        self.llm, self.faq, self.template = llm, faq, template
        self.fallback = fallback or FallbackLLM()

    @classmethod
    def criar(cls, config: Config, sem_ia: bool = False) -> "Analisador":
        faq = (config.content_dir / "faq_kallopolli.md").read_text(encoding="utf-8")
        template = PROMPT_PATH.read_text(encoding="utf-8")
        if sem_ia or not config.gemini_api_key:
            llm: LLM = FallbackLLM()
        else:
            llm = GeminiLLM(config.gemini_api_key, config.gemini_model, reserva=config.gemini_model_reserva or None,
                            tentativas=config.gemini_tentativas, max_rpm=config.gemini_max_rpm,
                            espera_maxima=config.gemini_espera_maxima, thinking=config.gemini_thinking,
                            limites=config.gemini_limite_diario, uso=UsoDiario(BASE_DIR / "data" / "uso_gemini.json"))
        return cls(llm, faq, template)

    def _prompt(self, contexto: Contexto) -> str:
        return self.template.replace("{{contexto}}", contexto.para_texto()).replace("{{faq}}", self.faq)

    def analisar(self, texto: str | None = None, audio: ArquivoAudio | None = None,
                 contexto: Contexto | None = None) -> Analise:
        if not texto and not audio:
            raise ValueError("Informe texto ou áudio.")
        prompt = self._prompt(contexto or Contexto())
        aviso = None
        try:
            bruto, origem = self.llm.analisar(prompt, texto, audio), self.llm.nome
        except LLMErro as erro:
            bruto, origem, aviso = self.fallback.analisar(prompt, texto, audio), "fallback", str(erro)
            log.warning("IA indisponível, respondendo pelo plano B: %s", erro)
        analise = Analise.from_dict(bruto)
        analise.origem_analise, analise.aviso = origem, aviso
        return seguranca.aplicar(analise, texto)
