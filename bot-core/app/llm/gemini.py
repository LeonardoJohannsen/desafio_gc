import json
import logging
import random
import re
import threading
import time

from app.llm.base import LLM, LLMConfigErro, LLMIndisponivel
from app.llm.resiliencia import Limitador, classificar
from app.models.schemas import ArquivoAudio

log = logging.getLogger("parceiro.gemini")
PEDIDO_AUDIO = "O colaborador enviou um áudio. Transcreva a fala em português e analise."
BLOQUEIO_COTA_DIARIA_S = 3600


def _extrair_json(bruto: str) -> dict:
    bruto = (bruto or "").strip()
    if bruto.startswith("```"):
        bruto = re.sub(r"^```(?:json)?\s*|\s*```$", "", bruto)
    dado = json.loads(bruto)
    if not isinstance(dado, dict):
        raise ValueError("a resposta não é um objeto JSON")
    return dado


class GeminiLLM(LLM):
    """Gemini com tentativas de espera crescente, respeito ao 'tente de novo em X s', limite de chamadas
    por minuto e modelo de reserva (cada modelo costuma ter a sua própria cota)."""
    nome = "gemini"

    def __init__(self, api_key: str, modelo: str, reserva: str | None = None, tentativas: int = 5,
                 max_rpm: float = 10, espera_maxima: float = 45.0, relogio=time.monotonic, dormir=time.sleep,
                 aleatorio=random.random, gerar=None, thinking: str = "minimal", uso=None, limites=None):
        self.modelos = [m for i, m in enumerate([modelo, reserva]) if m and m not in [modelo, reserva][:i]]
        self.tentativas, self.espera_maxima = tentativas, espera_maxima
        self.thinking = (thinking or "").strip().lower()
        self.relogio, self.dormir, self.aleatorio = relogio, dormir, aleatorio
        self.limitador = Limitador(max_rpm, relogio)
        self.uso, self.limites = uso, limites or {}  # limites: {modelo: chamadas por dia}
        self._fila = threading.Lock()  # uma chamada por vez: evita estampida quando chegam várias mensagens juntas
        self._types = None
        self.ultima_falha: str | None = None
        if gerar is not None:  # usado nos testes
            self._gerar = gerar
            return
        try:
            from google import genai
            from google.genai import types
        except ImportError as e:
            raise LLMConfigErro("Biblioteca ausente. Rode: pip install -r requirements.txt") from e
        self._types = types
        self._client = genai.Client(api_key=api_key)
        self._gerar = self._gerar_real

    # ---------- chamada real ----------
    def _gerar_real(self, modelo, partes, prompt_sistema) -> str:
        config = self._config(modelo, prompt_sistema)
        return self._client.models.generate_content(model=modelo, contents=partes, config=config).text

    def _config(self, modelo: str, prompt_sistema: str):
        """Configuração por modelo. Classificar mensagem curta não precisa de raciocínio longo:
        o padrão do Gemini 3.x é 'medium', que só deixa a resposta mais lenta e mais cara."""
        t = self._types
        kw = {"system_instruction": prompt_sistema, "response_mime_type": "application/json"}
        gemini3 = modelo.startswith("gemini-3")
        if not gemini3:
            kw["temperature"] = 0.2  # no Gemini 3.x o Google recomenda manter a temperatura padrão
        afc = getattr(t, "AutomaticFunctionCallingConfig", None)
        if afc:  # não usamos ferramentas: desliga a chamada automática de funções
            kw["automatic_function_calling"] = afc(disable=True)
        pensar = getattr(t, "ThinkingConfig", None)
        if pensar and self.thinking:
            try:
                if gemini3:
                    kw["thinking_config"] = pensar(thinking_level=self.thinking)
                elif "2.5-flash" in modelo:
                    kw["thinking_config"] = pensar(thinking_budget=0)
            except (TypeError, ValueError):
                log.warning("SDK sem suporte a thinking_level. Rode: pip install -U google-genai")
        return t.GenerateContentConfig(**kw)

    def _montar(self, prompt_sistema, texto, audio):
        t = self._types
        if t is None:
            return [texto or PEDIDO_AUDIO], prompt_sistema
        partes = ([t.Part.from_bytes(data=audio.dados, mime_type=audio.mime)] if audio else []) + [texto or PEDIDO_AUDIO]
        return partes, prompt_sistema

    # ---------- interface ----------
    def analisar(self, prompt_sistema: str, texto: str | None, audio: ArquivoAudio | None) -> dict:
        partes, prompt = self._montar(prompt_sistema, texto, audio)
        with self._fila:
            return self._com_tentativas(partes, prompt)

    def status(self) -> dict:
        return {"modelos": self.modelos, "ultima_falha": self.ultima_falha,
                "chamadas_hoje": self.uso.todos() if self.uso else {}, "limite_diario": self.limites,
                "em_espera_s": {m: round(self.limitador.restante(m), 1) for m in self.modelos if self.limitador.restante(m) > 0}}

    def _backoff(self, tentativa: int) -> float:
        return min(30.0, 2.0 ** tentativa) + self.aleatorio()  # ~1s, 2s, 4s, 8s, 16s (+ até 1s de variação)

    def _com_tentativas(self, partes, prompt_sistema) -> dict:
        inicio = self.relogio()
        for modelo in self.modelos:
            for tentativa in range(self.tentativas):
                limite = self.limites.get(modelo)
                if limite and self.uso and self.uso.total(modelo) >= limite:
                    self.ultima_falha = f"{modelo}: limite diário configurado ({limite} chamadas) atingido"
                    break  # guarda o resto da cota: vai para o modelo de reserva ou para o plano B
                espera = self.limitador.preparar(modelo, self.espera_maxima - (self.relogio() - inicio))
                if espera is None:  # esperar mais que o orçamento: tenta o modelo de reserva
                    self.ultima_falha = self.ultima_falha or f"{modelo} em espera por limite de uso"
                    break
                if espera > 0:
                    log.info("Gemini %s: aguardando %.1fs para respeitar o limite", modelo, espera)
                    self.dormir(espera)
                self.limitador.marcar_chamada()
                if self.uso:
                    self.uso.registrar(modelo)  # conta toda tentativa que chega na API (uma 429 também pode contar)
                try:
                    return _extrair_json(self._gerar(modelo, partes, prompt_sistema))
                except (json.JSONDecodeError, ValueError) as e:
                    self.ultima_falha = f"{modelo}: resposta inválida ({e})"
                    self.dormir(0.5 * (tentativa + 1))
                except Exception as e:
                    classe = classificar(e)
                    if classe.tipo == "config":
                        raise LLMConfigErro(f"O Gemini recusou o pedido ({getattr(e, 'code', '?')}): {e}") from e
                    self.ultima_falha = f"{modelo}: {classe.tipo} ({str(e)[:400]})"
                    if classe.tipo == "cota_diaria":
                        log.warning("Gemini %s: cota diária esgotada", modelo)
                        self.limitador.bloquear(modelo, BLOQUEIO_COTA_DIARIA_S)
                        break
                    espera_nova = max((classe.espera or 0) + 0.5, self._backoff(tentativa))
                    log.warning("Gemini %s: %s, nova tentativa em %.0fs (%d/%d). Detalhe: %s", modelo, classe.tipo,
                                espera_nova, tentativa + 1, self.tentativas, str(e)[:300])
                    self.limitador.bloquear(modelo, espera_nova)
        raise LLMIndisponivel(f"Gemini indisponível ({self.ultima_falha or 'sem detalhes'})")
