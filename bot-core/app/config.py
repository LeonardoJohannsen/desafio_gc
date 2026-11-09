import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _ler_env(caminho: Path) -> dict:
    valores = {}
    if caminho.exists():
        for linha in caminho.read_text(encoding="utf-8-sig").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            valores[chave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def _ler_limites(texto: str) -> dict:
    """'modelo-a:450,modelo-b:18' -> {'modelo-a': 450, 'modelo-b': 18}"""
    limites = {}
    for par in texto.split(","):
        if ":" in par:
            modelo, _, n = par.rpartition(":")
            if modelo.strip() and n.strip().isdigit():
                limites[modelo.strip()] = int(n)
    return limites


@dataclass(frozen=True)
class Config:
    gemini_api_key: str
    gemini_model: str
    content_dir: Path
    horario_inicio: int = 9
    horario_fim: int = 20
    gemini_model_reserva: str = ""
    gemini_max_rpm: float = 10
    gemini_tentativas: int = 5
    gemini_espera_maxima: float = 45.0
    gemini_thinking: str = "minimal"
    gemini_limite_diario: dict = field(default_factory=dict)
    demo_dados: bool = True

    @classmethod
    def carregar(cls) -> "Config":
        env = {**_ler_env(BASE_DIR / ".env"), **os.environ}
        return cls(
            gemini_api_key=env.get("GEMINI_API_KEY", "").strip(),
            gemini_model=env.get("GEMINI_MODEL", "gemini-2.5-flash").strip(),
            content_dir=BASE_DIR / "content",
            horario_inicio=int(env.get("HORARIO_INICIO", "9")),
            horario_fim=int(env.get("HORARIO_FIM", "20")),
            gemini_model_reserva=env.get("GEMINI_MODEL_RESERVA", "").strip(),
            gemini_max_rpm=float(env.get("GEMINI_MAX_RPM", "10")),
            gemini_tentativas=int(env.get("GEMINI_TENTATIVAS", "5")),
            gemini_espera_maxima=float(env.get("GEMINI_ESPERA_MAXIMA_S", "45")),
            gemini_thinking=env.get("GEMINI_THINKING", "minimal").strip(),
            gemini_limite_diario=_ler_limites(env.get("GEMINI_LIMITE_DIARIO", "")),
            demo_dados=env.get("DEMO_DADOS", "1").strip().lower() not in ("0", "false", "nao", "não"),
        )
