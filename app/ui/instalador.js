const TOKEN = "__TOKEN__";
const $ = id => document.getElementById(id);
const api = (m, r, c) => fetch(r, {method: m, headers: {"X-Token": TOKEN, "Content-Type": "application/json"}, body: c ? JSON.stringify(c) : undefined}).then(async x => { const d = await x.json(); if (x.ok === false) throw new Error(d.erro || "Não consegui concluir. Tenta de novo."); return d; });
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
let E, atual;
let consultandoWhats = false, avancando = false, relogio = null;
const ROTULOS = {boas_vindas: "Boas-vindas", verificar: "Seu computador", base: "As ferramentas", cerebros: "Os cérebros", login: "Entrar na sua IA", casa: "A casa da Sheep", whatsapp: "WhatsApp", telegram: "Telegram", pronto: "Tudo pronto"};
const FRASES = {
  verificar: ["Contando o espaço do disco…", "Testando a internet…"],
  base: ["Baixando as ferramentas…", "Arrumando o feno…", "Isso pode levar alguns minutos. Pega um café."],
  cerebros: ["Buscando o Claude…", "Buscando o Codex…", "Cérebro é pesado, tô carregando com jeito…"],
  casa: ["Levantando as paredes…", "Guardando as habilidades…", "Colocando meu nome na porta…"],
};
let som = true, audioLiberado = false, audioAtual;
try { som = localStorage.getItem("sheep-instalador-som") !== "0"; } catch (_) {}
function mostraSom() {
  $("som").textContent = som ? "🔊" : "🔇";
  $("som").setAttribute("aria-pressed", String(som));
  $("som").setAttribute("aria-label", som ? "Desligar narração" : "Ligar narração");
}
function paraFala() {
  if (audioAtual) audioAtual.pause();
  audioAtual = null;
  $("sheep")?.classList.remove("falando");
}
function narra() {
  paraFala();
  if (!som || !audioLiberado || !atual) return;
  try {
    const audio = audioAtual = new Audio(`voz/passos/${encodeURIComponent(atual)}.mp3`);
    audio.onplaying = () => { if (audioAtual === audio) $("sheep")?.classList.add("falando"); };
    audio.onended = audio.onpause = audio.onerror = () => { if (audioAtual === audio) $("sheep")?.classList.remove("falando"); };
    audio.play().catch(() => { if (audioAtual === audio) paraFala(); });
  } catch (_) { paraFala(); }
}
document.onclick = () => { if (!audioLiberado) { audioLiberado = true; narra(); } };
$("som").onclick = () => {
  som = !som; audioLiberado = true;
  try { localStorage.setItem("sheep-instalador-som", som ? "1" : "0"); } catch (_) {}
  mostraSom(); narra();
};
mostraSom();
function log(t, cls) { const d = document.createElement("div"); d.innerHTML = cls ? `<${cls}>${esc(t)}</${cls}>` : esc(t); $("log").append(d); $("log").scrollTop = 1e9; }
function alerta(t) { $("alertaTexto").textContent = t || ""; $("alerta").classList.toggle("on", Boolean(t)); }
function trabalhando(ligado) {
  clearInterval(relogio);
  $("status").classList.toggle("on", ligado);
  if (!ligado) return;
  const frases = FRASES[atual] || ["Só um instante…"];
  let n = 0;
  $("statusTexto").textContent = frases[0];
  relogio = setInterval(() => { $("statusTexto").textContent = frases[++n % frases.length]; }, 4000);
}
function etapas(situacao) {
  const i = E.passos.findIndex(p => p.id === atual), feitos = E.passos.filter(q => ["feito", "pulado"].includes(E.instalacao[q.id])).length, pct = Math.round(feitos / E.passos.length * 100);
  $("contador").textContent = `Passo ${i + 1} de ${E.passos.length}`;
  $("porcento").textContent = `${pct}%`;
  $("barra").style.width = `${pct}%`;
  $("trilha").innerHTML = E.passos.map((q, j) => {
    const marcado = E.instalacao[q.id], classe = marcado === "feito" ? "feito" : marcado === "pulado" ? "pulado" : j === i ? situacao : "";
    const icone = {feito: "✓", pulado: "–", falhou: "!"}[classe] || j + 1;
    return `<li class="${classe}"${j === i ? ' aria-current="step"' : ""}><span>${icone}</span>${esc(ROTULOS[q.id] || q.titulo)}</li>`;
  }).join("");
}
function digita(el, txt) { if (typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches) { el.textContent = txt; return; } el.innerHTML = ""; let i = 0; (function f() { el.innerHTML = esc(txt.slice(0, ++i)); if (i < txt.length) setTimeout(f, 22); })(); }
function bate(txt) { const p = $("palavra"); p.innerHTML = esc(txt); p.classList.remove("v"); void p.offsetWidth; p.classList.add("v"); }
function extra(id) {
  const x = $("extra"); x.innerHTML = "";
  if (id === "whatsapp") {
    x.innerHTML = '<p id="whatsappEstado" role="status">Preparando o WhatsApp…</p><img id="whatsappQr" class="whatsapp-qr" alt="QR para conectar seu WhatsApp" hidden>';
    api("POST", "/api/whatsapp/conectar", {}).catch(() => { if (atual === "whatsapp") $("whatsappEstado").textContent = "Não consegui conectar. Tenta de novo ou pula por enquanto."; });
  }
  if (id === "cerebros") x.innerHTML = `<p class="nota">Opcional: quer o Antigravity também? <a href="https://antigravity.google" target="_blank" rel="noopener noreferrer">Baixar aqui</a>. Pode deixar pra depois.</p>`;
  if (id === "login") {
    const NOMES = {claude: "Claude", codex: "ChatGPT (Codex)", antigravity: "Antigravity (Google)"};
    x.innerHTML = '<p class="nota">Clique em <b>Entrar</b> na IA que você assina. Quem assina o ChatGPT entra pelo Codex. Depois clique em <b>Já entrei, testar</b>.</p>' + Object.entries(E.motores).map(([k, v]) => `<div class="loginMotor"><span class="dot ${v ? "on" : "off"}"></span> ${esc(NOMES[k] || k)} ${v ? `<span class="acoesMotor"><button class="sec" data-entrar="${esc(k)}">Entrar</button><button class="sec" data-testar="${esc(k)}">Já entrei, testar</button></span><span class="resultado" aria-live="polite"></span>` : "<small>não instalado</small>"}</div>`).join("");
    x.querySelectorAll("[data-entrar],[data-testar]").forEach(b => b.onclick = async () => {
      const entrar = Boolean(b.dataset.entrar), nome = b.dataset.entrar || b.dataset.testar;
      const resultado = b.closest(".loginMotor").querySelector(".resultado");
      b.disabled = true; resultado.textContent = entrar ? "Abrindo…" : "Testando…";
      try {
        const r = await api("POST", entrar ? "/api/motor/entrar" : "/api/motor/testar", {nome});
        resultado.innerHTML = r.ok ? (entrar ? "Faça login na janela que abriu e volte aqui pra testar." : "Login confirmado ✓") : esc(r.erro || "Não consegui confirmar. Entre e teste de novo.");
      } catch (_) { resultado.textContent = "Não consegui concluir. Tenta de novo."; }
      finally { b.disabled = false; }
    });
  }
  if (id === "telegram") x.innerHTML = `<p class="rot">1. No Telegram, fale com @BotFather → /newbot · 2. Cole o token · 3. Gere o código</p><input id="tok" type="password" placeholder="cole o token do bot aqui" autocomplete="off"><button class="sec" id="gerar">Gerar código</button><p id="codigo" aria-live="polite"></p><button class="sec" id="vinc" disabled>Já mandei /start com o código</button>`;
  const g = $("gerar"); if (g) g.onclick = async () => {
    const t = $("tok").value.trim();
    if (!t && !E.conexoes.TELEGRAM_TOKEN) { alerta("Cole o token do bot primeiro."); return; }
    if (t) { await api("POST", "/api/conexao", {nome: "TELEGRAM_TOKEN", valor: t}); $("tok").value = ""; E.conexoes.TELEGRAM_TOKEN = true; }
    const r = await api("POST", "/api/telegram/codigo");
    $("codigo").innerHTML = `Mande /start ${esc(r.codigo)} para o seu bot`; $("vinc").disabled = false;
  };
  const v = $("vinc"); if (v) v.onclick = async () => {
    const r = await api("POST", "/api/telegram/vincular"); alerta(r.chat ? "" : "Ainda não vi seu /start com o código. Manda e clica de novo.");
    if (r.chat) { $("codigo").textContent = "Telegram ligado."; v.disabled = true; }
  };
}
function textoSeguir() { return atual === "pronto" ? "Abrir a Sheep" : atual === "whatsapp" ? "Conectar" : atual === "login" ? "Já entrei" : "Bora"; }
function mostra() {
  const p = E.passos.find(q => q.id === atual);
  etapas("agora"); alerta(""); trabalhando(false);
  $("titulo").innerHTML = esc(p.titulo) + '<span class="ponto">.</span>'; digita($("fala"), p.fala); extra(p.id); bate(p.titulo.split(" ").pop().toUpperCase());
  $("seguir").textContent = textoSeguir(); $("seguir").hidden = false; $("tentar").hidden = true;
  $("pular").hidden = !["login", "whatsapp", "telegram"].includes(atual);
  $("pular").textContent = "Pular por enquanto";
  narra();
}
async function consultaWhatsInst() {
  if (atual !== "whatsapp" || consultandoWhats || avancando) return;
  consultandoWhats = true;
  try {
    const w = await api("GET", "/api/whatsapp/estado");
    if (atual !== "whatsapp" || avancando) return;
    const nomes = {instalando: "Preparando o WhatsApp (1ª vez leva 1–2 min)…", qr: "Lê o QR com seu celular.", conectando: "Conectando…", conectado: "WhatsApp ligado.", desconectado: "Clica em Conectar ou pula por enquanto."};
    $("whatsappEstado").textContent = w.mensagem || nomes[w.estado] || "Não consegui conectar. Tenta de novo ou pula por enquanto.";
    const qr = $("whatsappQr");
    qr.hidden = !(typeof w.qr === "string" && /^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(w.qr));
    if (!qr.hidden) qr.src = w.qr;
    if (w.estado === "conectado") await avancar();
  } catch (_) { if (atual === "whatsapp") $("whatsappEstado").textContent = "Não consegui consultar. Já tento de novo."; }
  finally { consultandoWhats = false; }
}
async function roda() {
  if (atual !== "whatsapp") return avancar();
  $("seguir").disabled = true;
  try { await api("POST", "/api/whatsapp/conectar", {}); await consultaWhatsInst(); }
  catch (_) { $("whatsappEstado").textContent = "Não consegui conectar. Tenta de novo ou pula por enquanto."; }
  finally { $("seguir").disabled = false; }
}
async function avancar(pular = false) {
  if (avancando) return;
  avancando = true;
  $("seguir").disabled = true; $("seguir").hidden = false; $("seguir").textContent = "Trabalhando…"; $("tentar").hidden = true;
  $("pular").disabled = true; alerta(""); trabalhando(true); etapas("rodando");
  log(ROTULOS[atual] || atual);
  try {
    const r = await api("POST", "/api/instalar", {passo: atual, ...(pular ? {pular: true} : {})}); r.log.forEach(l => log(l));
    if (!r.ok) { falhou(atual === "login" ? "Ainda não confirmei um login. Clique em Entrar, faça login e volte aqui pra testar." : "Esse passo não deu certo. Confere a internet e tenta de novo."); return; }
    log("pronto", "b");
    if (atual === "pronto") { location.href = "/app.html"; return; }
    E = await api("GET", "/api/estado"); atual = E.proximo; mostra();
  } catch (_) { falhou("Não consegui concluir. Tenta de novo."); }
  finally { avancando = false; $("seguir").disabled = false; $("pular").disabled = false; }
}
function falhou(texto) {
  trabalhando(false); etapas("falhou"); alerta(texto); log(texto, "em");
  if (atual === "login") { $("seguir").textContent = textoSeguir(); return; }
  $("seguir").hidden = true; $("tentar").hidden = false;
}
$("seguir").onclick = roda; $("tentar").onclick = roda;
$("pular").onclick = () => avancar(true);
setInterval(consultaWhatsInst, 1500);
(async () => { E = await api("GET", "/api/estado"); atual = E.proximo || "pronto"; mostra(); })();
