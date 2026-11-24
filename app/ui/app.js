/* Interface do launcher. JS puro, sem framework.
   Regra de segurança: textos do catálogo (vêm do Drive) entram sempre via DOM/textContent, nunca innerHTML. */
"use strict";

// ---------- utilidades ----------

const $ = (sel) => document.querySelector(sel);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Cria um elemento. props: class, on<evento>, e qualquer atributo. Filhos: texto ou nós. */
function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : String(kid));
  return el;
}

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const fmtMB = (bytes) => (bytes / 1e6).toFixed(1).replace(".", ",");

/** Cor estável por título, para o espaço reservado de capas que ainda não chegaram. */
function hue(text) {
  let n = 0;
  for (const ch of text) n = (n * 31 + ch.codePointAt(0)) % 360;
  return n;
}

// Silhueta de um portátil, usada quando o emulador não tem ícone no catálogo (constante, sem dados externos).
const GLYPH = `<svg viewBox="0 0 120 72" fill="none" stroke="currentColor" stroke-width="3.5"
  stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <rect x="3" y="4" width="114" height="64" rx="16"/>
  <rect x="31" y="15" width="58" height="40" rx="5"/>
  <path d="M16 29v14M9 36h14"/>
  <circle cx="104" cy="31" r="4.5"/><circle cx="95" cy="42" r="4.5"/>
</svg>`;

function glyphNode(iconUrl) {
  const box = h("div", { class: "glyph" });
  if (iconUrl) box.append(h("img", { src: iconUrl, alt: "" }));
  else box.innerHTML = GLYPH;
  return box;
}

// ---------- ponte com o Python (pywebview) ----------

const api = () => window.pywebview.api;

function whenReady() {
  return new Promise((resolve) => {
    if (window.pywebview && window.pywebview.api) return resolve();
    window.addEventListener("pywebviewready", resolve, { once: true });
    // Modo de desenvolvimento: ?mock simula o Python para eu poder ver as telas sem abrir o app.
    if (new URLSearchParams(location.search).has("mock")) {
      const s = h("script", { src: "dev/mock-api.js" });
      s.onload = resolve;
      document.head.append(s);
    }
  });
}

// ---------- estado ----------

let lib = null;                 // resposta de get_library()
let route = { view: "home", emuId: null };
const jobs = new Map();         // game_id -> estado do download em andamento
const errors = new Map();       // game_id -> mensagem do último erro
const running = new Set();      // jogos abertos agora no emulador
const tiles = new Map();        // game_id -> elementos do cartão na tela atual

const findEmu = (id) => lib && lib.emulators.find((e) => e.id === id);

async function loadLibrary() {
  lib = await api().get_library();
}

// ---------- capas (carregadas aos poucos, 3 por vez) ----------

let coverCache = new Map();
const coverQueue = [];
let coverActive = 0;

function loadCover(gameId) {
  if (!coverCache.has(gameId)) {
    coverCache.set(gameId, new Promise((resolve) => { coverQueue.push({ gameId, resolve }); pumpCovers(); }));
  }
  return coverCache.get(gameId);
}

function pumpCovers() {
  while (coverActive < 3 && coverQueue.length) {
    const { gameId, resolve } = coverQueue.shift();
    coverActive++;
    api().get_cover(gameId)
      .then((url) => resolve(url || null))
      .catch(() => resolve(null))
      .finally(() => { coverActive--; pumpCovers(); });
  }
}

// ---------- avisos ----------

function toast(message, kind = "error") {
  const el = h("div", { class: `toast ${kind === "ok" ? "ok" : ""}` }, message);
  $("#toasts").append(el);
  setTimeout(() => el.remove(), 5500);
}

// ---------- navegação ----------

function go(view, emuId = null) {
  route = { view, emuId };
  render();
  $("#view").focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

function render() {
  tiles.clear();
  const view = $("#view");
  $("#back").hidden = route.view === "home";
  $("#brand").hidden = route.view !== "home";

  if (!lib || lib.error) return view.replaceChildren(renderCatalogError());
  const emu = route.view === "emulator" && findEmu(route.emuId);
  if (route.view === "emulator" && !emu) route = { view: "home", emuId: null };
  view.replaceChildren(emu ? renderEmulator(emu) : renderHome());
}

function renderCatalogError() {
  return h("section", {},
    h("h1", {}, "Sem catálogo"),
    h("p", { class: "empty" }, (lib && lib.error) || "Não consegui carregar o catálogo."),
    h("button", { class: "btn btn-get", onclick: onRefresh }, "Atualizar catálogo"));
}

// ---------- tela inicial ----------

function renderHome() {
  const section = h("section", { class: "home" }, h("h1", {}, "Seus emuladores"));
  if (!lib.emulators.length) {
    section.append(h("p", { class: "empty" },
      "O catálogo ainda não tem emuladores. Adicione um no catalog.json do Drive e use Atualizar catálogo."));
    return section;
  }
  const grid = h("div", { class: "emu-grid" });
  for (const emu of lib.emulators) grid.append(emuPanel(emu));
  section.append(grid);
  return section;
}

function emuPanel(emu) {
  const glyph = glyphNode(null);
  api().get_emulator_icon(emu.id).then((url) => { if (url) glyph.replaceWith(glyphNode(url)); }).catch(() => {});

  const fan = h("div", { class: "fan", "aria-hidden": "true" });
  emu.games.slice(0, 3).forEach((g, i) => {
    loadCover(g.id).then((url) => {
      if (url) fan.append(h("img", { src: url, alt: "", style: `--r:${(i - 1) * 7}deg` }));
    });
  });

  const ready = emu.games.filter((g) => g.has_rom && emu.installed).length;
  return h("button", { class: "emu-panel", onclick: () => go("emulator", emu.id) },
    glyph,
    h("div", {},
      h("h2", {}, emu.name),
      h("p", {}, emu.platform),
      h("p", { class: `state ${emu.installed ? "" : "off"}` },
        `${plural(emu.games.length, "jogo", "jogos")}, ${plural(ready, "pronto", "prontos")}`)),
    fan);
}

// ---------- tela de um emulador ----------

function renderEmulator(emu) {
  const ready = emu.games.filter((g) => g.has_rom && emu.installed).length;
  const head = h("header", {},
    h("div", { class: "shelf-head" },
      glyphNode(null),
      h("div", {},
        h("h1", {}, emu.name),
        h("p", { class: "sub-head" },
          `${emu.platform}: ${plural(emu.games.length, "jogo", "jogos")}, ${plural(ready, "pronto", "prontos")}`))));
  api().get_emulator_icon(emu.id).then((url) => {
    if (url) head.querySelector(".glyph").replaceWith(glyphNode(url));
  }).catch(() => {});
  if (!emu.installed) {
    head.firstChild.lastChild.append(h("p", { class: "hint" }, `O ${emu.name} é baixado junto com o primeiro jogo.`));
  }

  const section = h("section", {}, head);
  if (!emu.games.length) {
    section.append(h("p", { class: "empty" },
      `Nenhum jogo para ${emu.name} ainda. Suba a ROM no Drive, adicione no catalog.json e use Atualizar catálogo.`));
    return section;
  }
  const grid = h("div", { class: "games" });
  emu.games.forEach((g, i) => grid.append(buildTile(emu, g, i)));
  section.append(grid);
  return section;
}

function buildTile(emu, game, index) {
  const art = h("img", { alt: "", draggable: "false", hidden: true });
  const glow = h("img", { class: "glow", alt: "", "aria-hidden": "true", hidden: true });
  const placeholder = h("div", { class: "placeholder", style: `--hue:${hue(game.title)}` }, game.title);
  const zone = h("div", { class: "action-zone" });

  const root = h("article", { class: "game", style: `--i:${Math.min(index, 14)}` },
    h("div", { class: "cover-wrap" }, glow, h("div", { class: "cover" }, placeholder, art)),
    h("div", { class: "meta" },
      h("h3", { class: "title" }, game.title),
      game.subtitle && h("p", { class: "sub" }, game.subtitle)),
    zone);

  tiles.set(game.id, { root, zone, emuId: emu.id, shown: null });
  loadCover(game.id).then((url) => {
    if (!url) return;
    art.src = glow.src = url;
    art.hidden = glow.hidden = false;
    placeholder.hidden = true;
  });
  paint(game.id);
  return root;
}

/** Atualiza um cartão conforme o estado: missing (Baixar), downloading, ready (Jogar) ou error. */
function paint(gameId) {
  const t = tiles.get(gameId);
  const emu = t && findEmu(t.emuId);
  const game = emu && emu.games.find((g) => g.id === gameId);
  if (!game) return;

  const job = jobs.get(gameId);
  const ready = emu.installed && game.has_rom;
  const state = job ? "downloading" : running.has(gameId) ? "playing" : errors.has(gameId) ? "error" : ready ? "ready" : "missing";

  t.root.dataset.state = state;
  // a capa "acorda" junto com o download
  t.root.style.setProperty("--wake", job ? Math.max(0.05, job.fraction) : ready ? 1 : 0);

  if (t.shown !== state) {
    t.zone.replaceChildren(...zoneFor(state, t, emu, game));
    t.shown = state;
  }
  if (state === "downloading") updateProgress(t, emu, job);
}

function zoneFor(state, t, emu, game) {
  if (state === "ready") {
    return [h("button", { class: "btn btn-play", "aria-label": `Jogar ${game.title}`, onclick: () => onPlay(game.id) }, "Jogar")];
  }
  if (state === "playing") {
    return [h("button", { class: "btn btn-playing", disabled: true }, "Jogando"),
      h("p", { class: "detail" }, "Ao fechar o emulador, o botão volta.")];
  }
  if (state === "downloading") {
    t.bar = h("div", { class: "bar", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100",
      "aria-label": `Baixando ${game.title}` }, h("i"));
    t.stageEl = h("span");
    t.pctEl = h("span", { class: "pct" });
    t.detailEl = h("div", { class: "detail" });
    return [t.bar, h("div", { class: "progress-row" }, t.stageEl, t.pctEl), t.detailEl,
      h("button", { class: "cancel", onclick: () => api().cancel_download(game.id) }, "Cancelar")];
  }
  const label = state === "error" ? "Tentar de novo" : "Baixar";
  const out = [h("button", { class: "btn btn-get", "aria-label": `${label}: ${game.title}`, onclick: () => onDownload(game.id) }, label)];
  if (state === "error") out.push(h("p", { class: "error", title: errors.get(game.id) }, errors.get(game.id)));
  return out;
}

const STAGE_TEXT = {
  preparando: () => "Preparando",
  aguardando: (emu) => `Aguardando o ${emu.name}`,
  emulador: (emu) => `Baixando o ${emu.name}`,
  extraindo: (emu) => `Instalando o ${emu.name}`,
  rom: () => "Baixando o jogo",
};

function updateProgress(t, emu, job) {
  const pct = Math.round(job.fraction * 100);
  t.bar.firstChild.style.setProperty("--p", job.fraction);
  t.bar.setAttribute("aria-valuenow", pct);
  t.stageEl.textContent = (STAGE_TEXT[job.stage] || STAGE_TEXT.preparando)(emu);
  t.pctEl.textContent = `${pct}%`;
  t.detailEl.textContent = job.total ? `${fmtMB(job.done)} de ${fmtMB(job.total)} MB` : "";
}

// ---------- ações ----------

async function onDownload(gameId) {
  errors.delete(gameId);
  jobs.set(gameId, { stage: "preparando", fraction: 0, done: 0, total: null, pending: true });
  paint(gameId);
  const res = await api().start_download(gameId);
  if (res.error) {
    jobs.delete(gameId);
    errors.set(gameId, res.error);
    return paint(gameId);
  }
  jobs.get(gameId).pending = false;  // o Python já conhece este download
  poll();
}

let polling = false;

/** Pergunta ao Python, a cada 350 ms, como estão os downloads (para quando não há mais nenhum). */
async function poll() {
  if (polling) return;
  polling = true;
  try {
    while (jobs.size || running.size) {
      const [snapshot, play] = await Promise.all([api().get_jobs(), api().get_running()]);
      for (const id of [...running]) if (!play.running.includes(id)) running.delete(id);  // emulador fechou
      for (const [id, message] of Object.entries(play.errors)) toast(message);
      let reloadLibrary = false;
      for (const id of [...jobs.keys()]) {
        const mine = jobs.get(id);
        const server = snapshot[id];
        if (!server) {
          if (!mine.pending) { jobs.delete(id); reloadLibrary = true; }  // sumiu do Python: confere o disco
          continue;
        }
        if (server.finished) {
          jobs.delete(id);
          if (server.error) errors.set(id, server.error);
          else reloadLibrary = true;  // terminou (ou foi cancelado): relê o que existe no disco
          continue;
        }
        Object.assign(mine, server);
      }
      if (reloadLibrary) await loadLibrary();
      for (const id of tiles.keys()) paint(id);  // um download pode ter instalado o emulador para os outros jogos
      await sleep(350);
    }
  } catch (err) {
    toast("Perdi a conexão com o app. Feche e abra de novo.");
    jobs.clear();
  } finally {
    polling = false;
  }
}

async function onPlay(gameId) {
  const res = await api().play(gameId);
  if (res && res.error) return toast(res.error);
  running.add(gameId);
  paint(gameId);
  poll();  // acompanha até o emulador fechar
}

async function onRefresh() {
  const btn = $("#refresh");
  btn.disabled = true;
  btn.textContent = "Atualizando…";
  try {
    const res = await api().refresh_catalog();
    if (res.error) return toast(res.error);
    coverCache = new Map();
    await loadLibrary();
    render();
    toast("Catálogo atualizado.", "ok");
  } catch (err) {
    toast("Não consegui atualizar o catálogo.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Atualizar catálogo";
  }
}

// ---------- início ----------

$("#back").addEventListener("click", () => go("home"));
$("#refresh").addEventListener("click", onRefresh);
document.addEventListener("keydown", (e) => {
  if ((e.key === "Escape" || e.key === "Backspace") && route.view !== "home") go("home");
});

(async function init() {
  await whenReady();
  await loadLibrary();
  const params = new URLSearchParams(location.search);   // só usado pelo modo de desenvolvimento
  if (params.get("emu") && findEmu(params.get("emu"))) route = { view: "emulator", emuId: params.get("emu") };
  if (window.__mockJobs) window.__mockJobs(jobs);  // idem: simula um download em andamento
  render();
})();
