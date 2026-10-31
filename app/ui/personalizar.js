(() => {
const PALETA = [["#e0102f", "Vermelho"], ["#ff6a00", "Laranja"], ["#f5b301", "Dourado"], ["#14b86a", "Verde"], ["#00a7c4", "Turquesa"], ["#2f6bff", "Azul"], ["#7a3cff", "Roxo"], ["#ff2d9a", "Pink"]];
const NOMES_TELA = {projetos: "Projetos", pacotes: "Pacotes", conexoes: "Conexões", status: "Aprendi"};
const IMAGENS = [["rosto", "Rosto", "Aparece no chat, do lado de cada resposta."], ["recepcao", "Corpo inteiro", "Recebe você na tela inicial."], ["fundo", "Fundo", "Fica atrás da conversa e das telas."]];
const BLOQUEIO_NOME = ".msgs > :not(.recepcao), #cardsAprov, #listaSess, #cardsProj, #tituloSessao, #personalizar, .pagina > h2, textarea, input, script, style";
let AP = null, PROMPTS = [], salvarTimer, nomeDaCasa = "Sheep", pendente = {}, tintaPendente = false, tintaAtual = 0, telaPronta = false;
const manteveSheep = () => /\bsheep\b/i.test(nomeDaCasa);

const valorPrompt = (id, chave) => document.querySelector(`.perso-prompt[data-id="${id}"] input[data-campo="${chave}"]`)?.value.trim() || "";
const trocarSheep = texto => texto.replace(/\bSheep\b/g, () => nomeDaCasa).replace(/\bSHEEP\b/g, () => nomeDaCasa.toUpperCase());

function dadosDoPrompt(p) {
  const i = AP.identidade, faltou = "(ainda não definido)";
  const dados = {agente: i.nome, dono: E?.dono_nome || "o dono", personalidade: i.personalidade || faltou, fala: i.fala || faltou, missao: i.missao || faltou,
                 chama: i.chama || faltou, nunca: i.nunca || faltou, casa: AP.casa};
  for (const q of p.perguntas || []) dados[q.id] = valorPrompt(p.id, q.id) || `[${q.rotulo.replaceAll("{{agente}}", i.nome)}]`;
  return dados;
}
function preencher(texto, dados) { return texto.replace(/\{\{(\w+)\}\}/g, (tudo, chave) => dados[chave] ?? tudo); }
const textoDoPrompt = p => preencher(p.texto, dadosDoPrompt(p));

function aplicarTinta() {
  const vez = ++tintaAtual, link = document.querySelector('link[href^="estilo.css"]');
  if (!link) return;
  const novo = link.cloneNode();
  novo.href = `estilo.css?v=${Date.now()}`;
  novo.onload = () => {
    if (vez !== tintaAtual) return novo.remove();
    document.querySelectorAll('link[href^="estilo.css"]').forEach(l => { if (l !== novo) l.remove(); });
  };
  link.after(novo);
}
function aplicarFundo() {
  const tem = AP.imagens.fundo, forca = AP.ajustes.fundo_forca;
  let estilo = $("estiloFundo");
  if (!estilo) { estilo = document.createElement("style"); estilo.id = "estiloFundo"; document.head.append(estilo); }
  const propria = AP.imagens.recepcao || AP.imagens.rosto ? ".recepcao img{border-radius:24px}" : "";
  estilo.textContent = propria + (tem ? `main::before{content:"";position:absolute;inset:0;pointer-events:none;background:url("aparencia/fundo?v=${tem}") center/cover no-repeat;opacity:${forca / 100}}` : "");
}
function aplicarTelas() {
  for (const [id, original] of Object.entries(NOMES_TELA)) {
    const ajuste = AP.ajustes.telas[id] || {}, nome = ajuste.nome || original;
    const botao = document.querySelector(`nav [data-t="${id}"]`), titulo = $(id)?.querySelector("h2");
    if (!botao) continue;
    botao.classList.toggle("tela-escondida", !!ajuste.oculta);
    botao.dataset.dica = id === "status" && !ajuste.nome ? "Aprendi / Status" : id === "pacotes" && !ajuste.nome ? "Pacotes e habilidades" : nome;
    botao.setAttribute("aria-label", botao.dataset.dica);
    if (titulo?.firstChild) titulo.firstChild.textContent = nome;
    if (ajuste.oculta && botao.classList.contains("on")) tela("conversa");
  }
  $("texto").placeholder = AP.ajustes.frase || "Pede pra mim, chefe…";
}
function trocarNomesEm(raiz) {
  if (manteveSheep() || !raiz) return;
  const elemento = raiz.nodeType === 1 ? raiz : raiz.parentElement;
  if (!elemento || elemento.closest(BLOQUEIO_NOME)) return;
  const andador = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT);
  const textos = raiz.nodeType === 3 ? [raiz] : [];
  while (andador.nextNode()) textos.push(andador.currentNode);
  for (const n of textos) {
    const novo = trocarSheep(n.nodeValue);
    if (novo !== n.nodeValue && !n.parentElement?.closest(BLOQUEIO_NOME)) n.nodeValue = novo;
  }
  for (const el of raiz.nodeType === 1 ? [raiz, ...raiz.querySelectorAll("[aria-label],[title],[alt]")] : []) {
    for (const a of ["aria-label", "title", "alt"]) if (el.getAttribute?.(a)?.includes("Sheep")) el.setAttribute(a, trocarSheep(el.getAttribute(a)));
  }
}
function vigiarNomes() {
  if (manteveSheep()) return;
  document.title = nomeDaCasa;
  trocarNomesEm(document.body);
  new MutationObserver(lista => {
    for (const m of lista) { if (m.type === "characterData") trocarNomesEm(m.target); else m.addedNodes.forEach(trocarNomesEm); }
  }).observe(document.body, {subtree: true, childList: true, characterData: true});
}
function aplicarTudo() { aplicarFundo(); aplicarTelas(); }

function aviso(id, texto) { const el = $(id); if (el) el.textContent = texto; }
// Manda só o que mudou: o agente pode ter gravado o resto em ajustes.json.
async function descarregar() {
  clearTimeout(salvarTimer);
  const mudanca = pendente, tingir = tintaPendente;
  pendente = {}; tintaPendente = false;
  if (!Object.keys(mudanca).length) return;
  try {
    await api("POST", "/api/aparencia", mudanca);
    if (tingir) aplicarTinta();
    aviso("avisoPerso", "");
  } catch (e) { aviso("avisoPerso", e.message); }
}
function salvar(mudanca, tingir) {
  Object.assign(AP.ajustes, mudanca); Object.assign(pendente, mudanca);
  tintaPendente = tintaPendente || !!tingir;
  aplicarTudo();
  clearTimeout(salvarTimer);
  salvarTimer = setTimeout(descarregar, tintaPendente ? 120 : 350);
}

function mostraNome() {
  const i = AP.identidade;
  const campos = [["nome", "Nome"], ["personalidade", "Personalidade"], ["fala", "Como fala"], ["missao", "Missão"], ["chama", "Como chama você"], ["assinatura", "Assinatura"], ["nunca", "O que nunca faz"]];
  $("persoNome").innerHTML = `<div class="perso-card"><div class="perso-nome"><img src="rosto.jpg?v=${AP.imagens.rosto}" alt=""><div><b>${esc(i.nome)}</b><small>${i.trocado ? "É esse o nome aqui na sua casa. Ajuste quando quiser." : "Quer trocar? Vai ter drama."}</small></div>${i.trocado ? "" : `<a class="perso-acao" href="ritual.html">Trocar o nome</a>`}</div>${i.trocado ? `<form id="formIdentidade"><div class="perso-campos">${campos.map(([c, r]) => `<label>${r}<input name="${c}" value="${esc(i[c])}" maxlength="${c === "nome" ? 30 : 300}"></label>`).join("")}</div><div class="perso-botoes" style="margin-top:12px"><button class="perso-botao">Salvar</button></div><p class="perso-aviso" id="avisoIdentidade" role="status"></p></form>` : ""}</div>`;
  if (!i.trocado) return;
  $("formIdentidade").onsubmit = async ev => {
    ev.preventDefault();
    try {
      await descarregar();
      await api("POST", "/api/identidade", Object.fromEntries(new FormData(ev.target)));
      location.reload();
    } catch (e) { aviso("avisoIdentidade", e.message); }
  };
}
function mostraCores() {
  const a = AP.ajustes;
  $("persoCores").innerHTML = `<div class="perso-card"><div class="perso-cores">${PALETA.map(([c, n]) => `<button class="perso-cor" style="--c:${c}" data-cor="${c}" aria-label="${n}" title="${n}" aria-pressed="${a.cor === c}"></button>`).join("")}<span class="perso-hex"><input type="color" id="corLivre" value="${a.cor}" aria-label="Escolher outra cor"><input type="text" id="corHex" value="${a.cor}" maxlength="7" spellcheck="false" aria-label="Código da cor"></span></div><div class="perso-tons">${AP.tons.map(t => `<button class="perso-tom" data-tom="${t}" aria-pressed="${a.tom === t}">${t}</button>`).join("")}</div></div>`;
  const usar = cor => {
    document.querySelectorAll(".perso-cor").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.cor === cor)));
    $("corLivre").value = cor; $("corHex").value = cor;
    salvar({cor}, true);
  };
  document.querySelectorAll(".perso-cor").forEach(b => b.onclick = () => usar(b.dataset.cor));
  $("corLivre").oninput = ev => usar(ev.target.value);
  $("corHex").oninput = ev => { const v = ev.target.value.trim().toLowerCase(); if (/^#[0-9a-f]{6}$/.test(v)) usar(v); };
  document.querySelectorAll(".perso-tom").forEach(b => b.onclick = () => {
    document.querySelectorAll(".perso-tom").forEach(x => x.setAttribute("aria-pressed", String(x === b)));
    salvar({tom: b.dataset.tom}, true);
  });
}
function caminhoImagem(alvo) {
  return `${alvo === "rosto" ? "rosto.jpg" : alvo === "recepcao" ? "sheep.png" : "aparencia/fundo"}?v=${AP.imagens[alvo] || Date.now()}`;
}
function mostraImagens() {
  $("persoImagens").innerHTML = `<div class="perso-imagens">${IMAGENS.map(([alvo, titulo, resumo]) => {
    const previa = alvo !== "fundo" || AP.imagens.fundo ? `style="background-image:url('${caminhoImagem(alvo)}')"` : "";
    return `<div class="perso-imagem" data-alvo="${alvo}"><div class="perso-previa" ${previa}>${previa ? "" : "Sem fundo"}</div><h4>${titulo}</h4><p>${resumo}</p><div class="botoes"><button class="perso-botao" data-enviar>Enviar imagem</button><button class="sec" data-gerar>Gerar com IA</button>${AP.imagens[alvo] ? `<button class="sec" data-tirar>Tirar</button>` : ""}</div><input type="file" accept="image/png,image/jpeg,image/webp" hidden></div>`;
  }).join("")}</div><label class="perso-forca">Força do fundo: <input type="range" id="forcaFundo" min="0" max="60" value="${AP.ajustes.fundo_forca}" aria-label="Força do fundo"></label><p class="perso-aviso" id="avisoImagem" role="status"></p>`;
  document.querySelectorAll(".perso-imagem").forEach(card => {
    const alvo = card.dataset.alvo, arquivo = card.querySelector("input[type=file]");
    card.querySelector("[data-enviar]").onclick = () => arquivo.click();
    card.querySelector("[data-gerar]").onclick = () => { const p = document.querySelector(`.perso-prompt[data-id="${alvo}"]`); p.open = true; p.scrollIntoView({behavior: "smooth", block: "center"}); p.querySelector("input")?.focus({preventScroll: true}); };
    const tirar = card.querySelector("[data-tirar]");
    if (tirar) tirar.onclick = async () => {
      try { AP.imagens = await api("POST", "/api/aparencia/limpar", {alvo}); recarregarImagens(); }
      catch (e) { aviso("avisoImagem", e.message); }
    };
    arquivo.onchange = () => {
      const f = arquivo.files[0];
      if (!f) return;
      if (f.size > 8 * 1024 * 1024) return aviso("avisoImagem", "Essa imagem passou de 8 MB.");
      const leitor = new FileReader();
      leitor.onload = async () => {
        try { AP.imagens = await api("POST", "/api/aparencia/imagem", {alvo, base64: String(leitor.result).split(",")[1]}); recarregarImagens(); }
        catch (e) { aviso("avisoImagem", e.message); }
      };
      leitor.readAsDataURL(f);
    };
  });
  $("forcaFundo").oninput = ev => salvar({fundo_forca: Number(ev.target.value)});
}
function recarregarImagens() {
  if ($("persoImagens").firstChild) mostraImagens();
  aplicarFundo();
  const v = Date.now();
  document.querySelectorAll('img[src^="rosto.jpg"],img[src^="sheep.png"]').forEach(i => { i.src = `${i.getAttribute("src").split("?")[0]}?v=${v}`; });
}
function mostraTelas() {
  const a = AP.ajustes;
  $("persoTelas").innerHTML = `<div class="perso-card"><label for="fraseCaixa">Frase da caixa de pedido</label><input type="text" id="fraseCaixa" maxlength="80" value="${esc(a.frase)}" placeholder="Pede pra mim, chefe…" style="margin-bottom:14px">${Object.entries(NOMES_TELA).map(([t, n]) => `<div class="perso-linha"><span>${n}</span><input type="text" data-tela="${t}" maxlength="24" value="${esc(a.telas[t]?.nome || "")}" placeholder="${n}" aria-label="Novo nome de ${n}"><label><input type="checkbox" data-ocultar="${t}" ${a.telas[t]?.oculta ? "checked" : ""}> Esconder</label></div>`).join("")}<p class="perso-fixa">Conversa, Seu sim e Personalizar ficam sempre. Sem Seu sim, nada sairia daqui com o seu ok.</p></div>`;
  const muda = () => {
    const telas = {};
    for (const t of Object.keys(NOMES_TELA)) telas[t] = {nome: document.querySelector(`[data-tela="${t}"]`).value.trim(), oculta: document.querySelector(`[data-ocultar="${t}"]`).checked};
    salvar({telas, frase: $("fraseCaixa").value.trim()});
  };
  $("persoTelas").querySelectorAll("input").forEach(i => { i.oninput = muda; });
}
function mostraPrompts() {
  const nome = AP.identidade.nome;
  $("persoPrompts").innerHTML = `<div class="perso-prompts">${PROMPTS.map(p => `<details class="perso-prompt" data-id="${p.id}"><summary><b>${esc(p.titulo.replaceAll("{{agente}}", nome))}</b><span>${esc(p.resumo.replaceAll("{{agente}}", nome))}</span><em>${p.motor === "codex" ? "gera imagem" : "qualquer motor"}</em></summary><div class="perso-corpo">${(p.perguntas || []).map(q => `<label>${esc(q.rotulo.replaceAll("{{agente}}", nome))}<input data-campo="${q.id}" placeholder="${esc(q.exemplo)}" autocomplete="off"></label>`).join("")}<div class="perso-texto" aria-label="Prompt pronto"></div><div class="perso-botoes"><button class="perso-botao" data-mandar>${p.motor === "codex" ? "Pedir ao Codex" : `Pedir a ${esc(nome)}`}</button><button class="sec" data-copiar>Copiar prompt</button></div><p class="perso-aviso" role="status"></p></div></details>`).join("")}</div>`;
  document.querySelectorAll(".perso-prompt").forEach(el => {
    const p = PROMPTS.find(x => x.id === el.dataset.id), previa = el.querySelector(".perso-texto"), recado = el.querySelector(".perso-aviso");
    const atualiza = () => { previa.textContent = textoDoPrompt(p); };
    atualiza();
    el.ontoggle = atualiza;
    el.querySelectorAll("input").forEach(i => { i.oninput = atualiza; });
    el.querySelector("[data-copiar]").onclick = async ev => {
      const b = ev.currentTarget;
      try { await navigator.clipboard.writeText(textoDoPrompt(p)); b.textContent = "Copiado!"; setTimeout(() => { b.textContent = "Copiar prompt"; }, 1600); }
      catch (_) { recado.textContent = "Não consegui copiar. Selecione o texto acima."; }
    };
    el.querySelector("[data-mandar]").onclick = ev => mandarPrompt(p, ev.currentTarget, recado);
  });
}
async function mandarPrompt(p, botao, recado) {
  const faltando = (p.perguntas || []).find(q => !valorPrompt(p.id, q.id));
  if (faltando) { recado.textContent = "Responda às perguntas acima primeiro."; document.querySelector(`.perso-prompt[data-id="${p.id}"] input[data-campo="${faltando.id}"]`)?.focus(); return; }
  if (enviando || anexando) { recado.textContent = "Espere o pedido atual sair e tente de novo."; return; }
  const motor = p.motor === "codex" ? "codex" : E?.motor_padrao || "claude";
  if (!E?.motores?.[motor]) { recado.textContent = `O ${motor === "codex" ? "Codex" : motor} não está instalado aqui. Copie o prompt e cole no ChatGPT.`; return; }
  botao.disabled = true;
  try {
    const sessao = await api("POST", "/api/sessao", {titulo: p.titulo.replaceAll("{{agente}}", AP.identidade.nome), motor});
    await carrega();
    tela("conversa");
    await abre(sessao.id);
    await enviar(textoDoPrompt(p));
  } catch (e) { recado.textContent = e.message; }
  finally { botao.disabled = false; }
}
async function carregaPrompts() {
  const r = await fetch("prompts-master.json");
  const lista = r.ok ? await r.json() : null;
  if (!Array.isArray(lista)) throw new Error("Não achei os prompts master.");
  return lista;
}
async function abrirPersonalizar() {
  try {
    await descarregar();
    AP = await api("GET", "/api/aparencia");
    mostraCores(); mostraImagens(); mostraTelas();
    aplicarTudo();
    // Nome e prompts só desenham uma vez: voltar a esta tela não apaga o que a pessoa digitou.
    if (!telaPronta) {
      mostraNome();
      PROMPTS = await carregaPrompts();
      mostraPrompts();
      telaPronta = true;
    }
    aviso("avisoPerso", "");
  } catch (e) { aviso("avisoPerso", e.message || "Não consegui abrir. Tenta de novo."); }
}
// O agente grava em aparencia/ e a mudança aparece sozinha, sem F5.
async function olharMudancas() {
  if (document.hidden || !AP) return;
  try {
    const novo = await api("GET", "/api/aparencia");
    if (Object.keys(pendente).length) return;
    const imagensMudaram = JSON.stringify(novo.imagens) !== JSON.stringify(AP.imagens);
    const ajustesMudaram = !$("personalizar").classList.contains("on") && JSON.stringify(novo.ajustes) !== JSON.stringify(AP.ajustes);
    const tinta = ajustesMudaram && (novo.ajustes.cor !== AP.ajustes.cor || novo.ajustes.tom !== AP.ajustes.tom);
    if (imagensMudaram) AP.imagens = novo.imagens;
    if (ajustesMudaram) AP.ajustes = novo.ajustes;
    if (imagensMudaram) recarregarImagens();
    if (ajustesMudaram) aplicarTudo();
    if (tinta) aplicarTinta();
  } catch (_) {}
}
async function iniciarAparencia() {
  try {
    AP = await api("GET", "/api/aparencia");
    nomeDaCasa = AP.identidade.nome;
    aplicarTudo(); vigiarNomes();
  } catch (_) { return; }
  document.querySelector('[data-t="personalizar"]')?.addEventListener("click", abrirPersonalizar);
  setInterval(olharMudancas, 5000);
  if (location.hash === "#personalizar") { history.replaceState(null, "", location.pathname); tela("personalizar"); abrirPersonalizar(); }
}
iniciarAparencia();
})();
