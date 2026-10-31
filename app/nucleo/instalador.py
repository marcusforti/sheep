import json, os, re, shutil, subprocess, sys, urllib.request
from pathlib import Path
from nucleo import caminhos, cofre, motor

MODELO = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "modelo"
WINGET = {"git": "Git.Git", "node": "OpenJS.NodeJS.LTS", "ffmpeg": "Gyan.FFmpeg"}
NPM = {"claude": "@anthropic-ai/claude-code", "codex": "@openai/codex"}
PASSOS = [
    {"id": "boas_vindas", "titulo": "Oi, eu sou a Sheep", "fala": "Vou me mudar pro seu computador. Leva uns 10 minutos."},
    {"id": "verificar", "titulo": "Olhando seu PC", "fala": "Primeiro eu vejo se tem espaço e internet."},
    {"id": "base", "titulo": "Instalando a base", "fala": "Git, Node e ffmpeg. Coisa de bastidor, relaxa."},
    {"id": "cerebros", "titulo": "Buscando meus cérebros", "fala": "Claude, Codex e Antigravity. Eu uso o que você tiver."},
    {"id": "login", "titulo": "Entra em pelo menos um", "fala": "Abre a janela, faz login e volta aqui."},
    {"id": "casa", "titulo": "Montando a minha casa", "fala": "Agora eu crio a pasta onde eu moro e aprendo."},
    {"id": "whatsapp", "titulo": "Agora no WhatsApp", "fala": "Agora me coloca no seu WhatsApp. Abre o WhatsApp no celular, vai em Aparelhos conectados e lê o QR.", "opcional": True},
    {"id": "telegram", "titulo": "Telegram também?", "fala": "Se quiser, cria um bot no Telegram e cola o token aqui. Pode pular.", "opcional": True},
    {"id": "pronto", "titulo": "Pronto, chefe", "fala": "Daqui pra frente, nada sai sem o seu sim."},
]

def _arq(): return caminhos.sub(".instalacao") / "estado.json"
def estado(): return json.loads(_arq().read_text(encoding="utf-8")) if _arq().exists() else {}
def _marca(id, v): e = estado(); e[id] = v; _arq().write_text(json.dumps(e), encoding="utf-8")
def proximo(): return next((p["id"] for p in PASSOS if estado().get(p["id"]) not in ("feito", "pulado")), None)

def _rodar(cmd):
    return subprocess.run(cmd, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode

def _internet():
    try:
        with urllib.request.urlopen("https://www.google.com", timeout=5):
            return True
    except OSError:
        return False

def completar_path():
    partes = list(filter(None, os.environ.get("PATH", "").split(os.pathsep)))
    existentes = {os.path.normcase(os.path.normpath(p)) for p in partes}
    for pasta in [r"C:\Program Files\nodejs", r"C:\Program Files\Git\cmd",
                  os.path.expandvars(r"%APPDATA%\npm"), os.path.expandvars(r"%LOCALAPPDATA%\agy\bin")]:
        chave = os.path.normcase(os.path.normpath(pasta))
        if chave not in existentes and os.path.isdir(pasta):
            partes.append(pasta); existentes.add(chave)
    os.environ["PATH"] = os.pathsep.join(partes)

def versao_node():
    node = shutil.which("node")
    if not node: return 0
    r = subprocess.run([node, "-v"], capture_output=True, text=True, timeout=5,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    versao = re.match(r"v?(\d+)\.", r.stdout.strip())
    if r.returncode != 0 or not versao: raise OSError("Não consegui verificar o Node. Abre o instalador de novo.")
    return int(versao[1])


def erro_amigavel(erro):
    if isinstance(erro, FileNotFoundError) or re.search(r"\[(?:WinError|Errno) \d+\]|ENOENT", str(erro)):
        return "Faltou um programa ou arquivo necessário. Abre o instalador da Sheep de novo para reparar."
    if isinstance(erro, (TimeoutError, subprocess.TimeoutExpired)):
        return "Essa etapa demorou demais. Tenta de novo."
    return str(erro)


def _cmds(id):
    if id == "base":
        comandos = []
        for nome, pid in WINGET.items():
            instalado = shutil.which(nome)
            if instalado and (nome != "node" or versao_node() >= 20): continue
            comandos.append(["winget", "upgrade" if instalado else "install", "-e", "--id", pid, "--accept-source-agreements", "--accept-package-agreements", "--silent"])
        return comandos
    if id == "cerebros":
        falta = [k for k, v in motor.instalados().items() if not v]
        cmds = [["npm.cmd", "install", "-g", NPM[k]] for k in falta if k in NPM]
        return cmds
    return []

def executar(id, rodar=None, log=None, pular=False):
    if pular:
        if id not in ("whatsapp", "telegram"): raise ValueError("Esse passo precisa ser concluído.")
        if id == "whatsapp":
            from nucleo import whatsapp
            cofre.guardar("WHATSAPP_LIGADO", "0")
            whatsapp.ponte().parar()
        _marca(id, "pulado")
        return True
    rodar = rodar or _rodar
    try:
        if id == "verificar":
            ok = shutil.disk_usage(caminhos.casa().anchor or "C:\\").free > 3 * 1024**3 and _internet()
        elif id == "casa":
            for origem in MODELO.rglob("*"):
                if origem.relative_to(MODELO).parts[0].lower() == "pacotes":
                    continue
                destino = caminhos.casa() / origem.relative_to(MODELO)
                if origem.is_dir():
                    destino.mkdir(parents=True, exist_ok=True)
                elif not destino.exists():
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(origem, destino)
            from nucleo import pacotes
            try: embutidos = pacotes.listar()
            except ValueError as e:
                embutidos = []
                if log: log(f"Não consegui ler os pacotes: {e}")
            for p in embutidos:
                if p.get("erro"):
                    if log: log(f"Não consegui ler o pacote {p['nome']}: {p['erro']}")
                    continue
                if p["origem"] == "embutido" and not p["instalado"]:
                    try:
                        pacotes.instalar(p["id"])
                        if log: log(f"Pacote {p['nome']} instalado.")
                    except (OSError, ValueError) as e:
                        if log: log(f"Não consegui instalar o pacote {p['nome']}: {e}")
            ok = True
        elif id in ("base", "cerebros"):
            ok = True
            for c in _cmds(id):
                if log: log("> " + " ".join(c[:4]))
                ok = rodar(c) == 0 and ok
            completar_path()
        elif id == "login":
            ok = any(motor.testar(nome) for nome, instalado in motor.instalados().items() if instalado)
        elif id == "whatsapp":
            from nucleo import whatsapp
            ok = whatsapp.estado()["estado"] == "conectado"
        elif id == "telegram":
            ok = cofre.tem("TELEGRAM_DONO")
        elif id == "pronto" and getattr(sys, "frozen", False):
            executavel = sys.executable.replace("'", "''")
            script = ("$w = New-Object -ComObject WScript.Shell; "
                      "$a = $w.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Sheep.lnk')); "
                      f"$a.TargetPath = '{executavel}'; $a.Save()")
            ok = rodar(["powershell", "-NoProfile", "-Command", script]) == 0
            if not ok and log: log("Não consegui criar o atalho, mas a Sheep está pronta.")
            ok = True
        else:
            ok = True
    except (OSError, subprocess.SubprocessError) as e:
        with (caminhos.sub("logs") / "instalador.log").open("a", encoding="utf-8") as arquivo:
            arquivo.write(f"{type(e).__name__}: {e}\n")
        if log: log(erro_amigavel(e))
        ok = id == "pronto"
    _marca(id, "feito" if ok else "falhou"); return ok
