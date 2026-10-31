const TOKEN = "__TOKEN__";
const $ = id => document.getElementById(id);
const api = (m, r, c) => fetch(r, {method: m, headers: {"X-Token": TOKEN, "Content-Type": "application/json"}, body: c ? JSON.stringify(c) : undefined}).then(async x => { const d = await x.json(); if (x.ok === false) throw new Error(d.erro || "Não consegui concluir. Tenta de novo."); return d; });
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const CON = [
  ["TELEGRAM_TOKEN", "Telegram", "Eu fico no seu celular 24h."],
  ["ZERNIO_API_KEY", "Zernio", "Eu agendo seus posts (sempre com o seu sim)."],
  ["ELEVENLABS_API_KEY", "ElevenLabs", "Eu passo a falar com voz."],
  ["ELEVENLABS_VOZ", "Voz da Sheep", "Cole o ID da voz que quer ouvir no WhatsApp."],
  ["ANTHROPIC_API_KEY", "API Claude (US$ 200)", "Uso a API do presente quando a assinatura acabar no dia."],
  ["OPENAI_API_KEY", "API OpenAI", "Mais um cérebro de reserva."],
];
let E, sessAtual = null, codigoTelegram = "", avisoTelegram = "";
let som = false, audioLiberado = false, audioAtual, nAprovAnterior = 0, falaTimer, falaAtual = "", enviando = false;
let consultaEventos, consultaEstado;
let sessaoExibida = null, anexando = false, tituloSalvando = false;
const secoesUi = new Map(), rolagens = new Map(), rascunhos = new Map();
const preferenciasPendentes = new Set();
const igual = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const semMovimento = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
function atualizaSecao(id, dados, render, preservar = false) {
  const assinatura = JSON.stringify(dados);
  if (secoesUi.get(id) === assinatura || preservar) return;
  render(); secoesUi.set(id, assinatura);
}
function reconcilia(id, html) {
  const area = $(id), molde = document.createElement("template");
  molde.innerHTML = html;
  const antigos = new Map([...area.children].map((no, i) => [no.dataset.chave || String(i), no]));
  let posicao = 0;
  for (const novo of [...molde.content.children]) {
    const chave = novo.dataset.chave || String(posicao), antigo = antigos.get(chave);
    const no = antigo ? atualizaNo(antigo, novo) : novo;
    if (area.children[posicao] !== no) area.insertBefore(no, area.children[posicao] || null);
    antigos.delete(chave); posicao++;
  }
  while (area.children.length > posicao) area.lastElementChild.remove();
}
function atualizaNo(antigo, novo) {
  if (antigo.nodeName === "INPUT" && novo.nodeName === "INPUT" && ["checkbox", "radio"].includes(novo.type)) antigo.checked = novo.checked;
  if (antigo.isEqualNode(novo)) return antigo;
  if (antigo.nodeType !== novo.nodeType || antigo.nodeName !== novo.nodeName) return novo.cloneNode(true);
  if (antigo.nodeType === 3) { antigo.nodeValue = novo.nodeValue; return antigo; }
  for (const atributo of [...antigo.attributes]) if (!novo.hasAttribute(atributo.name)) antigo.removeAttribute(atributo.name);
  for (const atributo of [...novo.attributes]) if (antigo.getAttribute(atributo.name) !== atributo.value) antigo.setAttribute(atributo.name, atributo.value);
  [...novo.childNodes].forEach((filho, i) => {
    const atual = antigo.childNodes[i];
    if (!atual) antigo.append(filho.cloneNode(true));
    else { const atualizado = atualizaNo(atual, filho); if (atualizado !== atual) antigo.replaceChild(atualizado, atual); }
  });
  while (antigo.childNodes.length > novo.childNodes.length) antigo.lastChild.remove();
  if (antigo.nodeName === "SELECT") antigo.value = novo.value;
  return antigo;
}
function pertoDoFim() {
  const rolo = $("rolo");
  return rolo.scrollHeight - rolo.scrollTop - rolo.clientHeight <= 120;
}
function desce() {
  $("rolo").scrollTop = $("rolo").scrollHeight;
  $("novasMensagens").hidden = true;
}
function atualizaRolagem(seguir) {
  if (seguir) desce();
  else $("novasMensagens").hidden = false;
}
function cresce() {
  const t = $("texto"); t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 200) + "px";
}
function fechaMenus() {
  for (const id of ["novaConversa", "motorPop", "memPop", "menuConversa", "confirmacaoArquivar", "moverConversa"]) $(id).hidden = true;
  for (const id of ["novaSess", "motorBtn", "memBtn", "maisBtn", "barraContexto"]) $(id).setAttribute("aria-expanded", "false");
}
function alternaMenu(id, botao) {
  const abrir = $(id).hidden; fechaMenus(); $(id).hidden = !abrir;
  $(botao).setAttribute("aria-expanded", String(abrir));
  if (id === "memPop") $("barraContexto").setAttribute("aria-expanded", String(abrir));
}
function tela(nome) {
  fechaMenus();
  document.querySelectorAll("nav button[data-t],.tela").forEach(x => x.classList.remove("on"));
  document.querySelector(`[data-t="${nome}"]`)?.classList.add("on"); $(nome).classList.add("on");
  audioLiberado = true;
  if (nome === "conversa" && !sessAtual) { recepcao(); tocar("boas-vindas"); }
}
const sessoesUi = new Map();
let verArquivadas = false, parcialTimer, parcialQuando = 0;
const operacoesPacotes = new Map(), operacoesAprovacoes = new Set(), avisosAprovacoes = new Map(), operacoesMemoria = new Set();
let avisoPacote = "", avisoMemoria = "", avisoAprender = "", salvandoAprender = false, importandoPacote = false;
let pacoteEmPrevia = null;
let W = {}, whatsappOcupado = false, whatsappConsultando = false, whatsappConfirmar = false, whatsappTimer, whatsappAviso = "";
function mostraWhatsApp(estado) {
  if (estado) W = estado;
  const ligado = W.estado === "conectado", qr = typeof W.qr === "string" && /^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(W.qr) ? W.qr : "";
  const nomes = {desconectado: "Desconectado", qr: "Lê o QR com seu celular.", conectando: "Conectando…", conectado: "Conectado", sem_node: "Falta o Node. Roda o instalador de novo.", instalando: "Preparando o WhatsApp (1ª vez leva 1–2 min)…", erro: "Não consegui conectar."};
  const html = `<div class="card whatsapp-card"><div class="linha"><h3>WhatsApp</h3><span class="dot ${ligado ? "on" : "off"}"></span></div><p role="status">${esc(nomes[W.estado] || nomes.desconectado)}</p>${W.numero ? `<p>${esc(W.numero)}${W.nome ? ` · ${esc(W.nome)}` : ""}</p>` : ""}${qr ? `<img class="whatsapp-qr" src="${esc(qr)}" alt="QR para conectar seu WhatsApp">` : ""}<p>Fale comigo no chat 'Você' do seu WhatsApp (a conversa com você mesmo).</p><div class="acoes-pacote"><button id="whatsappConectar" ${whatsappOcupado || ligado || W.estado === "instalando" ? "disabled" : ""}>${W.estado === "erro" ? "Tentar de novo" : "Conectar"}</button><button class="sec" id="whatsappSair" ${whatsappOcupado || W.estado === "instalando" || (!W.ligado && !["qr", "conectado", "conectando"].includes(W.estado)) ? "disabled" : ""}>${whatsappConfirmar ? "Confirmar desconexão" : "Desconectar"}</button></div><label><input id="whatsappVoz" type="checkbox" ${W.voz ? "checked" : ""} ${whatsappOcupado ? "disabled" : ""}> Responder também em áudio</label><p role="status">${esc(W.voz_aviso || "")}</p><p aria-live="polite">${esc(whatsappAviso || W.mensagem || "")}</p></div>`;
  const assinatura = JSON.stringify([W, whatsappOcupado, whatsappConfirmar, whatsappAviso]);
  const ligadoTexto = ligado ? "conectado" : W.ligado || W.numero ? "desconectado" : "não configurado";
  if ($("whatsappResumo").textContent !== `WhatsApp ${ligadoTexto}`) $("whatsappResumo").textContent = `WhatsApp ${ligadoTexto}`;
  $("whatsappChip").classList.toggle("conectado", ligado);
  if (secoesUi.get("whatsapp") === assinatura) return;
  reconcilia("whatsappCon", html); secoesUi.set("whatsapp", assinatura);
  $("whatsappConectar").onclick = () => acaoWhatsapp("conectar");
  $("whatsappSair").onclick = () => {
    if (whatsappOcupado) return;
    if (whatsappConfirmar) return acaoWhatsapp("sair");
    whatsappConfirmar = true;
    whatsappTimer = setTimeout(() => { whatsappConfirmar = false; mostraWhatsApp(); }, 4000);
    mostraWhatsApp();
  };
  $("whatsappVoz").onchange = () => acaoWhatsapp("voz", {ligado: $("whatsappVoz").checked});
}
async function acaoWhatsapp(acao, corpo = {}) {
  if (whatsappOcupado) return;
  whatsappOcupado = true; clearTimeout(whatsappTimer); whatsappConfirmar = false; whatsappAviso = "";
  mostraWhatsApp();
  try {
    const resultado = confirmaResposta(await api("POST", `/api/whatsapp/${acao}`, corpo));
    if (acao === "voz") W.voz = corpo.ligado;
    whatsappAviso = acao === "sair" ? resultado.mensagem || "WhatsApp desligado." : acao === "voz" ? "Preferência salva." : "Já tô conectando…";
    await consultaWhatsapp();
  } catch (e) { whatsappAviso = e.message || "Não consegui concluir. Tenta de novo."; }
  finally { whatsappOcupado = false; mostraWhatsApp(); }
}
async function consultaWhatsapp() {
  if (whatsappConsultando) return;
  whatsappConsultando = true;
  try {
    const estado = await api("GET", "/api/whatsapp/estado");
    if (["conectado", "desconectado", "erro", "sem_node"].includes(estado.estado) && whatsappAviso === "Já tô conectando…") whatsappAviso = "";
    mostraWhatsApp(estado);
  }
  catch (_) { whatsappAviso = "Não consegui consultar o WhatsApp. Já tento de novo."; mostraWhatsApp(); }
  finally { whatsappConsultando = false; }
}
function confirmaResposta(r) {
  if (r.ok === false || r.erro) throw new Error(r.erro || "Não consegui concluir. Tenta de novo.");
  return r;
}
function versaoMaior(a, b) {
  const partes = v => String(v || "0").split(".").map(p => Number(p) || 0);
  const x = partes(a), y = partes(b);
  for (let i = 0; i < Math.max(x.length, y.length); i++) if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0);
  return false;
}
function mostraPacotes() {
  if (!E) return;
  $("avisoPacote").textContent = [...(E.avisos || []), avisoPacote].filter(Boolean).join("\n");
  $("pacoteFora").disabled = importandoPacote;
  $("pacoteFora").textContent = importandoPacote ? "instalando…" : "Escolher arquivo";
  $("arquivoPacote").disabled = importandoPacote;
  const html = (E.pacotes || []).map(p => {
    const op = operacoesPacotes.get(p.id) || {}, atualizar = p.instalado && versaoMaior(p.versao, p.versao_instalada);
    if (p.erro) return `<div class="card" data-chave="${esc(p.id)}"><h3>${esc(p.nome)}</h3><p role="status">${esc(p.erro)}</p><button class="sec" data-remover="${esc(p.id)}" ${op.ocupado ? "disabled" : ""}>${op.ocupado ? "aguarda…" : op.confirmar ? "Confirmar remoção" : "Remover"}</button></div>`;
    return `<div class="card" data-chave="${esc(p.id)}"><h3>${esc(p.nome)}</h3><p>${esc(p.descricao)}</p><p class="pacote-meta">v${esc(p.versao)}${p.instalado ? ` · instalada ${esc(p.versao_instalada || p.versao)}` : ""} · ${esc(p.autor)}</p><p>${esc(p.origem)}</p><ul>${(Array.isArray(p.traz) ? p.traz : p.traz ? [p.traz] : []).map(item => `<li>${esc(item)}</li>`).join("")}</ul><p>${(p.habilidades || []).length} habilidades · ${(p.rotinas || []).length} rotinas</p><div class="acoes-pacote">${!p.instalado || atualizar ? `<button data-instalar="${esc(p.id)}" ${op.ocupado ? "disabled" : ""}>${op.ocupado ? "instalando…" : atualizar ? "Atualizar" : "Instalar"}</button>` : '<span class="rot">Instalado</span>'}${p.instalado ? `<button class="sec" data-remover="${esc(p.id)}" ${op.ocupado ? "disabled" : ""}>${op.ocupado ? "aguarda…" : op.confirmar ? "Confirmar remoção" : "Remover"}</button>` : ""}</div></div>`;
  }).join("") || "<p>Nenhum pacote por aqui ainda.</p>";
  reconcilia("cardsPacotes", html);
  $("cardsPacotes").querySelectorAll("[data-instalar]").forEach(b => b.onclick = () => mudaPacote(b.dataset.instalar, "instalar"));
  $("cardsPacotes").querySelectorAll("[data-remover]").forEach(b => b.onclick = () => {
    const id = b.dataset.remover, op = operacoesPacotes.get(id) || {};
    if (op.ocupado) return;
    if (op.confirmar) return mudaPacote(id, "remover");
    op.confirmar = true; operacoesPacotes.set(id, op);
    op.timer = setTimeout(() => { op.confirmar = false; mostraPacotes(); }, 4000);
    mostraPacotes();
  });
  mostraPreviaPacote();
}
function mostraPreviaPacote() {
  const area = $("previaPacote");
  if (!pacoteEmPrevia) { if (area.firstChild) area.replaceChildren(); return; }
  const p = pacoteEmPrevia.dados;
  const lista = itens => (itens || []).map(item => `<li>${esc(item)}</li>`).join("") || "<li>Nenhum.</li>";
  reconcilia("previaPacote", `<div class="card aprendi"><h3>${esc(p.nome)}</h3><p>${esc(p.descricao)}</p><p>Só instale pacote de quem você confia. Este pacote traz:</p><ul>${lista(p.traz)}</ul><p>Habilidades:</p><ul>${lista(p.habilidades)}</ul><p>Rotinas:</p><ul>${lista(p.rotinas)}</ul><p>Scripts:</p><ul>${lista(p.scripts)}</ul><div class="acoes-pacote"><button id="instalarPacoteFora" ${importandoPacote ? "disabled" : ""}>${importandoPacote ? "instalando…" : "Instalar mesmo assim"}</button><button class="sec" id="cancelarPacoteFora" ${importandoPacote ? "disabled" : ""}>Cancelar</button></div></div>`);
  $("cancelarPacoteFora").onclick = () => {
    if (importandoPacote) return;
    pacoteEmPrevia = null; avisoPacote = ""; mostraPacotes();
  };
  $("instalarPacoteFora").onclick = async () => {
    if (importandoPacote || !pacoteEmPrevia) return;
    const conteudo = pacoteEmPrevia.conteudo;
    importandoPacote = true; avisoPacote = "Instalando pacote…"; mostraPacotes();
    try {
      confirmaResposta(await api("POST", "/api/pacote/instalar", conteudo));
      pacoteEmPrevia = null; avisoPacote = "Pacote instalado."; await carrega();
    } catch (e) { avisoPacote = e.message || "Não consegui instalar esse pacote."; }
    finally { importandoPacote = false; mostraPacotes(); }
  };
}
async function mudaPacote(id, acao) {
  const op = operacoesPacotes.get(id) || {};
  if (op.ocupado) return;
  clearTimeout(op.timer); op.confirmar = false; op.ocupado = true; operacoesPacotes.set(id, op);
  avisoPacote = acao === "remover" ? "Removendo pacote…" : "Instalando pacote…"; mostraPacotes();
  try {
    confirmaResposta(await api("POST", `/api/pacote/${acao}`, {id}));
    avisoPacote = acao === "remover" ? "Pacote removido." : "Pacote instalado.";
    await carrega();
  } catch (e) { avisoPacote = e.message || "Não consegui concluir. Tenta de novo."; }
  finally { op.ocupado = false; mostraPacotes(); }
}
$("pacoteFora").onclick = () => { if (!importandoPacote) $("arquivoPacote").click(); };
$("arquivoPacote").onchange = async () => {
  if (importandoPacote) return;
  const arquivo = $("arquivoPacote").files[0];
  if (!arquivo) return;
  pacoteEmPrevia = null;
  if (arquivo.size > 30 * 1024 * 1024) { avisoPacote = "O pacote pode ter até 30 MB."; $("arquivoPacote").value = ""; mostraPacotes(); return; }
  importandoPacote = true; avisoPacote = "Conferindo pacote…"; mostraPacotes();
  try {
    const bytes = new Uint8Array(await arquivo.arrayBuffer());
    let binario = "";
    for (let i = 0; i < bytes.length; i += 32768) binario += String.fromCharCode(...bytes.subarray(i, i + 32768));
    const conteudo = {zip_base64: btoa(binario), nome_arquivo: arquivo.name};
    const dados = confirmaResposta(await api("POST", "/api/pacote/previa", conteudo));
    pacoteEmPrevia = {dados, conteudo}; avisoPacote = "Confira o pacote antes de instalar.";
  } catch (e) { avisoPacote = e.message || "Não consegui ler esse pacote."; }
  finally { importandoPacote = false; $("arquivoPacote").value = ""; mostraPacotes(); }
};
function markdownSeguro(texto) {
  try {
    if (typeof marked === "undefined" || typeof DOMPurify === "undefined" || !DOMPurify.isSupported) throw new Error("indisponível");
    return DOMPurify.sanitize(marked.parse(String(texto || ""), {gfm: true, breaks: true}), {
      ALLOWED_TAGS: ["p", "br", "strong", "b", "em", "i", "del", "s", "a", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "code", "table", "thead", "tbody", "tr", "th", "td", "hr"],
      ALLOWED_ATTR: ["href", "title"], FORBID_TAGS: ["style", "iframe", "form", "input", "script"], FORBID_ATTR: ["style", "target"], ALLOW_DATA_ATTR: false,
      ALLOWED_URI_REGEXP: /^https?:\/\//i
    }).replace(/<table>/g, '<div class="tabela-rolavel"><table>').replace(/<\/table>/g, '</table></div>').replace(/<pre>/g, '<div class="codigo"><button class="sec" data-copiar="1">Copiar</button><pre>').replace(/<\/pre>/g, '</pre></div>');
  } catch (_) { return `<div class="texto-puro">${esc(texto)}</div>`; }
}
function separaOpcoes(texto) {
  const original = String(texto || ""), bloco = original.match(/(?:^|\r?\n)```opcoes\r?\n([\s\S]*?)\r?\n```\s*$/);
  if (!bloco) return {texto: original, opcoes: []};
  const linhas = bloco[1].split(/\r?\n/);
  if (linhas.length < 2 || linhas.length > 5 || linhas.some(l => !/^- .+/.test(l) || l.slice(2).trim().length > 60 || !l.slice(2).trim())) return {texto: original, opcoes: []};
  return {texto: original.slice(0, bloco.index), opcoes: linhas.map(l => l.slice(2).trim())};
}
function cardAprovacao(a, recolher = false) {
  const estado = a.estado || "pendente", classe = ["pendente", "feito", "recusado", "falhou", "executando"].includes(estado) ? estado : "", ocupado = operacoesAprovacoes.has(a.id);
  let destino = a.destino, arquivo = "";
  if (Array.isArray(a.comando) && a.comando[0] === "sheep-zap" && a.comando.length >= 4) {
    destino = a.comando[2] === "eu" ? "Você" : String(a.comando[2]).replace(/^55(\d{2})(\d{4,5})(\d{4})$/, "+55 $1 $2-$3");
    if (a.comando.length === 5 && ["audio", "imagem", "documento"].includes(a.comando[3])) arquivo = String(a.comando[4]).replaceAll("\\", "/").split("/").at(-1);
  }
  const comando = `<code class="comando">${esc(JSON.stringify(a.comando))}</code>`;
  return `<div class="card aprovacao ${classe}" data-chave="aprov-${esc(a.id)}"><span class="rot">${esc(a.tipo)} → ${esc(destino)} (${esc(a.id.slice(0, 5))})</span>${arquivo ? `<p>Arquivo: ${esc(arquivo)}</p>` : ""}<p class="previa">${esc(a.previa)}</p>${recolher ? `<details><summary>Ver comando</summary>${comando}</details>` : comando}${estado === "pendente" ? `<div class="linha"><button data-a="${esc(a.id)}" data-s="1" ${ocupado ? "disabled" : ""}>Aprovar</button><button class="sec" data-a="${esc(a.id)}" data-s="0" ${ocupado ? "disabled" : ""}>Recusar</button></div>` : `<span class="decisao">${esc(estado)}</span>`}<p class="aviso-aprovacao" aria-live="polite">${esc(avisosAprovacoes.get(a.id) || "")}</p></div>`;
}
function ligaAprovacoes(el) {
  el.querySelectorAll("[data-a]").forEach(b => b.onclick = async () => {
    const id = b.dataset.a;
    if (operacoesAprovacoes.has(id)) return;
    operacoesAprovacoes.add(id);
    for (const painel of [$("cardsAprov"), $("msgs")]) painel.querySelectorAll("[data-a]").forEach(x => { if (x.dataset.a === id) x.disabled = true; });
    try {
      confirmaResposta(await api("POST", "/api/aprovacao", {id, aprovar: b.dataset.s === "1"}));
      avisosAprovacoes.delete(id);
      if (sessAtual && !enviando) await abre(sessAtual);
      else await carrega();
    } catch (e) {
      avisosAprovacoes.set(id, e.message || "Não consegui concluir. Tenta de novo.");
      const aviso = b.closest?.(".aprovacao")?.querySelector(".aviso-aprovacao");
      if (aviso) aviso.textContent = avisosAprovacoes.get(id);
    } finally {
      operacoesAprovacoes.delete(id);
      for (const painel of [$("cardsAprov"), $("msgs")]) painel.querySelectorAll("[data-a]").forEach(x => { if (x.dataset.a === id) x.disabled = false; });
    }
  });
}
function ligaMensagem() {
  $("msgs").querySelectorAll("[data-copiar]").forEach(b => b.onclick = async () => {
    try { await navigator.clipboard.writeText(b.parentElement.querySelector("code").textContent); b.textContent = "copiado"; }
    catch (_) { b.textContent = "Não consegui copiar"; }
    setTimeout(() => { b.textContent = "Copiar"; }, 1500);
  });
  const abrirLink = async ev => {
    const link = ev.target.closest?.(".m.sheep a");
    if (!link || !$("msgs").contains(link)) return;
    ev.preventDefault();
    const url = link.getAttribute("href");
    if (!url || !/^https?:\/\//i.test(url)) return;
    try { confirmaResposta(await api("POST", "/api/abrir", {url})); }
    catch (_) {
      let aviso = link.parentElement.querySelector(".aviso-link");
      if (!aviso) { aviso = document.createElement("span"); aviso.className = "aviso-link"; aviso.setAttribute("role", "status"); link.parentElement.append(aviso); }
      aviso.textContent = "Não consegui abrir esse link.";
    }
  };
  $("msgs").onclick = ev => { if (ev.button === 0) return abrirLink(ev); };
  $("msgs").onauxclick = ev => { if (ev.button === 1) return abrirLink(ev); };
}
function mostraMensagens(s) {
  const escolhas = [], mensagens = s.mensagens || [], seguir = pertoDoFim();
  const html = mensagens.map((m, i) => {
    if (m.quem === "marcador") return `<div class="marcador msg" data-chave="msg-${i}">${esc(m.texto)}</div>`;
    if (m.quem !== "sheep") return `<div class="m dono msg" data-chave="msg-${i}">${esc(m.texto)}</div>`;
    const parte = separaOpcoes(m.texto), ativa = i === mensagens.length - 1 && !s.trabalhando && !s.arquivada && !(s.fila || []).length;
    return `<div class="m sheep msg" data-chave="msg-${i}"><img src="rosto.jpg" alt=""><div class="txt">${markdownSeguro(parte.texto)}${parte.opcoes.length ? `<div class="opcoes">${parte.opcoes.map(texto => {
      const indice = escolhas.push({texto, ativa}) - 1;
      return `<button class="sec" data-opcao="${indice}" data-ativa="${ativa ? "1" : "0"}" ${!ativa || enviando ? "disabled" : ""}>${esc(texto)}</button>`;
    }).join("")}</div>` : ""}</div></div>`;
  }).join("") + (s.aprovacoes || []).map(a => cardAprovacao(a, true)).join("") + (s.trabalhando ? `<div class="m sheep msg parcial" data-chave="progresso"><img src="rosto.jpg" alt=""><div class="txt"><div class="cursor" id="parcial" ${s.parcial ? "" : "hidden"}>${markdownSeguro(s.parcial || "")}</div><div class="pensando" id="pens" ${s.parcial ? "hidden" : ""}>${trabalhando(s.resumindo ? "Resumindo a conversa…" : "trabalhando…")}</div><div class="acao-atual" id="acaoAtual" role="status">${esc(s.resumindo ? "Resumindo a conversa…" : s.acao || "")}</div></div></div>` : "");
  reconcilia("msgs", html); sessaoExibida = sessAtual;
  parcialQuando = Date.now();
  $("msgs").querySelectorAll("[data-opcao]").forEach(b => b.onclick = () => {
    const escolha = escolhas[Number(b.dataset.opcao)];
    if (escolha.ativa && !b.disabled && !enviando) return enviar(escolha.texto);
  });
  ligaMensagem(); ligaAprovacoes($("msgs")); atualizaRolagem(seguir);
}
function cardAprendi() {
  return `<div class="card aprendi"><h3>Aprendi sozinha</h3>${(E.aprendi || []).map(m => `<div class="lembranca"><span class="rot">${esc(m.data)}</span><p>${esc(m.texto)}</p><div class="linha"><button data-memoria="${esc(m.arquivo)}" data-acao="manter" ${operacoesMemoria.has(m.arquivo) ? "disabled" : ""}>Guardar</button><button class="sec" data-memoria="${esc(m.arquivo)}" data-acao="descartar" ${operacoesMemoria.has(m.arquivo) ? "disabled" : ""}>Esquecer</button></div></div>`).join("") || '<p>Ainda nada novo. Vou aprendendo enquanto a gente trabalha.</p>'}<p id="avisoMemoria" aria-live="polite">${esc(avisoMemoria)}</p></div>`;
}
function paraEventos() {
  if (consultaEventos) clearTimeout(consultaEventos.timer);
  clearTimeout(parcialTimer);
  consultaEventos = null;
}
function trabalhando(frase = "trabalhando…") {
  return `<img src="rosto.jpg" alt=""><span>${esc(frase)}</span><span class="pontinhos" aria-hidden="true"><i></i><i></i><i></i></span>`;
}
async function iniciaEventos(sid) {
  paraEventos();
  const consulta = consultaEventos = {desde: 0};
  const rota = `/api/sessao/${encodeURIComponent(sid)}/eventos?desde=`;
  async function consultar() {
    if (consultaEventos !== consulta || sessAtual !== sid) return;
    try {
      const r = await api("GET", rota + consulta.desde);
      if (consultaEventos !== consulta || sessAtual !== sid) return;
      consulta.desde = r.total || 0;
      const antes = sessoesUi.get(sid) || {};
      if (r.revisao !== antes.revisao || antes.trabalhando && !r.trabalhando) {
        const completa = await api("GET", `/api/sessao/${encodeURIComponent(sid)}`);
        if (consultaEventos !== consulta || sessAtual !== sid) return;
        recebeSessao(sid, completa);
        if (antes.trabalhando && !completa.trabalhando) tocar("pronto");
      } else recebeSessao(sid, r);
      if ($("avisoConversa").textContent === "Não consegui atualizar a conversa. Já tento de novo.") $("avisoConversa").textContent = "";
    } catch (_) { if (consultaEventos === consulta) $("avisoConversa").textContent = "Não consegui atualizar a conversa. Já tento de novo."; }
    if (consultaEventos === consulta) consulta.timer = setTimeout(consultar, sessoesUi.get(sid)?.trabalhando ? 300 : 800);
  }
  if (consultaEventos === consulta && sessAtual === sid) consulta.timer = setTimeout(consultar, sessoesUi.get(sid)?.trabalhando ? 300 : 800);
}

function mostraContexto(s) {
  const c = s.contexto || {}, numero = n => Math.max(0, Number(n) || 0), usados = numero(c.usados), janela = numero(c.janela), base = numero(c.base);
  const proporcao = janela ? usados / janela * 100 : 0, porcentagem = Math.min(100, Math.round(proporcao)), barra = $("barraContexto");
  barra.dataset.faixa = proporcao >= 80 ? "vermelha" : proporcao >= 60 ? "amarela" : "verde";
  barra.setAttribute("aria-valuenow", String(porcentagem)); barra.firstElementChild.style.width = porcentagem + "%";
  $("contextoResumo").textContent = janela ? `Memória ${porcentagem}%` : "Memória —";
  $("memBtn").title = janela ? `Memória da conversa ${porcentagem}%` : "Memória da conversa ainda não medida";
  const basePct = janela ? Math.min(100, base / janela * 100) : 0, conversaPct = Math.max(0, porcentagem - basePct);
  $("detalheContexto").innerHTML = `<div class="barra"><i class="base-mem" style="width:${basePct}%"></i><i class="conversa-mem" style="width:${conversaPct}%"></i></div><div class="leg"><div><u style="background:#8b5cf6"></u><span class="leg-label">Minhas regras e memória: </span><span>${base.toLocaleString("pt-BR")}</span></div><div><u style="background:var(--ok)"></u><span class="leg-label">Nossa conversa: </span><span>${Math.max(usados - base, 0).toLocaleString("pt-BR")}</span></div><div><u style="background:var(--s3)"></u><span class="leg-label">Livre: </span><span>${janela ? Math.max(janela - usados, 0).toLocaleString("pt-BR") : "ainda não informado"}</span></div></div><p>Valores aproximados.</p><p>Quando passar de 80%, eu resumo sozinha pra continuar leve.</p>`;
  const total = numero(s.tokens_total);
  $("tokensTotal").textContent = `esta conversa: ${total >= 1000 ? (total / 1000).toLocaleString("pt-BR", {maximumFractionDigits:1}) + " mil" : total.toLocaleString("pt-BR")} tokens`;
}
function horaRelativa(valor) {
  let data = Number(valor);
  if (!Number.isFinite(data)) data = Date.parse(valor);
  if (data > 1e15) data /= 1e6;
  else if (data < 1e12) data *= 1000;
  if (!data || !Number.isFinite(data)) return "";
  const minutos = Math.max(0, Math.floor((Date.now() - data) / 60000));
  if (minutos < 1) return "agora";
  if (minutos < 60) return `${minutos}min`;
  if (minutos < 1440) return `${Math.floor(minutos / 60)}h`;
  if (minutos < 2880) return "ontem";
  return new Date(data).toLocaleDateString("pt-BR", {day:"2-digit", month:"2-digit"});
}
function mostraSessoes() {
  if (!E) return;
  const grupos = new Map([["Geral", []]]), busca = $("buscaConversas").value.trim().toLocaleLowerCase("pt-BR");
  const lista = (E.sessoes || []).filter(s => !!s.arquivada === verArquivadas && String(s.titulo || "").toLocaleLowerCase("pt-BR").includes(busca));
  const grupo = s => s.origem === "whatsapp" || /^WhatsApp \d{4}-\d{2}-\d{2}$/.test(s.titulo || "") ? "WhatsApp" : s.projeto || "Geral";
  for (const s of lista) { const g = grupo(s); if (!grupos.has(g)) grupos.set(g, []); grupos.get(g).push(s); }
  const ordem = ["Geral", ...[...grupos.keys()].filter(g => !["Geral", "WhatsApp"].includes(g)).sort((a,b) => a.localeCompare(b,"pt-BR")), ...(grupos.has("WhatsApp") ? ["WhatsApp"] : [])];
  const html = ordem.filter(g => grupos.get(g).length || g === "Geral" && !busca).map(g => `<h3 class="grupo" data-chave="grupo-${esc(g)}">${esc(g)}</h3>${grupos.get(g).map(s => `<button data-chave="sess-${esc(s.id)}" data-id="${esc(s.id)}" class="conv ${s.id === sessAtual ? "on" : ""}"><i class="dot ${s.viva ? "viva" : "dormindo"}" title="${s.viva ? "Acordada" : "Dormindo"}"></i><span>${esc(s.titulo)}</span><time>${esc(horaRelativa(s.atualizada || s.criada))}</time></button>`).join("")}`).join("") || '<p class="grupo">Nenhuma conversa</p>';
  if (secoesUi.get("listaSess") !== html) {
    reconcilia("listaSess", html); secoesUi.set("listaSess", html);
    $("listaSess").querySelectorAll("[data-id]").forEach(b => b.onclick = () => abre(b.dataset.id));
  }
  $("verArquivadas").textContent = verArquivadas ? "Ver conversas ativas" : "Ver arquivadas";
  $("verArquivadas").setAttribute("aria-pressed", String(verArquivadas));
}
function mostraCabecalho(s) {
  const fila = s.fila || [], ocupado = !!s.trabalhando || !!fila.length;
  $("enviar").disabled = !!s.arquivada || anexando;
  $("enviar").hidden = !!s.trabalhando;
  $("texto").disabled = !!s.arquivada;
  $("anexar").disabled = !!s.arquivada || anexando;
  $("parar").hidden = !s.trabalhando; $("resumir").disabled = !!s.trabalhando || !!s.arquivada || !sessAtual;
  $("dicaEnvio").textContent = s.trabalhando ? `Enter põe na fila +${fila.length + 1} · Shift+Enter quebra linha · Esc para` : "Enter envia · Shift+Enter quebra linha · Esc para";
  $("fecharSessao").disabled = ocupado || !sessAtual;
  $("arquivarSessao").disabled = ocupado || !sessAtual;
  $("moverSessao").disabled = ocupado || !sessAtual;
  $("arquivarSessao").textContent = s.arquivada ? "Reabrir" : "Arquivar";
  $("maisBtn").disabled = !sessAtual;
  $("tituloSessao").setAttribute("contenteditable", String(!!sessAtual && !tituloSalvando));
  if (document.activeElement !== $("tituloSessao")) $("tituloSessao").textContent = s.titulo || "Nova conversa";
  if ($("novaConversa").hidden) { $("motor").value = s.motor || $("motor").value; $("motor").disabled = ocupado; }
  const nome = $("motor").value || E?.motor_padrao || "Motor";
  $("motorNome").textContent = `${nome.charAt(0).toUpperCase() + nome.slice(1)} · ${s.viva ? "aberta" : "dormindo"}`;
  $("motorBtn").querySelector(".dot").classList.toggle("viva", !!s.viva);
  $("projAtivo").textContent = s.projeto ? `projeto: ${s.projeto}` : "Geral";
}
function recebeSessao(sid, dados) {
  const antes = sessoesUi.get(sid), s = {...(antes || {}), ...dados};
  sessoesUi.set(sid, s);
  if (sessAtual !== sid) return;
  const outra = sessaoExibida !== sid;
  if (outra || !antes || !igual([antes.mensagens,antes.aprovacoes,antes.trabalhando,antes.arquivada,antes.fila], [s.mensagens,s.aprovacoes,s.trabalhando,s.arquivada,s.fila])) mostraMensagens(s);
  const mostrarParcial = () => {
    if (sessAtual !== sid) return;
    const atual = sessoesUi.get(sid), parcial = $("parcial"), seguir = pertoDoFim();
    let mudou = false;
    if (parcial && parcial.dataset.texto !== (atual.parcial || "")) {
      parcial.innerHTML = markdownSeguro(atual.parcial || ""); parcial.dataset.texto = atual.parcial || ""; mudou = true;
    }
    if (parcial) parcial.hidden = !atual.parcial;
    if ($("pens")) $("pens").hidden = !!atual.parcial;
    if ($("acaoAtual")) {
      const acao = atual.resumindo ? "Resumindo a conversa…" : atual.acao || "";
      if ($("acaoAtual").textContent !== acao) { $("acaoAtual").textContent = acao; mudou = true; }
    }
    parcialQuando = Date.now(); ligaMensagem();
    if (mudou) atualizaRolagem(seguir);
  };
  if (outra || !antes || antes.parcial !== s.parcial || antes.acao !== s.acao || antes.resumindo !== s.resumindo) {
    clearTimeout(parcialTimer);
    if (Date.now() - parcialQuando >= 150) mostrarParcial();
    else parcialTimer = setTimeout(mostrarParcial, 150 - (Date.now() - parcialQuando));
  }
  const pendentes = [...(s.resumindo && s.atual?.texto ? [{...s.atual, atual:true}] : []), ...(s.fila || [])];
  atualizaSecao("fila", [sid, pendentes, !!s.fila_pausada], () => {
    const seguir = pertoDoFim();
    $("filaPedidos").hidden = !pendentes.length && !s.fila_pausada;
    reconcilia("filaPedidos", (s.fila_pausada ? '<div data-chave="fila-pausada"><button class="sec" data-retomar-fila>fila pausada · continuar</button></div>' : '') + pendentes.map(x => `<div class="m dono msg na-fila" data-chave="${esc(x.id)}"><span>${esc(x.texto || "Resumir conversa")}</span><small>na fila</small>${x.atual ? '' : `<button class="sec" data-cancelar-fila="${esc(x.id)}" aria-label="Tirar da fila">×</button>`}</div>`).join(""));
    $("filaPedidos").querySelectorAll("[data-retomar-fila]").forEach(b => b.onclick = () => acaoConversa("/api/fila/retomar"));
    $("filaPedidos").querySelectorAll("[data-cancelar-fila]").forEach(b => b.onclick = () => acaoConversa("/api/fila/cancelar", {id:b.dataset.cancelarFila}));
    if (pendentes.length) atualizaRolagem(seguir);
  });
  mostraCabecalho(s);
  atualizaSecao("contexto", [sid,s.contexto,s.tokens_total], () => mostraContexto(s));
  if (E) { const item = E.sessoes.find(x => x.id === sid); if (item) Object.assign(item, {viva:s.viva,arquivada:s.arquivada,titulo:s.titulo || item.titulo,projeto:s.projeto}); mostraSessoes(); }
}

async function acaoConversa(rota, extra = {}) {
  const sid = sessAtual;
  if (!sid) return;
  try {
    confirmaResposta(await api("POST", rota, {sessao:sid,...extra}));
    const dados = await api("GET", `/api/sessao/${encodeURIComponent(sid)}`);
    recebeSessao(sid, dados);
    if (sessAtual === sid) $("avisoConversa").textContent = "";
    await carrega();
  } catch (e) { if (sessAtual === sid) $("avisoConversa").textContent = e.message || "Não consegui concluir. Tenta de novo."; }
}
try { som = localStorage.getItem("sheep-som") === "1"; } catch (_) {}
function mostraSom() {
  $("som").textContent = som ? "🔊" : "🔇";
  $("som").setAttribute("aria-pressed", String(som));
  $("som").setAttribute("aria-label", som ? "Desligar som" : "Ligar som");
}
function tocar(nome) {
  if (!som || !audioLiberado) return;
  try {
    if (audioAtual) audioAtual.pause();
    audioAtual = new Audio(`voz/${nome}.mp3`);
    audioAtual.play().catch(() => {});
  } catch (_) {}
}
$("som").onclick = () => {
  som = !som; audioLiberado = true;
  try { localStorage.setItem("sheep-som", som ? "1" : "0"); } catch (_) {}
  mostraSom();
  if (!som && audioAtual) audioAtual.pause();
  if (som && !sessAtual && $("conversa").classList.contains("on")) tocar("boas-vindas");
};
mostraSom();
const CONHECER = "Acabei de te instalar. Siga o Primeiro uso do AGENTS.md: se apresente em duas linhas e me peça a resposta do prompt mestre.";
const PEDIDOS = ["Me conta o que você sabe fazer", "Faz um post sobre o meu negócio", "Organiza minha semana", "Cria um projeto novo"];
function recepcao() {
  if (!E || sessAtual) return;
  const fala = E.primeiro_uso ? "Antes de tudo, me deixa te conhecer. Trouxe a resposta do prompt mestre?" : `Oi, ${E.dono_nome || "chefe"}. Agora eu moro aqui. O que a gente faz primeiro?`;
  if ($("recepcao") && falaAtual === fala) return;
  clearTimeout(falaTimer); falaAtual = fala; sessaoExibida = null;
  $("msgs").innerHTML = `<div class="recepcao" id="recepcao"><img src="sheep.png" alt="Sheep, a agente dos Incomparáveis"><p id="falaSheep" aria-label="${esc(fala)}"></p><div class="pedidos">${E.primeiro_uso ? '<button id="bora">Bora</button>' : PEDIDOS.map((p, i) => `<button class="sec" data-pedido="${i}">${esc(p)}</button>`).join("")}</div></div>`;
  let i = 0;
  function letra() {
    if (sessAtual || !$("falaSheep")) return;
    $("falaSheep").innerHTML = esc(fala.slice(0, ++i));
    if (i < fala.length) falaTimer = setTimeout(letra, 22);
  }
  if (semMovimento()) $("falaSheep").textContent = fala; else letra();
  if ($("bora")) $("bora").onclick = () => enviar(CONHECER, "conhecendo você");
  $("msgs").querySelectorAll("[data-pedido]").forEach(b => b.onclick = () => enviar(PEDIDOS[Number(b.dataset.pedido)]));
}
function editando(id) {
  return [...$(id).querySelectorAll("input")].some(i => i.type !== "checkbox" && i.type !== "file" && (i === document.activeElement || i.value !== "")) || $(id).querySelector("select:focus") !== null;
}
async function mudaPreferencia(controle, rota, corpo, secao, aviso) {
  if (controle.disabled || preferenciasPendentes.has(secao)) return;
  const ligado = controle.checked;
  const controles = [...$(secao === "habilidades" ? "cardsHab" : "cardsStatus").querySelectorAll("[data-h],[data-r]")];
  preferenciasPendentes.add(secao); controles.forEach(c => { c.disabled = true; });
  try {
    confirmaResposta(await api("POST", rota, corpo));
    $(aviso).textContent = "Preferência salva.";
  } catch (e) { controle.checked = !ligado; $(aviso).textContent = e.message || "Não consegui salvar. Tenta de novo."; }
  finally { preferenciasPendentes.delete(secao); controles.forEach(c => { c.disabled = false; }); secoesUi.delete(secao); await carrega(); }
}
document.querySelectorAll("nav button[data-t]").forEach(b => b.onclick = () => tela(b.dataset.t));
async function carrega() {
  if (consultaEstado) return consultaEstado;
  consultaEstado = (async () => {
  E = await api("GET", "/api/estado");
  mostraWhatsApp(E.whatsapp || {});
  const dono = E.dono_nome ? `do ${E.dono_nome}` : "";
  if ($("donoNome").textContent !== dono) $("donoNome").textContent = dono;
  $("donoNome").hidden = !E.dono_nome;
  atualizaSecao("motores", [E.motores,E.motor_padrao], () => {
  const motorAtual = $("motor").value;
  $("motor").innerHTML = Object.entries(E.motores).filter(([, v]) => v).map(([k, v]) => `<option value="${esc(k)}" ${v ? "" : "disabled"}>${esc(k)}${v ? "" : " (não instalado)"}</option>`).join("");
  $("motor").value = motorAtual && E.motores[motorAtual] ? motorAtual : E.motor_padrao;
  }, document.activeElement === $("motor"));
  mostraSessoes();
  atualizaSecao("habilidades", E.habilidades, () => {
  reconcilia("cardsHab", E.habilidades.map(h => `<div class="card" data-chave="${esc(h.id)}"><div class="linha"><h3>${esc(h.nome)}</h3><label><input type="checkbox" data-h="${esc(h.id)}" ${h.ligada ? "checked" : ""}> ligada</label></div><p>${esc(h.descricao)}</p><p class="rot">ex.: ${esc(h.exemplo)}</p></div>`).join("") || "<p>Nenhuma habilidade ainda.</p>");
  $("cardsHab").querySelectorAll("[data-h]").forEach(c => c.onchange = () => mudaPreferencia(c, "/api/habilidade", {id: c.dataset.h, ligada: c.checked}, "habilidades", "avisoHab"));
  }, preferenciasPendentes.has("habilidades"));
  $("nAprov").hidden = !E.aprovacoes.length;
  if ($("nAprov").textContent !== String(E.aprovacoes.length)) $("nAprov").textContent = E.aprovacoes.length;
  if (E.aprovacoes.length > nAprovAnterior) tocar("aprovacao");
  nAprovAnterior = E.aprovacoes.length;
  atualizaSecao("aprovacoes", [E.aprovacoes,[...avisosAprovacoes]], () => {
    reconcilia("cardsAprov", E.aprovacoes.map(a => cardAprovacao(a)).join("") || "<p>Nada esperando o seu sim.</p>");
    ligaAprovacoes($("cardsAprov"));
  });
  atualizaSecao("pacotes", [E.pacotes,E.avisos], mostraPacotes);
  atualizaSecao("conexoes", [E.motores,E.motor_padrao,E.conexoes,E.aprender,codigoTelegram,avisoTelegram,avisoAprender], () => {
    reconcilia("cardsCon", `<h3 class="secao-titulo">Motores</h3><div class="card" data-chave="padrao"><label for="motorPadrao">Motor padrão</label><select id="motorPadrao"><option value="" disabled>Escolha um motor instalado</option>${Object.entries(E.motores).filter(([, v]) => v).map(([k]) => `<option value="${esc(k)}" ${k === E.motor_padrao ? "selected" : ""}>${esc(k)}</option>`).join("")}</select><p id="avisoMotor" aria-live="polite"></p></div>` + Object.entries(E.motores).map(([k, v]) => `<div class="card" data-chave="motor-${esc(k)}"><div class="linha"><h3>${esc(k)}</h3><span class="dot ${v ? "on" : "off"}"></span></div><p>${v ? "Instalado." : "Não instalado neste PC."}</p>${k === "antigravity" ? '<a href="https://antigravity.google" target="_blank" rel="noopener noreferrer">Instalar o Antigravity</a><p>baixe, instale e volte aqui</p>' : ""}</div>`).join("") +
      '<h3 class="secao-titulo">Chaves e conexões</h3>' + CON.map(([n, t, g]) => `<div class="card" data-chave="con-${n}"><div class="linha"><h3>${t}</h3><span class="dot ${E.conexoes[n] ? "on" : "off"}"></span></div><p>${g}</p><form class="linha" data-c="${n}"><input type="password" placeholder="${E.conexoes[n] ? "ligada · cole outra pra trocar" : "cole aqui"}" autocomplete="off"><button>Salvar</button></form>${n === "TELEGRAM_TOKEN" ? `<p>${E.conexoes.TELEGRAM_DONO ? "Dono vinculado." : "Salve o token e gere um código para me vincular a você."}</p><button class="sec" id="gerarTelegram" ${E.conexoes.TELEGRAM_TOKEN ? "" : "disabled"}>Gerar código</button><p id="codigoTelegram" aria-live="polite">${codigoTelegram ? `Mande /start ${esc(codigoTelegram)} para o seu bot` : esc(avisoTelegram)}</p><button class="sec" id="vincularTelegram" ${codigoTelegram ? "" : "disabled"}>Já mandei /start com o código</button>` : ""}</div>`).join("") + `<div class="card" data-chave="aprender"><h3>Aprender sozinha</h3><label><input type="checkbox" id="aprender" ${E.aprender !== false ? "checked" : ""}> Aprender enquanto a gente trabalha</label><p id="avisoAprender" aria-live="polite">${esc(avisoAprender)}</p></div>`);
    $("gerarTelegram").onclick = async () => {
      const r = await api("POST", "/api/telegram/codigo"); codigoTelegram = r.codigo; avisoTelegram = ""; carrega();
    };
    $("vincularTelegram").onclick = async () => {
      const r = await api("POST", "/api/telegram/vincular");
      if (r.chat) { codigoTelegram = ""; avisoTelegram = "Telegram ligado: achei você."; carrega(); }
      else $("codigoTelegram").innerHTML = `Ainda não vi seu /start. Mande /start ${esc(codigoTelegram)} para o seu bot e clique de novo.`;
    };
    $("motorPadrao").onchange = async ev => {
      const r = await api("POST", "/api/conexao", {nome: "MOTOR_PADRAO", valor: ev.target.value});
      $("avisoMotor").innerHTML = r.ok ? "Motor padrão salvo." : esc(r.erro || "Não consegui salvar.");
    };
    $("aprender").onchange = async () => {
      if (salvandoAprender) return;
      const ligado = $("aprender").checked;
      salvandoAprender = true; $("aprender").disabled = true;
      try {
        confirmaResposta(await api("POST", "/api/conexao", {nome: "APRENDER", valor: ligado ? "1" : "0"}));
        E.aprender = ligado; avisoAprender = ligado ? "Vou aprendendo com você." : "Aprendizado automático desligado.";
      } catch (e) { $("aprender").checked = !ligado; avisoAprender = e.message || "Não consegui salvar."; }
      finally { salvandoAprender = false; $("aprender").disabled = false; $("avisoAprender").textContent = avisoAprender; }
    };
    $("cardsCon").querySelectorAll("form[data-c]").forEach(f => f.onsubmit = async ev => { ev.preventDefault(); const input = f.querySelector("input"), v = input.value.trim(); if (!v) return; await api("POST", "/api/conexao", {nome: f.dataset.c, valor: v}); input.value = ""; input.blur(); carrega(); });
  }, editando("cardsCon") || salvandoAprender);
  atualizaSecao("projetos", E.projetos, () => {
    reconcilia("cardsProj", `<form class="card" id="novoProj"><h3>+ Novo projeto</h3><input placeholder="nome do projeto" autocomplete="off"><button>Criar</button></form>` +
      E.projetos.map(p => `<div class="card" data-chave="proj-${esc(p)}"><h3>${esc(p)}</h3><button class="sec" data-p="${esc(p)}">Conversar aqui</button></div>`).join(""));
    $("novoProj").onsubmit = async ev => {
      ev.preventDefault(); const n = ev.target.querySelector("input").value.trim(); if (!n) return;
      const s = await api("POST", "/api/projeto", {nome: n, motor: $("motor").value});
      ev.target.querySelector("input").value = "";
      document.querySelector('[data-t="conversa"]').click(); await abre(s.id);
      await enviar("Novo projeto. Me faça 5 perguntas, uma por vez, e depois escreva a casa.md desta pasta com o que eu responder.");
    };
    $("cardsProj").querySelectorAll("[data-p]").forEach(b => b.onclick = async () => {
      const s = E.sessoes.find(x => x.projeto === b.dataset.p && !x.arquivada) || await api("POST", "/api/projeto", {nome: b.dataset.p, motor: $("motor").value});
      document.querySelector('[data-t="conversa"]').click(); abre(s.id);
    });
  }, editando("cardsProj"));
  atualizaSecao("status", [E.avisos,E.aprendi,E.whatsapp?.estado,E.whatsapp?.pedidos_hoje,E.sessoes.length,E.habilidades.filter(h=>h.ligada).length,E.aprovacoes.length,E.motores,E.rotinas,avisoMemoria], () => {
  reconcilia("cardsStatus", (E.avisos || []).map(a => `<div class="card aprendi" role="status">${esc(a)}</div>`).join("") + cardAprendi() + `<div class="card"><h3>WhatsApp</h3><p>${E.whatsapp?.estado === "conectado" ? "Conectado" : "Desconectado"} · ${esc(E.whatsapp?.pedidos_hoje || 0)} pedidos hoje</p></div>` + [["Conversas", E.sessoes.length], ["Habilidades ligadas", E.habilidades.filter(h => h.ligada).length], ["Esperando seu sim", E.aprovacoes.length], ["Cérebros instalados", Object.values(E.motores).filter(Boolean).length]]
    .map(([t, n]) => `<div class="card"><span class="rot">${t}</span><div style="font:400 64px/1 var(--display)">${n}</div></div>`).join("") +
    E.rotinas.map(r => `<div class="card"><div class="linha"><h3>${esc(r.nome)} · ${esc(r.hora)}</h3><label><input type="checkbox" data-r="${esc(r.nome)}" ${r.ativo ? "checked" : ""}> ligada</label></div><p>${esc(r.prompt)}</p></div>`).join(""));
  $("cardsStatus").querySelectorAll("[data-r]").forEach(c => c.onchange = () => mudaPreferencia(c, "/api/rotina", {nome: c.dataset.r, ativo: c.checked}, "status", "avisoStatus"));
  $("cardsStatus").querySelectorAll("[data-memoria]").forEach(b => b.onclick = async () => {
    const arquivo = b.dataset.memoria;
    if (operacoesMemoria.has(arquivo)) return;
    operacoesMemoria.add(arquivo);
    $("cardsStatus").querySelectorAll("[data-memoria]").forEach(x => { if (x.dataset.memoria === arquivo) x.disabled = true; });
    try {
      confirmaResposta(await api("POST", "/api/memoria", {arquivo, acao: b.dataset.acao}));
      avisoMemoria = b.dataset.acao === "manter" ? "Guardei na memória." : "Esqueci essa.";
      await carrega();
    } catch (e) { avisoMemoria = e.message || "Não consegui concluir."; }
    finally {
      operacoesMemoria.delete(arquivo); $("avisoMemoria").textContent = avisoMemoria;
      $("cardsStatus").querySelectorAll("[data-memoria]").forEach(x => { if (x.dataset.memoria === arquivo) x.disabled = false; });
    }
  });
  }, preferenciasPendentes.has("status"));
  if (!sessAtual) { recepcao(); mostraCabecalho({}); }
  })();
  try { await consultaEstado; }
  catch (e) { $("avisoConversa").textContent = e.message || "Não consegui atualizar. Já tento de novo."; }
  finally { consultaEstado = null; }
}
async function abre(id) {
  rascunhos.set(sessAtual, $("texto").value);
  if (sessAtual) rolagens.set(sessAtual, $("rolo").scrollTop);
  paraEventos(); fechaMenus(); tela("conversa"); clearTimeout(falaTimer);
  const mudou = sessAtual !== id;
  sessAtual = id;
  if (mudou) { $("texto").value = rascunhos.get(id) || ""; cresce(); }
  const cache = sessoesUi.get(id);
  if (cache) {
    recebeSessao(id, cache);
    $("rolo").scrollTop = rolagens.get(id) ?? $("rolo").scrollHeight;
    $("novasMensagens").hidden = true;
  } else if (mudou) {
    $("msgs").innerHTML = '<div class="acao" role="status">Abrindo conversa…</div>';
    $("filaPedidos").hidden = true;
    mostraCabecalho(E?.sessoes.find(x => x.id === id) || {});
  }
  try {
    const s = await api("GET", `/api/sessao/${encodeURIComponent(id)}`);
    if (sessAtual !== id) { sessoesUi.set(id, s); return; }
    recebeSessao(id, s);
    if (!cache && mudou) desce();
    await carrega();
    if (sessAtual === id) await iniciaEventos(id);
  } catch (e) { if (sessAtual === id) $("avisoConversa").textContent = e.message || "Não consegui abrir essa conversa."; }
}
$("novaSess").onclick = () => {
  const abrir = $("novaConversa").hidden;
  tela("conversa"); $("novaConversa").hidden = !abrir; $("novaSess").setAttribute("aria-expanded", String(abrir));
  $("motorNova").innerHTML = Object.entries(E?.motores || {}).filter(([, instalado]) => instalado).map(([nome]) => `<option value="${esc(nome)}">${esc(nome)}</option>`).join("");
  $("motorNova").value = E?.motor_padrao || $("motor").value;
  $("ondeConversa").innerHTML = '<option value="">Geral</option>' + [...(E?.projetos || [])].sort((a,b) => a.localeCompare(b,"pt-BR")).map(p => `<option value="${esc(p)}">${esc(p)}</option>`).join("");
  if (abrir) $("ondeConversa").focus();
};
$("cancelarNova").onclick = fechaMenus;
$("novaConversa").onsubmit = async ev => {
  ev.preventDefault();
  try {
    const s = await api("POST", "/api/sessao", {titulo: $("nomeConversa").value.trim() || "Nova conversa", projeto: $("ondeConversa").value || null, motor: $("motorNova").value});
    fechaMenus(); $("nomeConversa").value = ""; await abre(s.id); $("texto").focus();
  } catch (e) { $("avisoConversa").textContent = e.message; }
};
$("verArquivadas").onclick = () => { verArquivadas = !verArquivadas; mostraSessoes(); };
$("buscaConversas").oninput = mostraSessoes;
$("memBtn").onclick = () => alternaMenu("memPop", "memBtn");
$("maisBtn").onclick = () => alternaMenu("menuConversa", "maisBtn");
$("motorBtn").onclick = () => { if (!$("novaConversa").hidden) $("motorNova").focus(); else alternaMenu("motorPop", "motorBtn"); };
$("barraContexto").onclick = () => $("memBtn").click();
$("barraContexto").onkeydown = ev => {
  if (["Enter", " "].includes(ev.key)) { ev.preventDefault(); $("barraContexto").click(); }
};
$("tituloSessao").onkeydown = async ev => {
  if (ev.key === "Escape") {
    ev.preventDefault(); ev.stopPropagation(); $("tituloSessao").textContent = sessoesUi.get(sessAtual)?.titulo || "Nova conversa"; $("tituloSessao").blur(); return;
  }
  if (ev.key !== "Enter" || ev.isComposing || tituloSalvando) return;
  ev.preventDefault();
  const titulo = $("tituloSessao").textContent.trim();
  if (!titulo || titulo.length > 120) { $("avisoConversa").textContent = "Use um título de 1 a 120 caracteres."; return; }
  tituloSalvando = true;
  $("tituloSessao").blur();
  try { await acaoConversa("/api/sessao/renomear", {titulo}); }
  finally { tituloSalvando = false; $("tituloSessao").setAttribute("contenteditable", String(!!sessAtual)); }
};
$("tituloSessao").onpaste = ev => {
  ev.preventDefault();
  const texto = (ev.clipboardData?.getData("text/plain") || "").replace(/[\r\n]+/g, " ");
  const selecao = window.getSelection();
  if (!selecao.rangeCount) return;
  const range = selecao.getRangeAt(0); range.deleteContents(); const no = document.createTextNode(texto); range.insertNode(no); range.setStartAfter(no); range.collapse(true);
};
$("tituloSessao").onblur = () => { if (!tituloSalvando) $("tituloSessao").textContent = sessoesUi.get(sessAtual)?.titulo || "Nova conversa"; };
$("fecharSessao").onclick = () => { fechaMenus(); return acaoConversa("/api/sessao/fechar"); };
$("arquivarSessao").onclick = () => {
  if (sessoesUi.get(sessAtual)?.arquivada) { fechaMenus(); return acaoConversa("/api/sessao/arquivar", {arquivada:false}); }
  $("confirmacaoArquivar").hidden = false; $("moverConversa").hidden = true;
};
$("cancelarArquivar").onclick = () => { $("confirmacaoArquivar").hidden = true; };
$("confirmarArquivar").onclick = () => { fechaMenus(); return acaoConversa("/api/sessao/arquivar", {arquivada:true}); };
$("moverSessao").onclick = () => {
  $("confirmacaoArquivar").hidden = true; $("moverConversa").hidden = false;
  $("projetoDestino").innerHTML = '<option value="">Geral</option>' + (E?.projetos || []).map(p => `<option value="${esc(p)}">${esc(p)}</option>`).join("");
  $("projetoDestino").value = sessoesUi.get(sessAtual)?.projeto || "";
};
$("moverConversa").onsubmit = ev => { ev.preventDefault(); const projeto = $("projetoDestino").value || null; fechaMenus(); return acaoConversa("/api/sessao/mover", {projeto}); };
$("motor").onchange = () => {
  if (sessAtual && $("novaConversa").hidden) { const motor = $("motor").value; fechaMenus(); return acaoConversa("/api/sessao/motor", {motor}); }
  mostraCabecalho({});
};
$("parar").onclick = () => acaoConversa("/api/parar");
$("resumir").onclick = () => { fechaMenus(); return acaoConversa("/api/resumir"); };
$("novasMensagens").onclick = desce;
$("rolo").onscroll = () => { if (pertoDoFim()) $("novasMensagens").hidden = true; };
$("whatsappChip").onclick = () => tela("conexoes");
document.addEventListener("click", ev => { if (!ev.target.closest(".menu,.pop,#maisBtn,#memBtn,#motorBtn,#novaSess,#barraContexto")) fechaMenus(); });
document.addEventListener("keydown", ev => {
  if (ev.ctrlKey && ev.key.toLowerCase() === "n") { ev.preventDefault(); $("novaSess").click(); }
  if (ev.ctrlKey && ev.key.toLowerCase() === "k") { ev.preventDefault(); $("buscaConversas").focus(); }
  if (ev.key === "Escape") {
    const aberto = ["novaConversa", "motorPop", "memPop", "menuConversa"].some(id => !$(id).hidden);
    if (aberto) { ev.preventDefault(); fechaMenus(); }
    else if (sessoesUi.get(sessAtual)?.trabalhando) { ev.preventDefault(); $("parar").click(); }
  }
});
$("texto").oninput = cresce;
$("texto").onkeydown = ev => { if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); enviar($("texto").value.trim()); } };
$("anexar").onclick = () => { if (!anexando) $("arquivoAnexo").click(); };
$("arquivoAnexo").onchange = async () => {
  const arquivo = $("arquivoAnexo").files[0], sid = sessAtual;
  if (!arquivo || anexando) return;
  if (arquivo.size > 20 * 1024 * 1024) { $("avisoConversa").textContent = "O anexo pode ter até 20 MB."; $("arquivoAnexo").value = ""; return; }
  anexando = true; $("anexar").disabled = true; $("avisoConversa").textContent = "Guardando anexo…";
  try {
    const bytes = new Uint8Array(await arquivo.arrayBuffer()); let binario = "";
    for (let i = 0; i < bytes.length; i += 32768) binario += String.fromCharCode(...bytes.subarray(i, i + 32768));
    const r = confirmaResposta(await api("POST", "/api/anexo", {nome:arquivo.name, base64:btoa(binario)}));
    const anterior = sessAtual === sid ? $("texto").value : rascunhos.get(sid) || "";
    const texto = `${anterior}${anterior && !anterior.endsWith("\n") ? "\n" : ""}[arquivo: ${r.caminho}]\n`;
    rascunhos.set(sid, texto);
    if (sessAtual === sid) { $("texto").value = texto; cresce(); $("texto").focus(); $("avisoConversa").textContent = "Anexo pronto. Envie o pedido quando quiser."; }
  } catch (e) { if (sessAtual === sid) $("avisoConversa").textContent = e.message || "Não consegui anexar. Tenta de novo."; }
  finally { anexando = false; $("arquivoAnexo").value = ""; mostraCabecalho(sessoesUi.get(sessAtual) || {}); }
};
async function enviar(t, titulo) {
  if (!t || enviando || anexando || sessoesUi.get(sessAtual)?.arquivada) return;
  enviando = true; audioLiberado = true; tocar("recebido");
  $("msgs").querySelectorAll("[data-opcao]").forEach(b => { b.disabled = true; });
  let sid;
  try {
    if (!sessAtual) {
      const s = await api("POST", "/api/sessao", {titulo: titulo || t.slice(0, 30), motor: $("motor").value});
      sessAtual = s.id; clearTimeout(falaTimer); $("msgs").innerHTML = "";
    }
    sid = sessAtual;
    $("texto").value = ""; rascunhos.set(sid, ""); cresce();
    confirmaResposta(await api("POST", "/api/conversar", {sessao: sid, texto: t}));
    const dados = await api("GET", `/api/sessao/${encodeURIComponent(sid)}`);
    recebeSessao(sid, dados);
    if (!dados.trabalhando) tocar("pronto");
    if (sessAtual === sid) { await iniciaEventos(sid); }
    await carrega();
  } catch (e) {
    if (sessAtual === sid) { $("texto").value = t; $("avisoConversa").textContent = e.message || "Não consegui enviar esse pedido. Tenta de novo."; }
  } finally {
    enviando = false;
    $("msgs").querySelectorAll("[data-opcao]").forEach(b => { b.disabled = b.dataset.ativa !== "1"; });
  }
}
$("form").onsubmit = ev => { ev.preventDefault(); enviar($("texto").value.trim()); };
carrega(); setInterval(carrega, 15000);
setInterval(() => { if ($("conexoes").classList.contains("on")) return consultaWhatsapp(); }, 1500);

api("GET", "/api/identidade").then(i => { if (i.trocado) { $("marcaNome").textContent = i.nome.toUpperCase(); document.title = i.nome; } }).catch(() => {});
