import re
from nucleo import caminhos

_NOME = re.compile(r"^[A-Z0-9_]+$")

def _arq(nome: str):
    if not _NOME.match(nome):
        raise ValueError("nome de chave inválido")
    return caminhos.cofre() / nome

def guardar(nome: str, valor: str) -> None:
    _arq(nome).write_text(valor.strip(), encoding="utf-8")

def ler(nome: str):
    a = _arq(nome)
    return a.read_text(encoding="utf-8").strip() if a.exists() else None

def tem(nome: str) -> bool:
    return bool(ler(nome))

def apagar(nome: str) -> None:
    _arq(nome).unlink(missing_ok=True)

def status(nomes):
    return {n: tem(n) for n in nomes}
