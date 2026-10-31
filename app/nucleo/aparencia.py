"""A cara da casa: cor, tom, frase, telas e imagens que o dono escolheu.
Tudo fica em aparencia/ na casa da Sheep. O agente também pode gravar ali, então nada lido dessa pasta é confiado sem conferir."""
import base64, binascii, json, os, re, tempfile
from nucleo import caminhos

LIMITE_IMAGEM = 8 * 1024 * 1024
LIMITE_AJUSTES = 64 * 1024
ALVOS = ("rosto", "recepcao", "fundo")
TONS = {
    "preto": ("#0a0708", "#0e0a0b", "#141012", "#1b1517", "#241c1f"),
    "grafite": ("#141518", "#191a1e", "#1f2126", "#272a30", "#31343b"),
    "noite": ("#0a0e1a", "#0d1220", "#131a2c", "#1a2339", "#232e48"),
    "floresta": ("#08110d", "#0b1611", "#111f18", "#172a21", "#1f382c"),
    "vinho": ("#14060c", "#190911", "#220d17", "#2d1220", "#3a182a"),
}
TELAS = ("projetos", "pacotes", "conexoes", "status")
PADRAO = {"cor": "#e0102f", "tom": "preto", "frase": "", "fundo_forca": 18, "telas": {}}
ARQUIVO = "ajustes.json"
PARA_TIPO = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}
ALVO_DA_UI = {"rosto.jpg": "rosto", "sheep.png": "recepcao"}


def _pasta():
    return caminhos.sub("aparencia")


def _ajustes_limpos(dados):
    """Só passa o que a tela sabe usar. Valor estranho volta ao padrão em vez de quebrar a casa."""
    dados = dados if isinstance(dados, dict) else {}
    cor = str(dados.get("cor", ""))
    tom = dados.get("tom")
    frase = " ".join(str(dados.get("frase") or "").split())[:80]
    try: forca = max(0, min(60, int(dados.get("fundo_forca", PADRAO["fundo_forca"]))))
    except (TypeError, ValueError, OverflowError): forca = PADRAO["fundo_forca"]
    telas = {}
    pedidas = dados.get("telas") if isinstance(dados.get("telas"), dict) else {}
    for tela in TELAS:
        item = pedidas.get(tela)
        if not isinstance(item, dict): continue
        nome = " ".join(str(item.get("nome") or "").split())[:24]
        oculta = item.get("oculta") is True
        if nome or oculta: telas[tela] = {"nome": nome, "oculta": oculta}
    return {"cor": cor.lower() if re.fullmatch(r"#[0-9a-fA-F]{6}", cor) else PADRAO["cor"],
            "tom": tom if tom in TONS else PADRAO["tom"], "frase": frase, "fundo_forca": forca, "telas": telas}


def ler():
    try:
        arquivo = _pasta() / ARQUIVO
        if arquivo.stat().st_size > LIMITE_AJUSTES: raise ValueError("grande demais")
        return _ajustes_limpos(json.loads(arquivo.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError, RecursionError):
        return dict(PADRAO, telas={})


def gravar(dados):
    if not isinstance(dados, dict): raise ValueError("Pedido inválido.")
    limpo = _ajustes_limpos({**ler(), **dados})
    pasta = _pasta()
    fd, temporario = tempfile.mkstemp(dir=pasta, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as saida:
            json.dump(limpo, saida, ensure_ascii=False, indent=2)
        os.replace(temporario, pasta / ARQUIVO)
    except OSError:
        os.unlink(temporario)
        raise ValueError("Não consegui gravar. Tenta de novo.") from None
    return limpo


def _extensao(cabeca):
    if cabeca[:8] == b"\x89PNG\r\n\x1a\n": return ".png"
    if cabeca[:3] == b"\xff\xd8\xff": return ".jpg"
    if cabeca[:4] == b"RIFF" and cabeca[8:12] == b"WEBP": return ".webp"
    return None


def _arquivo(alvo):
    """Devolve (caminho, tipo) da imagem do alvo. Só nomes fixos, só imagem de verdade, nada de link."""
    if alvo not in ALVOS: return None
    for extensao in PARA_TIPO:
        caminho = _pasta() / f"{alvo}{extensao}"
        if caminho.is_symlink() or not caminho.is_file(): continue
        try:
            if caminho.stat().st_size > LIMITE_IMAGEM: continue
            with caminho.open("rb") as entrada:
                real = _extensao(entrada.read(16))
        except OSError:
            continue
        if real: return caminho, PARA_TIPO[real]
    return None


def imagens():
    resposta = {}
    for alvo in ALVOS:
        achado = _arquivo(alvo)
        resposta[alvo] = int(achado[0].stat().st_mtime) if achado else 0
    return resposta


def imagem_da_ui(nome):
    """rosto.jpg e sheep.png viram a imagem do dono. Sem foto de corpo inteiro, a recepção usa o rosto."""
    alvo = ALVO_DA_UI.get(nome) or ("fundo" if nome == "aparencia/fundo" else None)
    if not alvo: return None
    achado = _arquivo(alvo) or (_arquivo("rosto") if alvo == "recepcao" else None)
    if not achado: return None
    return achado[0].read_bytes(), achado[1]


def limpar(alvo):
    if alvo not in ALVOS: raise ValueError("Essa imagem não existe.")
    for extensao in PARA_TIPO:
        (_pasta() / f"{alvo}{extensao}").unlink(missing_ok=True)
    return imagens()


def guardar_imagem(alvo, conteudo):
    if alvo not in ALVOS or not isinstance(conteudo, str): raise ValueError("Pedido inválido.")
    try:
        bruto = base64.b64decode(conteudo, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("Não consegui ler essa imagem.") from None
    if len(bruto) > LIMITE_IMAGEM: raise ValueError("Essa imagem passou de 8 MB.")
    extensao = _extensao(bruto[:16])
    if not extensao: raise ValueError("Use uma imagem PNG, JPG ou WEBP.")
    limpar(alvo)
    (_pasta() / f"{alvo}{extensao}").write_bytes(bruto)
    return imagens()


def _rgb(cor):
    return tuple(int(cor[i:i + 2], 16) for i in (1, 3, 5))


def _clarear(cor, quanto=.22):
    return "#" + "".join(f"{round(v + (255 - v) * quanto):02x}" for v in _rgb(cor))


def tingir(css):
    """Troca a cor e o tom direto no estilo.css servido: vale para sombra e brilho, sem mexer no arquivo."""
    a = ler()
    if a["cor"] == PADRAO["cor"] and a["tom"] == PADRAO["tom"]: return css
    texto = css.decode("utf-8")
    r, g, b = _rgb(a["cor"])
    texto = texto.replace("#e0102f", a["cor"]).replace("#ff2d4b", _clarear(a["cor"])).replace("224,16,47", f"{r},{g},{b}")
    for original, novo in zip(TONS["preto"], TONS[a["tom"]]):
        texto = texto.replace(original, novo)
    return texto.encode("utf-8")


def identidade_completa():
    arquivo = caminhos.sub("casa") / "identidade.md"
    campos = {}
    if arquivo.exists():
        for linha in arquivo.read_text(encoding="utf-8", errors="replace").splitlines():
            if ":" in linha:
                titulo, valor = linha.split(":", 1)
                campos[titulo.strip()] = valor.strip()
    return {"nome": campos.get("Nome", "Sheep"), "personalidade": campos.get("Personalidade", ""), "fala": campos.get("Como fala", ""),
            "missao": campos.get("Missão", ""), "chama": campos.get("Como chama o dono", ""), "assinatura": campos.get("Assinatura", ""),
            "nunca": campos.get("Nunca", ""), "trocado": arquivo.exists()}


def tudo():
    return {"ajustes": ler(), "imagens": imagens(), "identidade": identidade_completa(), "casa": str(caminhos.casa()), "tons": list(TONS)}
