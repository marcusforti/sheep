import hashlib, json, os, re, secrets, shutil, socket, subprocess, sys, threading, time, urllib.error, urllib.request, uuid
from pathlib import Path
from datetime import date
from nucleo import caminhos, cofre, motor, sessoes, instalador

FONTE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "whatsapp"


def _registrar(erro):
    with (caminhos.sub("logs") / "whatsapp.log").open("a", encoding="utf-8") as arquivo:
        arquivo.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {erro}\n")


class ErroPonte(OSError):
    def __init__(self, status, mensagem):
        super().__init__(mensagem)
        self.status = status


class Ponte:
    def __init__(self, abrir=None):
        self.token = secrets.token_urlsafe(32)
        self.porta = None
        self._abrir = abrir or urllib.request.build_opener(urllib.request.ProxyHandler({})).open
        self._processo = None
        self._fechar = None
        self._log = None
        self._thread = None
        self._parar = threading.Event()
        self._lock = threading.RLock()
        self._estado = {"estado": "desconectado", "qr": None, "numero": None, "nome": None}
        self._reconectar = False
        self._conectando_desde = None
        self._saida_lock = threading.RLock()
        self._saida_thread = None
        self._saida_arquivo = caminhos.sub(".whatsapp") / "saida.json"
        self._saida = json.loads(self._saida_arquivo.read_text(encoding="utf-8")) if self._saida_arquivo.exists() else []

    def _situacao(self, estado, mensagem=None):
        self._conectando_desde = time.monotonic() if estado == "conectando" else None
        self._estado = {"estado": estado, "mensagem": mensagem, "qr": None, "numero": None, "nome": None}

    def _instalar(self):
        instalador.completar_path()
        pasta = caminhos.sub(".whatsapp") / "ponte"
        pasta.mkdir(parents=True, exist_ok=True)
        versao = hashlib.sha256((FONTE / "package-lock.json").read_bytes()).hexdigest()
        marca = pasta / ".lock-instalado"
        for nome in ("ponte.mjs", "package.json", "package-lock.json"):
            origem, destino = FONTE / nome, pasta / nome
            if not destino.exists() or origem.read_bytes() != destino.read_bytes():
                shutil.copy2(origem, destino)
        if not (pasta / "node_modules").is_dir() or not marca.exists() or marca.read_text() != versao:
            self._situacao("instalando", "Preparando o WhatsApp (1ª vez leva 1–2 min)…")
            npm = shutil.which("npm.cmd")
            if not npm: raise OSError("Falta o npm. Roda o instalador de novo.")
            if re.search(r"git\+|github:", (FONTE / "package-lock.json").read_text(encoding="utf-8")) and not shutil.which("git"):
                raise OSError("Falta o Git para preparar o WhatsApp. Abre o instalador da Sheep de novo.")
            temporarios = caminhos.sub(".whatsapp") / "tmp"
            temporarios.mkdir(exist_ok=True)
            env = {**os.environ, "npm_config_cache": str(pasta.parent / "npm-cache"), "TEMP": str(temporarios), "TMP": str(temporarios)}
            with (caminhos.sub("logs") / "whatsapp.log").open("a", encoding="utf-8") as log:
                r, fechar = motor.iniciar_processo([npm, "ci", "--omit=dev", "--no-audit", "--no-fund"], cwd=str(pasta), env=env,
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
                inicio = time.monotonic()
                try:
                    while r.poll() is None:
                        if self._parar.wait(0.2): raise OSError("Instalação do WhatsApp interrompida.")
                        if time.monotonic() - inicio > 600: raise OSError("A instalação demorou demais. Tenta de novo.")
                finally:
                    fechar()
            if r.returncode != 0: raise OSError("Não consegui preparar o WhatsApp. Confere logs/whatsapp.log e tenta de novo.")
            marca.write_text(versao, encoding="ascii")
        return pasta

    def _pedido(self, metodo, rota, dados=None):
        if self.porta is None: raise OSError("WhatsApp desconectado. Abre Conexões pra ligar.")
        req = urllib.request.Request(f"http://127.0.0.1:{self.porta}{rota}", method=metodo,
            data=json.dumps(dados, ensure_ascii=False).encode("utf-8") if dados is not None else None,
            headers={"X-Token": self.token, "Content-Type": "application/json"})
        try:
            with self._abrir(req, timeout=240 if rota == "/enviar" else 20 if rota == "/sair" else 5 if rota == "/parar" else 10 if rota == "/conectar" else 3) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as erro:
            try: mensagem = json.loads(erro.read()).get("erro", "Não consegui falar com o WhatsApp.")
            except ValueError: mensagem = "Não consegui falar com o WhatsApp."
            _registrar(f"HTTP {erro.code}: {mensagem}")
            raise ErroPonte(erro.code, instalador.erro_amigavel(OSError(mensagem))) from None

    def _encerrar(self):
        if self._fechar:
            self._fechar()
            self._fechar = None
        self._processo = None
        if self._log:
            self._log.close()
            self._log = None

    def _subir(self):
        self._encerrar()
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.porta = s.getsockname()[1]
        pasta = caminhos.casa() / ".whatsapp" / "ponte"
        cmd = [shutil.which("node") or "node", str(pasta / "ponte.mjs"), str(self.porta),
               str(caminhos.cofre() / "whatsapp-auth"), str(caminhos.sub("whatsapp-midia")), shutil.which("ffmpeg") or "ffmpeg"]
        self._log = (caminhos.sub("logs") / "whatsapp.log").open("a", encoding="utf-8")
        self._processo, self._fechar = motor.iniciar_processo(cmd, str(pasta), stdin=subprocess.DEVNULL,
            stdout=self._log, stderr=subprocess.STDOUT, env={**os.environ, "SHEEP_WHATSAPP_TOKEN": self.token})
        self._situacao("conectando" if self._reconectar else "desconectado")

    def iniciar(self):
        with self._lock:
            if self._processo is not None and self._processo.poll() is None: return True
            if self._parar.is_set() and self._thread is not None and self._thread.is_alive(): return False
            if not shutil.which("node"):
                self._situacao("sem_node", "Falta o Node. Roda o instalador de novo.")
                return False
            self._parar.clear()
            try:
                if instalador.versao_node() < 20:
                    self._situacao("sem_node", "Seu Node está velho. Abre o instalador da Sheep de novo pra eu atualizar.")
                    return False
                self._instalar()
                if self._parar.is_set(): return False
                self._subir()
            except (OSError, subprocess.SubprocessError) as erro:
                _registrar(erro)
                self._encerrar()
                self._situacao("erro", instalador.erro_amigavel(erro))
                return False
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._vigiar, daemon=True)
                self._thread.start()
            if self._saida: self._iniciar_saida()
            return True

    def _pronto(self):
        limite = time.monotonic() + 90
        for _ in range(50):
            if self._parar.is_set(): raise OSError("WhatsApp parado.")
            try:
                return self._pedido("POST", "/conectar")
            except ErroPonte:
                raise
            except OSError as erro:
                if time.monotonic() >= limite:
                    _registrar(erro)
                    break
                if self._parar.wait(0.2): break
        raise OSError("A ponte não respondeu. Tenta conectar de novo.")

    def _vigiar(self):
        falhas, desde = 0, time.monotonic()
        while not self._parar.wait(1):
            if self._processo is not None and self._processo.poll() is None:
                if time.monotonic() - desde >= 60: falhas = 0
                continue
            if falhas >= 5:
                self._situacao("erro", "A ponte caiu 5 vezes seguidas. Abre Conexões e tenta de novo.")
                return
            falhas += 1
            self._situacao("conectando", f"A ponte caiu. Tentando de novo ({falhas}/5)…")
            if self._parar.wait(min(2 ** falhas, 30)): return
            try:
                with self._lock:
                    if self._parar.is_set(): return
                    self._subir()
                if self._reconectar: self._pronto()
                desde = time.monotonic()
            except OSError:
                self._encerrar()

    def parar(self):
        self._parar.set()
        if self._thread is not None and hasattr(self._thread, "join") and self._thread is not threading.current_thread():
            self._thread.join(timeout=4)
        with self._lock:
            if self._processo is not None and self._processo.poll() is None:
                try:
                    self._pedido("POST", "/parar")
                except (OSError, subprocess.SubprocessError) as erro:
                    _registrar(erro)
                try:
                    if hasattr(self._processo, "wait"): self._processo.wait(timeout=3)
                except subprocess.SubprocessError as erro:
                    _registrar(erro)
            self._encerrar()
            self._situacao("desconectado")

    def estado(self):
        if self._processo is not None and self._processo.poll() is None:
            try:
                atual = self._pedido("GET", "/estado")
                if atual.get("estado") == "conectando":
                    if self._conectando_desde is None: self._conectando_desde = time.monotonic()
                    if not atual.get("mensagem"): atual["mensagem"] = self._estado.get("mensagem")
                else:
                    self._conectando_desde = None
                if not (atual.get("estado") == "desconectado" and not atual.get("mensagem") and self._estado.get("estado") == "erro"):
                    self._estado = atual
                if atual.get("estado") == "desconectado" and atual.get("codigo") in (440, 403, 405):
                    self._reconectar = False
            except (OSError, ValueError) as erro:
                _registrar(erro)
        if self._conectando_desde is not None and time.monotonic() - self._conectando_desde > 90:
            if self._estado.get("estado") != "erro":
                self._estado = {**self._estado, "estado": "erro", "qr": None,
                    "mensagem": "A conexão passou de 90 segundos. " + (self._estado.get("mensagem") or "O WhatsApp ainda não respondeu.")}
        return dict(self._estado)

    def conectar(self):
        if self._estado.get("estado") == "erro": self.parar()
        self._reconectar = True
        if not self.iniciar(): return self.estado()
        try: return self._pronto()
        except OSError as erro:
            _registrar(erro)
            self._situacao("erro", instalador.erro_amigavel(erro))
            return dict(self._estado)

    def sair(self):
        self._reconectar = False
        try: resultado = self._pedido("POST", "/sair")
        except OSError:
            self.parar()
            auth = caminhos.cofre() / "whatsapp-auth"
            if auth.is_symlink() or getattr(auth, "is_junction", lambda: False)() or auth.resolve().parent != caminhos.cofre().resolve():
                raise OSError("A pasta de credenciais do WhatsApp não é válida.") from None
            if auth.exists(): shutil.rmtree(auth)
            resultado = {"estado": "desconectado", "mensagem": "Desliguei aqui. Se o aparelho ainda aparecer no celular, desconecta por lá também."}
        self._situacao("desconectado")
        midia = caminhos.casa() / "whatsapp-midia"
        if midia.exists() and not midia.is_symlink() and not getattr(midia, "is_junction", lambda: False)() and midia.resolve().parent == caminhos.casa().resolve():
            shutil.rmtree(midia)
        return resultado

    def novas(self, desde):
        return self._pedido("GET", f"/mensagens?desde={max(0, int(desde))}")

    def _gravar_saida(self):
        temporario = self._saida_arquivo.with_suffix(".tmp")
        temporario.write_text(json.dumps(self._saida, ensure_ascii=False), encoding="utf-8")
        os.replace(temporario, self._saida_arquivo)

    def _iniciar_saida(self):
        if self._saida_thread is None or not self._saida_thread.is_alive():
            self._saida_thread = threading.Thread(target=self._repetir_saida, daemon=True)
            self._saida_thread.start()

    def _repetir_saida(self):
        while not self._parar.wait(30):
            try: self.reenviar()
            except Exception as erro: _registrar(erro)

    def reenviar(self, alvo=None):
        with self._saida_lock:
            resultado = None
            while self._saida:
                item = self._saida[0]
                if time.time() - item["criado"] >= 7200:
                    _registrar(f"Envio {item['id']} expirou após 2 horas; não vou tentar novamente.")
                    self._saida.pop(0)
                    self._gravar_saida()
                    continue
                if item.get("proxima", 0) > time.time(): break
                try:
                    resposta = self._pedido("POST", "/enviar", {k: v for k, v in item.items() if k not in ("criado", "proxima")})
                except OSError as erro:
                    _registrar(f"Envio {item['id']}: {erro}")
                    if not isinstance(erro, ErroPonte) or erro.status in (408, 409, 502, 503, 504):
                        item["proxima"] = time.time() + 30
                        self._gravar_saida()
                        break
                    self._saida.pop(0)
                    self._gravar_saida()
                    if item["id"] == alvo: raise
                    continue
                self._saida.pop(0)
                self._gravar_saida()
                if item["id"] == alvo: resultado = resposta
            return resultado

    def enviar(self, para, tipo, texto=None, arquivo=None):
        item = {"id": uuid.uuid4().hex, "para": para, "tipo": tipo, "texto": texto,
            "arquivo": str(arquivo) if arquivo else None, "criado": time.time(), "proxima": 0}
        with self._saida_lock:
            self._saida.append(item)
            self._gravar_saida()
            self._iniciar_saida()
            return self.reenviar(item["id"]) or {"id": item["id"], "pendente": True}


_atual = None
_casa = None
_criacao = threading.Lock()


def ponte():
    global _atual, _casa
    with _criacao:
        if _atual is None or _casa != caminhos.casa():
            if _atual is not None: _atual.parar()
            _atual, _casa = Ponte(), caminhos.casa()
        return _atual


def enviar(para, tipo, texto=None, arquivo=None):
    return ponte().enviar(para, tipo, texto, arquivo)


def estado():
    hoje = date.today().isoformat()
    titulo = "WhatsApp " + hoje
    pedidos = sum(sum(m["quem"] == "dono" for m in sessoes.ler(s["id"])["mensagens"])
                  for s in sessoes.listar() if s["titulo"] == titulo or s.get('origem')=='whatsapp' and s.get('dia')==hoje)
    return {**ponte().estado(), "voz": cofre.ler("WHATSAPP_VOZ") == "1", "ligado": cofre.ler("WHATSAPP_LIGADO") == "1", "pedidos_hoje": pedidos}
