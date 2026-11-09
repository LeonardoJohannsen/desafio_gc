from app.models.schemas import ArquivoAudio


class LLMErro(Exception):
    """Qualquer falha ao falar com o provedor de IA."""


class LLMIndisponivel(LLMErro):
    """Falha temporária (cota, sobrecarga, resposta inválida)."""


class LLMConfigErro(LLMErro):
    """Chave inválida, modelo inexistente etc. Precisa de ajuste de configuração."""


class LLM:
    nome = "base"

    def analisar(self, prompt_sistema: str, texto: str | None, audio: ArquivoAudio | None) -> dict:
        """Devolve um dict com os campos da análise (ver prompts/analisador.md)."""
        raise NotImplementedError
