import json, os, threading, time, uuid
from nucleo import caminhos

_criacao = threading.Lock()
_ultima_criada = 0
_dados = threading.RLock()
_modos = {}

def _pasta(id): return caminhos.sub("sessoes") / id

def _meta(id):
    meta = json.loads((_pasta(id) / "sessao.json").read_text(encoding="utf-8"))
    meta.pop('modo_unico', None)
    if _modos.get(str(_pasta(id))): meta['modo_unico'] = True
    return meta

def _grava(meta):
    p = _pasta(meta["id"]); p.mkdir(parents=True, exist_ok=True)
    meta['revisao'] = meta.get('revisao',0) + 1
    temporario = p / (uuid.uuid4().hex + ".tmp")
    try:
        temporario.write_text(json.dumps({k:v for k,v in meta.items() if k != 'modo_unico'}, ensure_ascii=False), encoding="utf-8")
        for tentativa in range(5):
            try:
                os.replace(temporario, p / "sessao.json")
                break
            except PermissionError:
                if tentativa == 4: raise
                time.sleep(.03)
    finally: temporario.unlink(missing_ok=True)

def criar(titulo, projeto=None, motor="claude"):
    global _ultima_criada
    with _criacao:
        _ultima_criada = max(time.time_ns(), _ultima_criada + 1)
        criada = _ultima_criada
    meta = {"id": uuid.uuid4().hex[:12], "titulo": titulo, "projeto": projeto, "motor": motor,
            "motor_id": None, "criada": criada}
    with _dados: _grava(meta)
    return meta

def listar():
    with _dados:
        out = [_meta(d.name) for d in caminhos.sub("sessoes").iterdir() if (d / "sessao.json").exists()]
        return sorted(out, key=lambda m: m["criada"], reverse=True)

def anexar(id, quem, texto):
    with _dados:
        with open(_pasta(id) / "mensagens.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"quem": quem, "texto": texto, "ts": int(time.time())}, ensure_ascii=False) + "\n")
        _grava(_meta(id))

def ler(id):
    with _dados:
        meta = _meta(id); arq = _pasta(id) / "mensagens.jsonl"
        meta["mensagens"] = [json.loads(l) for l in arq.read_text(encoding="utf-8").splitlines()] if arq.exists() else []
        return meta

def atualizar(id, **campos):
    with _dados:
        if 'modo_unico' in campos: _modos[str(_pasta(id))] = campos['modo_unico']
        meta = _meta(id); meta.update(campos); _grava(meta); return meta


def registrar_motor_id(id, motor_id):
    with _dados:
        if _meta(id).get('motor_id') != motor_id: atualizar(id, motor_id=motor_id)


def registrar_uso(id, usados, janela, gasto=None):
    with _dados:
        meta = _meta(id)
        contexto = meta.get("contexto", {})
        meta["contexto"] = {"usados": usados, "janela": janela, "base": contexto.get("base", usados)}
        meta["tokens_total"] = meta.get("tokens_total", 0) + (usados if gasto is None else gasto)
        meta['contexto_estimado'] = False
        _grava(meta)


def somar_gasto(id, usados):
    with _dados:
        meta = _meta(id)
        meta['tokens_total'] = meta.get('tokens_total', 0) + usados
        _grava(meta)
