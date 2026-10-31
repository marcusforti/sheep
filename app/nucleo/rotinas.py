import json, os, uuid
from nucleo import caminhos, sessoes, motor

def _cfg(): return caminhos.casa() / "rotinas.json"
def _feitas(): return caminhos.casa() / ".rotinas_feitas.json"
def _le(p, padrao): return json.loads(p.read_text(encoding="utf-8")) if p.exists() else padrao

def listar(): return _le(_cfg(), [])

def desligar_memoria_legada():
    arquivo = _cfg()
    if not arquivo.exists(): return
    marca = caminhos.casa() / ".migracoes.json"
    try:
        migracoes = _le(marca, {})
        if not isinstance(migracoes, dict): raise ValueError("Registro de migrações inválido.")
        if migracoes.get("rotina_memoria_desligada"): return
        atuais = listar()
        if not isinstance(atuais, list) or not all(isinstance(r, dict) for r in atuais):
            raise ValueError("Seu rotinas.json está com problema. Abra a pasta da Sheep e confira esse arquivo.")
        antigo = "Revise as conversas de hoje (pasta sessoes/) e grave em memoria/ os fatos novos sobre o dono e o negócio, um fato por arquivo .md com a data. Não repita fatos que já existem."
        mudou = False
        for rotina in atuais:
            if rotina.get("nome") == "memoria" and rotina.get("prompt") == antigo and rotina.get("ativo") is not False:
                rotina["ativo"] = False
                mudou = True
        migracoes["rotina_memoria_desligada"] = True
        for destino, dados in ([(arquivo, atuais)] if mudou else []) + [(marca, migracoes)]:
            temporario = destino.with_name(destino.name + "." + uuid.uuid4().hex + ".tmp")
            try:
                temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                os.replace(temporario, destino)
            finally:
                temporario.unlink(missing_ok=True)
    except ValueError as erro:
        raise OSError(str(erro)) from erro

def ligar(nome, ativo):
    rs = listar()
    for r in rs:
        if r["nome"] == nome: r["ativo"] = bool(ativo)
    _cfg().write_text(json.dumps(rs, ensure_ascii=False), encoding="utf-8")

def devidas(agora):
    hoje, hhmm, feitas = agora.strftime("%Y-%m-%d"), agora.strftime("%H:%M"), _le(_feitas(), {})
    return [r for r in listar() if r.get("ativo") and r["hora"] <= hhmm and feitas.get(r["nome"]) != hoje]

def rodar_devidas(agora, conversar=None, avisar=None):
    pend = devidas(agora)
    if not pend: return []
    conversar = conversar or motor.conversar
    s = next((x for x in sessoes.listar() if x["titulo"] == "rotinas"), None) or sessoes.criar("rotinas", motor=motor.padrao())
    sessoes.atualizar(s["id"], modo_unico=True)
    feitas, nomes = _le(_feitas(), {}), []
    for r in pend:
        texto = conversar(s["id"], r["prompt"])
        if motor.eh_erro(texto): continue
        feitas[r["nome"]] = agora.strftime("%Y-%m-%d"); nomes.append(r["nome"])
        _feitas().write_text(json.dumps(feitas), encoding="utf-8")
        if avisar: avisar(texto)
    return nomes
