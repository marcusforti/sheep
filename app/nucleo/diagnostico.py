"""Texto de diagnóstico para a pessoa colar no grupo quando algo não funciona.
Regra de ouro: na dúvida, a linha fica de fora. Nada de chave, token, cofre, conversa nem nome de pessoa."""
import getpass, os, platform, re, shutil, subprocess, sys, tempfile, threading
from datetime import datetime
from pathlib import Path
from nucleo import caminhos, cofre, login, motor

SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PROGRAMAS = [("git", "git", "--version"), ("node", "node", "--version"), ("python", "python", "--version"),
             ("ffmpeg", "ffmpeg", "-version"), ("claude", "claude", "--version"), ("codex", "codex", "--version")]
LINHAS = 30
INOFENSIVAS = ("MOTOR_PADRAO", "APRENDER", "WHATSAPP_LIGADO", "WHATSAPP_VOZ")
SUSPEITA = re.compile(r"sk-|key|token|secret|senha|password|passwd|bearer|authorization|credential|cookie|cofre|@|\d{8,}|[\\/](anexos|projetos|sessoes|memoria)[\\/]|[A-Za-z0-9_\-+/=]{28,}", re.I)
EXCECAO = re.compile(r"^[A-Za-z_][\w.]*(Error|Exception|Exit|Interrupt|Expired|Timeout)\b(: .*)?$")
ARQUIVO = re.compile(r'^\s*File "[^"]+", line \d+, in \S+$')


def _nomes_de_pessoa():
    achados = {os.environ.get("USERNAME", ""), os.environ.get("USER", ""), Path.home().name}
    try: achados.add(getpass.getuser())
    except Exception: pass
    return sorted({n for n in achados if len(n) >= 3}, key=len, reverse=True)


def limpar(texto):
    """Troca o nome de quem usa o PC e qualquer valor guardado no cofre."""
    try:
        for arquivo in caminhos.cofre().iterdir():
            valor = arquivo.read_text(encoding="utf-8", errors="ignore").strip() if arquivo.is_file() else ""
            if len(valor) >= 4 and arquivo.name not in INOFENSIVAS: texto = texto.replace(valor, "<oculto>")
    except OSError: pass
    texto = re.sub(r"(?i)([A-Z]:[\\/]+Users[\\/]+)[^\\/\s\"']+", r"\1<usuario>", texto)
    texto = re.sub(r"(?i)(/(?:Users|home)/)[^/\s\"']+", r"\1<usuario>", texto)
    for nome in _nomes_de_pessoa():
        texto = re.sub(re.escape(nome), "<usuario>", texto, flags=re.I)
    return texto


def _primeira_linha(texto):
    linha = next((l.strip() for l in (texto or "").splitlines() if l.strip()), "")
    return linha.split(" Copyright")[0][:80]


def _versao(rotulo, programa, argumento, saida):
    caminho = shutil.which(programa)
    if not caminho:
        saida[rotulo] = "não encontrado"
        return
    try:
        p = subprocess.run([caminho, argumento], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=6, stdin=subprocess.DEVNULL, creationflags=SEM_JANELA)
        versao = _primeira_linha(p.stdout or p.stderr)
        if not _linha_segura(versao): versao = "(texto omitido por segurança)"
        saida[rotulo] = f"{versao or 'sem resposta'} ({caminho})"
    except subprocess.TimeoutExpired:
        saida[rotulo] = f"demorou demais para responder ({caminho})"
    except OSError:
        saida[rotulo] = f"não consegui abrir ({caminho})"


def _linha_segura(linha):
    return len(linha) <= 240 and not SUSPEITA.search(linha)


def _registro(arquivo, tracebacks):
    """Últimas linhas de um registro. Em registro de erro do programa só entram o 'onde' e o tipo do erro."""
    try:
        linhas = arquivo.read_text(encoding="utf-8", errors="replace").splitlines()[-LINHAS * 4:]
    except OSError:
        return None
    if tracebacks:
        linhas = [l for l in linhas if ARQUIVO.match(l) or l.startswith("Traceback (most recent call last)") or EXCECAO.match(l)]
    linhas = linhas[-LINHAS:]
    boas = [l.rstrip() for l in linhas if _linha_segura(l)]
    return boas, len(linhas) - len(boas)


def montar():
    saida, fios = {}, []
    for rotulo, programa, argumento in PROGRAMAS:
        fio = threading.Thread(target=_versao, args=(rotulo, programa, argumento, saida), daemon=True)
        fio.start(); fios.append(fio)
    for fio in fios: fio.join(8)
    partes = ["Diagnóstico da Sheep", f"Data: {datetime.now():%d/%m/%Y %H:%M}",
              f"Windows: {platform.system()} {platform.release()} (versão {platform.version()})",
              f"Python da Sheep: {platform.python_version()}", f"Motor padrão: {motor.padrao() or 'nenhum'}", "", "Programas"]
    partes += [f"{rotulo}: {saida.get(rotulo, 'sem resposta')}" for rotulo, _, _ in PROGRAMAS]
    partes += ["", "Login"]
    for nome, estado in login.estado(espera=8).items():
        if not estado.get("instalado"): situacao = "não instalado"
        elif estado.get("logado"): situacao = f"entrou ({estado.get('como') or 'sem detalhe'})"
        elif estado.get("consultando") or estado.get("consultado") is False: situacao = "não consegui conferir"
        else: situacao = "falta entrar"
        partes.append(f"{motor.NOMES[nome]}: {situacao}")
    for titulo, arquivo, tracebacks in (("Erros do painel", caminhos.casa() / "logs" / "servidor.log", True),
                                        ("Instalador", caminhos.casa() / "logs" / "instalador.log", False),
                                        ("Instalação no PC", Path(tempfile.gettempdir()) / "sheep-instalar.log", False)):
        lido = _registro(arquivo, tracebacks)
        if lido is None: continue
        boas, fora = lido
        partes += ["", f"{titulo} (últimas linhas)"] + (boas or ["(nada que possa ser mostrado)"])
        if fora: partes.append(f"({fora} linhas ficaram de fora por segurança)")
    return limpar("\n".join(partes))
