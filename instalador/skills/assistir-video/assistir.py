"""Baixa um vídeo público do YouTube, Instagram ou TikTok, transcreve e monta uma folha de quadros.
Uso: python assistir.py URL [quadros=24]
Saída em ~/Sheep/videos/<id>/: video.mp4, quadros.jpg, info.md."""
import json, math, re, subprocess, sys
from pathlib import Path


def yt_dlp(*args):
    return subprocess.run(["yt-dlp", "--ignore-config", "--no-warnings", "--no-playlist", *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def legenda(url, pasta):
    """YouTube costuma ter legenda: é mais rápido que transcrever."""
    yt_dlp("--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", "pt,pt-BR,en", "--sub-format", "vtt",
           "-o", str(pasta / "legenda"), url)
    arquivos = sorted(pasta.glob("legenda*.vtt"), key=lambda p: not p.name.startswith("legenda.pt"))
    if not arquivos:
        return ""
    linhas = []
    for linha in arquivos[0].read_text(encoding="utf-8", errors="replace").splitlines():
        limpa = re.sub(r"<[^>]+>", "", linha).strip()
        if limpa and "-->" not in limpa and not limpa.startswith(("WEBVTT", "Kind:", "Language:")) and limpa not in linhas[-2:]:
            linhas.append(limpa)
    return "\n".join(linhas)


def transcrever(video):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("Instalando o transcritor (só na primeira vez)...", flush=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "faster-whisper"], check=True)
        from faster_whisper import WhisperModel
    import numpy
    # O ffmpeg decodifica o áudio: o decodificador do faster-whisper quebra com a versão atual do PyAV.
    audio = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                           capture_output=True).stdout
    if not audio:
        return ""
    trechos, _ = WhisperModel("small", device="cpu", compute_type="int8").transcribe(
        numpy.frombuffer(audio, dtype=numpy.float32), language="pt", vad_filter=True)
    return "\n".join(f"[{t.start:5.1f}s] {t.text.strip()}" for t in trechos)


url = sys.argv[1]
quadros = int(sys.argv[2]) if len(sys.argv) > 2 else 24

dados = yt_dlp("-j", url)
if dados.returncode != 0:
    sys.exit("Não consegui ler esse vídeo. Ele pode ser privado, ou o site pode ter pedido login.\n" + dados.stderr[-400:])
meta = json.loads(dados.stdout)
pasta = Path.home() / "Sheep" / "videos" / re.sub(r"[^\w-]", "_", str(meta["id"]))
pasta.mkdir(parents=True, exist_ok=True)
video = pasta / "video.mp4"
if not video.exists():
    baixa = yt_dlp("-q", "-f", "best[height<=720][ext=mp4]/best[height<=720]/mp4/best", "-o", str(video), url)
    if baixa.returncode != 0 or not video.exists():
        sys.exit("Não consegui baixar esse vídeo.\n" + baixa.stderr[-400:])

duracao = float(meta.get("duration") or 0) or float(subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
    capture_output=True, text=True).stdout.strip() or 1)
# Um salto por quadro: decodificar o vídeo inteiro leva minutos em vídeo longo.
for i in range(quadros):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{duracao * (i + 0.5) / quadros:.2f}", "-i", str(video),
                    "-frames:v", "1", "-vf", "scale=270:-2", "-q:v", "4", str(pasta / f"q{i:03d}.jpg")])
subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(pasta / "q%03d.jpg"), "-vf", f"tile=6x{math.ceil(quadros / 6)}",
                "-frames:v", "1", "-q:v", "4", str(pasta / "quadros.jpg")], check=True)
for arquivo in pasta.glob("q[0-9][0-9][0-9].jpg"):
    arquivo.unlink()

texto = legenda(url, pasta) or transcrever(video) or "(sem fala)"
(pasta / "info.md").write_text(
    f"# {meta.get('uploader') or meta.get('channel') or 'Autor desconhecido'}\n\n{url}\n\n"
    f"Duração: {duracao:.0f} s\n\n## Legenda do post\n{meta.get('description') or ''}\n\n## Transcrição\n{texto}\n",
    encoding="utf-8")
print(pasta)
