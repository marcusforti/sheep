import json, os, shutil, uuid
from pathlib import Path
from nucleo import cofre

CHAVES = ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN")


def _arquivo():
    return Path(os.environ.get("SHEEP_CLAUDE_HOME") or Path.home()) / ".claude" / "settings.json"


def _ler():
    arq = _arquivo()
    if not arq.exists():
        return {}
    try:
        dados = json.loads(arq.read_text(encoding="utf-8"))
    except ValueError:
        raise ValueError("A configuração do Claude neste computador está com defeito. Não mexi nela.")
    if not isinstance(dados, dict):
        raise ValueError("A configuração do Claude neste computador está com defeito. Não mexi nela.")
    return dados


def _gravar(dados):
    arq = _arquivo()
    arq.parent.mkdir(parents=True, exist_ok=True)
    temp = arq.with_name(f".{uuid.uuid4().hex}.tmp")
    try:
        temp.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, arq)
    finally:
        temp.unlink(missing_ok=True)


def _permitido():
    if os.environ.get("SHEEP_HOME") and not os.environ.get("SHEEP_CLAUDE_HOME"):
        raise ValueError("Numa casa de teste eu não mexo na configuração do computador.")


def estado():
    try:
        return {"ligado": all(k in (_ler().get("env") or {}) for k in CHAVES)}
    except (OSError, ValueError):
        return {"ligado": False}


def ligar():
    """Faz o Claude do terminal e do Orca usarem a chave da revenda, no lugar do login por assinatura."""
    _permitido()
    chave, url = cofre.ler("ANTHROPIC_API_KEY"), cofre.ler("ANTHROPIC_BASE_URL")
    if not chave or not url:
        raise ValueError("Salve a chave e o \"de onde vem\" antes.")
    dados = _ler()
    arq = _arquivo()
    copia = arq.with_name("settings.antes-da-sheep.json")
    if arq.exists() and not copia.exists():
        shutil.copy2(arq, copia)
    dados.setdefault("env", {}).update({"ANTHROPIC_BASE_URL": url, "ANTHROPIC_AUTH_TOKEN": chave})
    _gravar(dados)
    return estado()


def desligar():
    """Tira só as duas linhas da chave: o resto da configuração da pessoa fica como estava."""
    _permitido()
    dados = _ler()
    env = dados.get("env") or {}
    for nome in CHAVES:
        env.pop(nome, None)
    if not env:
        dados.pop("env", None)
    _gravar(dados)
    return estado()
