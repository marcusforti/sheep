import json, os, re, threading, time, uuid
from nucleo import caminhos, sessoes

_trava = threading.RLock()
PADRAO = "padrao"
NOME_PADRAO = "Meus projetos"
GERAL = ""
WHATSAPP = "@whatsapp"

def _arquivo(): return caminhos.casa() / "organizacao.json"

def _gravar(dados):
    arq = _arquivo(); arq.parent.mkdir(parents=True, exist_ok=True)
    temp = arq.with_name(uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
        if arq.exists():
            try: arq.with_suffix(".json.bak").write_bytes(arq.read_bytes())
            except OSError: pass
        os.replace(temp, arq)
    finally: temp.unlink(missing_ok=True)

def _copia_das_sessoes():
    """Guarda uma vez só o projeto de cada conversa, antes da primeira organização, para dar pra voltar."""
    destino = caminhos.casa() / "organizacao-antes.json"
    if destino.exists(): return
    try:
        destino.write_text(json.dumps({s["id"]: s.get("projeto") for s in sessoes.listar()}, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError: pass

def _carregar():
    arq = _arquivo()
    if arq.exists():
        try:
            dados = json.loads(arq.read_text(encoding="utf-8"))
            if isinstance(dados, dict) and isinstance(dados.get("pastas"), list): return dados
        except (OSError, ValueError): pass
        try: arq.replace(arq.with_name(f"organizacao.corrompido-{int(time.time())}.json"))
        except OSError: pass
    else:
        _copia_das_sessoes()
    return {"versao": 1, "pastas": [], "recolhidos": [], "nomes": {}}

def _normaliza(dados, projetos):
    todos = [GERAL, *sorted(projetos, key=lambda p: p.casefold()), WHATSAPP]
    existentes, vistos, pastas = set(todos), set(), []
    for p in dados.get("pastas", []):
        if not isinstance(p, dict) or not isinstance(p.get("id"), str) or not isinstance(p.get("nome"), str): continue
        itens = []
        for chave in p.get("projetos", []):
            if isinstance(chave, str) and chave in existentes and chave not in vistos: vistos.add(chave); itens.append(chave)
        pastas.append({"id": p["id"], "nome": p["nome"], "projetos": itens})
    padrao = next((p for p in pastas if p["id"] == PADRAO), None)
    if padrao is None:
        padrao = {"id": PADRAO, "nome": NOME_PADRAO, "projetos": []}; pastas.insert(0, padrao)
    padrao["projetos"].extend(c for c in todos if c not in vistos)
    ids = {p["id"] for p in pastas}
    validas = {f"pasta:{i}" for i in ids} | {f"proj:{c}" for c in existentes}
    recolhidos = [c for c in dados.get("recolhidos", []) if c in validas]
    nomes = {c: n for c, n in (dados.get("nomes") or {}).items() if c in existentes and isinstance(n, str) and n.strip()}
    return {"versao": 1, "pastas": pastas, "recolhidos": recolhidos, "nomes": nomes}

def _nome_valido(nome, rotulo):
    if not isinstance(nome, str): raise ValueError(f"Escolha um nome para {rotulo}.")
    nome = " ".join(nome.split())
    if not nome or len(nome) > 60 or any(ord(c) < 32 for c in nome): raise ValueError(f"Use um nome de 1 a 60 caracteres para {rotulo}.")
    return nome

def estado(projetos):
    with _trava:
        dados = _normaliza(_carregar(), projetos)
        if not _arquivo().exists():
            try: _gravar(dados)
            except OSError: pass
        return dados

def _alterar(projetos, funcao):
    with _trava:
        dados = _normaliza(_carregar(), projetos)
        resultado = funcao(dados)
        _gravar(dados)
        return resultado

def _pasta(dados, id):
    pasta = next((p for p in dados["pastas"] if p["id"] == id), None)
    if pasta is None: raise ValueError("Essa pasta não existe mais.")
    return pasta

def criar_pasta(projetos, nome):
    nome = _nome_valido(nome, "a pasta")
    def faz(dados):
        if any(p["nome"].casefold() == nome.casefold() for p in dados["pastas"]): raise ValueError("Já existe uma pasta com esse nome.")
        pasta = {"id": uuid.uuid4().hex[:10], "nome": nome, "projetos": []}
        dados["pastas"].append(pasta); return pasta
    return _alterar(projetos, faz)

def renomear_pasta(projetos, id, nome):
    nome = _nome_valido(nome, "a pasta")
    def faz(dados):
        pasta = _pasta(dados, id)
        if any(p["id"] != id and p["nome"].casefold() == nome.casefold() for p in dados["pastas"]): raise ValueError("Já existe uma pasta com esse nome.")
        pasta["nome"] = nome
    return _alterar(projetos, faz)

def excluir_pasta(projetos, id):
    def faz(dados):
        if id == PADRAO: raise ValueError("A pasta padrão não pode ser excluída.")
        pasta = _pasta(dados, id)
        _pasta(dados, PADRAO)["projetos"].extend(pasta["projetos"])
        dados["pastas"].remove(pasta)
        dados["recolhidos"] = [c for c in dados["recolhidos"] if c != f"pasta:{id}"]
    return _alterar(projetos, faz)

def mover_projeto(projetos, chave, id):
    def faz(dados):
        if chave not in {c for p in dados["pastas"] for c in p["projetos"]}: raise ValueError("Esse projeto não existe mais.")
        destino = _pasta(dados, id)
        for p in dados["pastas"]:
            if chave in p["projetos"]: p["projetos"].remove(chave)
        destino["projetos"].append(chave)
    return _alterar(projetos, faz)

def adotar_projeto(projetos, chave, id):
    """Põe um projeto recém-criado na pasta escolhida."""
    return mover_projeto(projetos, chave, id or PADRAO)

def renomear_projeto(projetos, chave, nome):
    def faz(dados):
        if chave in (GERAL, WHATSAPP) or chave not in {c for p in dados["pastas"] for c in p["projetos"]}: raise ValueError("Esse projeto não pode ser renomeado.")
        if isinstance(nome, str) and not nome.strip(): dados["nomes"].pop(chave, None)
        else: dados["nomes"][chave] = _nome_valido(nome, "o projeto")
    return _alterar(projetos, faz)

def esquecer_projeto(projetos):
    """Chamada depois de apagar um projeto: `projetos` já é a lista sem ele. Tira dele a pasta, o nome e o recolhido."""
    return _alterar(projetos, lambda dados: None)

def esquecer_conversas(ids):
    """Tira as conversas apagadas da cópia de segurança da organização antiga."""
    with _trava:
        arq = caminhos.casa() / "organizacao-antes.json"
        try:
            dados = json.loads(arq.read_text(encoding="utf-8"))
            if not isinstance(dados, dict) or not any(i in dados for i in ids): return
            arq.write_text(json.dumps({k: v for k, v in dados.items() if k not in ids}, ensure_ascii=False, indent=1), encoding="utf-8")
        except (OSError, ValueError): pass

def recolher(projetos, chave, recolhido):
    def faz(dados):
        validas = {f"pasta:{p['id']}" for p in dados["pastas"]} | {f"proj:{c}" for p in dados["pastas"] for c in p["projetos"]}
        if not isinstance(chave, str) or chave not in validas: raise ValueError("Item desconhecido.")
        dados["recolhidos"] = [c for c in dados["recolhidos"] if c != chave]
        if recolhido: dados["recolhidos"].append(chave)
    return _alterar(projetos, faz)
