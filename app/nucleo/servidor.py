import base64, json, os, re, secrets, shutil, stat, subprocess, sys, threading, traceback, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from nucleo import aprovacoes, caminhos, cofre, habilidades, instalador, motor, rotinas, sessoes, telegram, pacotes, memorias, refletor
from nucleo import whatsapp, identidade, organizacao, pastas, login, aparencia, diagnostico, claude_global

UI = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "ui"
CONEXOES = ["TELEGRAM_TOKEN", "TELEGRAM_DONO", "ZERNIO_API_KEY", "ELEVENLABS_API_KEY", "ELEVENLABS_VOZ", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "OPENAI_API_KEY", "OPENAI_BASE_URL", "EVOLUTION_URL", "EVOLUTION_API_KEY", "OUTRA_API_NOME", "OUTRA_API_URL", "OUTRA_API_KEY", "MOTOR_PADRAO", "APRENDER"]
LIMITE_ZIP = 30 * 1024**2
LIMITE_ANEXO = 20 * 1024**2
TIPOS = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".png": "image/png",
         ".jpg": "image/jpeg", ".woff2": "font/woff2", ".mp3": "audio/mpeg", ".mp4": "video/mp4"}

def _nome_seguro(nome):
    if not isinstance(nome, str) or not nome or len(nome.encode("utf-16-le")) > 480 or nome != nome.strip() or nome.endswith("."):
        raise ValueError("Escolha um nome de arquivo válido.")
    if any(ch in '/\\<>:"|?*' or ord(ch) < 32 or 127 <= ord(ch) < 160 for ch in nome):
        raise ValueError("Escolha um nome de arquivo válido.")
    if re.fullmatch(r"CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|CLOCK\$|COM[1-9¹²³]|LPT[1-9¹²³]", nome.split(".")[0].rstrip(), re.IGNORECASE):
        raise ValueError("Esse nome é reservado pelo Windows.")
    return nome

def _sem_links(caminho):
    for parte in (caminho, *caminho.absolute().parents):
        try: info = parte.lstat()
        except FileNotFoundError: continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 1024:
            raise ValueError("Essa pasta ou arquivo usa um link. Escolha um destino direto na casa da Sheep.")

def _arquivos_sem_links(pasta):
    """Conta os arquivos de uma pasta da casa e recusa se achar algum link por dentro."""
    total = 0
    for atual, subpastas, arquivos in os.walk(pasta):
        for nome in subpastas + arquivos:
            info = os.lstat(os.path.join(atual, nome))
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 1024:
                raise ValueError("Achei um atalho (link) dentro dessa pasta. Por segurança, não apago.")
        total += len(arquivos)
    return total

def _alvo_apagavel(sub, nome):
    """A pasta `nome` dentro de casa/<sub>, só se for direta (sem link) e estiver mesmo dentro da casa da Sheep."""
    casa, raiz = caminhos.casa().resolve(), caminhos.sub(sub)
    alvo = raiz / nome
    _sem_links(raiz); _sem_links(alvo)
    if raiz.resolve().parent != casa or alvo.resolve().parent != raiz.resolve():
        raise ValueError("Só apago o que está dentro da casa da Sheep.")
    if not alvo.is_dir(): raise FileNotFoundError(nome)
    return alvo

def _apagar_pasta(alvo):
    def liberar(funcao, caminho, _erro):
        os.chmod(caminho, stat.S_IWRITE); funcao(caminho)
    try: shutil.rmtree(alvo, **({"onexc": liberar} if sys.version_info >= (3, 12) else {"onerror": liberar}))
    except OSError: pass
    if alvo.exists(): raise ValueError("Não consegui apagar tudo. Feche o que estiver usando essa pasta e tente de novo.")

def _titulo_do_pedido(texto):
    """As primeiras 6 palavras do pedido, sem os marcadores de anexo e com no máximo 50 letras."""
    limpo = " ".join(re.sub(r"\[arquivo:[^\]\r\n]*\]", " ", texto or "").split())
    titulo = " ".join(limpo.split()[:6])[:50].rstrip(" ,;:-")
    return titulo[:1].upper() + titulo[1:]

def _projetos():
    return sorted(d.name for d in caminhos.sub("projetos").iterdir() if d.is_dir())

def _estado():
    dono = caminhos.casa() / "casa" / "dono.md"
    linhas = dono.read_text(encoding="utf-8").splitlines() if dono.exists() else []
    nome = next((l.removeprefix("Nome:").strip() for l in linhas if l.startswith("Nome:")), None)
    parciais, avisos = {}, []
    for campo, ler, aviso in (("pacotes", pacotes.listar, "Não consegui carregar os pacotes. Confira os arquivos da Sheep e tente de novo."),
                              ("aprendi", memorias.novas, "Não consegui carregar os aprendizados. Confira a pasta memoria da Sheep e tente de novo.")):
        try:
            parciais[campo] = ler()
        except Exception:
            parciais[campo] = []
            avisos.append(aviso)
            try:
                with (caminhos.sub("logs") / "servidor.log").open("a", encoding="utf-8") as log:
                    log.write(traceback.format_exc() + "\n")
            except OSError:
                pass
    return {"instalacao": instalador.estado(), "proximo": instalador.proximo(), "passos": instalador.PASSOS,
            "dono_nome": nome or None, "primeiro_uso": not dono.exists(), "motor_padrao": motor.padrao(),
            "motores": motor.instalados(), "login": login.estado(), "conexoes": cofre.status(CONEXOES), "habilidades": habilidades.listar(),
            "aprovacoes": aprovacoes.pendentes(), "sessoes": sessoes.listar(),
            "projetos": _projetos(), "pastas_projetos": pastas.todas(), "claude_global": claude_global.estado(), "organizacao": organizacao.estado(_projetos()),
            "rotinas": rotinas.listar(), **parciais, "avisos": avisos,
            "aprender": cofre.ler("APRENDER") != "0", "whatsapp": whatsapp.estado()}

def iniciar(porta=0, ao_mostrar=None, refletir=None):
    token = secrets.token_urlsafe(24)
    eventos, totais, trabalhos = {}, {}, {}
    trava = threading.RLock()
    conexao_whatsapp = threading.Lock()
    encerrando = threading.Event()
    aprendiz = refletir or refletor.refletir

    def trabalho(sid):
        return trabalhos.setdefault(sid, {"trabalhando": False, "resumindo": False, "fila": [], "atual": None,
                                         "parcial": "", "acao": "", "revisao": 0, "cancelar": None, "fila_pausada": False})

    def situacao(sid, sessao=None):
        with trava:
            t = trabalho(sid)
            estado = {**{k: t[k] for k in ("trabalhando", "resumindo", "parcial", "acao", "revisao", "fila_pausada")},
                    "fila": [{"id": x["id"], "texto": x["texto"]} for x in t["fila"]],
                    "atual": {k: t["atual"][k] for k in ("id", "texto")} if t["atual"] else None,
                    "revisao": t["revisao"] + (sessao or {}).get("revisao", 0)}
        estado.update(viva=motor.viva(sid), trabalhando=estado['trabalhando'] or motor.ocupada(sid))
        if sessao and "mensagens" in sessao:
            # Pedido do dono sem resposta e nada rodando: a janela fechou no meio.
            ultima = sessao["mensagens"][-1] if sessao["mensagens"] else {}
            estado["interrompida"] = (ultima.get("quem") == "dono" and not estado["trabalhando"] and not estado["resumindo"]
                                      and not estado["fila"] and not estado["fila_pausada"] and not sessao.get("arquivada"))
        return estado

    def guardar(sid, evento):
        with trava:
            t = trabalho(sid)
            tipo, valor = evento.get("tipo"), evento.get("valor")
            if tipo == "parcial":
                t["parcial"] = str(valor or "")
                return
            if tipo == "acao": t["acao"] = str(valor or "")
            if tipo == "resumindo": t["resumindo"] = bool(valor)
            if tipo in ("fim", "erro"): t.update(parcial="", acao="")
            if tipo in ("marcador", "fim", "erro"): t["revisao"] += 1
            lista = eventos.setdefault(sid, [])
            lista.append(dict(evento)); del lista[:-50]
            totais[sid] = totais.get(sid, 0) + 1

    def nomear(sid, texto):
        """Conversa que ainda se chama 'Nova conversa' ganha o nome do primeiro pedido, sem chamar modelo.
        Título que a pessoa escolheu, de projeto ou do WhatsApp não muda."""
        try:
            sessao = sessoes.ler(sid)
            if sessao.get("titulo") not in ("Nova conversa", "nova") or sessao.get("titulo_manual") or sessao.get("origem"): return
            titulo = _titulo_do_pedido(texto)
            if titulo: sessoes.atualizar(sid, titulo=titulo)
        except (OSError, ValueError): pass

    def parada(sid):
        """Conversa sem pedido rodando nem na fila. Chamar com `trava`."""
        t = trabalho(sid)
        return not (t["trabalhando"] or t["fila"] or t["resumindo"] or motor.ocupada(sid))

    def esquecer(sids):
        with trava:
            for sid in sids:
                for memoria in (eventos, totais, trabalhos): memoria.pop(sid, None)
        organizacao.esquecer_conversas(set(sids))

    def executar(sid):
        while True:
            with trava:
                t = trabalho(sid)
                if not t["fila"] or t['fila_pausada']:
                    t.update(trabalhando=False, atual=None, cancelar=None)
                    return
                item = None if motor.ocupada(sid) else t["fila"].pop(0)
                if item:
                    cancelar = item["cancelar"]
                    t.update(atual=item, cancelar=cancelar, parcial="", acao="", resumindo=item["resumo"])
            if item is None:
                encerrando.wait(.05)
                continue
            try:
                if not item["resumo"]: nomear(sid, item["texto"])
                callback = lambda evento: guardar(sid, evento)
                if item["resumo"]:
                    motor.resumir(sid, ao_evento=callback, cancelar=cancelar)
                else:
                    resposta = motor.conversar(sid, item["texto"], ao_evento=callback, cancelar=cancelar)
                    if isinstance(resposta, str) and not cancelar.is_set(): aprender(sid, item["texto"], resposta)
            except motor.Cancelado:
                sessoes.anexar(sid, 'sheep', motor.PARADA)
                guardar(sid, {'tipo':'fim','valor':motor.PARADA})
            except Exception:
                detalhe = traceback.format_exc()
                try:
                    with (caminhos.sub("logs") / "servidor.log").open("a", encoding="utf-8") as log: log.write(detalhe + "\n")
                    sessoes.anexar(sid, "sheep", "Não consegui terminar esse pedido. Tenta de novo.")
                except OSError: pass
                guardar(sid, {"tipo": "erro", "valor": "Não consegui terminar esse pedido. Tenta de novo."})
            finally:
                with trava:
                    t.update(parcial="", acao="", resumindo=False, atual=None, cancelar=None)
                    t["revisao"] += 1

    def enfileirar(sid, texto="", resumo=False):
        with trava:
            t = trabalho(sid)
            ocupada = t["trabalhando"]
            na_fila = ocupada or t['fila_pausada'] or motor.ocupada(sid)
            item = {"id": secrets.token_hex(12), "texto": texto, "resumo": resumo, "cancelar": threading.Event()}
            t["fila"].append(item)
            if not ocupada and not t['fila_pausada']:
                t["trabalhando"] = True
                threading.Thread(target=executar, args=(sid,), daemon=True).start()
            return {"ok": True, "id": item["id"], "na_fila": na_fila}

    def aprender(sid, pedido, resposta):
        def trabalhar():
            try:
                refletor.executar(aprendiz, sid, pedido, resposta)
            except Exception:
                try:
                    with (caminhos.sub("logs") / "refletor.log").open("a", encoding="utf-8") as log:
                        log.write(traceback.format_exc() + "\n")
                except OSError: pass
        try:
            threading.Thread(target=trabalhar, daemon=True).start()
        except Exception: pass

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def parse_request(self):
            if not super().parse_request(): return False
            hosts = self.headers.get_all("Host", [])
            permitidos = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if len(hosts) != 1 or hosts[0] not in permitidos:
                self._json({"erro": "host não permitido"}, 403)
                return False
            return True
        def _json(self, obj, code=200):
            b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def _ok(self): return self.headers.get("X-Token") == token
        def _corpo(self):
            n = int(self.headers.get("Content-Length") or 0); return json.loads(self.rfile.read(n) or b"{}")
        def _atender(self, rota):
            try: return rota()
            except Exception:
                detalhe = traceback.format_exc()
                try:
                    with trava, (caminhos.sub("logs") / "servidor.log").open("a", encoding="utf-8") as log:
                        log.write(detalhe + "\n")
                except OSError: pass
                return self._json({"erro": "algo deu errado, tenta de novo"}, 500)
        def do_GET(self):
            return self._atender(self._get)
        def _get(self):
            if self.path.startswith("/api/"):
                if not self._ok(): return self._json({"erro": "sem permissão"}, 403)
                if self.path == "/api/identidade": return self._json(identidade.ler())
                if self.path == "/api/aparencia": return self._json(aparencia.tudo())
                if self.path == "/api/prompt-mestre":
                    for arq in (caminhos.casa() / "prompt-mestre.md", Path(__file__).resolve().parents[2] / "modelo" / "prompt-mestre.md"):
                        if arq.exists(): return self._json({"texto": arq.read_text(encoding="utf-8")})
                    return self._json({"erro": "Não achei o prompt mestre."}, 404)
                if self.path == "/api/estado":
                    estado = _estado()
                    estado["sessoes"] = [{**s, **situacao(s["id"], s)} for s in estado["sessoes"]]
                    return self._json(estado)
                if self.path == "/api/diagnostico": return self._json({"texto": diagnostico.montar()})
                if self.path == "/api/whatsapp/estado": return self._json(whatsapp.estado())
                if self.path.startswith("/api/sessao/"):
                    url = urlsplit(self.path)
                    partes = unquote(url.path).removeprefix("/api/sessao/").split("/")
                    sid = partes[0]
                    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", sid): return self._json({"erro": "sessão inválida"}, 400)
                    try: sessao = sessoes.ler(sid)
                    except FileNotFoundError: return self._json({"erro": "Conversa não encontrada."}, 404)
                    if partes[1:] == ["eventos"]:
                        try:
                            query = parse_qs(url.query, keep_blank_values=True)
                            if set(query) - {"desde"} or len(query.get("desde", ["0"])) != 1: raise ValueError()
                            desde = int(query.get("desde", ["0"])[0])
                            if desde < 0: raise ValueError()
                        except ValueError: return self._json({"erro": "cursor inválido"}, 400)
                        with trava:
                            lista, total = eventos.get(sid, []), totais.get(sid, 0)
                            resposta = {"eventos": lista[max(0, desde - (total - len(lista))):], "total": total,
                                        "contexto": sessao.get("contexto", {}), "tokens_total": sessao.get("tokens_total", 0)}
                        resposta.update(situacao(sid, sessao))
                        return self._json(resposta)
                    if len(partes) == 1:
                        sessao["aprovacoes"] = aprovacoes.da_sessao(sid)
                        return self._json({**sessao, **situacao(sid, sessao)})
                return self._json({"erro": "não encontrado"}, 404)
            nome = "instalador.html" if self.path in ("/", "") and instalador.proximo() else ("app.html" if self.path in ("/", "") else self.path.lstrip("/").split("?")[0])
            if nome.startswith("voz/") and identidade.ler()["trocado"]: return self._json({"erro": "não encontrado"}, 404)
            propria = aparencia.imagem_da_ui(nome)
            if propria:
                self.send_response(200); self.send_header("Content-Type", propria[1]); self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(propria[0]))); self.end_headers(); self.wfile.write(propria[0])
                return
            arq = (UI / nome).resolve()
            if UI.resolve() not in arq.parents or not arq.is_file(): return self._json({"erro": "não encontrado"}, 404)
            b = arq.read_bytes().replace(b"__TOKEN__", token.encode()) if arq.suffix in (".html", ".js") else arq.read_bytes()
            if arq.name == "estilo.css": b = aparencia.tingir(b)
            self.send_response(200); self.send_header("Content-Type", TIPOS.get(arq.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def do_POST(self):
            return self._atender(self._post)
        def _post(self):
            if not self._ok():
                anterior = self.connection.gettimeout()
                try:
                    tamanho = int(self.headers.get("Content-Length") or 0)
                    if 0 < tamanho <= 4096:
                        self.connection.settimeout(.3)
                        self.rfile.read(tamanho)
                except (ValueError, OSError):
                    pass
                finally:
                    self.connection.settimeout(anterior)
                return self._json({"erro": "sem permissão"}, 403)
            p = self.path
            if p.startswith("/api/aparencia"):
                try: return self._aparencia(p)
                except (ValueError, UnicodeError) as erro: return self._json({"erro": str(erro)}, 400)
            if p in ("/api/anexo", "/api/sessao/motor", "/api/sessao/mover"):
                try:
                    tamanhos = self.headers.get_all("Content-Length", [])
                    if len(tamanhos) != 1 or not re.fullmatch(r"[0-9]+", tamanhos[0]) or self.headers.get("Transfer-Encoding"):
                        raise ValueError("Pedido inválido.")
                    limite = 4 * ((LIMITE_ANEXO + 2) // 3) + 4096 if p == "/api/anexo" else 4096
                    if int(tamanhos[0]) > limite:
                        return self._json({"erro": "Esse arquivo passou de 20 MB." if p == "/api/anexo" else "Pedido grande demais."}, 413)
                    try: c = self._corpo()
                    except (ValueError, UnicodeError): raise ValueError("Pedido inválido.") from None
                    if not isinstance(c, dict): raise ValueError("Pedido inválido.")
                    return self._anexo(c) if p == "/api/anexo" else self._conversa(p, c)
                except (ValueError, UnicodeError) as erro:
                    return self._json({"erro": str(erro)}, 400)
                except FileNotFoundError:
                    return self._json({"erro": "Conversa não encontrada."}, 404)
            if p in ("/api/projeto/resumo", "/api/projeto/apagar"):
                try:
                    tamanho = int(self.headers.get("Content-Length") or 0)
                    if not 0 <= tamanho <= 4096: raise ValueError("Pedido inválido.")
                    c = self._corpo()
                    if not isinstance(c, dict): raise ValueError("Pedido inválido.")
                    return self._projeto_apagar(p, c)
                except (ValueError, UnicodeError) as erro:
                    return self._json({"erro": str(erro)}, 400)
                except FileNotFoundError:
                    return self._json({"erro": "Esse projeto não existe mais."}, 404)
            if p in ("/api/conversar", "/api/parar", "/api/resumir", "/api/fila/cancelar", "/api/fila/retomar", "/api/sessao/renomear", "/api/sessao/fechar", "/api/sessao/arquivar", "/api/sessao/apagar"):
                try:
                    tamanho = int(self.headers.get("Content-Length") or 0)
                    if not 0 <= tamanho <= 1024 * 1024: raise ValueError("Pedido inválido.")
                    c = self._corpo()
                    if not isinstance(c, dict): raise ValueError("Pedido inválido.")
                    return self._conversa(p, c)
                except (ValueError, UnicodeError) as erro:
                    return self._json({"erro": str(erro)}, 400)
                except FileNotFoundError:
                    return self._json({"erro": "Conversa não encontrada."}, 404)
            if p.startswith("/api/whatsapp/"):
                try:
                    tamanho = int(self.headers.get("Content-Length") or 0)
                    if not 0 <= tamanho <= 4096: raise ValueError("Pedido de WhatsApp inválido.")
                    c = self._corpo()
                    if not isinstance(c, dict): raise ValueError("Pedido de WhatsApp inválido.")
                    return self._whatsapp(p, c)
                except (ValueError, UnicodeError) as erro:
                    return self._json({"erro": str(erro)}, 400)
                except OSError as erro:
                    whatsapp._registrar(erro)
                    return self._json({"erro": instalador.erro_amigavel(erro)}, 503)
            if p in ("/api/pacote/instalar", "/api/pacote/previa", "/api/pacote/remover", "/api/memoria", "/api/abrir"):
                try:
                    try: tamanho = int(self.headers.get("Content-Length") or 0)
                    except ValueError: raise ValueError("Pedido inválido.") from None
                    if tamanho < 0: raise ValueError("Pedido inválido.")
                    if tamanho > 4 * ((LIMITE_ZIP + 2) // 3) + 4096:
                        return self._json({"erro": "Esse arquivo passou de 30 MB."}, 413)
                    try: c = self._corpo()
                    except (ValueError, UnicodeError): raise ValueError("Pedido inválido.") from None
                    if not isinstance(c, dict): raise ValueError("Pedido inválido.")
                    return self._nova_rota(p, c)
                except ValueError as erro:
                    return self._json({"erro": str(erro)}, 400)
            c = self._corpo()
            if p.startswith("/api/organizacao/"):
                try: return self._organizacao(p, c)
                except ValueError as erro: return self._json({"erro": str(erro)}, 400)
            if p in ("/api/sessao", "/api/projeto") and c.get("motor", "claude") not in motor.MOTORES:
                return self._json({"erro": "motor desconhecido"}, 400)
            if p == "/api/identidade":
                try: return self._json(identidade.gravar(c))
                except ValueError as erro: return self._json({"erro": str(erro)}, 400)
            if p == "/api/mostrar":
                if ao_mostrar is not None: ao_mostrar()
                return self._json({"ok": True})
            if p in ("/api/motor/entrar", "/api/motor/testar"):
                nome = c.get("nome")
                if nome not in motor.MOTORES: return self._json({"erro": "motor desconhecido"}, 400)
                if p.endswith("/testar"): return self._json({"ok": motor.testar(nome)})
                instalador.completar_path()
                caminho = shutil.which(motor.MOTORES[nome])
                if not caminho: return self._json({"ok": False})
                subprocess.Popen([caminho], creationflags=subprocess.CREATE_NEW_CONSOLE)
                return self._json({"ok": True})
            if p == "/api/motor/login":
                nome = c.get("nome")
                if nome not in login.ENTRAR: return self._json({"erro": "motor desconhecido"}, 400)
                return self._json({"ok": login.entrar(nome)})
            if p == "/api/instalar":
                if c.get("passo") not in [passo["id"] for passo in instalador.PASSOS]:
                    return self._json({"erro": "passo desconhecido"}, 400)
                if "pular" in c and (not isinstance(c["pular"], bool) or c["pular"] and c["passo"] not in ("login", "whatsapp", "telegram")):
                    return self._json({"erro": "Esse passo precisa ser concluído."}, 400)
                log = []
                opcoes = {"pular": True} if c.get("pular") else {}
                ok = instalador.executar(c["passo"], log=log.append, **opcoes)
                return self._json({"ok": ok, "log": log})
            if p == "/api/sessao":
                projeto = "".join(ch for ch in (c.get("projeto") or "") if ch.isalnum() or ch in " -_").strip() or None
                return self._json(sessoes.criar(c.get("titulo", "nova"), projeto, c.get("motor", "claude")))
            if p == "/api/aprovacao": return self._json(aprovacoes.decidir(c["id"], bool(c["aprovar"])))
            if p == "/api/habilidade": habilidades.ligar(c["id"], c["ligada"]); return self._json({"ok": True})
            if p == "/api/conexao":
                if c["nome"] not in CONEXOES: return self._json({"erro": "conexão desconhecida"}, 400)
                cofre.guardar(c["nome"], c["valor"]); return self._json({"ok": True})
            if p == "/api/telegram/codigo": return self._json({"codigo": telegram.novo_codigo()})
            if p == "/api/telegram/vincular": return self._json({"chat": telegram.vincular(cofre.ler("TELEGRAM_CODIGO"))})
            if p == "/api/claude/global":
                try: return self._json(claude_global.ligar() if c.get("ligar") else claude_global.desligar())
                except (OSError, ValueError) as erro: return self._json({"erro": str(erro)}, 400)
            if p == "/api/projeto/pasta":
                caminho = c.get("caminho") or pastas.escolher()
                if not caminho: return self._json({"cancelado": True})
                try: pasta = pastas.validar(caminho)
                except ValueError as erro: return self._json({"erro": str(erro)}, 400)
                nome = "".join(ch for ch in pasta.name if ch.isalnum() or ch in " -_").strip() or "Projeto"
                pastas.ligar(nome, pasta)
                if c.get("grupo"): organizacao.adotar_projeto(_projetos(), nome, c.get("grupo"))
                return self._json(sessoes.criar(nome, projeto=nome, motor=c.get("motor", "claude")))
            if p == "/api/projeto":
                nome = "".join(ch for ch in c["nome"] if ch.isalnum() or ch in " -_").strip()
                if not nome: return self._json({"erro": "nome vazio"}, 400)
                (caminhos.sub("projetos") / nome).mkdir(exist_ok=True)
                return self._json(sessoes.criar(nome, projeto=nome, motor=c.get("motor", "claude")))
            if p == "/api/rotina": rotinas.ligar(c["nome"], c["ativo"]); return self._json({"ok": True})
            return self._json({"erro": "não encontrado"}, 404)

        def _aparencia(self, p):
            tamanho = self.headers.get("Content-Length", "")
            if not tamanho.isdigit() or self.headers.get("Transfer-Encoding"): raise ValueError("Pedido inválido.")
            if int(tamanho) > 4 * ((aparencia.LIMITE_IMAGEM + 2) // 3) + 4096: return self._json({"erro": "Essa imagem passou de 8 MB."}, 413)
            c = self._corpo()
            if not isinstance(c, dict): raise ValueError("Pedido inválido.")
            if p == "/api/aparencia": return self._json(aparencia.gravar(c))
            if p == "/api/aparencia/imagem": return self._json(aparencia.guardar_imagem(c.get("alvo"), c.get("base64")))
            if p == "/api/aparencia/limpar": return self._json(aparencia.limpar(c.get("alvo")))
            return self._json({"erro": "não encontrado"}, 404)

        def _organizacao(self, p, c):
            if not isinstance(c, dict): raise ValueError("Pedido inválido.")
            projetos = _projetos()
            acao = p.removeprefix("/api/organizacao/")
            if acao == "pasta": organizacao.criar_pasta(projetos, c.get("nome"))
            elif acao == "pasta/renomear": organizacao.renomear_pasta(projetos, c.get("id"), c.get("nome"))
            elif acao == "pasta/excluir": organizacao.excluir_pasta(projetos, c.get("id"))
            elif acao == "projeto":
                nome = "".join(ch for ch in str(c.get("nome") or "") if ch.isalnum() or ch in " -_").strip()
                if not nome: raise ValueError("Escolha um nome para o projeto.")
                _nome_seguro(nome)
                if nome.casefold() == "geral" or nome in projetos: raise ValueError("Já existe um projeto com esse nome.")
                (caminhos.sub("projetos") / nome).mkdir(exist_ok=True)
                organizacao.adotar_projeto(_projetos(), nome, c.get("pasta"))
            elif acao == "projeto/mover": organizacao.mover_projeto(projetos, c.get("projeto"), c.get("pasta"))
            elif acao == "projeto/renomear": organizacao.renomear_projeto(projetos, c.get("projeto"), c.get("nome"))
            elif acao == "recolher": organizacao.recolher(projetos, c.get("chave"), bool(c.get("recolhido")))
            else: return self._json({"erro": "não encontrado"}, 404)
            return self._json({"ok": True, "organizacao": organizacao.estado(_projetos())})

        def _anexo(self, c):
            if set(c) != {"nome", "base64"} or not isinstance(c["base64"], str): raise ValueError("Pedido inválido.")
            nome = _nome_seguro(c["nome"])
            codificado = c["base64"]
            if len(codificado) > 4 * ((LIMITE_ANEXO + 2) // 3):
                return self._json({"erro": "Esse arquivo passou de 20 MB."}, 413)
            try: dados = base64.b64decode(codificado, validate=True)
            except (ValueError, UnicodeError): raise ValueError("Esse anexo não tem um conteúdo válido.") from None
            if base64.b64encode(dados).decode() != codificado: raise ValueError("Esse anexo não tem um conteúdo válido.")
            if len(dados) > LIMITE_ANEXO:
                return self._json({"erro": "Esse arquivo passou de 20 MB."}, 413)
            pasta = caminhos.casa() / "anexos"
            _sem_links(pasta)
            pasta.mkdir(parents=True, exist_ok=True)
            destino = pasta / nome
            while True:
                _sem_links(destino)
                if pasta.resolve().parent != caminhos.casa().resolve() or destino.resolve().parent != pasta.resolve():
                    raise ValueError("Escolha um destino dentro da casa da Sheep.")
                try:
                    with destino.open("xb") as arquivo: arquivo.write(dados)
                    break
                except FileExistsError:
                    destino = pasta / f"{Path(nome).stem}-{secrets.token_hex(6)}{Path(nome).suffix}"
            return self._json({"ok": True, "nome": destino.name, "caminho": "anexos/" + destino.name})

        def _conversa(self, p, c):
            extras = {"/api/conversar": {"texto"}, "/api/fila/cancelar": {"id"},
                      "/api/sessao/renomear": {"titulo"}, "/api/sessao/arquivar": {"arquivada"},
                      "/api/sessao/motor": {"motor"}, "/api/sessao/mover": {"projeto"}}
            sid = c.get("sessao")
            if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", sid): raise ValueError("sessão inválida")
            if set(c) != {"sessao"} | extras.get(p, set()): raise ValueError("Pedido inválido.")
            if p == "/api/sessao/apagar":
                with trava:
                    reserva = motor.reservar(sid) if parada(sid) else None
                    if reserva is None: return self._json({"erro": "Essa conversa está trabalhando ou na fila. Espera terminar para apagar."}, 409)
                    try:
                        alvo = _alvo_apagavel("sessoes", sid)
                        _arquivos_sem_links(alvo)
                        motor.adormecer(sid)
                        sessoes.apagar(sid, lambda: _apagar_pasta(alvo))
                    finally: reserva.release()
                    esquecer([sid])
                return self._json({"ok": True})
            sessao = sessoes.ler(sid)
            if p in ("/api/conversar", "/api/resumir"):
                if p == "/api/conversar" and (not isinstance(c["texto"], str) or not c["texto"].strip()): raise ValueError("Escreva seu pedido.")
                with trava:
                    if sessoes.ler(sid).get("arquivada"): return self._json({"erro": "Reabra a conversa antes de enviar ou resumir."}, 409)
                    resposta = enfileirar(sid, c.get("texto", ""), resumo=p == "/api/resumir")
                return self._json(resposta, 202)
            with trava:
                t = trabalho(sid)
                if p == "/api/parar":
                    t['fila_pausada'] = True
                    if t["cancelar"]: t["cancelar"].set()
                    motor.parar(sid)
                elif p == '/api/fila/retomar':
                    if sessao.get('arquivada'): return self._json({'erro':'Reabra a conversa antes de continuar.'}, 409)
                    t['fila_pausada'] = False
                    if t['fila'] and not t['trabalhando']:
                        t['trabalhando'] = True
                        threading.Thread(target=executar, args=(sid,), daemon=True).start()
                elif p == "/api/fila/cancelar":
                    id = c["id"]
                    if not isinstance(id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", id): raise ValueError("Pedido inválido.")
                    antes = len(t["fila"])
                    t["fila"] = [x for x in t["fila"] if x["id"] != id]
                    if len(t["fila"]) == antes: return self._json({"erro": "Esse pedido já saiu da fila."}, 409)
                elif p == "/api/sessao/renomear":
                    titulo = c["titulo"]
                    if not isinstance(titulo, str) or not titulo.strip() or len(titulo.strip()) > 120 or any(ord(x) < 32 for x in titulo): raise ValueError("Use um título de 1 a 120 caracteres.")
                    sessoes.atualizar(sid, titulo=titulo.strip(), titulo_manual=True)
                elif p in ("/api/sessao/motor", "/api/sessao/mover"):
                    campo = "motor" if p.endswith("motor") else "projeto"
                    valor = c[campo]
                    if campo == "motor":
                        if not isinstance(valor, str) or valor not in motor.MOTORES: raise ValueError("Motor desconhecido.")
                        if not motor.instalados().get(valor): raise ValueError("Esse motor não está instalado neste PC.")
                    elif valor is not None:
                        _nome_seguro(valor)
                        pasta = caminhos.casa() / "projetos"
                        projeto = pasta / valor
                        _sem_links(projeto)
                        if not projeto.is_dir() or pasta.resolve().parent != caminhos.casa().resolve() or projeto.resolve().parent != pasta.resolve():
                            raise ValueError("Escolha um projeto existente na casa da Sheep.")
                    reserva = None if t["trabalhando"] or t["fila"] or motor.ocupada(sid) else motor.reservar(sid)
                    if reserva is None:
                        return self._json({"erro": "Espera esse pedido terminar antes de trocar o motor ou mover a conversa."}, 409)
                    try:
                        if sessoes.ler(sid).get(campo) == valor: return self._json({"ok": True})
                        motor.adormecer(sid)
                        sessoes.atualizar(sid, **{campo: valor}, motor_id=None, contexto={}, contexto_estimado=False)
                    finally: reserva.release()
                else:
                    if p.endswith("arquivar") and not isinstance(c["arquivada"], bool): raise ValueError("Escolha se quer arquivar a conversa.")
                    if t["trabalhando"] or t["fila"] or motor.ocupada(sid): return self._json({"erro": "Espera esse pedido terminar antes de fechar ou arquivar."}, 409)
                    motor.adormecer(sid)
                    if p.endswith("arquivar"): sessoes.atualizar(sid, arquivada=c["arquivada"])
                t["revisao"] += 1
            return self._json({"ok": True})

        def _projeto_apagar(self, p, c):
            if set(c) != {"projeto"}: raise ValueError("Pedido inválido.")
            nome = _nome_seguro(c["projeto"])
            if nome.casefold() in ("geral", "@whatsapp"): raise ValueError("O Geral e o WhatsApp não se apagam.")
            with trava:
                if nome not in _projetos(): raise FileNotFoundError(nome)
                alvo = _alvo_apagavel("projetos", nome)
                arquivos = _arquivos_sem_links(alvo)
                ids = [s["id"] for s in sessoes.listar() if s.get("projeto") == nome and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", str(s.get("id")))]
                if p == "/api/projeto/resumo":
                    return self._json({"ok": True, "conversas": len(ids), "arquivos": arquivos, "externa": bool(pastas.externa(nome))})
                reservas, apagadas = [], []
                try:
                    for sid in ids:
                        reserva = motor.reservar(sid) if parada(sid) else None
                        if reserva is None: return self._json({"erro": "Tem conversa trabalhando ou na fila nesse projeto. Espera terminar para apagar."}, 409)
                        reservas.append(reserva)
                    alvos = [_alvo_apagavel("sessoes", sid) for sid in ids]
                    for a in alvos: _arquivos_sem_links(a)
                    for sid, a in zip(ids, alvos):
                        motor.adormecer(sid)
                        sessoes.apagar(sid, lambda a=a: _apagar_pasta(a))
                        apagadas.append(sid)
                    _apagar_pasta(alvo)
                finally:
                    for reserva in reservas: reserva.release()
                    esquecer(apagadas)
                organizacao.esquecer_projeto(_projetos())
                return self._json({"ok": True, "conversas": len(ids), "organizacao": organizacao.estado(_projetos())})

        def _whatsapp(self, p, c):
            if p == "/api/whatsapp/conectar":
                if conexao_whatsapp.acquire(blocking=False):
                    cofre.guardar("WHATSAPP_LIGADO", "1")
                    ponte = whatsapp.ponte()
                    def conectar():
                        try:
                            if cofre.ler("WHATSAPP_LIGADO") == "1": ponte.conectar()
                        finally:
                            if cofre.ler("WHATSAPP_LIGADO") != "1": ponte.parar()
                            conexao_whatsapp.release()
                    threading.Thread(target=conectar, daemon=True).start()
                return self._json({"ok": True})
            if p == "/api/whatsapp/sair":
                if not conexao_whatsapp.acquire(blocking=False):
                    raise ValueError("Ainda tô preparando o WhatsApp. Espera terminar pra desconectar.")
                try:
                    resultado = whatsapp.ponte().sair()
                finally:
                    cofre.guardar("WHATSAPP_LIGADO", "0")
                    whatsapp.ponte().parar()
                    conexao_whatsapp.release()
                return self._json({"ok": True, **({"mensagem": resultado["mensagem"]} if resultado.get("mensagem") else {})})
            if p == "/api/whatsapp/voz":
                if not isinstance(c.get("ligado"), bool): raise ValueError("Escolhe se quer resposta em áudio.")
                cofre.guardar("WHATSAPP_VOZ", "1" if c["ligado"] else "0")
                return self._json({"ok": True})
            return self._json({"erro": "não encontrado"}, 404)

        def _nova_rota(self, p, c):
            if p == "/api/abrir":
                url = c.get("url")
                if not isinstance(url, str) or any(ord(ch) <= 32 for ch in url):
                    raise ValueError("Esse link não pode abrir aqui.")
                try:
                    partes = urlsplit(url)
                    valido = partes.scheme.lower() in ("http", "https") and bool(partes.hostname)
                except ValueError:
                    valido = False
                if not valido: raise ValueError("Só abro links http ou https no navegador.")
                if not webbrowser.open(url):
                    raise ValueError("Não consegui abrir o navegador. Tente de novo.")
                return self._json({"ok": True})
            if p == "/api/memoria":
                acao, arquivo = c.get("acao"), c.get("arquivo")
                if acao not in ("manter", "descartar") or not isinstance(arquivo, str):
                    raise ValueError("Não entendi o que fazer com essa memória.")
                getattr(memorias, acao)(arquivo)
                return self._json({"ok": True})
            if p == "/api/pacote/previa" and "zip_base64" not in c:
                raise ValueError("Escolha um arquivo ZIP para ver a prévia.")
            if p in ("/api/pacote/instalar", "/api/pacote/previa") and "zip_base64" in c:
                if "id" in c or not isinstance(c["zip_base64"], str):
                    raise ValueError("Esse arquivo não parece um pacote da Sheep.")
                codificado = c["zip_base64"]
                if len(codificado) > 4 * ((LIMITE_ZIP + 2) // 3):
                    return self._json({"erro": "Esse arquivo passou de 30 MB."}, 413)
                try: origem = base64.b64decode(codificado, validate=True)
                except (ValueError, UnicodeError):
                    raise ValueError("Esse arquivo não parece um pacote da Sheep.") from None
                if len(origem) > LIMITE_ZIP:
                    return self._json({"erro": "Esse arquivo passou de 30 MB."}, 413)
            else:
                origem = c.get("id")
                if not isinstance(origem, str) or not re.fullmatch(r"[a-z0-9-]{2,40}", origem):
                    raise ValueError("Escolha um pacote da Sheep.")
            if p == "/api/pacote/previa":
                return self._json(pacotes.previa(origem))
            if p == "/api/pacote/instalar":
                return self._json({"ok": True, "pacote": pacotes.instalar(origem)})
            pacotes.remover(origem)
            return self._json({"ok": True})

    class Servidor(ThreadingHTTPServer):
        def server_close(self):
            with trava:
                encerrando.set()
                for sid, t in trabalhos.items():
                    t["fila"].clear()
                    if t["cancelar"]: t["cancelar"].set()
                    if t["trabalhando"]: motor.parar(sid)
            super().server_close()

    srv = Servidor(("127.0.0.1", porta), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}", token
