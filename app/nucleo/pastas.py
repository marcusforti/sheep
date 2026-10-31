import json, os, subprocess
from pathlib import Path
from nucleo import caminhos

DIALOGO = """
Add-Type -AssemblyName System.Windows.Forms
$dono = New-Object System.Windows.Forms.Form
$dono.TopMost = $true; $dono.Opacity = 0; $dono.ShowInTaskbar = $false
$dono.Show(); $dono.Activate()
$janela = New-Object System.Windows.Forms.FolderBrowserDialog
$janela.Description = 'Escolha a pasta do seu projeto'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
if ($janela.ShowDialog($dono) -eq 'OK') { $janela.SelectedPath }
$dono.Close()
"""


def escolher():
    """Abre a janela de pastas do Windows, porque o navegador não entrega o caminho real."""
    r = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", DIALOGO], capture_output=True, encoding="utf-8",
                       errors="ignore", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=600)
    return r.stdout.strip().splitlines()[-1].strip() if r.stdout.strip() else ""


def validar(caminho):
    pasta = Path(str(caminho or "").strip().strip('"'))
    if not pasta.is_absolute() or not pasta.is_dir():
        raise ValueError("Não achei essa pasta no computador.")
    pasta = pasta.resolve()
    sistema = Path(os.environ.get("WINDIR", r"C:\Windows")).resolve()
    if pasta == Path(pasta.anchor) or pasta == Path.home() or pasta == sistema or sistema in pasta.parents:
        raise ValueError("Escolha a pasta do projeto, não a do sistema nem o disco inteiro.")
    casa = caminhos.casa().resolve()
    if pasta == casa or casa in pasta.parents:
        raise ValueError("Essa pasta já é a casa da Sheep.")
    return pasta


def ligar(nome, pasta):
    """O projeto segue dentro da casa, para a Sheep manter identidade e memória, e ganha acesso à pasta real."""
    projeto = caminhos.sub("projetos") / nome
    casa = caminhos.casa().resolve()
    (projeto / ".claude").mkdir(parents=True, exist_ok=True)
    (projeto / ".pasta").write_text(str(pasta), encoding="utf-8")
    (projeto / ".claude" / "settings.local.json").write_text(json.dumps({"permissions": {"additionalDirectories": [str(pasta)]}}, ensure_ascii=False, indent=2), encoding="utf-8")
    texto = (f"# Projeto {nome}\n\nA pasta real deste projeto é `{pasta}`. Leio e gravo os arquivos do projeto lá, não aqui.\n\n"
             f"Quem eu sou, minhas regras e a memória do dono continuam em `{casa / 'AGENTS.md'}`, `{casa / 'casa'}` e `{casa / 'memoria'}`: leio antes de começar.\n")
    (projeto / "AGENTS.md").write_text(texto, encoding="utf-8")
    (projeto / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    return projeto


def externa(nome):
    arquivo = caminhos.sub("projetos") / str(nome or "") / ".pasta"
    return arquivo.read_text(encoding="utf-8").strip() if nome and arquivo.exists() else ""


def todas():
    return {d.name: externa(d.name) for d in caminhos.sub("projetos").iterdir() if d.is_dir() and externa(d.name)}
