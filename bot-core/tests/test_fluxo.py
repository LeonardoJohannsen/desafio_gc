import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.llm.base import LLM
from app.models.schemas import ArquivoAudio
from app.pipeline.analisador import Analisador
from app.seed import popular
from app.services.conversa import Conversa
from app.services.relogio import Relogio
from app.storage.db import Banco
from app.storage.repositorio import Repositorio

ANA, MARCOS, HELENA, JOAO = "5551999990001", "5551999990002", "5551999990004", "5551999990011"


class LLMRoteirizado(LLM):
    nome = "roteiro"

    def analisar(self, prompt_sistema, texto, audio):
        t = (texto or "") + " " + ("piada machista" if audio else "")
        if "cansad" in t:
            return {"intencao": "RECLAMACAO", "sinal": "CANSACO", "gravidade": "MEDIA", "destinatario": "GERENTE",
                    "resposta": "Poxa, dia puxado. Posso avisar o seu gerente? Só aviso com o seu ok.",
                    "sugestao_acao": "vale uma conversa ainda hoje", "resumo_alerta": "A pessoa relatou cansaço.",
                    "resumo_contexto": "Relatou cansaço."}
        if "machista" in t:
            return {"intencao": "RECLAMACAO", "sinal": "SITUACAO_GRAVE", "gravidade": "ALTA", "destinatario": "RH",
                    "transcricao": "ele fez piada machista", "resposta": "Sinto muito. Posso avisar o RH?",
                    "resumo_alerta": "Relato de comentário machista."}
        return {"intencao": "CONVERSA", "resposta": "Que bom! Como foi o resto do dia?"}


class FluxoBase(unittest.TestCase):
    def setUp(self):
        banco = Banco()
        self.repo, self.relogio = Repositorio(banco), Relogio(banco)
        popular(self.repo, self.relogio)
        analisador = Analisador(LLMRoteirizado(), faq="", template="{{contexto}}{{faq}}")
        self.c = Conversa(self.repo, analisador, self.relogio)

    def aceitar_ana(self):
        self.c.boas_vindas_se_preciso(ANA)
        self.c.processar_escolha(ANA, "ACEITO")

    def ana_pede_alerta(self, texto="estou muito cansado"):
        self.aceitar_ana()
        return self.c.processar_texto(ANA, texto)

    def alerta_aberto(self):
        self.ana_pede_alerta()
        saidas = self.c.processar_escolha(ANA, "AVISAR")
        return next(s for s in saidas if s.alerta_id), saidas


class TestPrimeiroContato(FluxoBase):
    def test_boas_vindas_uma_vez_e_explica_transparencia(self):
        s = self.c.boas_vindas_se_preciso(ANA)
        self.assertEqual(len(s), 1)
        self.assertIn("SEMPRE te pergunto", s[0].texto)
        self.assertEqual([o["id"] for o in s[0].opcoes], ["ACEITO", "AGORA_NAO"])
        self.assertEqual(self.c.boas_vindas_se_preciso(ANA), [])

    def test_sem_aceite_nao_conversa(self):
        self.c.boas_vindas_se_preciso(ANA)
        s = self.c.processar_texto(ANA, "estou cansado")
        self.assertIn("ok", s[0].texto)
        self.assertIsNone(self.repo.alerta_pendente(self.repo.colaborador_por_telefone(ANA).id))

    def test_aceite_por_texto(self):
        self.c.boas_vindas_se_preciso(ANA)
        self.c.processar_texto(ANA, "sim")
        self.assertIsNotNone(self.repo.colaborador_por_telefone(ANA).consentimento_em)

    def test_telefone_desconhecido(self):
        self.assertIn("cadastro", self.c.processar_texto("000", "oi")[0].texto)

    def test_gerente_escrevendo_recebe_orientacao(self):
        self.assertIn("botões", self.c.processar_texto(MARCOS, "oi")[0].texto)


class TestAlerta(FluxoBase):
    def test_sinal_pede_confirmacao_e_nao_avisa_ninguem_antes(self):
        s = self.ana_pede_alerta()
        self.assertEqual([x.para for x in s], [ANA])
        self.assertEqual([o["id"] for o in s[0].opcoes], ["AVISAR", "NAO_AVISAR"])
        self.assertEqual(self.repo.contar_alertas(), {"AGUARDANDO_CONFIRMACAO": 1})

    def test_confirmar_avisa_gerente_com_botoes_e_abre_alerta(self):
        alerta_msg, saidas = self.alerta_aberto()
        self.assertEqual({s.para for s in saidas}, {ANA, MARCOS})
        self.assertEqual(alerta_msg.para, MARCOS)
        self.assertIn("Sugestão: vale uma conversa ainda hoje", alerta_msg.texto)
        self.assertEqual([o["id"] for o in alerta_msg.opcoes], ["CONVERSEI", "NAO_CONSEGUIU"])
        a = self.repo.alerta(alerta_msg.alerta_id)
        self.assertEqual((a.estado, a.canal), ("ABERTO", "GERENTE"))
        self.assertIsNotNone(a.lembrete_em)

    def test_confirmar_por_texto(self):
        self.ana_pede_alerta()
        s = self.c.processar_texto(ANA, "pode sim")
        self.assertEqual({x.para for x in s}, {ANA, MARCOS})

    def test_recusar_guarda_so_como_contexto(self):
        self.ana_pede_alerta()
        s = self.c.processar_escolha(ANA, "NAO_AVISAR")
        self.assertEqual([x.para for x in s], [ANA])
        self.assertEqual(self.repo.contar_alertas(), {"SO_CONTEXTO": 1})

    def test_retorno_conversei_atende_e_nao_repete(self):
        msg, _ = self.alerta_aberto()
        s = self.c.registrar_retorno(msg.alerta_id, "CONVERSEI")
        self.assertEqual(s[0].para, MARCOS)
        self.assertEqual(self.repo.alerta(msg.alerta_id).estado, "ATENDIDO")
        self.assertIn("encerrado", self.c.registrar_retorno(msg.alerta_id, "CONVERSEI")[0].texto)

    def test_nao_consegui_fica_registrado(self):
        msg, _ = self.alerta_aberto()
        self.c.registrar_retorno(msg.alerta_id, "NAO_CONSEGUIU")
        self.assertEqual(self.repo.alerta(msg.alerta_id).estado, "NAO_CONSEGUIU")

    def test_retorno_invalido(self):
        with self.assertRaises(ValueError):
            self.c.registrar_retorno(1, "TALVEZ")
        with self.assertRaises(LookupError):
            self.c.registrar_retorno(999, "CONVERSEI")

    def test_lembrete_so_depois_de_24h_e_uma_vez(self):
        msg, _ = self.alerta_aberto()
        self.relogio.avancar(23)
        self.assertEqual(self.c.processar_lembretes(), [])
        self.relogio.avancar(2)
        s = self.c.processar_lembretes()
        self.assertEqual([x.para for x in s], [MARCOS])
        self.assertIn("Lembrete", s[0].texto)
        self.assertEqual(self.repo.alerta(msg.alerta_id).estado, "SEM_RESPOSTA_24H")
        self.assertEqual(self.c.processar_lembretes(), [])

    def test_retorno_depois_do_lembrete_ainda_atende(self):
        msg, _ = self.alerta_aberto()
        self.relogio.avancar(25)
        self.c.processar_lembretes()
        self.c.registrar_retorno(msg.alerta_id, "CONVERSEI")
        self.assertEqual(self.repo.alerta(msg.alerta_id).estado, "ATENDIDO")

    def test_atendido_nao_gera_lembrete(self):
        msg, _ = self.alerta_aberto()
        self.c.registrar_retorno(msg.alerta_id, "CONVERSEI")
        self.relogio.avancar(30)
        self.assertEqual(self.c.processar_lembretes(), [])


class TestRHeAudio(FluxoBase):
    def test_audio_sensivel_vai_para_rh_com_sigilo(self):
        self.aceitar_ana()
        s = self.c.processar_texto(ANA, None, ArquivoAudio(b"x"), "AUDIO")
        self.assertIn("RH", s[0].texto)
        out = self.c.processar_escolha(ANA, "AVISAR")
        self.assertEqual({x.para for x in out}, {ANA, HELENA})
        self.assertIn("🔒", next(x for x in out if x.para == HELENA).texto)
        self.assertEqual(self.repo.contar_alertas(), {"ABERTO": 1})
        msg = self.repo.ultimas_mensagens(self.repo.colaborador_por_telefone(ANA).id)
        self.assertIn("ele fez piada machista", [t for _, t in msg])  # transcrição guardada

    def test_alerta_do_rh_nao_vai_para_o_gerente(self):
        self.aceitar_ana()
        self.c.processar_texto(ANA, None, ArquivoAudio(b"x"), "AUDIO")
        out = self.c.processar_escolha(ANA, "AVISAR")
        self.assertNotIn(MARCOS, {x.para for x in out})


class TestPausa(FluxoBase):
    def test_parar_e_voltar(self):
        self.aceitar_ana()
        self.assertIn("pausar", self.c.processar_texto(ANA, "parar")[0].texto)
        self.assertIn("pausado", self.c.processar_texto(ANA, "estou cansado")[0].texto)
        self.assertEqual(self.repo.contar_alertas(), {})
        self.assertIn("de volta", self.c.processar_texto(ANA, "voltar")[0].texto)
        self.assertEqual(self.c.processar_texto(ANA, "oi")[0].texto, "Que bom! Como foi o resto do dia?")


class TestContexto(FluxoBase):
    def test_resumo_e_historico_alimentam_a_proxima_analise(self):
        self.ana_pede_alerta()
        ana = self.repo.colaborador_por_telefone(ANA)
        self.assertEqual(ana.resumo_contexto, "Relatou cansaço.")
        self.assertGreaterEqual(len(self.repo.ultimas_mensagens(ana.id)), 2)

    def test_dia_da_jornada_segue_o_relogio(self):
        ana = self.repo.colaborador_por_telefone(ANA)
        self.assertEqual(self.c._dia(ana), 6)
        self.relogio.avancar(48)
        self.assertEqual(self.c._dia(ana), 8)


if __name__ == "__main__":
    unittest.main()
