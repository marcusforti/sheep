import json, re, secrets, threading, urllib.request
from nucleo import cofre, sessoes, motor, aprovacoes

def _api_real(metodo, dados):
    tok = cofre.ler("TELEGRAM_TOKEN")
    req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/{metodo}", data=json.dumps(dados).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())

class Bot:
    def __init__(self, api=None, conversar=None, rodar=None):
        self.api = api or _api_real; self.rodar = rodar; self.offset = 0
        self.conversar = conversar or (lambda sid, t: motor.conversar(sid, t))

    def _dono(self): return cofre.ler("TELEGRAM_DONO")

    def _sessao(self):
        s = next((x for x in sessoes.listar() if x["titulo"] == "telegram"), None)
        return (s or sessoes.criar("telegram", motor=motor.padrao()))["id"]

    def _envia(self, chat, texto, botoes=None):
        d = {"chat_id": chat, "text": texto[:4000]}
        if botoes: d["reply_markup"] = {"inline_keyboard": [botoes]}
        self.api("sendMessage", d)

    def tratar(self, u):
        if "callback_query" in u:
            q = u["callback_query"]
            if str(q["from"]["id"]) != self._dono(): return
            acao, aid = q["data"].split(":", 1)
            r = aprovacoes.decidir(aid, acao == "ok", rodar=self.rodar)
            self.api("answerCallbackQuery", {"callback_query_id": q["id"], "text": r["estado"]})
            return
        m = u.get("message") or {}
        chat = str(m.get("chat", {}).get("id", ""))
        if not chat or chat != self._dono() or not m.get("text"): return
        decisao = re.fullmatch(r"(sim|s|não|nao)\s+([A-Za-z0-9_-]{4,80})", m["text"].strip(), re.I)
        a = aprovacoes.por_codigo(decisao[2]) if decisao else None
        if a:
            r = aprovacoes.decidir(a["id"], decisao[1].lower() in ("sim", "s"), rodar=self.rodar)
            self._envia(chat, "🐑 " + {"feito": "Feito.", "recusado": "Beleza, não mandei.", "executando": "Esse pedido já está sendo executado."}.get(r["estado"], "Deu ruim: " + r.get("erro", "não consegui concluir esse envio.")))
            return
        self._envia(chat, "Recebido, trabalhando. 🐑")
        self._envia(chat, self.conversar(self._sessao(), m["text"]))

    def avisar_aprovacao(self, a):
        dono = self._dono()
        if dono:
            partes = aprovacoes.aviso(a)
            for i, parte in enumerate(partes):
                self._envia(dono, parte, [{"text": "✅ Aprovar", "callback_data": f"ok:{a['id']}"}, {"text": "✖ Recusar", "callback_data": f"nao:{a['id']}"}] if i == len(partes) - 1 else None)

    def rodar_para_sempre(self, parar: threading.Event):
        while not parar.is_set():
            try:
                for u in self.api("getUpdates", {"offset": self.offset, "timeout": 30}).get("result", []):
                    self.offset = u["update_id"] + 1; self.tratar(u)
            except Exception:
                parar.wait(10)

def novo_codigo() -> str:
    codigo = f"{secrets.randbelow(1000000):06d}"
    cofre.guardar("TELEGRAM_CODIGO", codigo)
    return codigo

def vincular(codigo: str, api=None):
    if not codigo: return None
    api = api or _api_real
    for u in api("getUpdates", {"timeout": 0}).get("result", []):
        m = u.get("message") or {}
        if m.get("text", "") == f"/start {codigo}":
            chat = str(m["chat"]["id"]); cofre.guardar("TELEGRAM_DONO", chat)
            api("sendMessage", {"chat_id": chat, "text": "Achei você, chefe. A partir de agora só obedeço a você. 🐑"})
            cofre.apagar("TELEGRAM_CODIGO")
            return chat
    return None
