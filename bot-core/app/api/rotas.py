import logging
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.audio_utils import FFmpegErro, converter_para_wav
from app.seed import popular, popular_demo
from app.services.conversa import Saida

log = logging.getLogger("parceiro")
router = APIRouter()


class MensagemIn(BaseModel):
    telefone: str
    texto: str = ""
    opcaoId: str | None = None


class RetornoIn(BaseModel):
    telefone: str | None = None
    resultado: str


class AvancarIn(BaseModel):
    horas: float = 24


def _ctx(request: Request):
    return request.app.state.ctx


async def _executar(ctx, telefone, funcao, *args):
    """Mostra 'digitando…', roda o fluxo (em thread, porque chama o Gemini) e entrega as saídas."""
    await ctx.hub.digitando(telefone, True)
    try:
        saidas = await run_in_threadpool(funcao, *args)
    except FFmpegErro as e:
        log.exception("falha no áudio")
        saidas = [Saida(telefone, "Não consegui ouvir esse áudio. Pode tentar de novo ou escrever?")]
        log.error("ffmpeg: %s", e)
    except Exception:
        log.exception("falha ao processar a mensagem")
        saidas = [Saida(telefone, "Tive um problema aqui agora. Pode tentar de novo em instantes?")]
    await ctx.hub.enviar(saidas)
    await ctx.hub.digitando(telefone, False)
    return saidas


@router.get("/saude")
async def saude():
    return {"ok": True}


@router.post("/mensagens")
async def receber_mensagem(corpo: MensagemIn, request: Request):
    ctx = _ctx(request)
    if corpo.opcaoId:
        saidas = await _executar(ctx, corpo.telefone, ctx.conversa.processar_escolha, corpo.telefone, corpo.opcaoId)
    else:
        saidas = await _executar(ctx, corpo.telefone, ctx.conversa.processar_texto, corpo.telefone, corpo.texto)
    return {"ok": True, "enviadas": len(saidas)}


@router.post("/mensagens/audio")
async def receber_audio(request: Request, telefone: str = Form(...), duracao: float = Form(0.0),
                        audio: UploadFile = File(...)):
    ctx = _ctx(request)
    dados = await audio.read()
    extensao = Path(audio.filename or "audio.webm").suffix or ".webm"

    def tratar():
        wav = converter_para_wav(dados, extensao)
        return ctx.conversa.processar_texto(telefone, None, wav, "AUDIO")

    saidas = await _executar(ctx, telefone, tratar)
    return {"ok": True, "enviadas": len(saidas)}


@router.post("/alertas/{alerta_id}/retorno")
async def retorno(alerta_id: int, corpo: RetornoIn, request: Request):
    ctx = _ctx(request)
    try:
        saidas = await run_in_threadpool(ctx.conversa.registrar_retorno, alerta_id, corpo.resultado)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    await ctx.hub.enviar(saidas)
    return {"ok": True}


# ---------- ferramentas da demo ----------
@router.get("/simulador/estado")
async def estado(request: Request):
    ctx = _ctx(request)
    return {"agora": ctx.relogio.agora_str(), "alertas": ctx.repo.contar_alertas(), "modo_ia": ctx.conversa.analisador.llm.nome,
            "ia": getattr(ctx.conversa.analisador.llm, "status", lambda: {})()}


@router.post("/simulador/relogio/avancar")
async def avancar(corpo: AvancarIn, request: Request):
    ctx = _ctx(request)
    ctx.relogio.avancar(corpo.horas)
    lembretes = await run_in_threadpool(ctx.conversa.processar_lembretes)
    cadencia = await run_in_threadpool(ctx.cadencia.executar, True)  # na demo, ignora a janela de horário
    await ctx.hub.enviar(lembretes + cadencia)
    return {"agora": ctx.relogio.agora_str(), "lembretes_enviados": len(lembretes), "mensagens_da_cadencia": len(cadencia)}


@router.post("/simulador/cadencia/executar")
async def executar_cadencia(request: Request, ignorar_horario: bool = True):
    ctx = _ctx(request)
    saidas = await run_in_threadpool(ctx.cadencia.executar, ignorar_horario)
    await ctx.hub.enviar(saidas)
    return {"agora": ctx.relogio.agora_str(), "mensagens_da_cadencia": len(saidas)}


@router.post("/simulador/reset")
async def reset(request: Request):
    ctx = _ctx(request)
    ctx.banco.resetar()
    popular(ctx.repo, ctx.relogio)
    if ctx.demo_dados:
        popular_demo(ctx.repo, ctx.relogio)
    return {"ok": True, "mensagem": "Dados recriados. Recarregue o app fake."}


@router.websocket("/ws/{telefone}")
async def ws(websocket: WebSocket, telefone: str):
    ctx = websocket.app.state.ctx
    await ctx.hub.conectar(telefone, websocket)
    try:
        saidas = await run_in_threadpool(ctx.conversa.boas_vindas_se_preciso, telefone)
        await ctx.hub.enviar(saidas)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ctx.hub.desconectar(telefone, websocket)
