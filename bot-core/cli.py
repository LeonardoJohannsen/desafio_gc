"""Testa o classificador pelo terminal (sem servidor)."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

from app.audio_utils import FFmpegErro, carregar_arquivo
from app.config import BASE_DIR, Config
from app.llm.uso import UsoDiario
from app.models.schemas import Contexto
from app.pipeline.analisador import Analisador


def imprimir(analise):
    print(json.dumps(analise.to_dict(), ensure_ascii=False, indent=2))


class LLMComCache:
    """Só para o --casos: repetir o mesmo caso não gasta chamada (a cota diária é pequena)."""

    def __init__(self, llm, caminho):
        self.llm, self.caminho, self.nome = llm, Path(caminho), llm.nome
        self.chamadas = self.acertos = 0
        self._cache = json.loads(self.caminho.read_text(encoding="utf-8")) if self.caminho.exists() else {}

    def analisar(self, prompt, texto, audio):
        if audio is not None:
            return self.llm.analisar(prompt, texto, audio)
        chave = hashlib.sha1(("|".join(getattr(self.llm, "modelos", [])) + "\0" + prompt + "\0" + texto).encode()).hexdigest()
        if chave in self._cache:
            self.acertos += 1
            return dict(self._cache[chave])
        self.chamadas += 1
        resultado = self.llm.analisar(prompt, texto, audio)
        self._cache[chave] = resultado
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.caminho.write_text(json.dumps(self._cache, ensure_ascii=False), encoding="utf-8")
        return resultado


def mostrar_uso(config):
    uso = UsoDiario(BASE_DIR / "data" / "uso_gemini.json").todos()
    modelos = sorted(set(uso) | set(config.gemini_limite_diario) | {config.gemini_model})
    print("Chamadas de hoje (dia da cota do Google, fuso do Pacífico):")
    for m in modelos:
        limite = config.gemini_limite_diario.get(m)
        print(f"  {m}: {uso.get(m, 0)}" + (f" de {limite} (limite configurado)" if limite else " (sem limite configurado)"))


def rodar_casos(analisador, caminho, maximo=None, todos=False):
    casos = json.loads(Path(caminho).read_text(encoding="utf-8"))
    if maximo:
        casos = casos[:maximo]
    elif not todos:
        casos = [c for c in casos if c.get("essencial")] or casos[:5]  # amostra padrão: 5 casos
    if analisador.llm.nome == "gemini":
        print(f"Atenção: até {len(casos)} chamadas ao Gemini (cada uma conta na cota do dia; caso repetido vem do cache).\n", file=sys.stderr)
    acertos, total, falhas = {}, {}, []
    for caso in casos:
        a = analisador.analisar(texto=caso["texto"]).to_dict()
        for campo, esperado in caso["esperado"].items():
            total[campo] = total.get(campo, 0) + 1
            if a[campo] == esperado:
                acertos[campo] = acertos.get(campo, 0) + 1
            else:
                falhas.append(f'  "{caso["texto"][:60]}" -> {campo}: esperado {esperado}, veio {a[campo]} ({a["origem_analise"]})')
    print(f"{len(casos)} casos analisados" + (" (amostra; use --todos para rodar todos)" if not todos and not maximo else "") + "\n")
    for campo in total:
        n = acertos.get(campo, 0)
        print(f"{campo:13s} {n}/{total[campo]}  ({100 * n / total[campo]:.0f}%)")
    if falhas:
        print("\nDivergências:")
        print("\n".join(falhas))
    if isinstance(analisador.llm, LLMComCache):
        print(f"\nChamadas à API: {analisador.llm.chamadas} (reaproveitadas do cache: {analisador.llm.acertos})")


def conversar(analisador, nome, dia):
    contexto = Contexto(nome=nome, dia_jornada=dia)
    print('Conversa de teste. Digite "sair" para encerrar.\n')
    while True:
        try:
            texto = input(f"{nome}: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if texto.lower() in ("sair", "exit", "quit"):
            break
        if not texto:
            continue
        a = analisador.analisar(texto=texto, contexto=contexto)
        print(f"Bot: {a.resposta}")
        print(f"     [{a.intencao.value} | {a.sinal.value} | gravidade {a.gravidade.value} | avisar: {a.destinatario.value} | {a.origem_analise}]")
        if a.aviso:
            print(f"     aviso: {a.aviso}")
        contexto.historico += [("colaborador", texto), ("assistente", a.resposta)]
        contexto.resumo = a.resumo_contexto or contexto.resumo


def main():
    p = argparse.ArgumentParser(description="Classificador do Parceiro dos 90 dias")
    p.add_argument("texto", nargs="?", help="mensagem do colaborador")
    p.add_argument("--audio", help="arquivo de áudio (wav, webm, ogg, mp3, m4a)")
    p.add_argument("--casos", help="JSON de casos rotulados para medir a precisão")
    p.add_argument("--chat", action="store_true", help="conversa interativa")
    p.add_argument("--sem-ia", action="store_true", help="usa só o plano B (sem Gemini)")
    p.add_argument("--todos", action="store_true", help="com --casos: roda todos os casos (uma chamada por caso)")
    p.add_argument("--sem-cache", action="store_true", help="com --casos: ignora o cache")
    p.add_argument("--uso", action="store_true", help="mostra quantas chamadas ao Gemini já foram feitas hoje")
    p.add_argument("--max", type=int, help="com --casos: roda só os N primeiros (economiza cota)")
    p.add_argument("--nome", default="Ana")
    p.add_argument("--dia", type=int, default=1)
    args = p.parse_args()

    config = Config.carregar()
    analisador = Analisador.criar(config, sem_ia=args.sem_ia)
    modo = analisador.llm.nome
    print(f"[modo: {modo}" + (f", modelo {config.gemini_model}" if modo == "gemini" else ", sem GEMINI_API_KEY ou --sem-ia") + "]\n", file=sys.stderr)

    if args.uso:
        mostrar_uso(config)
    elif args.casos:
        if modo == "gemini" and not args.sem_cache:
            analisador.llm = LLMComCache(analisador.llm, BASE_DIR / "data" / "cache_casos.json")
        rodar_casos(analisador, args.casos, args.max, args.todos)
    elif args.chat:
        conversar(analisador, args.nome, args.dia)
    elif args.audio:
        try:
            audio = carregar_arquivo(args.audio)
        except (FFmpegErro, OSError) as e:
            sys.exit(f"Erro ao ler o áudio: {e}")
        imprimir(analisador.analisar(audio=audio, contexto=Contexto(args.nome, args.dia)))
    elif args.texto:
        imprimir(analisador.analisar(texto=args.texto, contexto=Contexto(args.nome, args.dia)))
    else:
        p.print_help()


if __name__ == "__main__":
    main()
