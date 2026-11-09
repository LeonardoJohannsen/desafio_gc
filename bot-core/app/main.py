import asyncio
import logging
from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app.api.hub import Hub
from app.api.rh import router as rh_router
from app.api.rotas import router
from app.config import BASE_DIR, Config
from app.pipeline.analisador import Analisador
from app.seed import popular, popular_demo
from app.services.cadencia import Cadencia
from app.services.conteudo import Conteudo
from app.services.conversa import Conversa
from app.services.painel import Painel
from app.services.relogio import Relogio
from app.storage.db import Banco
from app.storage.repositorio import Repositorio

log = logging.getLogger("parceiro")
logging.basicConfig(level=logging.INFO)


async def _loop_lembretes(ctx):
    """A cada 30 s reais, dispara lembretes de 24h vencidos e a cadência do dia (pelo relógio da demo)."""
    while True:
        await asyncio.sleep(30)
        try:
            saidas = await run_in_threadpool(ctx.conversa.processar_lembretes)
            saidas += await run_in_threadpool(ctx.cadencia.executar)
            await ctx.hub.enviar(saidas)
        except Exception:
            log.exception("falha no loop de lembretes")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = Config.carregar()
    (BASE_DIR / "data").mkdir(exist_ok=True)
    banco = Banco(str(BASE_DIR / "data" / "parceiro.sqlite3"))
    repo, relogio = Repositorio(banco), Relogio(banco)
    if not repo.tem_dados():
        popular(repo, relogio)
        if config.demo_dados:
            popular_demo(repo, relogio)
    analisador = Analisador.criar(config)
    log.info("IA: %s", analisador.llm.nome)
    conteudo = Conteudo.carregar(config.content_dir)
    conversa = Conversa(repo, analisador, relogio, conteudo)
    cadencia = Cadencia(repo, conversa, relogio, conteudo, config.horario_inicio, config.horario_fim)
    app.state.ctx = SimpleNamespace(banco=banco, repo=repo, relogio=relogio, hub=Hub(), conversa=conversa, cadencia=cadencia,
                                    painel=Painel(repo, relogio, conteudo), demo_dados=config.demo_dados)
    tarefa = asyncio.create_task(_loop_lembretes(app.state.ctx))
    yield
    tarefa.cancel()


app = FastAPI(title="Parceiro dos 90 dias", lifespan=lifespan)
# Liberado para qualquer origem só porque é uma demonstração local.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
app.include_router(rh_router)

_fake = BASE_DIR.parent / "whatsapp-fake"
if _fake.exists():
    app.mount("/whatsapp", StaticFiles(directory=_fake, html=True), name="whatsapp")
_painel = BASE_DIR.parent / "painel-rh"
if _painel.exists():
    app.mount("/painel", StaticFiles(directory=_painel, html=True), name="painel")
