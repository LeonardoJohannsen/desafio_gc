import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import _ler_limites
from app.llm.base import LLMIndisponivel
from app.llm.uso import UsoDiario
from tests.test_resiliencia import OK, Roteiro, llm


class TestUso(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.arq = Path(self.tmp.name) / "uso.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_conta_e_persiste(self):
        UsoDiario(self.arq).registrar("a")
        u = UsoDiario(self.arq)
        u.registrar("a")
        u.registrar("b")
        self.assertEqual(UsoDiario(self.arq).todos(), {"a": 2, "b": 1})

    def test_zera_no_dia_seguinte(self):
        t = [datetime(2026, 11, 8, 20, 0, tzinfo=timezone.utc)]
        u = UsoDiario(self.arq, agora=lambda: t[0])
        u.registrar("a")
        t[0] += timedelta(hours=14)  # passou da meia-noite do Pacífico
        self.assertEqual(u.total("a"), 0)

    def test_soma_entre_processos(self):
        a, b = UsoDiario(self.arq), UsoDiario(self.arq)
        a.registrar("m")
        b.registrar("m")
        self.assertEqual(UsoDiario(self.arq).total("m"), 2)

    def test_arquivo_corrompido_nao_quebra(self):
        self.arq.write_text("{lixo", encoding="utf-8")
        self.assertEqual(UsoDiario(self.arq).total("a"), 0)

    def test_ler_limites(self):
        self.assertEqual(_ler_limites("gemini-3.5-flash-lite:450, gemini-3.5-flash:18"),
                         {"gemini-3.5-flash-lite": 450, "gemini-3.5-flash": 18})
        self.assertEqual(_ler_limites(""), {})
        self.assertEqual(_ler_limites("sem-numero:abc"), {})


class TestLimiteDiario(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.uso = UsoDiario(Path(self.tmp.name) / "uso.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_para_de_chamar_ao_atingir_o_limite(self):
        r = Roteiro(OK, OK, OK)
        m, _ = llm(r, uso=self.uso, limites={"principal": 2})
        m.analisar("p", "1", None)
        m.analisar("p", "2", None)
        with self.assertRaises(LLMIndisponivel):
            m.analisar("p", "3", None)
        self.assertEqual(len(r.chamadas), 2)
        self.assertIn("limite diário configurado", m.status()["ultima_falha"])

    def test_vai_para_a_reserva_quando_o_principal_atinge_o_limite(self):
        r = Roteiro(OK, OK)
        m, _ = llm(r, reserva="reserva", uso=self.uso, limites={"principal": 1})
        m.analisar("p", "1", None)
        m.analisar("p", "2", None)
        self.assertEqual(r.chamadas, ["principal", "reserva"])
        self.assertEqual(m.status()["chamadas_hoje"], {"principal": 1, "reserva": 1})

    def test_retentativas_tambem_contam(self):
        from tests.test_resiliencia import Erro
        r = Roteiro(Erro(503), OK)
        m, _ = llm(r, uso=self.uso, espera_maxima=60)
        m.analisar("p", "1", None)
        self.assertEqual(self.uso.total("principal"), 2)


class TestCacheDoCli(unittest.TestCase):
    def test_repetir_o_caso_nao_chama_a_api(self):
        import cli
        with tempfile.TemporaryDirectory() as tmp:
            r = Roteiro(OK)
            m, _ = llm(r)
            c = cli.LLMComCache(m, Path(tmp) / "cache.json")
            c.analisar("prompt", "texto", None)
            c.analisar("prompt", "texto", None)
            c2 = cli.LLMComCache(m, Path(tmp) / "cache.json")  # nova execução do comando
            c2.analisar("prompt", "texto", None)
            self.assertEqual(len(r.chamadas), 1)
            self.assertEqual((c.chamadas, c.acertos, c2.acertos), (1, 1, 1))

    def test_casos_essenciais_sao_cinco(self):
        casos = json.loads((Path(__file__).parent / "casos_rotulados.json").read_text(encoding="utf-8"))
        self.assertEqual(sum(c.get("essencial", False) for c in casos), 5)


if __name__ == "__main__":
    unittest.main()
