const TOKEN = "__TOKEN__";
const $ = id => document.getElementById(id);
const api = (m, r, c) => fetch(r, {method: m, headers: {"X-Token": TOKEN, "Content-Type": "application/json"}, body: c ? JSON.stringify(c) : undefined}).then(async x => { const d = await x.json(); if (x.ok === false) throw new Error(d.erro || "Não consegui concluir. Tenta de novo."); return d; });
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
let E, atual;
let consultandoWhats = false, avancando = false;
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
function digita(el, txt) { if (typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches) { el.textContent = txt; return; } el.innerHTML = ""; let i = 0; (function f() { el.innerHTML = esc(txt.slice(0, ++i)); if (i < txt.length) setTimeout(f, 22); })(); }
function bate(txt) { const p = $("palavra"); p.innerHTML = esc(txt); p.classList.remove("v"); void p.offsetWidth; p.classList.add("v"); }
function extra(id) {
  const x = $("extra"); x.innerHTML = "";
  if (id === "whatsapp") {
    x.innerHTML = '<p id="whatsappEstado" role="status">Preparando o WhatsApp…</p><img id="whatsappQr" class="whatsapp-qr" alt="QR para conectar seu WhatsApp" hidden>';
    api("POST", "/api/whatsapp/conectar", {}).catch(() => { if (atual === "whatsapp") $("whatsappEstado").textContent = "Não consegui conectar. Tenta de novo ou pula por enquanto."; });
  }
  if (id === "cerebros") x.innerHTML = `<a href="https://antigravity.google" target="_blank" rel="noopener noreferrer">Instalar o Antigravity</a><p>baixe, instale e volte aqui</p>`;
  if (id === "login") {
    x.innerHTML = '<p>Faça login na janela que abriu e volte aqui pra testar.</p>' + Object.entries(E.motores).map(([k, v]) => `<div class="loginMotor"><span class="dot ${v ? "on" : "off"}"></span> ${esc(k)} ${v ? `<button class="sec" data-entrar="${esc(k)}">Entrar</button> <button class="sec" data-testar="${esc(k)}">Testar</button><span class="resultado" aria-live="polite"></span>` : "não instalado"}</div>`).join("");
    x.querySelectorAll("[data-entrar],[data-testar]").forEach(b => b.onclick = async () => {
      const entrar = Boolean(b.dataset.entrar), nome = b.dataset.entrar || b.dataset.testar;
      const resultado = b.parentElement.querySelector(".resultado");
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
    if (!t && !E.conexoes.TELEGRAM_TOKEN) { log("Cole o token do bot primeiro.", "em"); return; }
    if (t) { await api("POST", "/api/conexao", {nome: "TELEGRAM_TOKEN", valor: t}); $("tok").value = ""; E.conexoes.TELEGRAM_TOKEN = true; }
    const r = await api("POST", "/api/telegram/codigo");
    $("codigo").innerHTML = `Mande /start ${esc(r.codigo)} para o seu bot`; $("vinc").disabled = false;
  };
  const v = $("vinc"); if (v) v.onclick = async () => {
    const r = await api("POST", "/api/telegram/vincular"); log(r.chat ? "Telegram ligado: achei você." : "Ainda não vi seu /start com o código. Manda e clica de novo.", r.chat ? "b" : "em");
    if (r.chat) { $("codigo").textContent = "Telegram ligado."; v.disabled = true; }
  };
}
function mostra() {
  const i = E.passos.findIndex(p => p.id === atual), p = E.passos[i];
  $("contador").textContent = `passo ${i + 1} de ${E.passos.length}`;
  $("trilha").innerHTML = E.passos.map((q, j) => `<i class="${["feito", "pulado"].includes(E.instalacao[q.id]) ? "f" : j === i ? "a" : ""}"></i>`).join("");
  $("titulo").innerHTML = esc(p.titulo) + '<span class="ponto">.</span>'; digita($("fala"), p.fala); extra(p.id); bate(p.titulo.split(" ").pop().toUpperCase());
  $("seguir").textContent = p.id === "pronto" ? "Abrir a Sheep" : p.id === "whatsapp" ? "Conectar" : "Bora"; $("tentar").hidden = true;
  $("pular").hidden = !["whatsapp", "telegram"].includes(atual);
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
  $("seguir").disabled = true; log(`→ ${atual}`);
  $("pular").disabled = true;
  try {
    const r = await api("POST", "/api/instalar", {passo: atual, ...(pular ? {pular: true} : {})}); r.log.forEach(l => log(l));
    if (!r.ok) { log(atual === "login" ? "Ainda não confirmei um login. Clique em Entrar, faça login e volte aqui pra testar." : "Esse passo falhou. Confere a internet e tenta de novo.", "em"); $("tentar").hidden = false; return; }
    log("feito ✓", "b");
    if (atual === "pronto") { location.href = "/app.html"; return; }
    E = await api("GET", "/api/estado"); atual = E.proximo; mostra();
  } catch (_) { log("Não consegui concluir. Tenta de novo.", "em"); $("tentar").hidden = false; }
  finally { avancando = false; $("seguir").disabled = false; $("pular").disabled = false; }
}
$("seguir").onclick = roda; $("tentar").onclick = roda;
$("pular").onclick = () => avancar(true);
setInterval(consultaWhatsInst, 1500);
(async () => { E = await api("GET", "/api/estado"); atual = E.proximo || "pronto"; mostra(); })();
