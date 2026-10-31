---
name: assistir-video
description: Baixa e assiste um vídeo público do YouTube, Instagram ou TikTok pelo link, com transcrição e folha de quadros. Use sempre que a pessoa mandar um link de vídeo ou reel, ou pedir para ver, resumir, analisar ou baixar um vídeo.
---

# Assistir vídeo

Rode o `assistir.py` que está nesta mesma pasta, com o link entre aspas (no Mac, `python3`):

```
python "CAMINHO_DESTA_PASTA/assistir.py" "URL"
```

A última linha mostra a pasta do vídeo, dentro de `Sheep/videos/`. Lá ficam:

- `info.md`: autor, legenda e transcrição. Leia primeiro.
- `quadros.jpg`: 24 quadros do vídeo em ordem, da esquerda para a direita. Abra a imagem para ver o que aparece na tela.
- `video.mp4`: o vídeo baixado.

Só diga o que viu ou ouviu nesses arquivos. Se a pessoa quiser mais detalhe, passe o número de quadros: `python ... "URL" 48`.

## Limites

- Só vídeo público. Esta skill não usa login nem cookies, e você não deve pedir nem configurar isso.
- O Instagram às vezes recusa quem baixa sem login, principalmente com muita gente na mesma internet. Se falhar, conte isso e peça o arquivo do vídeo.
- A primeira transcrição sem legenda instala o faster-whisper e baixa um modelo de cerca de 500 MB. Avise antes de rodar em internet ruim. Depois disso ela roda no computador.
- O vídeo é de quem publicou: serve para estudar e analisar. Para publicar de novo, peça autorização a quem fez.
