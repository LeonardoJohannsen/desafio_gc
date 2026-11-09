import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.audio_utils import converter_para_wav
from app.llm.base import LLM, LLMIndisponivel
from app.llm.fallback import FallbackLLM
from app.models.schemas import Analise, ArquivoAudio, Destinatario, Gravidade, Intencao, Sinal
from app.pipeline.analisador import Analisador


class FakeLLM(LLM):
    nome = "fake"

    def __init__(self, resposta=None):
        self.resposta = resposta or {"intencao": "CONVERSA", "resposta": "Oi!"}

    def analisar(self, prompt_sistema, texto, audio):
        return dict(self.resposta)


class LLMFora(LLM):
    nome = "fora"

    def analisar(self, prompt_sistema, texto, audio):
        raise LLMIndisponivel("cota estourada")


def analisador(llm):
    return Analisador(llm, faq="FAQ de teste", template="CTX={{contexto}} FAQ={{faq}}")


class TestSchemas(unittest.TestCase):
    def test_valores_invalidos_viram_padrao_seguro(self):
        a = Analise.from_dict({"intencao": "XYZ", "sinal": None, "confianca": "abc", "destinatario": "CEO"})
        self.assertEqual(a.intencao, Intencao.CONVERSA)
        self.assertEqual(a.sinal, Sinal.NENHUM)
        self.assertEqual(a.destinatario, Destinatario.NENHUM)
        self.assertEqual(a.confianca, 0.0)
        self.assertTrue(a.resposta)

    def test_to_dict_usa_strings(self):
        d = Analise.from_dict({"intencao": "duvida"}).to_dict()
        self.assertEqual(d["intencao"], "DUVIDA")


class TestSeguranca(unittest.TestCase):
    def analisar(self, texto):
        return analisador(FakeLLM()).analisar(texto=texto)

    def test_assedio_vai_para_rh(self):
        a = self.analisar("Meu chefe fica me assediando todo dia")
        self.assertEqual(a.destinatario, Destinatario.RH)
        self.assertEqual(a.gravidade, Gravidade.ALTA)
        self.assertTrue(a.escalado_por_regra)
        self.assertIn("ok", a.resposta)

    def test_negacao_nao_escala(self):
        self.assertEqual(self.analisar("Não teve assédio nenhum aqui").destinatario, Destinatario.NENHUM)

    def test_negacao_de_outra_coisa_nao_protege(self):
        self.assertEqual(self.analisar("Não aguento mais o assédio").destinatario, Destinatario.RH)

    def test_crise_traz_cvv_e_rh(self):
        a = self.analisar("às vezes penso em me matar")
        self.assertEqual(a.destinatario, Destinatario.RH)
        self.assertIn("188", a.resposta)

    def test_risco_fisico_vai_para_gerente(self):
        a = self.analisar("deu choque na tomada da cozinha")
        self.assertEqual(a.destinatario, Destinatario.GERENTE)

    def test_regra_nao_rebaixa_a_ia(self):
        llm = FakeLLM({"intencao": "RECLAMACAO", "destinatario": "RH", "gravidade": "ALTA", "resposta": "Posso avisar o RH?"})
        a = analisador(llm).analisar(texto="sofri assédio")
        self.assertFalse(a.escalado_por_regra)
        self.assertEqual(a.resposta, "Posso avisar o RH?")

    def test_usa_transcricao_do_audio(self):
        llm = FakeLLM({"intencao": "RECLAMACAO", "transcricao": "ele fez piada machista de novo", "resposta": "Poxa."})
        a = analisador(llm).analisar(audio=ArquivoAudio(b"x"))
        self.assertEqual(a.destinatario, Destinatario.RH)


class TestFallback(unittest.TestCase):
    def test_ia_fora_usa_plano_b_e_avisa(self):
        a = analisador(LLMFora()).analisar(texto="Estou exausto, dobrei turno")
        self.assertEqual(a.origem_analise, "fallback")
        self.assertIn("cota", a.aviso)
        self.assertEqual(a.sinal, Sinal.SOBRECARGA)
        self.assertEqual(a.destinatario, Destinatario.GERENTE)

    def test_duvida_simples(self):
        a = analisador(FallbackLLM()).analisar(texto="Como troco de turno?")
        self.assertEqual(a.intencao, Intencao.DUVIDA)

    def test_audio_sem_ia_pede_texto(self):
        a = analisador(FallbackLLM()).analisar(audio=ArquivoAudio(b"x"))
        self.assertIn("escrever", a.resposta)

    def test_entrada_vazia_e_erro(self):
        with self.assertRaises(ValueError):
            analisador(FakeLLM()).analisar()


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg não instalado")
class TestAudio(unittest.TestCase):
    def test_converte_webm_para_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            webm = Path(tmp) / "t.webm"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                            "-c:a", "libopus", str(webm)], check=True)
            r = converter_para_wav(webm.read_bytes(), "webm")
        self.assertEqual(r.mime, "audio/wav")
        self.assertEqual(r.dados[:4], b"RIFF")


if __name__ == "__main__":
    unittest.main()
