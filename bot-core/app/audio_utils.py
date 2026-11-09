import shutil
import subprocess
import tempfile
from pathlib import Path

from app.models.schemas import ArquivoAudio


class FFmpegErro(Exception):
    pass


def converter_para_wav(dados: bytes, extensao: str = "webm") -> ArquivoAudio:
    """Converte qualquer áudio (webm/ogg/m4a/mp3...) para WAV mono 16 kHz usando o ffmpeg."""
    if shutil.which("ffmpeg") is None:
        raise FFmpegErro("ffmpeg não encontrado no PATH.")
    extensao = extensao.lstrip(".").lower() or "webm"
    with tempfile.TemporaryDirectory() as tmp:
        entrada, saida = Path(tmp) / f"in.{extensao}", Path(tmp) / "out.wav"
        entrada.write_bytes(dados)
        proc = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(entrada), "-ac", "1", "-ar", "16000", str(saida)],
            capture_output=True,
        )
        if proc.returncode != 0 or not saida.exists():
            raise FFmpegErro(proc.stderr.decode("utf-8", "ignore").strip() or "falha ao converter o áudio")
        return ArquivoAudio(dados=saida.read_bytes(), mime="audio/wav")


def carregar_arquivo(caminho: str) -> ArquivoAudio:
    p = Path(caminho)
    return converter_para_wav(p.read_bytes(), p.suffix)
