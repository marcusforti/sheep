import json, os, re, subprocess, threading, time, uuid
from pathlib import Path
from nucleo import caminhos

_lock = threading.Lock()
_avisos_lock = threading.Lock()
_avisando = set()

def _arq(id):
    if not isinstance(id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", id):
        raise ValueError("Esse código de aprovação não vale. Confere e manda de novo.")
    return caminhos.sub("aprovacoes") / f"{id}.json"
def _grava(a): _arq(a["id"]).write_text(json.dumps(a, ensure_ascii=False), encoding="utf-8")

def _ler(p):
    try:
        a = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        a = None
    if not isinstance(a, dict):
        p.rename(p.with_suffix(".invalido"))
        return None
    if any(k not in a for k in ("id", "estado", "criado")):
        a.setdefault("id", p.stem)
        a.setdefault("estado", "pendente")
        a.setdefault("criado", p.stat().st_mtime)
        p.write_text(json.dumps(a, ensure_ascii=False), encoding="utf-8")
    return a

def pedir(tipo, previa, destino, comando):
    a = {"id": uuid.uuid4().hex[:10], "tipo": tipo, "previa": previa, "destino": destino,
         "comando": comando, "estado": "pendente", "criado": int(time.time())}
    with _lock: _grava(a)
    return a

def pendentes():
    with _lock:
        todos = [_ler(p) for p in caminhos.sub("aprovacoes").glob("*.json")]
    return sorted([a for a in todos if a is not None and a["estado"] == "pendente"], key=lambda a: a["criado"])

def marcar_sessao(id, sessao):
    with _lock:
        a = _ler(_arq(id))
        if a is None: return None
        if a.get("sessao"): return a
        a["sessao"] = sessao
        _grava(a)
        return a

def da_sessao(id):
    with _lock:
        todos = [_ler(p) for p in caminhos.sub("aprovacoes").glob("*.json")]
    return sorted([a for a in todos if a is not None and a.get("sessao") == id], key=lambda a: a["criado"])

def _rodar(cmd):
    return subprocess.run(cmd, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode

def _ler_avisos(arquivo):
    try:
        avisos = json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else {}
        if not isinstance(avisos, dict) or any(not isinstance(v, list) for k, v in avisos.items() if k != "tentativas") or not isinstance(avisos.get("tentativas", {}), dict):
            raise ValueError()
        return avisos
    except ValueError:
        invalido = arquivo.with_suffix(".invalido")
        if invalido.exists(): invalido = arquivo.with_suffix("." + uuid.uuid4().hex + ".invalido")
        arquivo.rename(invalido)
        arquivo.write_text("{}", encoding="utf-8")
        return {}


def avisar_novas(canal, enviar):
    arquivo = caminhos.casa() / ".avisos_aprovacao.json"
    with _avisos_lock:
        _ler_avisos(arquivo)
    for a in pendentes():
        chave = canal + ":" + a["id"]
        reserva = (str(arquivo), chave)
        with _avisos_lock:
            avisos = _ler_avisos(arquivo)
            tentativa = avisos.get("tentativas", {}).get(chave, {})
            if reserva in _avisando or a["id"] in avisos.get(canal, []) or tentativa.get("proxima", 0) > time.time(): continue
            _avisando.add(reserva)
        sucesso = False
        try:
            enviar(a)
            sucesso = True
        except (OSError, ValueError, RuntimeError):
            pass
        finally:
            with _avisos_lock:
                try:
                    avisos = _ler_avisos(arquivo)
                    tentativas = avisos.setdefault("tentativas", {})
                    if sucesso:
                        avisos.setdefault(canal, []).append(a["id"])
                        tentativas.pop(chave, None)
                    else:
                        n = min(8, tentativas.get(chave, {}).get("falhas", 0) + 1)
                        tentativas[chave] = {"falhas": n, "proxima": time.time() + min(300, 10 * 2 ** (n - 1))}
                    temporario = arquivo.with_suffix("." + uuid.uuid4().hex + ".tmp")
                    try:
                        temporario.write_text(json.dumps(avisos), encoding="utf-8")
                        os.replace(temporario, arquivo)
                    finally:
                        temporario.unlink(missing_ok=True)
                finally:
                    _avisando.discard(reserva)


def por_codigo(codigo):
    if len(codigo) < 4: return None
    candidatos = [a for a in pendentes() if a["id"].lower().startswith(codigo.lower())]
    return candidatos[0] if len(candidatos) == 1 else None


def aviso(a):
    cmd = a.get("comando", [])
    destino, arquivo = a.get("destino", ""), ""
    if isinstance(cmd, list) and len(cmd) >= 4 and cmd[0] == "sheep-zap":
        numero = str(cmd[2])
        destino = "Você" if numero == "eu" else re.sub(r"^55(\d{2})(\d{4,5})(\d{4})$", r"+55 \1 \2-\3", numero)
        if len(cmd) == 5 and cmd[3] in ("audio", "imagem", "documento"):
            arquivo = "\nArquivo: " + str(cmd[4]).replace("\\", "/").rsplit("/", 1)[-1]
    codigo = a["id"][:5]
    previa = str(a.get("previa", ""))
    return [f"Preciso do teu sim ({codigo}): {a['tipo']} → {destino}{arquivo}"] + [previa[i:i + 700] for i in range(0, len(previa), 700)] + [f"Responde: sim {codigo} ou não {codigo}"]

def _enviar_zap(a):
    from nucleo import whatsapp
    cmd = a["comando"]
    if len(cmd) not in (4, 5) or not all(isinstance(x, str) for x in cmd) or cmd[1] != "enviar":
        raise ValueError("Pedido de WhatsApp inválido.")
    para, tipo = cmd[2:4]
    if para != "eu" and not re.fullmatch(r"[0-9]{10,15}", para):
        raise ValueError("Preciso do número com DDI e DDD, só dígitos (10 a 15).")
    if tipo == "texto":
        if len(cmd) != 4: raise ValueError("O texto deve estar só na prévia da aprovação, sem quinto argumento.")
        texto = a.get("previa")
        if not isinstance(texto, str) or not texto.strip(): raise ValueError("Faltou o texto da mensagem.")
        whatsapp.enviar(para, tipo, texto=texto)
    elif tipo in ("audio", "imagem", "documento") and len(cmd) == 5:
        raiz = caminhos.casa().resolve()
        arquivo = Path(cmd[4])
        if not arquivo.is_absolute(): arquivo = raiz / arquivo
        arquivo = arquivo.resolve()
        if not arquivo.is_relative_to(raiz) or not arquivo.is_file():
            raise ValueError("O arquivo precisa existir dentro da casa da Sheep.")
        whatsapp.enviar(para, tipo, arquivo=str(arquivo), texto=a.get("previa", ""))
    else:
        raise ValueError("Escolhe texto, áudio, imagem ou documento com um arquivo da casa.")

def decidir(id, aprovar, rodar=None):
    with _lock:
        a = _ler(_arq(id))
        if a["estado"] != "pendente": return a
        if not aprovar:
            a["estado"] = "recusado"
            a["decidido"] = int(time.time()); _grava(a); return a
        a["estado"] = "executando"
        _grava(a)
    erro_envio = None
    try:
        if isinstance(a.get("comando"), list) and a["comando"][:1] == ["sheep-zap"]:
            _enviar_zap(a)
            estado = "feito"
        else:
            estado = "feito" if (rodar or _rodar)(a["comando"]) == 0 else "falhou"
    except (OSError, ValueError) as erro:
        estado = "falhou"
        from nucleo import instalador
        with (caminhos.sub("logs") / "aprovacoes.log").open("a", encoding="utf-8") as arquivo:
            arquivo.write(f"{type(erro).__name__}: {erro}\n")
        erro_envio = instalador.erro_amigavel(erro)
    with _lock:
        a = _ler(_arq(id))
        a["estado"] = estado
        if erro_envio: a["erro"] = erro_envio
        a["decidido"] = int(time.time()); _grava(a)
    return a
