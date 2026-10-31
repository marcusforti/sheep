"""Quem está logado no Claude e no Codex, sem gastar pedido e sem travar o painel.
A consulta roda ao fundo, com tempo limite curto, e o resultado fica guardado por alguns segundos.
Só guardamos o que a tela precisa (logado, conta, como entrou). A saída crua dos programas nunca sai daqui."""
import json, os, re, shutil, subprocess, threading, time
from nucleo import cofre, motor

_Popen = subprocess.Popen
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TEMPO = 4
VALIDADE = {True: 20, False: 5}
ESPERA_INICIAL = 1.5
CHAVES = {"claude": "ANTHROPIC_API_KEY", "codex": "OPENAI_API_KEY"}
ENTRAR = {"claude": ["auth", "login"], "codex": ["login"]}
_consulta = {"claude": ["auth", "status", "--json"], "codex": ["login", "status"]}
_guardado, _fazendo, _trava = {}, set(), threading.Lock()


def _matar(processo):
    try:
        _Popen(["taskkill", "/F", "/T", "/PID", str(processo.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=SEM_JANELA).wait(3)
    except (OSError, subprocess.SubprocessError):
        processo.kill()


def _rodar(caminho, argumentos):
    """Devolve (código de saída, texto) ou None se o programa não respondeu a tempo."""
    processo = _Popen([caminho, *argumentos], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                      text=True, encoding="utf-8", errors="replace", creationflags=SEM_JANELA)
    try:
        texto, _ = processo.communicate(timeout=TEMPO)
    except subprocess.TimeoutExpired:
        _matar(processo)
        processo.communicate()
        return None
    return processo.returncode, texto or ""


def _entender(nome, resposta):
    if resposta is None:
        return {"instalado": True, "consultado": False, "logado": False}
    codigo, texto = resposta
    if nome == "claude":
        try:
            dados = json.loads(texto[texto.index("{"):])
        except (ValueError, TypeError):
            return {"instalado": True, "consultado": codigo != 0, "logado": False}
        conta = dados.get("email") if isinstance(dados.get("email"), str) else ""
        como = "" if not dados.get("loggedIn") else "assinatura" if dados.get("authMethod") == "claude.ai" else "conta da Anthropic"
        return {"instalado": True, "consultado": True, "logado": dados.get("loggedIn") is True, "conta": conta, "como": como}
    logado = codigo == 0 and "logged in" in texto.lower()
    como = "assinatura" if "chatgpt" in texto.lower() else "chave de API" if logado else ""
    return {"instalado": True, "consultado": codigo in (0, 1), "logado": logado, "conta": "", "como": como}


def _descobrir(nome):
    caminho = shutil.which(motor.MOTORES[nome])
    if not caminho:
        return {"instalado": False, "logado": False}
    try:
        achado = _entender(nome, _rodar(caminho, _consulta[nome]))
    except (OSError, subprocess.SubprocessError):
        achado = {"instalado": True, "consultado": False, "logado": False}
    if not achado["logado"] and cofre.tem(CHAVES[nome]):
        achado.update(consultado=True, logado=True, como="chave de API")
    return achado


def _atualizar(nome):
    try:
        achado = _descobrir(nome)
    except Exception:
        achado = {"instalado": True, "consultado": False, "logado": False}
    with _trava:
        _guardado[nome] = (time.monotonic(), achado)
        _fazendo.discard(nome)


def invalidar():
    with _trava:
        _guardado.clear()


def estado(espera=ESPERA_INICIAL):
    """Responde na hora com o que já sabe. Se estiver velho, confere de novo ao fundo.
    Só na primeira vez espera um pouco, para a tela já abrir com a resposta."""
    saida, fios = {}, []
    for nome in CHAVES:
        if not shutil.which(motor.MOTORES[nome]):
            saida[nome] = {"instalado": False, "logado": False}
            continue
        with _trava:
            guardado = _guardado.get(nome)
            velho = guardado is None or time.monotonic() - guardado[0] > VALIDADE[guardado[1].get("logado", False)]
            if velho and nome not in _fazendo:
                _fazendo.add(nome)
                fio = threading.Thread(target=_atualizar, args=(nome,), daemon=True)
                fio.start()
                if guardado is None: fios.append(fio)
        saida[nome] = guardado[1] if guardado else None
    prazo = time.monotonic() + espera
    for fio in fios:
        fio.join(max(0, prazo - time.monotonic()))
    with _trava:
        for nome, valor in saida.items():
            if valor is None:
                guardado = _guardado.get(nome)
                saida[nome] = guardado[1] if guardado else {"instalado": True, "consultando": True, "logado": False}
    return saida


def entrar(nome):
    """Abre o login do motor numa janela própria. Devolve False se o programa não estiver instalado."""
    from nucleo.instalador import completar_path
    completar_path()
    caminho = shutil.which(motor.MOTORES[nome])
    if not caminho:
        return False
    _Popen([caminho, *ENTRAR[nome]], creationflags=subprocess.CREATE_NEW_CONSOLE)
    invalidar()
    return True
