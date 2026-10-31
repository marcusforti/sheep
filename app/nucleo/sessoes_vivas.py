import json, queue, subprocess, threading, time
from collections import deque
from nucleo import caminhos, sessoes


class Gerenciador:
    def __init__(self, iniciar=None, agora=None, limite=2, ocioso=300, monitorar=True):
        from nucleo import motor
        self.iniciar = iniciar or motor.iniciar_processo
        self.agora = agora or time.monotonic
        self.limite, self.ocioso = limite, ocioso
        self._vivas, self._falhas = {}, {}
        self._vez = threading.Condition(threading.RLock())
        self._parar = threading.Event()
        self._monitor = None
        self._monitorar = monitorar

    def _vigiar(self):
        while not self._parar.wait(1): self.limpar()

    def _encerrar(self, sid, item):
        try:
            item['fechar']()
            if item.get('escritor'): item['escritor'].join(timeout=1)
            if item.get('leitor'): item['leitor'].join(timeout=1)
            for canal in (item['processo'].stdin, item['processo'].stdout):
                if canal and not canal.closed: canal.close()
        finally:
            with self._vez:
                if self._vivas.get(sid) is item: self._vivas.pop(sid)
                self._vez.notify_all()

    def adormecer(self, sid):
        with self._vez:
            item = self._vivas.get(sid)
            if not item or item.get('fechando'): return
            item['fechando'] = True
            if item.get('abrindo'): return
        self._encerrar(sid, item)

    def viva(self, sid):
        with self._vez:
            item = self._vivas.get(sid)
            return bool(item and not item.get('abrindo') and not item.get('fechando') and item['processo'].poll() is None)

    def limpar(self):
        fechar = []
        with self._vez:
            for sid, item in list(self._vivas.items()):
                if not item['ocupada'] and not item.get('fechando') and (item['processo'].poll() is not None or self.agora() - item['ultimo'] >= self.ocioso):
                    item['fechando'] = True
                    fechar.append((sid, item))
        for sid, item in fechar: self._encerrar(sid, item)

    def _acordar(self, sid, cancelar, prazo, sem_resume=False):
        from nucleo import motor
        while True:
            self.limpar()
            dormir = None
            with self._vez:
                if self._parar.is_set() or cancelar is not None and cancelar.is_set(): raise motor.Cancelado()
                item = self._vivas.get(sid)
                if item and not item['ocupada'] and not item.get('fechando'):
                    item['ocupada'] = True
                    return item
                if not item:
                    if len(self._vivas) >= self.limite:
                        livres = [(s, v) for s, v in self._vivas.items() if not v['ocupada'] and not v.get('fechando')]
                        if livres:
                            dormir = min(livres, key=lambda v:v[1]['ultimo'])
                            dormir[1]['fechando'] = True
                    if len(self._vivas) < self.limite:
                        item = {'abrindo':True, 'ocupada':True, 'ultimo':self.agora()}
                        self._vivas[sid] = item
                        break
                if time.monotonic() >= prazo: raise subprocess.TimeoutExpired('sessão', 900)
                if not dormir: self._vez.wait(.05)
            if dormir: self._encerrar(*dormir)
        try:
            s = sessoes.ler(sid)
            if sem_resume: s['motor_id'] = None
            cmd = motor.comando('claude', '', s.get('motor_id')) + ['--input-format', 'stream-json']
            cwd = caminhos.sub('projetos') / s['projeto'] if s.get('projeto') else caminhos.casa()
            inicio = time.monotonic()
            p, fechar = self.iniciar(cmd, str(cwd), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
            saida = queue.Queue()
            def ler():
                try:
                    for linha in p.stdout: saida.put(linha)
                finally: saida.put(None)
            leitor = threading.Thread(target=ler, daemon=True)
            with self._vez:
                item.update(processo=p, fechar=fechar, saida=saida, leitor=leitor, motor_id=s.get('motor_id'),
                            resume=bool(s.get('motor_id')), inicio=inicio, diagnostico=deque(maxlen=20), abrindo=False)
                leitor.start()
                abortar = item.get('fechando') or self._parar.is_set() or cancelar is not None and cancelar.is_set()
                if abortar: item['fechando'] = True
                if self._monitorar and self._monitor is None:
                    self._monitor = threading.Thread(target=self._vigiar, daemon=True)
                    self._monitor.start()
                self._vez.notify_all()
            if abortar:
                self._encerrar(sid, item)
                raise motor.Cancelado()
            return item
        except BaseException:
            with self._vez:
                if item.get('abrindo') and self._vivas.get(sid) is item: self._vivas.pop(sid)
                self._vez.notify_all()
            raise

    def executar(self, sid, pedido, cancelar=None, tempo_limite=900):
        from nucleo import motor
        prazo = time.monotonic() + tempo_limite
        for tentativa in range(2):
            item, terminou, falhou = None, False, False
            try:
                item = self._acordar(sid, cancelar, prazo, sem_resume=tentativa > 0)
                p = item['processo']
                item['diagnostico'].clear()
                iniciais = []
                while True:
                    try: linha = item['saida'].get_nowait()
                    except queue.Empty: break
                    if linha is None: raise OSError('O processo da sessão encerrou antes do pedido.')
                    try: dado = json.loads(linha)
                    except (ValueError, TypeError):
                        item['diagnostico'].append(linha.rstrip())
                        continue
                    if isinstance(dado, dict) and dado.get('type') == 'system' and dado.get('subtype') == 'init': iniciais.append(linha)
                erros = queue.Queue()
                def escrever():
                    try:
                        p.stdin.write(json.dumps({'type':'user','message':{'role':'user','content':pedido}},ensure_ascii=False)+'\n')
                        p.stdin.flush()
                    except Exception as erro: erros.put(erro)
                with self._vez:
                    if self._parar.is_set() or cancelar is not None and cancelar.is_set(): raise motor.Cancelado()
                    if self._vivas.get(sid) is not item or item.get('fechando'): raise OSError('O processo da sessão já encerrou.')
                    escritor = item['escritor'] = threading.Thread(target=escrever, daemon=True)
                    escritor.start()
                while True:
                    if self._parar.is_set() or cancelar is not None and cancelar.is_set(): raise motor.Cancelado()
                    if time.monotonic() >= prazo: raise subprocess.TimeoutExpired('claude', tempo_limite)
                    if escritor.is_alive():
                        escritor.join(timeout=.05)
                        continue
                    if not erros.empty(): raise OSError('Não consegui enviar o pedido ao motor.') from erros.get()
                    try: linha = iniciais.pop(0) if iniciais else item['saida'].get(timeout=.05)
                    except queue.Empty: continue
                    if linha is None: raise OSError('O processo da sessão encerrou antes da resposta.')
                    try: dado = json.loads(linha)
                    except (ValueError, TypeError):
                        item['diagnostico'].append(linha.rstrip())
                        erro = motor.erro_amigavel('claude', linha)
                        if erro: yield json.dumps({'type':'error','message':erro})
                        continue
                    if not isinstance(dado, dict) or dado.get('parent_tool_use_id'): continue
                    if dado.get('session_id') and dado['session_id'] != item['motor_id']:
                        motor._persistir(sessoes.registrar_motor_id, sid, dado['session_id'])
                        item['motor_id'] = dado['session_id']
                    if dado.get('type') == 'result':
                        terminou, falhou = True, bool(dado.get('is_error'))
                        self._falhas[sid] = 0
                    yield linha
                    if terminou: return
            except OSError:
                if item and item.get('resume') and time.monotonic() - item['inicio'] < 5 and tentativa == 0:
                    motor._persistir(sessoes.registrar_motor_id, sid, None)
                else:
                    self._falhas[sid] = self._falhas.get(sid, 0) + 1
                    if self._falhas[sid] >= 2:
                        motor._persistir(sessoes.atualizar, sid, modo_unico=True)
                        motor._log(f'{sid}: fallback para processo único após duas falhas consecutivas.')
                    raise
            finally:
                if item and (not terminou or falhou): motor._log(f'{sid}: turno falhou\n' + '\n'.join(item['diagnostico']))
                if item and not terminou: self.adormecer(sid)
                with self._vez:
                    if item and self._vivas.get(sid) is item:
                        item['ocupada'] = False
                        item['ultimo'] = self.agora()
                    self._vez.notify_all()

    def fechar(self):
        self._parar.set()
        with self._vez: ids = list(self._vivas)
        for sid in ids: self.adormecer(sid)
        if self._monitor and self._monitor is not threading.current_thread(): self._monitor.join(timeout=2)


_instancia, _casa = None, None
_trava = threading.Lock()


def ocupadas():
    g = _instancia
    if not g or _casa != caminhos.casa(): return 0
    with g._vez: return sum(bool(v['ocupada']) for v in g._vivas.values())


def instancia():
    global _instancia, _casa
    with _trava:
        casa = caminhos.casa()
        if _instancia is None or _casa != casa or _instancia._parar.is_set():
            if _instancia: _instancia.fechar()
            _instancia, _casa = Gerenciador(), casa
        return _instancia


def fechar():
    with _trava:
        if _instancia: _instancia.fechar()
