import os, re, shutil, subprocess, unicodedata
from pathlib import Path
from nucleo import caminhos

CAMPOS = [("nome", "Nome"), ("personalidade", "Personalidade"), ("fala", "Como fala"), ("missao", "Missão"),
          ("chama", "Como chama o dono"), ("assinatura", "Assinatura"), ("nunca", "Nunca")]


def _arquivo():
    return caminhos.sub("casa") / "identidade.md"


def ler():
    if not _arquivo().exists():
        return {"nome": "Sheep", "trocado": False}
    achado = re.search(r"^Nome:\s*(.+)$", _arquivo().read_text(encoding="utf-8"), re.MULTILINE)
    return {"nome": achado[1].strip() if achado else "Sheep", "trocado": True}


def comando(nome):
    limpo = unicodedata.normalize("NFD", nome.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", limpo)


def _atalhos(nome):
    """Só na casa de verdade: um teste com SHEEP_HOME não mexe no computador."""
    if os.environ.get("SHEEP_HOME"):
        return
    binarios = Path.home() / ".local" / "bin"
    apelido = comando(nome)
    if apelido and (binarios / "sheep.cmd").exists():
        shutil.copy2(binarios / "sheep.cmd", binarios / f"{apelido}.cmd")
    script = ("$d = [Environment]::GetFolderPath('Desktop'); $a = Join-Path $d 'Sheep.lnk'; "
              "if (Test-Path $a) { Rename-Item -LiteralPath $a -NewName $env:SHEEP_NOVO_ATALHO -Force }")
    subprocess.run(["powershell", "-NoProfile", "-Command", script], env={**os.environ, "SHEEP_NOVO_ATALHO": f"{nome}.lnk"},
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=20)


def gravar(dados):
    nome = str(dados.get("nome", "")).strip()
    if not 2 <= len(nome) <= 30 or not comando(nome) or re.search(r'[<>:"/\\|?*]', nome):
        raise ValueError("Escolha um nome de 2 a 30 letras, sem símbolos.")
    linhas = [f"{titulo}: {' '.join(str(dados.get(chave, '')).split())}" for chave, titulo in CAMPOS]
    _arquivo().write_text("\n".join(linhas) + "\n", encoding="utf-8")
    try:
        _atalhos(nome)
    except (OSError, subprocess.SubprocessError):
        pass
    return ler()
