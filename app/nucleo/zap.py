import json, mimetypes, queue, re, threading, time, urllib.parse, urllib.request, uuid
from collections import deque
from datetime import date, datetime
from pathlib import Path
from nucleo import aprovacoes, caminhos, cofre, motor, refletor, sessoes, whatsapp

_conversa_lock = threading.Lock()


def _conversar(sessao, pedido, cancelar=None):
    contexto = ("Pedido recebido pelo WhatsApp do dono. Sua resposta final será enviada automaticamente nesse chat. "
        "Responda em 1 a 6 linhas, sem tabela, e siga a seção WhatsApp de AGENTS.md. "
        "Envios a terceiros exigem aprovação pelo aplicativo.\n\nPedido do dono:\n")
    return motor.conversar(sessao, contexto + pedido, cancelar=cancelar)


def _log(erro):
    try:
        with (caminhos.sub("logs") / "whatsapp-bot.log").open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {type(erro).__name__}\n")
    except Exception:
        pass


def _formatar(texto):
    texto = re.sub(r"^🐑\s*", "", str(texto).strip())
    texto = texto.replace("**", "*")
    linhas = []
    for linha in texto.splitlines():
        if re.match(r"^\s*#{1,6}\s+", linha):
            linha = "*" + re.sub(r"^\s*#{1,6}\s+", "", linha).strip("* ") + "*"
        elif linha.strip().startswith("|") and linha.strip().endswith("|"):
            colunas = [c.strip() for c in linha.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-+:?", c) for c in colunas):
                continue
            linha = "- " + ": ".join(colunas)
        linhas.append(linha)
    return "\n".join(linhas)


def _arquivo(nome):
    casa = caminhos.casa().resolve()
    pasta = caminhos.sub("whatsapp-midia").resolve()
    arquivo = Path(nome or "")
    if not arquivo.is_absolute():
        arquivo = casa / arquivo
    arquivo = arquivo.resolve()
    if pasta.parent != casa or not arquivo.is_relative_to(pasta) or not arquivo.is_file():
        raise ValueError("O arquivo precisa estar em whatsapp-midia dentro da casa da Sheep.")
    return arquivo


def _transcrever(arquivo, chave):
    arquivo = _arquivo(arquivo)
    limite = "sheep-" + uuid.uuid4().hex
    partes = []
    for nome, valor in (("model_id", "scribe_v1"), ("language_code", "por")):
        partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="{nome}"\r\n\r\n{valor}\r\n'.encode())
    mime = mimetypes.guess_type(arquivo.name)[0] or "application/octet-stream"
    partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="file"; filename="audio{arquivo.suffix}"\r\nContent-Type: {mime}\r\n\r\n'.encode())
    partes.extend((arquivo.read_bytes(), f"\r\n--{limite}--\r\n".encode()))
    req = urllib.request.Request("https://api.elevenlabs.io/v1/speech-to-text", data=b"".join(partes),
        headers={"xi-api-key": chave, "Content-Type": "multipart/form-data; boundary=" + limite})
    with urllib.request.urlopen(req, timeout=90) as resposta:
        texto = json.loads(resposta.read()).get("text", "")
    if not isinstance(texto, str) or not texto.strip():
        raise ValueError("Não consegui entender o áudio. Tenta de novo ou me manda em texto.")
    return "🎤 " + texto.strip()


def _voz(texto):
    if cofre.ler("WHATSAPP_VOZ") != "1" or not texto or len(texto) > 600:
        return None
    chave, voz = cofre.ler("ELEVENLABS_API_KEY"), cofre.ler("ELEVENLABS_VOZ")
    if not chave or not voz:
        return None
    pasta = caminhos.sub("whatsapp-midia")
    if pasta.resolve().parent != caminhos.casa().resolve():
        raise ValueError("Pasta de mídia inválida.")
    req = urllib.request.Request("https://api.elevenlabs.io/v1/text-to-speech/" + urllib.parse.quote(voz, safe="") + "?output_format=opus_48000_64",
        data=json.dumps({"text": texto, "model_id": "eleven_multilingual_v2"}).encode("utf-8"),
        headers={"xi-api-key": chave, "Content-Type": "application/json", "Accept": "audio/ogg"})
    with urllib.request.urlopen(req, timeout=90) as resposta:
        audio = resposta.read()
    if not audio:
        raise ValueError("A voz não retornou áudio.")
    arquivo = pasta / ("sheep-" + uuid.uuid4().hex + ".ogg")
    with arquivo.open("xb") as f:
        f.write(audio)
    return arquivo


class Bot:
    def __init__(self, ponte=None, conversar=None, refletir=None, agora=None):
        self.ponte = ponte or whatsapp.ponte()
        self.conversar = conversar or _conversar
        self.refletir = refletir or refletor.refletir
        self.agora = agora or time.monotonic
        self.ativos = {}
        self.fila = deque()
        self._ordem = deque()
        self._lock = threading.RLock()
        self._vez = threading.Condition(self._lock)
        self._parar = threading.Event()
        self._desde = 0
        self._porta = None
        self._conexao = None
        self._descartadas = 0
        self._avisou_retorno = False
        self._vistos = set()
        self._historico = deque()
        self._opcoes = []
        self._reflexoes = queue.Queue()
        self._reflexao = None
        self._controles = queue.Queue()
        self._controle = None
        self._avisos_pendentes = False
        self._cancelar_aprovacoes = threading.Event()

    def _enviar(self, texto, cancelar=None):
        texto = _formatar(texto)
        for inicio in range(0, len(texto) or 1, 3498):
            if cancelar is not None and cancelar.is_set():
                return False
            self.ponte.enviar("eu", "texto", texto="🐑 " + texto[inicio:inicio + 3498])
        return True

    def _seguro(self, texto, cancelar=None):
        try:
            return self._enviar(texto, cancelar=cancelar)
        except Exception as erro:
            _log(erro)
            return False

    def _sessao(self):
        titulo = "WhatsApp " + date.today().isoformat()
        sessao = next((s for s in sessoes.listar() if not s.get('arquivada') and (s["titulo"] == titulo or s.get('origem') == 'whatsapp' and s.get('dia') == date.today().isoformat())), None)
        sessao = sessao or sessoes.criar(titulo, motor=motor.padrao())
        sessoes.atualizar(sessao['id'], origem='whatsapp', dia=date.today().isoformat())
        return sessao['id']

    def _decidir(self, escolha, codigo, cancelar=None):
        if cancelar is not None and cancelar.is_set():
            return
        aprovacao = aprovacoes.por_codigo(codigo)
        if not aprovacao: return
        try:
            with self._lock:
                if cancelar is not None and cancelar.is_set():
                    return
            resultado = aprovacoes.decidir(aprovacao["id"], escolha.lower() in ("sim", "s"))
            estado = resultado.get("estado")
            if estado == "feito":
                self._seguro("Feito.")
            elif estado == "recusado":
                self._seguro("Beleza, não mandei.")
            elif estado == "executando":
                self._seguro("Esse pedido já está sendo executado.")
            else:
                self._seguro("Deu ruim: " + resultado.get("erro", "não consegui concluir esse envio."))
        except Exception as erro:
            _log(erro)
            self._seguro("Deu ruim: " + str(erro))

    def status(self):
        with self._lock:
            if not self.ativos and not self.fila:
                return "Tô livre agora, nada rodando. Manda!"
            linhas = [f"Em andamento ({len(self.ativos)}/2):"]
            for t in self.ativos.values():
                linhas.append(f"- {t['resumo']} ({t['estado']}, {int(self.agora() - t['inicio'])} s)")
            if self.fila:
                linhas.append(f"Na fila ({len(self.fila)}):")
                linhas.extend(f"- {t['resumo']}" for t in self.fila)
            return "\n".join(linhas)

    def _cancelar(self):
        with self._vez:
            self._cancelar_aprovacoes.set()
            self._cancelar_aprovacoes = threading.Event()
            for tarefa in list(self.ativos.values()) + list(self.fila):
                tarefa["cancelar"].set()
            self.fila.clear()
            self._opcoes = []
            self._vez.notify_all()

    def parar(self):
        self._parar.set()
        self._cancelar()
        while True:
            try:
                self._controles.get_nowait()
                self._controles.task_done()
            except queue.Empty:
                break

    def tratar(self, mensagem):
        with self._lock:
            acao = self._receber(mensagem)
        if acao:
            self._executar_controle(acao)

    def _executar_controle(self, acao):
        if acao[0] == "decidir":
            self._decidir(*acao[1], cancelar=acao[2] if len(acao) > 2 else None)
        elif acao[0] == "avisos":
            try:
                aprovacoes.avisar_novas("whatsapp", self.avisar_aprovacao)
            finally:
                with self._lock:
                    self._avisos_pendentes = False
        elif acao[0] == "recebido":
            tarefa = acao[1]
            with tarefa["envio"]:
                with self._lock:
                    avisar = not tarefa["final"] and not tarefa["cancelar"].is_set()
                if avisar:
                    self._seguro("Recebi, tô nisso.", cancelar=tarefa["cancelar"])
        else:
            self._seguro(acao[1], cancelar=acao[2] if len(acao) > 2 else None)

    def _enfileirar_controle(self, acao):
        with self._lock:
            if self._parar.is_set():
                return
            if acao[0] == "avisos":
                if self._avisos_pendentes:
                    return
                self._avisos_pendentes = True
            self._controles.put(acao)
            if self._controle is None or not self._controle.is_alive():
                self._controle = threading.Thread(target=self._controlar, daemon=True)
                self._controle.start()

    def _controlar(self):
        while not self._parar.is_set():
            try:
                acao = self._controles.get(timeout=.2)
            except queue.Empty:
                continue
            try:
                if not self._parar.is_set():
                    self._executar_controle(acao)
            except Exception as erro:
                _log(erro)
            finally:
                self._controles.task_done()

    def _receber(self, mensagem):
        if self._parar.is_set():
            return
        id = str(mensagem.get("id") or "")
        if id:
            if id in self._vistos:
                return
            self._vistos.add(id)
            self._historico.append(id)
            if len(self._historico) > 2000:
                self._vistos.discard(self._historico.popleft())
        texto = str(mensagem.get("texto") or "").strip()
        tipo = mensagem.get("tipo", "texto")
        if mensagem.get("erro") == "download":
            return "texto", "Esse arquivo é grande demais pra mim. Manda um de até 25 MB?" if mensagem.get("grande") else "Não consegui baixar esse arquivo. Manda de novo?"
        if tipo == "texto":
            if texto.lower() == "status":
                return "texto", self.status()
            if texto.lower() == "cancela tudo":
                self._cancelar()
                return "texto", "Parei tudo. Zerado."
            decisao = re.fullmatch(r"(sim|s|não|nao)\s+([A-Za-z0-9_-]{1,80})", texto, re.I)
            if decisao and aprovacoes.por_codigo(decisao[2]):
                cancelar = self._cancelar_aprovacoes if decisao[1].lower() in ("sim", "s") else None
                return "decidir", decisao.groups(), cancelar
            if self._opcoes and re.fullmatch(r"[0-9]+", texto):
                numero = int(texto) if len(texto) < 4 else 0
                if not 1 <= numero <= len(self._opcoes):
                    return "texto", f"Escolhe um número de 1 a {len(self._opcoes)}, ou escreve outro pedido."
                texto = self._opcoes[numero - 1]
            self._opcoes = []
            if not texto:
                return
        elif tipo not in ("audio", "imagem", "documento"):
            return "texto", "Me manda texto, áudio, imagem ou documento."
        else:
            self._opcoes = []
        tarefa = {"id": uuid.uuid4().hex, "mensagem": {**mensagem, "texto": texto}, "cancelar": threading.Event(),
            "resumo": (texto or tipo)[:80], "inicio": self.agora(), "avisado": False, "final": False,
            "estado": "aguardando contexto", "envio": threading.Lock()}
        self.fila.append(tarefa)
        em_fila = len(self.ativos) >= 2
        if em_fila:
            tarefa["avisado"] = True
        self._iniciar()
        if em_fila:
            return "texto", "Já tô em 2 coisas, a tua entra na fila.", tarefa["cancelar"]

    def _iniciar(self):
        while self.fila and len(self.ativos) < 2 and not self._parar.is_set():
            tarefa = self.fila.popleft()
            if tarefa["cancelar"].is_set():
                continue
            self.ativos[tarefa["id"]] = tarefa
            self._ordem.append(tarefa["id"])
            threading.Thread(target=self._executar, args=(tarefa,), daemon=True).start()

    def _resposta(self, texto):
        opcoes = re.search(r"(?:^|\n)```opcoes\s*\n(.*?)\n```\s*$", texto, re.S)
        escolhas = []
        if opcoes:
            escolhas = [re.sub(r"^[-*]\s+", "", linha.strip()) for linha in opcoes[1].splitlines() if linha.strip()]
            if 2 <= len(escolhas) <= 5 and all(len(o) <= 60 for o in escolhas):
                texto = texto[:opcoes.start()].rstrip() + "\n" + "\n".join(f"{i}. {o}" for i, o in enumerate(escolhas, 1)) + "\nResponde com o número:"
            else:
                escolhas = []
        self._opcoes = escolhas
        return _formatar(texto)

    def _aprender(self, sid, pedido, resposta, cancelar):
        with self._lock:
            if self._parar.is_set() or cancelar.is_set():
                return
            self._reflexoes.put((sid, pedido, resposta, cancelar))
            if self._reflexao is None or not self._reflexao.is_alive():
                self._reflexao = threading.Thread(target=self._refletir, daemon=True)
                self._reflexao.start()

    def _refletir(self):
        while not self._parar.is_set():
            try:
                sid, pedido, resposta, cancelar = self._reflexoes.get(timeout=.2)
            except queue.Empty:
                continue
            try:
                if not self._parar.is_set() and not cancelar.is_set():
                    refletor.executar(self.refletir, sid, pedido, resposta)
            except Exception as erro:
                _log(erro)

    def _executar(self, tarefa):
        sid, pedido, resposta = None, "", ""
        cancelar = tarefa["cancelar"]
        try:
            if cancelar.is_set():
                return
            mensagem = tarefa["mensagem"]
            pedido = mensagem["texto"]
            tipo = mensagem.get("tipo", "texto")
            if tipo == "audio":
                chave = cofre.ler("ELEVENLABS_API_KEY")
                if not chave:
                    with tarefa["envio"]:
                        if cancelar.is_set():
                            return
                        with self._lock:
                            tarefa["final"] = True
                        self._seguro("Ainda não consigo ouvir áudio. Liga a ElevenLabs em Conexões ou me manda em texto.", cancelar=cancelar)
                    return
                pedido = _transcrever(mensagem.get("arquivo"), chave)
            elif tipo in ("imagem", "documento"):
                pedido = (pedido + "\n" if pedido else "") + f"[arquivo: {_arquivo(mensagem.get('arquivo'))}]"
            with self._vez:
                while not cancelar.is_set() and self._ordem[0] != tarefa["id"]:
                    self._vez.wait(.1)
                if cancelar.is_set():
                    return
            while not _conversa_lock.acquire(timeout=.1):
                if cancelar.is_set():
                    return
            try:
                if cancelar.is_set():
                    return
                with self._lock:
                    tarefa["estado"] = "trabalhando"
                sid = self._sessao()
                resposta = self.conversar(sid, pedido, cancelar=cancelar)
                if cancelar.is_set():
                    return
                with tarefa["envio"]:
                    if cancelar.is_set():
                        return
                    with self._lock:
                        tarefa["final"] = True
                        tarefa["estado"] = "enviando resposta"
                        formatada = self._resposta(resposta)
                    if not self._seguro(formatada, cancelar=cancelar):
                        with self._lock:
                            self._opcoes = []
            finally:
                _conversa_lock.release()
                with self._vez:
                    if tarefa["id"] in self._ordem:
                        self._ordem.remove(tarefa["id"])
                    self._vez.notify_all()
            if not cancelar.is_set() and not motor.eh_erro(resposta):
                try:
                    arquivo = _voz(formatada)
                    if arquivo and not cancelar.is_set():
                        self.ponte.enviar("eu", "audio", arquivo=str(arquivo))
                except Exception as erro:
                    _log(erro)
                self._aprender(sid, pedido, resposta, cancelar)
        except Exception as erro:
            _log(erro)
            with tarefa["envio"]:
                with self._lock:
                    tarefa["final"] = True
                if not cancelar.is_set():
                    self._seguro("Deu ruim: " + str(erro), cancelar=cancelar)
        finally:
            with self._vez:
                self.ativos.pop(tarefa["id"], None)
                if tarefa["id"] in self._ordem:
                    self._ordem.remove(tarefa["id"])
                self._vez.notify_all()
                self._iniciar()

    def avisar_aprovacao(self, aprovacao):
        for parte in aprovacoes.aviso(aprovacao):
            if self._parar.is_set(): raise RuntimeError("O aviso foi interrompido antes do envio.")
            self.ponte.enviar("eu", "texto", texto="🐑 " + parte)

    def passo(self):
        with self._lock:
            ativos = list(self.ativos.values())
        for tarefa in ativos:
            if not tarefa["envio"].acquire(blocking=False):
                continue
            try:
                with self._lock:
                    avisar = not tarefa["final"] and not tarefa["avisado"] and not tarefa["cancelar"].is_set() and self.agora() - tarefa["inicio"] >= 8
                    if avisar:
                        tarefa["avisado"] = True
                if avisar:
                    self._enfileirar_controle(("recebido", tarefa))
            finally:
                tarefa["envio"].release()
        if self._parar.is_set() or cofre.ler("WHATSAPP_LIGADO") != "1":
            return
        try:
            situacao = self.ponte.estado()
            if situacao.get("estado") != "conectado":
                self._avisou_retorno = False
                return
            porta = self.ponte.porta
            if porta != self._porta:
                self._porta, self._desde = porta, 0
                self._descartadas = 0
                self._avisou_retorno = False
            if situacao.get("conexao") != self._conexao:
                self._conexao = situacao.get("conexao")
                self._avisou_retorno = False
            descartadas = situacao.get("descartadas", 0)
            if descartadas > self._descartadas and not self._avisou_retorno:
                total = descartadas - self._descartadas
                self._enfileirar_controle(("texto", f"Voltei! Chegaram {total} mensagens enquanto eu estava desligada; se ainda precisar de algo, me manda de novo."))
                self._avisou_retorno = True
            self._descartadas = descartadas
            for mensagem in self.ponte.novas(self._desde):
                try:
                    sequencia = int(mensagem.get("seq", 0))
                    with self._lock:
                        acao = self._receber(mensagem)
                    if acao:
                        self._enfileirar_controle(acao)
                    self._desde = max(self._desde, sequencia)
                except Exception as erro:
                    _log(erro)
        except Exception as erro:
            _log(erro)
            return
        self._enfileirar_controle(("avisos", None))

    def rodar_para_sempre(self, parar):
        while not parar.is_set() and not self._parar.is_set():
            try:
                self.passo()
            except Exception as erro:
                _log(erro)
            if parar.wait(2):
                break
