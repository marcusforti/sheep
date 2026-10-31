import re
from nucleo import caminhos


def _arquivo(nome):
    if not isinstance(nome, str) or not re.fullmatch(r'[^\x00-\x1f<>:"/\\|?*]+\.md', nome) or nome.startswith("."):
        raise ValueError("Escolha um arquivo de memória válido.")
    pasta = caminhos.sub("memoria")
    p = pasta / nome
    if pasta.is_symlink() or pasta.resolve().parent != caminhos.casa().resolve() or p.is_symlink() or p.resolve().parent != pasta.resolve():
        raise ValueError("Esse arquivo não é uma memória válida desta casa.")
    if not p.is_file(): raise ValueError("Não encontrei esse arquivo de memória.")
    return p


def _partes(texto):
    linhas = texto.splitlines(keepends=True)
    if not linhas or linhas[0].strip() != "---": return [], texto
    for i, linha in enumerate(linhas[1:], 1):
        if linha.strip() == "---": return linhas[:i + 1], "".join(linhas[i + 1:])
    return [], texto


def novas():
    out = []
    for p in sorted(caminhos.sub("memoria").glob("*.md")):
        try:
            p = _arquivo(p.name)
            frente, corpo = _partes(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if not any(re.fullmatch(r"nova\s*:\s*true\s*", l.strip()) for l in frente): continue
        data = next((l.split(":", 1)[1].strip() for l in frente if l.startswith("data:")), "")
        out.append({"arquivo": p.name, "data": data, "texto": corpo.strip()})
    return out


def manter(nome):
    try:
        p = _arquivo(nome)
        with p.open("r", encoding="utf-8", newline="") as f:
            texto = f.read()
        frente, corpo = _partes(texto)
        if not frente: return
        novo = "".join(l for l in frente if not re.fullmatch(r"nova\s*:\s*true\s*", l.strip())) + corpo
        if novo != texto:
            with p.open("w", encoding="utf-8", newline="") as f:
                f.write(novo)
    except (OSError, UnicodeError) as erro:
        raise ValueError("Não consegui manter essa memória. Tente novamente.") from erro


def descartar(nome):
    try:
        _arquivo(nome).unlink()
    except OSError as erro:
        raise ValueError("Não consegui descartar essa memória. Tente novamente.") from erro
