import os, re, uuid
from pathlib import Path
from nucleo import instalador


def _substituir(texto, inicio, fim, bloco):
    achados, aberto = [], None
    for marcador in re.finditer(re.escape(inicio) + b"|" + re.escape(fim), texto):
        if marcador.group() == inicio:
            if aberto is not None:
                raise ValueError("Os marcadores do bloco estão aninhados. Confira o AGENTS.md antes de atualizar.")
            aberto = marcador.start()
        else:
            if aberto is None:
                raise ValueError("Os marcadores do bloco estão incompletos ou fora de ordem. Confira o AGENTS.md.")
            achados.append((aberto, marcador.end()))
            aberto = None
    if aberto is not None:
        raise ValueError("Os marcadores do bloco estão incompletos. Confira o AGENTS.md antes de atualizar.")
    if not achados:
        return texto + (b"\n\n" if texto else b"") + bloco if bloco else texto
    partes, posicao = [], 0
    for indice, (comeco, final) in enumerate(achados):
        partes.extend([texto[posicao:comeco], bloco if indice == 0 else b""])
        posicao = final
    return b"".join(partes) + texto[posicao:]


def atualizar_bloco_app(casa):
    arquivo = Path(casa) / "AGENTS.md"
    if not arquivo.exists():
        return False
    modelo = (instalador.MODELO / "AGENTS.md").read_bytes()
    inicio, fim = b"<!-- sheep:app:inicio -->", b"<!-- sheep:app:fim -->"
    bloco = re.search(re.escape(inicio) + b".*?" + re.escape(fim), modelo, re.DOTALL)
    if bloco is None:
        raise OSError("O modelo não contém as instruções do aplicativo.")
    antes = arquivo.read_bytes()
    partes = re.split(rb"(<!-- sheep:[^>]+:inicio -->.*?<!-- sheep:[^>]+:fim -->)", antes, flags=re.DOTALL)
    for indice in range(0, len(partes), 2):
        partes[indice] = partes[indice].replace(b"ovelha negra ciborgue", "ovelha incomparável ciborgue".encode())
        if inicio not in antes and fim not in antes:
            partes[indice] = re.sub("^## Como eu peço o sim do dono(?:\\r?\\n|\\Z).*?(?=^## |\\Z)".encode(), b"", partes[indice], flags=re.MULTILINE | re.DOTALL)
    try:
        depois = _substituir(b"".join(partes), inicio, fim, bloco.group())
    except ValueError as erro:
        raise OSError(str(erro)) from erro
    if depois == antes:
        return False
    temporario = arquivo.with_name(".AGENTS-" + uuid.uuid4().hex + ".tmp")
    try:
        temporario.write_bytes(depois)
        os.replace(temporario, arquivo)
    finally:
        temporario.unlink(missing_ok=True)
    return True


def conteudo_pacote(texto, id, instrucoes):
    inicio = f"<!-- sheep:pacote:{id}:inicio -->".encode()
    fim = f"<!-- sheep:pacote:{id}:fim -->".encode()
    bloco = inicio + b"\n" + instrucoes.rstrip(b"\r\n") + b"\n" + fim if instrucoes is not None else b""
    return _substituir(texto, inicio, fim, bloco)
