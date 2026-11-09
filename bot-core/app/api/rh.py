"""Rotas do painel do RH. Sem login: é uma demonstração local (em produção precisaria de autenticação)."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.services.painel import Conflito

router = APIRouter(prefix="/rh")


class ColaboradorIn(BaseModel):
    nome: str
    telefone: str
    lojaId: int | None = None
    papel: str = "COLABORADOR"
    dataEntrada: str | None = None
    gerenteId: int | None = None


class ColaboradorPatch(BaseModel):
    nome: str | None = None
    lojaId: int | None = None
    gerenteId: int | None = None
    ativo: bool | None = None


class MentoriaIn(BaseModel):
    mentorId: int
    aprendizId: int


def _dados(corpo) -> dict:
    return (corpo.model_dump if hasattr(corpo, "model_dump") else corpo.dict)(exclude_unset=True)


async def _chamar(funcao, *args):
    try:
        return await run_in_threadpool(funcao, *args)
    except Conflito as e:
        raise HTTPException(409, str(e))
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/dashboard")
async def dashboard(request: Request):
    return await _chamar(request.app.state.ctx.painel.dashboard)


@router.get("/colaboradores")
async def colaboradores(request: Request):
    return await _chamar(request.app.state.ctx.painel.colaboradores)


@router.post("/colaboradores", status_code=201)
async def criar_colaborador(corpo: ColaboradorIn, request: Request):
    return await _chamar(request.app.state.ctx.painel.criar_colaborador, _dados(corpo))


@router.patch("/colaboradores/{id_}")
async def atualizar_colaborador(id_: int, corpo: ColaboradorPatch, request: Request):
    return await _chamar(request.app.state.ctx.painel.atualizar_colaborador, id_, _dados(corpo))


@router.get("/mentorias")
async def mentorias(request: Request):
    return await _chamar(request.app.state.ctx.painel.mentorias)


@router.post("/mentorias", status_code=201)
async def vincular(corpo: MentoriaIn, request: Request):
    return await _chamar(request.app.state.ctx.painel.vincular, corpo.mentorId, corpo.aprendizId)


@router.delete("/mentorias/{id_}")
async def encerrar_mentoria(id_: int, request: Request):
    return await _chamar(request.app.state.ctx.painel.encerrar_mentoria, id_)


@router.get("/insights")
async def insights(request: Request):
    return await _chamar(request.app.state.ctx.painel.insights)


@router.post("/alertas/{alerta_id}/lembrete")
async def reenviar_lembrete(alerta_id: int, request: Request):
    ctx = request.app.state.ctx
    saidas = await _chamar(ctx.conversa.reenviar_lembrete, alerta_id)
    await ctx.hub.enviar(saidas)
    return {"ok": True}
