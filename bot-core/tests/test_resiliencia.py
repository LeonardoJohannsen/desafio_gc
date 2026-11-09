import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.llm.base import LLMConfigErro, LLMIndisponivel
from app.llm.gemini import GeminiLLM
from app.llm.resiliencia import classificar, espera_sugerida


class Erro(Exception):
    def __init__(self, code, msg=""):
        super().__init__(msg)
        self.code = code


E429 = lambda msg="Please retry in 13.2s": Erro(429, f"429 RESOURCE_EXHAUSTED. {msg}")


class Relogio:
    def __init__(self):
        self.t, self.dormidos = 0.0, []

    def agora(self):
        return self.t

    def dormir(self, s):
        self.dormidos.append(s)
        self.t += s


class Roteiro:
    """Devolve, em ordem, as reações programadas (exceção ou texto)."""

    def __init__(self, *reacoes):
        self.reacoes, self.chamadas = list(reacoes), []

    def __call__(self, modelo, partes, config):
        self.chamadas.append(modelo)
        r = self.reacoes.pop(0) if self.reacoes else '{"intencao":"CONVERSA"}'
        if isinstance(r, Exception):
            raise r
        return r


OK = '{"intencao": "CONVERSA", "resposta": "oi"}'


def llm(roteiro, relogio=None, **kw):
    relogio = relogio or Relogio()
    kw.setdefault("max_rpm", 0)
    kw.setdefault("aleatorio", lambda: 0.0)
    return GeminiLLM("k", "principal", relogio=relogio.agora, dormir=relogio.dormir, gerar=roteiro, **kw), relogio


class TestClassificacao(unittest.TestCase):
    def test_le_o_tempo_sugerido(self):
        self.assertEqual(espera_sugerida(Exception("Please retry in 13.2s.")), 13.2)
        self.assertEqual(espera_sugerida(Exception("{'retryDelay': '34s'}")), 34.0)
        self.assertIsNone(espera_sugerida(Exception("erro qualquer")))

    def test_tipos(self):
        self.assertEqual(classificar(Erro(401)).tipo, "config")
        self.assertEqual(classificar(Erro(404)).tipo, "config")
        self.assertEqual(classificar(E429()).tipo, "limite")
        self.assertEqual(classificar(E429("GenerateRequestsPerDayPerProjectPerModel-FreeTier")).tipo, "cota_diaria")
        self.assertEqual(classificar(Erro(503, "overloaded")).tipo, "transitorio")
        self.assertEqual(classificar(ConnectionError("rede")).tipo, "transitorio")


class TestTentativas(unittest.TestCase):
    def test_sucesso_direto_nao_espera(self):
        r = Roteiro(OK)
        m, rel = llm(r)
        self.assertEqual(m.analisar("p", "oi", None)["resposta"], "oi")
        self.assertEqual((len(r.chamadas), rel.dormidos), (1, []))

    def test_429_espera_o_tempo_que_a_api_pediu(self):
        r = Roteiro(E429("Please retry in 13.2s"), OK)
        m, rel = llm(r)
        m.analisar("p", "oi", None)
        self.assertEqual(len(r.chamadas), 2)
        self.assertGreaterEqual(rel.dormidos[0], 13.7)

    def test_espera_cresce_a_cada_falha(self):
        r = Roteiro(Erro(503), Erro(503), Erro(503), Erro(503), OK)
        m, rel = llm(r, espera_maxima=120)
        m.analisar("p", "oi", None)
        self.assertEqual(rel.dormidos, [1.0, 2.0, 4.0, 8.0])

    def test_json_invalido_tenta_de_novo(self):
        r = Roteiro("isso não é json", OK)
        m, _ = llm(r)
        self.assertEqual(m.analisar("p", "oi", None)["intencao"], "CONVERSA")
        self.assertEqual(len(r.chamadas), 2)

    def test_esgotou_as_tentativas(self):
        r = Roteiro(*[Erro(503)] * 5)
        m, _ = llm(r, tentativas=3, espera_maxima=120)
        with self.assertRaises(LLMIndisponivel):
            m.analisar("p", "oi", None)
        self.assertEqual(len(r.chamadas), 3)

    def test_chave_invalida_nao_insiste(self):
        r = Roteiro(Erro(401, "API key not valid"))
        m, rel = llm(r)
        with self.assertRaises(LLMConfigErro):
            m.analisar("p", "oi", None)
        self.assertEqual((len(r.chamadas), rel.dormidos), (1, []))


class TestLimitesEReserva(unittest.TestCase):
    def test_espera_longa_demais_vai_para_o_modelo_de_reserva(self):
        r = Roteiro(E429("Please retry in 120s"), OK)
        m, rel = llm(r, reserva="reserva", espera_maxima=45)
        m.analisar("p", "oi", None)
        self.assertEqual(r.chamadas, ["principal", "reserva"])
        self.assertLess(sum(rel.dormidos), 45)

    def test_cota_diaria_pula_para_reserva_sem_esperar(self):
        r = Roteiro(E429("GenerateRequestsPerDayPerProjectPerModel-FreeTier"), OK)
        m, rel = llm(r, reserva="reserva")
        m.analisar("p", "oi", None)
        self.assertEqual((r.chamadas, rel.dormidos), (["principal", "reserva"], []))

    def test_cota_diaria_sem_reserva_falha_rapido_e_nao_chama_de_novo(self):
        r = Roteiro(E429("GenerateRequestsPerDayPerProjectPerModel-FreeTier"))
        m, _ = llm(r)
        for _ in range(2):
            with self.assertRaises(LLMIndisponivel):
                m.analisar("p", "oi", None)
        self.assertEqual(len(r.chamadas), 1)  # a 2ª mensagem nem chegou a bater na API
        self.assertIn("principal", m.status()["em_espera_s"])

    def test_limite_por_minuto_espaca_as_chamadas(self):
        r = Roteiro(OK, OK)
        m, rel = llm(r, max_rpm=6)  # 1 chamada a cada 10 s
        m.analisar("p", "a", None)
        m.analisar("p", "b", None)
        self.assertEqual(rel.dormidos, [10.0])

    def test_sem_reserva_repetido_nao_duplica_modelo(self):
        m, _ = llm(Roteiro(), reserva="principal")
        self.assertEqual(m.modelos, ["principal"])


class TestConfigPorModelo(unittest.TestCase):
    def tipos(self, falha_thinking=False):
        from types import SimpleNamespace as NS

        def pensar(**kw):
            if falha_thinking:
                raise TypeError("campo desconhecido")
            return NS(**kw)
        return NS(GenerateContentConfig=lambda **kw: NS(**kw), ThinkingConfig=pensar,
                  AutomaticFunctionCallingConfig=lambda **kw: NS(**kw))

    def cfg(self, modelo, **kw):
        m, _ = llm(Roteiro(), **kw)
        m._types = self.tipos()
        return m._config(modelo, "prompt")

    def test_gemini3_usa_thinking_minimal_e_nao_mexe_na_temperatura(self):
        c = self.cfg("gemini-3.5-flash")
        self.assertEqual(c.thinking_config.thinking_level, "minimal")
        self.assertFalse(hasattr(c, "temperature"))
        self.assertTrue(c.automatic_function_calling.disable)

    def test_gemini25_flash_desliga_o_raciocinio_por_orcamento(self):
        c = self.cfg("gemini-2.5-flash")
        self.assertEqual(c.thinking_config.thinking_budget, 0)
        self.assertEqual(c.temperature, 0.2)

    def test_thinking_vazio_nao_configura(self):
        self.assertFalse(hasattr(self.cfg("gemini-3.5-flash", thinking=""), "thinking_config"))

    def test_sdk_antigo_nao_quebra(self):
        m, _ = llm(Roteiro())
        m._types = self.tipos(falha_thinking=True)
        self.assertFalse(hasattr(m._config("gemini-3.5-flash", "p"), "thinking_config"))


if __name__ == "__main__":
    unittest.main()
