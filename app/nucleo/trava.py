import msvcrt
import json, urllib.request


def avisar_instancia(caminho, post=None):
    try:
        instancia = json.loads(caminho.read_text(encoding="utf-8"))
        req = urllib.request.Request(f"http://127.0.0.1:{instancia['porta']}/api/mostrar", method="POST",
                                     headers={"X-Token": instancia["token"]})
        resposta = (post or urllib.request.urlopen)(req, timeout=3)
        resposta.close()
    except (OSError, ValueError, KeyError, TypeError):
        pass


def obter_trava(caminho):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    arquivo = caminho.open("a+b")
    try:
        arquivo.seek(0)
        msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        arquivo.close()
        return None
    return arquivo
