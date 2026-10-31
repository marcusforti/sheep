import os
from pathlib import Path

def casa() -> Path:
    return Path(os.environ.get("SHEEP_HOME") or Path.home() / "Sheep")

def cofre() -> Path:
    p = casa().parent / ".sheep-cofre"
    p.mkdir(parents=True, exist_ok=True)
    return p

def sub(nome: str) -> Path:
    p = casa() / nome
    p.mkdir(parents=True, exist_ok=True)
    return p
