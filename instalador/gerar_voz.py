"""Gera as falas do instalador (voz da Sheep) e empacota em voz.zip.
Uso: ELEVENLABS_API_KEY=... python gerar_voz.py PASTA_DE_TRABALHO [fala ...]"""
import json, os, subprocess, sys, urllib.request, zipfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
VOZ = "GM2UA3fbsIaLHcswCDX9"
AJUSTE = dict(stability=0.3, similarity_boost=0.8, style=0.55)

trabalho = Path(sys.argv[1]).resolve()
trabalho.mkdir(parents=True, exist_ok=True)
falas = json.loads((AQUI / "falas.json").read_text(encoding="utf-8"))

for nome in sys.argv[2:] or falas:
    corpo = json.dumps({"text": falas[nome], "model_id": "eleven_v4", "voice_settings": AJUSTE}).encode("utf-8")
    pedido = urllib.request.Request(f"https://api.elevenlabs.io/v1/text-to-speech/{VOZ}", data=corpo, method="POST",
                                    headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "Content-Type": "application/json"})
    (trabalho / f"{nome}.mp3").write_bytes(urllib.request.urlopen(pedido, timeout=180).read())
    (trabalho / f"{nome}.txt").unlink(missing_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(trabalho / f"{nome}.mp3"), "-af", "loudnorm=I=-16:TP=-1.5",
                    "-ar", "22050", "-ac", "1", "-c:a", "pcm_s16le", str(trabalho / f"{nome}.wav")], check=True)
    print(nome, flush=True)

with zipfile.ZipFile(AQUI / "voz.zip", "w", zipfile.ZIP_DEFLATED) as pacote:
    for nome in falas:
        pacote.write(trabalho / f"{nome}.wav", f"{nome}.wav")
print("voz.zip", (AQUI / "voz.zip").stat().st_size)
