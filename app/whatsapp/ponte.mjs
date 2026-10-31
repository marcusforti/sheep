import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomBytes, randomUUID, timingSafeEqual } from 'node:crypto';
import { mkdir, readdir, unlink, writeFile, readFile, rename, rm, stat, lstat } from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

function falha(status, mensagem) {
  return Object.assign(new Error(mensagem), { status });
}

function normalizar(jid) {
  if (typeof jid !== 'string') return '';
  const partes = /^(\d+)(?::\d+)?@(s\.whatsapp\.net|lid)$/.exec(jid);
  return partes ? `${partes[1]}@${partes[2]}` : '';
}

function conteudo(message) {
  for (let i = 0; i < 8 && message; i++) {
    if (message.protocolMessage || message.reactionMessage) return null;
    const embrulho = message.ephemeralMessage || message.viewOnceMessage || message.viewOnceMessageV2 || message.viewOnceMessageV2Extension || message.documentWithCaptionMessage;
    if (!embrulho) break;
    message = embrulho.message;
  }
  if (!message) return null;
  if (typeof message.conversation === 'string') return { tipo: 'texto', texto: message.conversation };
  if (typeof message.extendedTextMessage?.text === 'string') return { tipo: 'texto', texto: message.extendedTextMessage.text };
  for (const [campo, tipo] of [['audioMessage', 'audio'], ['imageMessage', 'imagem'], ['documentMessage', 'documento']]) {
    if (message[campo]) return { tipo, texto: message[campo].caption || '', midia: message[campo] };
  }
  return null;
}

function extensao(midia, tipo) {
  const mime = (midia.mimetype || '').split(';')[0];
  const conhecidos = { 'audio/ogg': '.ogg', 'audio/mpeg': '.mp3', 'audio/mp4': '.m4a', 'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp', 'application/pdf': '.pdf' };
  if (conhecidos[mime]) return conhecidos[mime];
  const ext = path.extname(midia.fileName || '').toLowerCase();
  return tipo === 'documento' && /^\.[a-z0-9]{1,8}$/.test(ext) ? ext : '.bin';
}

async function dependenciasReais() {
  const [baileys, qrcode, pino] = await Promise.all([import('@whiskeysockets/baileys'), import('qrcode'), import('pino')]);
  const logger = pino.default({ level: 'warn' }, pino.destination(2));
  return {
    loadAuth: baileys.useMultiFileAuthState,
    fetchLatestBaileysVersion: baileys.fetchLatestBaileysVersion,
    generateMessageIDV2: baileys.generateMessageIDV2,
    makeSocket: options => baileys.default({ ...options, logger, syncFullHistory: false, shouldSyncHistoryMessage: () => false, markOnlineOnConnect: false }),
    qr: valor => qrcode.default.toDataURL(valor, { type: 'image/png', margin: 2 }),
    download: (message, socket) => baileys.downloadMediaMessage(message, 'stream', {}, { logger, reuploadRequest: socket.updateMediaMessage }),
  };
}

export function criarPonte({ token, authdir, midiadir, statedir, ffmpeg = 'ffmpeg', deps = {} }) {
  if (typeof token !== 'string' || token.length < 16) throw falha(400, 'Token local ausente ou curto.');
  if (!path.isAbsolute(authdir || '') || !path.isAbsolute(midiadir || '')) throw falha(400, 'As pastas precisam de caminhos absolutos.');
  authdir = path.resolve(authdir);
  midiadir = path.resolve(midiadir);
  statedir = path.resolve(statedir || path.join(path.dirname(midiadir), '.whatsapp', 'estado'));
  if (authdir === path.parse(authdir).root || midiadir === path.parse(midiadir).root || statedir === path.parse(statedir).root || authdir === midiadir) throw falha(400, 'Use uma pasta exclusiva para as credenciais, mídia e estado.');
  const agora = deps.now || Date.now;
  const agendar = deps.setTimeout || setTimeout;
  const cancelar = deps.clearTimeout || clearTimeout;
  const executar = deps.execFile || promisify(execFile);
  const dormir = deps.sleep || (ms => new Promise(resolve => setTimeout(resolve, ms)));
  const log = deps.log || (mensagem => process.stderr.write(`${mensagem}\n`));
  let runtime;
  let socket;
  let autenticacao;
  let geracao = 0;
  let revisaoQR = 0;
  let sequencia = 0;
  let tentativa = 0;
  let timer;
  let iniciando;
  let saindo;
  let gravando = Promise.resolve();
  let recebendo = Promise.resolve();
  let servidor;
  let encerrada = false;
  let permitirReconexao = false;
  let situacao = { estado: 'desconectado', qr: null, numero: null, nome: null };
  const mensagens = [];
  const vistos = new Set();
  const enviados = new Set();
  let terceiros = [];
  let descartadas = 0;
  let conectandoDesde;
  let tentou405 = false;
  let carregado = false;
  let persistindo = Promise.resolve();
  let vezTerceiros = Promise.resolve();
  const requisicoes = new Map();
  const emEnvio = new Map();

  function limitar(colecao) {
    while (colecao.size > 2000) colecao.delete(colecao.keys().next().value);
  }

  function persistir() {
    const dados = JSON.stringify({ enviados: [...enviados], requisicoes: [...requisicoes], terceiros });
    const trabalho = persistindo.then(async () => {
      const temporario = path.join(statedir, 'ponte.tmp');
      await writeFile(temporario, dados);
      await rename(temporario, path.join(statedir, 'ponte.json'));
    });
    persistindo = trabalho.catch(erro => log(erro.message));
    return trabalho;
  }

  const estado = () => {
    if (situacao.estado === 'conectando' && agora() - conectandoDesde > 90000) {
      situacao = { ...situacao, estado: 'erro', mensagem: `A conexão passou de 90 segundos. ${situacao.mensagem || 'O WhatsApp ainda não respondeu.'}` };
      permitirReconexao = false;
      cancelarReconexao();
      desligarSocket(socket);
      socket = undefined;
    }
    return { ...situacao, conexao: geracao, ...(descartadas ? { descartadas } : {}) };
  };

  function identidade() {
    const candidatos = [socket?.user, autenticacao?.state?.creds?.me].filter(Boolean);
    const jids = new Set(candidatos.flatMap(user => [normalizar(user.id), normalizar(user.lid)]).filter(Boolean));
    const pn = [...jids].find(jid => jid.endsWith('@s.whatsapp.net'));
    return { jids, pn, nome: candidatos.find(user => user.name)?.name || null };
  }

  function cancelarReconexao() {
    if (timer) cancelar(timer);
    timer = undefined;
  }

  function desligarSocket(atual) {
    if (!atual) return;
    atual.ev.removeAllListeners('connection.update');
    atual.ev.removeAllListeners('creds.update');
    atual.ev.removeAllListeners('messages.upsert');
    try { atual.end(new Error('Ponte local desconectada.')); } catch {}
  }

  async function pastas() {
    await mkdir(authdir, { recursive: true });
    await mkdir(midiadir, { recursive: true });
    if ((await lstat(authdir)).isSymbolicLink() || (await lstat(midiadir)).isSymbolicLink()) throw falha(400, 'As pastas da ponte não podem ser links.');
    await mkdir(statedir, { recursive: true });
    if ((await lstat(statedir)).isSymbolicLink()) throw falha(400, 'A pasta de estado não pode ser um link.');
    if (!carregado) {
      try {
        const dados = JSON.parse(await readFile(path.join(statedir, 'ponte.json'), 'utf8'));
        for (const id of (dados.enviados || []).slice(-2000)) enviados.add(id);
        for (const item of (dados.requisicoes || []).slice(-2000)) requisicoes.set(...item);
        terceiros = (dados.terceiros || []).filter(ts => agora() - ts < 3600000).slice(-20);
      } catch (erro) { if (erro.code !== 'ENOENT') throw erro; }
      for (const nome of await readdir(midiadir, { withFileTypes: true })) {
        if (!nome.isFile()) continue;
        const arquivo = path.join(midiadir, nome.name);
        if (agora() - (await stat(arquivo)).mtimeMs > 7 * 86400000) await unlink(arquivo);
      }
      carregado = true;
    }
  }

  function gravar(versao, trabalho) {
    const proxima = gravando.then(() => versao === geracao && !encerrada ? trabalho() : undefined);
    gravando = proxima.catch(() => {});
    return proxima;
  }

  async function limparCredenciais() {
    const nomes = await readdir(authdir, { withFileTypes: true }).catch(erro => {
      if (erro.code === 'ENOENT') return [];
      throw erro;
    });
    for (const nome of nomes) {
      if (!nome.isFile() || !/^(creds|(?:pre-key|session|sender-key|sender-key-memory|app-state-sync-key|app-state-sync-version|lid-mapping|device-list|tctoken|identity-key)-.+)\.json$/.test(nome.name)) continue;
      await unlink(path.join(authdir, nome.name));
    }
  }

  function prepararReconexao(versao) {
    if (!permitirReconexao || encerrada || versao !== geracao || timer) return;
    const espera = Math.min(30000, 1000 * 2 ** Math.min(tentativa++, 5));
    timer = agendar(async () => {
      timer = undefined;
      if (versao !== geracao || !permitirReconexao || encerrada) return;
      try { await conectar(); } catch {}
    }, espera);
    timer?.unref?.();
  }

  async function atualizar(update, versao, atual) {
    if (versao !== geracao || encerrada) return;
    if (update.connection === 'close') {
      revisaoQR++;
      situacao = { ...situacao, estado: 'desconectado', qr: null };
      const codigo = update.lastDisconnect?.error?.output?.statusCode ?? update.lastDisconnect?.error?.statusCode;
      log(`WhatsApp close: DisconnectReason ${codigo ?? 'desconhecido'}`);
      situacao.codigo = codigo;
      situacao.mensagem = `O WhatsApp desconectou (código ${codigo ?? 'desconhecido'}).`;
      if (codigo === 401) {
        await sair(false);
        situacao.codigo = codigo;
        situacao.mensagem = 'O WhatsApp saiu da conta (código 401). Conecta de novo aqui.';
        return;
      }
      desligarSocket(atual);
      if (socket === atual) socket = undefined;
      if (codigo === 440 || codigo === 403 || (codigo === 405 && tentou405)) {
        permitirReconexao = false;
        cancelarReconexao();
        situacao.mensagem = codigo === 440 ? 'Outra Sheep ou WhatsApp Web assumiu essa conta. Conecta de novo aqui se quiser usar nesta.' : `O WhatsApp recusou a conexão (código ${codigo}). Tenta de novo; se continuar, atualiza a Sheep pelo instalador.`;
        return;
      }
      if (codigo === 405) tentou405 = true;
      prepararReconexao(versao);
      return;
    }
    if (update.connection === 'open') {
      revisaoQR++;
      tentativa = 0;
      const eu = identidade();
      situacao = { estado: 'conectado', qr: null, numero: eu.pn?.split('@')[0] || null, nome: eu.nome };
      return;
    }
    if (update.qr) {
      const revisao = ++revisaoQR;
      const qr = await runtime.qr(update.qr);
      if (versao === geracao && revisao === revisaoQR && !encerrada) situacao = { ...situacao, estado: 'qr', qr };
    } else if (update.connection === 'connecting' && situacao.estado !== 'qr') {
      situacao = { ...situacao, estado: 'conectando', qr: null };
    }
  }

  async function receber(evento, versao, atual, chegada) {
    if (evento.type !== 'notify' || versao !== geracao || encerrada) return;
    for (const message of evento.messages || []) {
      if (versao !== geracao || encerrada) return;
      const id = message.key?.id;
      const jid = normalizar(message.key?.remoteJid);
      const alternativo = normalizar(message.key?.remoteJidAlt);
      const eu = identidade();
      if (!id || !jid || (!eu.jids.has(jid) && !eu.jids.has(alternativo)) || vistos.has(id) || enviados.has(id)) continue;
      const item = conteudo(message.message);
      if (!item || item.texto.trimStart().startsWith('🐑')) continue;
      vistos.add(id);
      limitar(vistos);
      const ts = Number(message.messageTimestamp ?? Math.floor(chegada / 1000));
      if (chegada - ts * 1000 > 600000) { descartadas++; continue; }
      let arquivo = null;
      let erroMidia;
      try {
        if (item.midia) {
          const limite = 25 * 1024 * 1024;
          if (Number(item.midia.fileLength || 0) > limite) throw Object.assign(new Error('Mídia grande'), { grande: true });
          const stream = await runtime.download(message, atual);
          const partes = [];
          let tamanho = 0;
          for await (const parte of Buffer.isBuffer(stream) ? [stream] : stream) {
            tamanho += parte.length;
            if (tamanho > limite) throw Object.assign(new Error('Mídia grande'), { grande: true });
            partes.push(parte);
          }
          const dados = Buffer.concat(partes);
          if (versao !== geracao || encerrada) return;
          arquivo = path.join(midiadir, `${randomUUID()}${extensao(item.midia, item.tipo)}`);
          await writeFile(arquivo, dados, { flag: 'wx' });
        }
      } catch (erro) {
        log(`Download: ${erro.message}`);
        erroMidia = { erro: 'download', ...(erro.grande ? { grande: true } : {}) };
      }
      if (versao !== geracao || encerrada) return;
      mensagens.push({ id, ts, tipo: item.tipo, texto: item.texto, arquivo, seq: ++sequencia, ...erroMidia });
      if (mensagens.length > 200) mensagens.splice(0, mensagens.length - 200);
    }
  }

  async function conectar() {
    if (encerrada) throw falha(503, 'A ponte foi encerrada.');
    if (saindo) await saindo;
    if (iniciando) return iniciando;
    if (socket && ['conectando', 'conectado', 'qr'].includes(situacao.estado)) return estado();
    permitirReconexao = true;
    cancelarReconexao();
    const versao = ++geracao;
    situacao = { ...situacao, estado: 'conectando', qr: null };
    conectandoDesde = agora();
    const trabalho = (async () => {
      await pastas();
      runtime ||= deps.makeSocket ? deps : await dependenciasReais();
      await gravando;
      if (versao !== geracao || encerrada) return estado();
      autenticacao = await runtime.loadAuth(authdir);
      if (versao !== geracao || encerrada) return estado();
      const auth = autenticacao;
      if (auth.state.keys?.set) {
        const salvarKeys = auth.state.keys.set.bind(auth.state.keys);
        auth.state.keys.set = dados => gravar(versao, () => salvarKeys(dados));
      }
      let version, timeout;
      if (runtime.fetchLatestBaileysVersion) {
        try {
          const resposta = await Promise.race([runtime.fetchLatestBaileysVersion(), new Promise((_, reject) => {
            timeout = agendar(() => reject(new Error('Consulta da versão excedeu 5 segundos.')), 5000);
          })]);
          version = resposta?.version;
        } catch (erro) { log(`Versão embutida: ${erro.message}`); }
        finally { cancelar(timeout); }
      }
      if (versao !== geracao || encerrada) return estado();
      const atual = await runtime.makeSocket({ auth: auth.state, ...(version ? { version } : {}) });
      if (versao !== geracao || encerrada) { desligarSocket(atual); return estado(); }
      socket = atual;
      atual.ev.on('connection.update', update => { atualizar(update, versao, atual).catch(erro => log(erro.message)); });
      atual.ev.on('creds.update', () => { gravar(versao, () => auth.saveCreds()).catch(erro => log(erro.message)); });
      atual.ev.on('messages.upsert', evento => {
        const chegada = agora();
        recebendo = recebendo.then(() => receber(evento, versao, atual, chegada)).catch(erro => log(erro.message));
      });
      return estado();
    })();
    iniciando = trabalho;
    try { return await trabalho; }
    catch (erro) {
      if (versao === geracao && !encerrada) {
        log(erro.message);
        situacao = { ...situacao, estado: 'desconectado', qr: null, mensagem: 'Não consegui iniciar a conexão. Tenta de novo.' };
        prepararReconexao(versao);
      }
      throw erro;
    } finally { if (iniciando === trabalho) iniciando = undefined; }
  }

  async function sair(remoto = true) {
    if (saindo) return saindo;
    permitirReconexao = false;
    geracao++;
    revisaoQR++;
    cancelarReconexao();
    const atual = socket;
    socket = undefined;
    situacao = { estado: 'desconectado', qr: null, numero: null, nome: null };
    if (atual) {
      atual.ev.removeAllListeners('connection.update');
      atual.ev.removeAllListeners('creds.update');
      atual.ev.removeAllListeners('messages.upsert');
    }
    const trabalho = (async () => {
      let logoutFalhou = false;
      try { if (remoto && atual) await atual.logout(); } catch { logoutFalhou = true; }
      desligarSocket(atual);
      if (iniciando) await iniciando.catch(() => {});
      await gravando;
      await limparCredenciais();
      await recebendo;
      if (!(await lstat(midiadir).catch(() => null))?.isSymbolicLink()) await rm(midiadir, { recursive: true, force: true });
      autenticacao = undefined;
      mensagens.length = 0;
      vistos.clear();
      return logoutFalhou ? { ...estado(), mensagem: 'Desliguei aqui. Se o aparelho ainda aparecer no celular, desconecta por lá também.' } : estado();
    })();
    saindo = trabalho;
    try { return await trabalho; }
    finally { if (saindo === trabalho) saindo = undefined; }
  }

  async function enviarAgora(pedido) {
    if (!pedido || typeof pedido !== 'object' || Array.isArray(pedido)) throw falha(400, 'Pedido inválido.');
    const eu = identidade();
    const atual = socket;
    const versao = geracao;
    if (!atual || situacao.estado !== 'conectado' || !eu.pn) throw falha(409, 'WhatsApp desconectado.');
    if (pedido.para !== 'eu' && (typeof pedido.para !== 'string' || !/^\d{10,15}$/.test(pedido.para))) throw falha(400, 'Destino inválido.');
    if (!['texto', 'audio', 'imagem', 'documento'].includes(pedido.tipo)) throw falha(400, 'Tipo de mensagem inválido.');
    if (pedido.texto != null && (typeof pedido.texto !== 'string' || pedido.texto.length > 65000)) throw falha(400, 'Texto inválido.');
    const destino = pedido.para === 'eu' ? eu.pn : `${pedido.para}@s.whatsapp.net`;
    let arquivo = pedido.arquivo;
    let body;
    if (pedido.tipo === 'texto') {
      if (!pedido.texto?.trim()) throw falha(400, 'Texto vazio.');
      body = { text: pedido.texto };
    } else {
      if (typeof arquivo !== 'string' || !path.isAbsolute(arquivo)) throw falha(400, 'Arquivo local inválido.');
      let info;
      try { info = await stat(arquivo); } catch { throw falha(400, 'Arquivo local não encontrado.'); }
      if (!info.isFile()) throw falha(400, 'Arquivo local inválido.');
      if (pedido.tipo === 'audio') {
        const ext = path.extname(arquivo).toLowerCase();
        if (!['.ogg', '.opus', '.mp3'].includes(ext)) throw falha(400, 'O áudio precisa ser OGG Opus ou MP3.');
        if (ext === '.mp3') {
          const convertido = path.join(midiadir, `${randomUUID()}.ogg`);
          try {
            await executar(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-nostdin', '-i', arquivo, '-vn', '-c:a', 'libopus', '-b:a', '48k', '-ar', '48000', '-ac', '1', '-f', 'ogg', convertido], { shell: false, windowsHide: true, timeout: 120000, maxBuffer: 1024 * 1024 });
          } catch (erro) {
            log(`Conversão: ${erro.message}`);
            situacao.voz_aviso = erro.code === 'ENOENT' ? 'Falta o ffmpeg para converter esse áudio. Abre o instalador da Sheep de novo.' : 'Não consegui converter esse áudio. Tenta mandar em OGG.';
            throw falha(422, situacao.voz_aviso);
          }
          arquivo = convertido;
        }
        body = { audio: { url: arquivo }, mimetype: 'audio/ogg; codecs=opus', ptt: true };
      } else if (pedido.tipo === 'imagem') {
        body = { image: { url: arquivo }, caption: pedido.texto || '' };
      } else {
        body = { document: { url: arquivo }, caption: pedido.texto || '', fileName: path.basename(arquivo), mimetype: path.extname(arquivo).toLowerCase() === '.pdf' ? 'application/pdf' : 'application/octet-stream' };
      }
    }
    if (versao !== geracao || atual !== socket || situacao.estado !== 'conectado') throw falha(409, 'WhatsApp desconectado.');
    if (destino !== eu.pn) {
      const inicioEspera = agora();
      const reserva = vezTerceiros.then(async () => {
        terceiros = terceiros.filter(ts => agora() - ts < 3600000);
        if (terceiros.length >= 20) throw falha(429, 'Limite de envio: 20 por hora.');
        const espera = terceiros.length ? Math.max(0, 8000 - (agora() - terceiros.at(-1))) : 0;
        if (agora() - inicioEspera + espera > 60000) throw falha(429, 'A fila de envios passou de um minuto. Tenta de novo.');
        if (espera) await dormir(espera);
        if (versao !== geracao || atual !== socket || situacao.estado !== 'conectado') throw falha(409, 'WhatsApp desconectado.');
        terceiros.push(agora());
        await persistir();
      });
      vezTerceiros = reserva.catch(() => {});
      await reserva;
    }
    const anterior = pedido.id && requisicoes.get(pedido.id);
    const id = anterior?.id || (runtime.generateMessageIDV2 ? runtime.generateMessageIDV2(eu.pn) : '3EB0' + randomBytes(9).toString('hex').toUpperCase());
    enviados.add(id);
    limitar(enviados);
    if (pedido.id) { requisicoes.set(pedido.id, { id, feito: false }); limitar(requisicoes); }
    await persistir();
    const enviada = await atual.sendMessage(destino, body, { messageId: id });
    if (enviada?.key?.id) enviados.add(enviada.key.id);
    limitar(enviados);
    const resultado = { id: enviada?.key?.id || id };
    if (pedido.id) requisicoes.set(pedido.id, { ...resultado, feito: true });
    await persistir();
    return resultado;
  }

  function enviar(pedido) {
    if (pedido?.id != null && (typeof pedido.id !== 'string' || !/^[A-Za-z0-9_-]{1,100}$/.test(pedido.id))) return Promise.reject(falha(400, 'ID de envio inválido.'));
    if (pedido?.id && emEnvio.has(pedido.id)) return emEnvio.get(pedido.id);
    if (pedido?.id && requisicoes.get(pedido.id)?.feito) return Promise.resolve({ id: requisicoes.get(pedido.id).id });
    const trabalho = enviarAgora(pedido);
    if (pedido?.id) {
      emEnvio.set(pedido.id, trabalho);
      trabalho.finally(() => emEnvio.delete(pedido.id)).catch(() => {});
    }
    return trabalho;
  }

  async function corpo(req) {
    const chunks = [];
    let tamanho = 0;
    for await (const chunk of req) {
      tamanho += chunk.length;
      if (tamanho > 1024 * 1024) throw falha(413, 'Pedido muito grande.');
      chunks.push(chunk);
    }
    try { return JSON.parse(Buffer.concat(chunks).toString('utf8')); }
    catch { throw falha(400, 'JSON inválido.'); }
  }

  async function escutar(porta) {
    if (servidor) return servidor;
    servidor = http.createServer(async (req, res) => {
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.setHeader('Cache-Control', 'no-store');
      const responder = (status, valor) => { res.writeHead(status); res.end(JSON.stringify(valor)); };
      try {
        const recebido = Buffer.from(typeof req.headers['x-token'] === 'string' ? req.headers['x-token'] : '');
        const esperado = Buffer.from(token);
        if (recebido.length !== esperado.length || !timingSafeEqual(recebido, esperado)) return responder(403, { erro: 'Token local inválido.' });
        const url = new URL(req.url, 'http://127.0.0.1');
        if (req.method === 'GET' && url.pathname === '/estado') return responder(200, estado());
        if (req.method === 'GET' && url.pathname === '/mensagens') {
          const desde = url.searchParams.get('desde') ?? '0';
          if (!/^\d+$/.test(desde) || !Number.isSafeInteger(Number(desde))) throw falha(400, 'Sequência inválida.');
          return responder(200, mensagens.filter(item => item.seq > Number(desde)));
        }
        if (req.method === 'POST' && url.pathname === '/conectar') return responder(200, await conectar());
        if (req.method === 'POST' && url.pathname === '/sair') return responder(200, await sair());
        if (req.method === 'POST' && url.pathname === '/parar') {
          await parar();
          res.once('finish', () => { fechar().catch(erro => log(erro.message)); });
          return responder(200, estado());
        }
        if (req.method === 'POST' && url.pathname === '/enviar') return responder(200, await enviar(await corpo(req)));
        responder(404, { erro: 'Rota não encontrada.' });
      } catch (erro) {
        log(`HTTP: ${erro.status || 500} ${erro.message}`);
        responder(erro.status || 500, { erro: erro.status ? erro.message : 'A ponte não conseguiu concluir o pedido.' });
      }
    });
    servidor.requestTimeout = 150000;
    servidor.headersTimeout = 10000;
    await new Promise((resolve, reject) => {
      servidor.once('error', reject);
      servidor.listen(porta, '127.0.0.1', () => { servidor.off('error', reject); resolve(); });
    });
    return servidor;
  }

  async function parar() {
    if (encerrada) return;
    permitirReconexao = false;
    cancelarReconexao();
    await gravando;
    if (autenticacao) await autenticacao.saveCreds();
    encerrada = true;
    permitirReconexao = false;
    geracao++;
    revisaoQR++;
    cancelarReconexao();
    desligarSocket(socket);
    socket = undefined;
    if (iniciando) await iniciando.catch(() => {});
    if (saindo) await saindo.catch(() => {});
    await gravando;
    await persistindo;
    situacao = { estado: 'desconectado', qr: null, numero: null, nome: null };
  }

  async function fechar() {
    await parar();
    if (servidor) {
      const atual = servidor;
      servidor = undefined;
      atual.closeIdleConnections();
      await new Promise(resolve => atual.close(resolve));
    }
    situacao = { estado: 'desconectado', qr: null, numero: null, nome: null };
  }

  return { estado, conectar, sair, enviar, mensagens: desde => mensagens.filter(item => item.seq > desde).map(item => ({ ...item })), escutar, fechar };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [porta, authdir, midiadir, ffmpeg] = process.argv.slice(2);
  try {
    if (!/^\d+$/.test(porta || '') || Number(porta) < 1 || Number(porta) > 65535) throw falha(400, 'Porta local inválida.');
    const ponte = criarPonte({ token: process.env.SHEEP_WHATSAPP_TOKEN, authdir, midiadir, ffmpeg });
    await ponte.escutar(Number(porta));
    const encerrar = () => { ponte.fechar().then(() => process.exit(0), () => process.exit(1)); };
    process.once('SIGTERM', encerrar);
    process.once('SIGINT', encerrar);
  } catch (erro) {
    process.stderr.write(`${erro.status ? erro.message : 'Não foi possível iniciar a ponte local.'}\n`);
    process.exitCode = 1;
  }
}
