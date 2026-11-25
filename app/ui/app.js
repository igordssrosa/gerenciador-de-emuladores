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
const fmtKB = (bytes) => `${Math.max(1, Math.round(bytes / 1024))} KB`;
const fmtDate = (seconds) => new Date(seconds * 1000).toLocaleString("pt-BR",
  { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });

/** "há 5 h", "ontem", "há 3 dias": tempo relativo para a linha do tempo de backups. */
function fmtAgo(seconds) {
  const diff = Math.max(0, Date.now() / 1000 - seconds);
  const min = Math.floor(diff / 60), hr = Math.floor(diff / 3600), day = Math.floor(diff / 86400);
  if (min < 1) return "agora há pouco";
  if (hr < 1) return `há ${min} min`;
  if (day < 1) return `há ${hr} h`;
  return day === 1 ? "ontem" : `há ${day} dias`;
}

/** Cor estável por título, para o espaço reservado de capas que ainda não chegaram. */
function hue(text) {
  let n = 0;
  for (const ch of text) n = (n * 31 + ch.codePointAt(0)) % 360;
  return n;
}

// Silhueta de um portátil, usada quando o emulador não tem ícone no catálogo (constante, sem dados externos).
// Traço fino (non-scaling-stroke mantém a espessura igual em qualquer tamanho).
const GLYPH = `<svg viewBox="0 0 48 32" fill="none" stroke="currentColor" stroke-width="1.5"
  stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <rect x="2" y="3" width="44" height="26" rx="9" vector-effect="non-scaling-stroke"/>
  <path d="M14 11v10M9 16h10" vector-effect="non-scaling-stroke"/>
  <circle cx="33" cy="13.5" r="2" vector-effect="non-scaling-stroke"/>
  <circle cx="38" cy="19" r="2" vector-effect="non-scaling-stroke"/>
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
let route = { view: "home", emuId: null, gameId: null };
let savesData = null;           // resposta de get_saves() do jogo aberto na tela de saves
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
      .then((url) => {
        if (!url) coverCache.delete(gameId);   // falhou: deixa tentar de novo na próxima vez
        resolve(url || null);
      })
      .catch(() => { coverCache.delete(gameId); resolve(null); })
      .finally(() => { coverActive--; pumpCovers(); });
  }
}

// ---------- avisos ----------

function toast(message, kind = "error") {
  const el = h("div", { class: kind === "error" ? "toast" : `toast ${kind}` }, message);
  $("#toasts").append(el);
  setTimeout(() => el.remove(), 5500);
}

// ---------- navegação ----------

async function go(view, emuId = null, gameId = null) {
  // ao entrar em outro emulador, os filtros da biblioteca voltam ao padrão
  if (view === "emulator" && route.emuId !== emuId) { filters.status = "all"; filters.query = ""; }
  route = { view, emuId, gameId };
  if (view === "saves") await loadSaves();
  render();
  $("#view").focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

/** Voltar um nível: saves -> jogos do emulador -> início. */
function goBack() {
  if (route.view === "saves") go("emulator", route.emuId);
  else if (route.view === "emulator") go("home");
}

async function loadSaves() {
  const res = await api().get_saves(route.gameId);
  if (res.error) {
    toast(res.error);
    savesData = null;
    route = { view: "emulator", emuId: route.emuId, gameId: null };
    return;
  }
  savesData = res;
}

/** Relê os saves e redesenha, se a tela de saves ainda estiver aberta. */
async function reloadSaves() {
  if (route.view !== "saves") return;
  await loadSaves();
  // o Python sabe se o jogo está aberto (por exemplo, depois de "Carregar e jogar")
  if (savesData && savesData.running && !running.has(route.gameId)) { running.add(route.gameId); poll(); }
  render();
}

function render() {
  tiles.clear();
  const view = $("#view");
  const emu = route.view !== "home" && lib && !lib.error && findEmu(route.emuId);
  if (lib && !lib.error) {
    if (route.view !== "home" && !emu) route = { view: "home", emuId: null, gameId: null };
    if (route.view === "saves" && !savesData) route = { view: "emulator", emuId: route.emuId, gameId: null };
  }
  renderChrome(route.view === "home" ? null : emu);
  if (!lib || lib.error) return view.replaceChildren(renderCatalogError());
  view.replaceChildren(route.view === "saves" ? renderSaves(emu)
    : route.view === "emulator" ? renderEmulator(emu) : renderHome());
}

/** Menu lateral (emuladores) e trilha de navegação no alto. */
const emuIcons = new Map();   // emulador -> url do ícone próprio (ou null), para não pedir de novo

function renderChrome(emu) {
  const emus = (lib && !lib.error && lib.emulators) || [];
  $("#nav-home").setAttribute("aria-current", route.view === "home" ? "page" : "false");
  $("#nav-emus").replaceChildren(...emus.map((e) => {
    if (!emuIcons.has(e.id)) {
      emuIcons.set(e.id, null);
      api().get_emulator_icon(e.id).then((url) => { if (url) { emuIcons.set(e.id, url); renderChrome(emu); } }).catch(() => {});
    }
    return h("button", { class: "nav-item", type: "button", title: e.name,
      "aria-current": route.view !== "home" && route.emuId === e.id ? "page" : "false", onclick: () => go("emulator", e.id) },
      glyphNode(emuIcons.get(e.id)), h("span", { class: "nav-label" }, e.name), h("span", { class: "nav-count" }, String(e.games.length)));
  }));

  const sep = () => h("span", { class: "sep", "aria-hidden": "true" }, "/");
  const now = (text) => h("span", { class: "crumb now", "aria-current": "page" }, text);
  const link = (text, onclick) => h("button", { class: "crumb", type: "button", onclick }, text);
  const parts = [route.view === "home" ? now("Início") : link("Início", () => go("home"))];
  if (emu) {
    parts.push(sep(), route.view === "emulator" ? now(emu.name) : link(emu.name, () => go("emulator", emu.id)));
    if (route.view === "saves" && savesData) parts.push(sep(), now(savesData.game.title));
  }
  $("#crumbs").replaceChildren(...parts);
}

function renderCatalogError() {
  return h("section", {},
    h("h1", {}, "Sem catálogo"),
    h("p", { class: "empty" }, (lib && lib.error) || "Não consegui carregar o catálogo."),
    h("button", { class: "btn btn-get", onclick: onRefresh }, "Atualizar catálogo"));
}

// ---------- preferências simples (guardadas neste computador) ----------

function loadPref(key, fallback) {
  try { return localStorage.getItem(key) || fallback; } catch (e) { return fallback; }
}
function savePref(key, value) {
  try { localStorage.setItem(key, value); } catch (e) { /* sem armazenamento: vale só nesta sessão */ }
}

/** Ícone fixo (SVG do próprio código, sem dados externos). */
function icon(svg) {
  const el = h("span", { class: "icon", "aria-hidden": "true" });
  el.innerHTML = svg;
  return el;
}
const svgWrap = (path) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${path}</svg>`;
const ICON_GRID = svgWrap('<rect x="4" y="4" width="6.5" height="6.5" rx="1.2"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.2"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.2"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.2"/>');
const ICON_LIST = svgWrap('<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1"/><circle cx="4.5" cy="12" r="1"/><circle cx="4.5" cy="18" r="1"/>');

const pageHead = (title, sub) => h("header", { class: "page-head" },
  h("div", {}, h("h1", {}, title), sub && h("p", { class: "sub-head" }, sub)));

// ---------- início: resumo e um bloco por emulador ----------

function renderHome() {
  const section = h("section", { class: "home" }, pageHead("Início", "Seus emuladores e jogos."));
  if (!lib.emulators.length) {
    section.append(h("p", { class: "empty" },
      "O catálogo ainda não tem emuladores. Adicione um no catalog.json do Drive e use Atualizar catálogo."));
    return section;
  }
  const total = lib.emulators.reduce((n, e) => n + e.games.length, 0);
  const ready = lib.emulators.reduce((n, e) => n + e.games.filter((g) => e.installed && g.has_rom).length, 0);
  const stat = (n, label) => h("div", { class: "block stat" }, h("strong", {}, String(n)), h("span", {}, label));
  section.append(
    h("div", { class: "stats" }, stat(lib.emulators.length, "Emuladores"), stat(total, "Jogos no catálogo"), stat(ready, "Prontos para jogar")),
    h("h2", { class: "section-title" }, "Seus emuladores"),
    h("div", { class: "emu-grid" }, ...lib.emulators.map(emuCard)));
  return section;
}

function emuCard(emu) {
  const strip = h("div", { class: "strip", "aria-hidden": "true" });
  emu.games.slice(0, 4).forEach((g) => {
    const ph = h("div", { class: "mini ph", style: `--hue:${hue(g.title)}` }, g.title);
    strip.append(ph);
    loadCover(g.id).then((url) => { if (url) ph.replaceWith(h("img", { class: "mini", src: url, alt: "" })); });
  });
  const ready = emu.games.filter((g) => g.has_rom && emu.installed).length;
  return h("article", { class: "block emu-card" },
    h("div", { class: "emu-head" }, glyphNode(emuIcons.get(emu.id)),
      h("div", {}, h("h3", {}, emu.name), h("p", { class: "muted" }, emu.platform))),
    strip,
    h("div", { class: "emu-foot" },
      h("p", { class: "muted" }, `${plural(emu.games.length, "jogo", "jogos")}, ${plural(ready, "pronto", "prontos")}`),
      h("button", { class: "btn btn-play", type: "button", "aria-label": `Abrir ${emu.name}`, onclick: () => go("emulator", emu.id) }, "Abrir")));
}

// ---------- biblioteca de um emulador: blocos ou lista ----------

const filters = { status: "all", query: "" };   // valem enquanto você está neste emulador
let libView = loadPref("libview", "blocks");    // "blocks" ou "list"

const normalize = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

function renderEmulator(emu) {
  const isReady = (g) => emu.installed && g.has_rom;
  const ready = emu.games.filter(isReady).length;
  const section = h("section", { class: "emulator" },
    pageHead(emu.name, `${emu.platform}: ${plural(emu.games.length, "jogo", "jogos")}, ${plural(ready, "pronto", "prontos")}`));
  if (!emu.installed) section.append(h("p", { class: "hint" }, `O ${emu.name} é baixado junto com o primeiro jogo.`));
  if (!emu.games.length) {
    section.append(h("p", { class: "empty" },
      `Nenhum jogo para ${emu.name} ainda. Suba a ROM no Drive, adicione no catalog.json e use Atualizar catálogo.`));
    return section;
  }

  const host = h("div", { class: "games-host" });
  const refresh = () => { syncToolbar(); tiles.clear(); host.replaceChildren(buildGames(emu, isReady)); };

  // filtros por estado, com contagem
  const count = (key) => key === "all" ? emu.games.length : emu.games.filter((g) => (key === "ready") === isReady(g)).length;
  const tabs = [["all", "Todos"], ["ready", "Prontos"], ["missing", "Não baixados"]].map(([key, label]) => {
    const el = h("button", { class: "tab", type: "button", onclick: () => { filters.status = key; refresh(); } },
      label, h("span", { class: "tab-count" }, String(count(key))));
    el.dataset.key = key;
    return el;
  });
  const search = h("input", { class: "search", type: "search", placeholder: "Buscar jogo", "aria-label": "Buscar jogo",
    value: filters.query, oninput: (e) => { filters.query = e.target.value; refresh(); } });
  // alternador blocos / lista
  const segs = [["blocks", "Ver em blocos", ICON_GRID], ["list", "Ver em lista", ICON_LIST]].map(([mode, label, svg]) => {
    const el = h("button", { class: "seg", type: "button", title: label, "aria-label": label,
      onclick: () => { libView = mode; savePref("libview", mode); refresh(); } }, icon(svg));
    el.dataset.mode = mode;
    return el;
  });
  function syncToolbar() {
    tabs.forEach((el) => el.setAttribute("aria-pressed", String(el.dataset.key === filters.status)));
    segs.forEach((el) => el.setAttribute("aria-pressed", String(el.dataset.mode === libView)));
  }

  section.append(
    h("div", { class: "toolbar" }, h("div", { class: "tabs", role: "group", "aria-label": "Filtrar jogos" }, ...tabs),
      search, h("div", { class: "seg-group", role: "group", "aria-label": "Modo de exibição" }, ...segs)),
    host);
  refresh();
  return section;
}

/** Monta os jogos que passam pelo filtro e pela busca, em blocos ou lista. */
function buildGames(emu, isReady) {
  const q = normalize(filters.query.trim());
  const list = emu.games.filter((g) =>
    (filters.status === "all" || (filters.status === "ready") === isReady(g))
    && (!q || normalize(`${g.title} ${g.subtitle || ""}`).includes(q)));
  if (!list.length) {
    return h("div", { class: "empty-block" }, h("p", {}, "Nenhum jogo encontrado com esse filtro."),
      h("button", { class: "btn-small", type: "button", onclick: () => { filters.status = "all"; filters.query = ""; render(); } }, "Limpar filtros"));
  }
  const grid = h("div", { class: `games ${libView === "list" ? "is-list" : ""}` });
  list.forEach((g, i) => grid.append(buildGame(emu, g, i)));
  return grid;
}

/** Um jogo: capa, título, estado e ações (sempre visíveis). */
function buildGame(emu, game, index) {
  const art = h("img", { alt: "", draggable: "false", hidden: true });
  const placeholder = h("div", { class: "placeholder", style: `--hue:${hue(game.title)}` }, game.title);
  const badge = h("span", { class: "badge" });
  const zone = h("div", { class: "zone" });
  const open = () => go("saves", emu.id, game.id);

  const root = h("article", { class: "game-card", style: `--i:${Math.min(index, 14)}` },
    h("button", { class: "gc-cover", type: "button", title: "Saves e save states", "aria-label": `Saves de ${game.title}`,
      onclick: open }, placeholder, art),
    h("div", { class: "gc-info" },
      h("h3", { class: "title" }, h("button", { class: "title-btn", type: "button", onclick: open }, game.title)),
      game.subtitle && h("p", { class: "sub" }, game.subtitle)),
    badge, zone);

  tiles.set(game.id, { root, zone, badge, emuId: emu.id, shown: null });
  loadCover(game.id).then((url) => {
    if (!url) return;
    art.src = url;
    art.hidden = false;
    placeholder.hidden = true;
  });
  paint(game.id);
  return root;
}

const STATE_LABEL = { ready: "Pronto", playing: "Jogando", downloading: "Baixando", error: "Erro", missing: "Não baixado" };

/** Estado de um jogo: missing (Baixar), downloading, playing, error ou ready (Jogar). */
function stateOf(emu, game) {
  const job = jobs.get(game.id);
  const ready = emu.installed && game.has_rom;
  const state = job ? "downloading" : running.has(game.id) ? "playing" : errors.has(game.id) ? "error" : ready ? "ready" : "missing";
  return { state, job, wake: job ? Math.max(0.05, job.fraction) : ready ? 1 : 0 };   // a capa "acorda" junto com o download
}

/** Atualiza o bloco do jogo conforme o estado. */
function paint(gameId) {
  const t = tiles.get(gameId);
  const emu = t && findEmu(t.emuId);
  const game = emu && emu.games.find((g) => g.id === gameId);
  if (!game) return;

  const { state, job, wake } = stateOf(emu, game);
  t.root.dataset.state = state;
  t.root.style.setProperty("--wake", wake);
  t.badge.textContent = STATE_LABEL[state];
  if (t.shown !== state) {
    t.zone.replaceChildren(...zoneFor(state, t, emu, game));
    t.shown = state;
  }
  if (state === "downloading") updateProgress(t, emu, job);
}

/** Botões de cada estado. "Excluir jogo" só existe com o jogo baixado (e sempre pede confirmação). */
function zoneFor(state, t, emu, game) {
  const savesBtn = () => h("button", { class: "btn-small", type: "button", onclick: () => go("saves", emu.id, game.id) }, "Saves");
  if (state === "ready") {
    return [
      h("button", { class: "btn btn-play", "aria-label": `Jogar ${game.title}`, onclick: () => onPlay(game.id) }, "Jogar"),
      savesBtn(),
      h("button", { class: "btn-small danger", type: "button", title: "Apaga a ROM do PC; os saves ficam guardados",
        "aria-label": `Excluir ${game.title} do PC`, onclick: () => onDeleteGame(game) }, "Excluir jogo")];
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
    return [h("div", { class: "dl" }, t.bar, h("div", { class: "progress-row" }, t.stageEl, t.pctEl), t.detailEl,
      h("button", { class: "cancel", type: "button", onclick: () => api().cancel_download(game.id) }, "Cancelar"))];
  }
  const label = state === "error" ? "Tentar de novo" : "Baixar";
  const out = [h("button", { class: "btn btn-get", "aria-label": `${label}: ${game.title}`, onclick: () => onDownload(game.id) }, label), savesBtn()];
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
      let closedHere = false;
      for (const id of [...running]) {
        if (play.running.includes(id)) continue;
        running.delete(id);  // emulador fechou
        if (route.view === "saves" && route.gameId === id) closedHere = true;
      }
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
      if (closedHere) await reloadSaves();
      await sleep(350);
    }
  } catch (err) {
    toast("Perdi a conexão com o app. Feche e abra de novo.");
    jobs.clear();
  } finally {
    polling = false;
  }
}

async function onPlay(gameId, state = null) {
  const res = await api().play(gameId, state);
  if (res && res.error) return toast(res.error);
  if (res && res.warning) toast(res.warning);
  running.add(gameId);
  paint(gameId);
  poll();  // acompanha até o emulador fechar
  if (route.view === "saves") reloadSaves();  // a tela de saves passa a mostrar "jogo aberto"
}

async function onRefresh() {
  const btn = $("#refresh");
  btn.disabled = true;
  $("#refresh-label").textContent = "Atualizando…";
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
    $("#refresh-label").textContent = "Atualizar catálogo";
  }
}

// ---------- tela de saves de um jogo ----------

/** "ss1" -> "slot 1" (o mGBA chama o slot de ss0 a ss9). */
const stateLabel = (slot) => { const m = /(\d+)$/.exec(slot); return m ? `slot ${m[1]}` : slot; };

function renderSaves(emu) {
  const d = savesData;
  const g = d.game;
  const save = d.save;
  const locked = d.running;   // com o jogo aberto, nada que troque ou apague o save
  const lockedWhy = locked ? "Feche o jogo no emulador primeiro." : "";

  const cover = h("div", { class: "detail-cover", style: `--hue:${hue(g.title)}` });
  loadCover(g.id).then((url) => { if (url) cover.replaceChildren(h("img", { src: url, alt: "" })); });

  const playButton = locked
    ? h("button", { class: "btn btn-playing", disabled: true }, "Jogando")
    : g.ready
      ? h("button", { class: "btn btn-play", onclick: () => onPlay(g.id) }, "Jogar")
      : h("button", { class: "btn btn-get", onclick: () => { onDownload(g.id); go("emulator", emu.id); } },
        "Baixar o jogo");   // começa o download e leva para a biblioteca, onde o progresso aparece

  const head = h("header", { class: "block detail-head" },
    cover,
    h("div", {},
      h("h1", {}, g.title),
      g.subtitle && h("p", { class: "sub-head" }, g.subtitle),
      h("span", { class: `badge ${locked ? "is-playing" : g.ready ? "is-ready" : ""}` },
        locked ? "Jogando" : g.ready ? "Pronto" : "Não baixado")),
    h("div", { class: "detail-actions" }, playButton));

  const status = !save.exists
    ? "Ainda sem save. Jogue e salve dentro do jogo, ou importe um arquivo .sav."
    : save.blank
      ? "O jogo ainda não salvou nada."
      : `Salvo em ${fmtDate(save.modified)}, ${fmtKB(save.size)}.`;
  const big = !save.exists ? "Sem save" : save.blank ? "Save vazio" : fmtAgo(save.modified);

  const tool = (label, handler, { disabled = false, why = "", danger = false } = {}) =>
    h("button", { class: `btn-small ${danger ? "danger" : ""}`, type: "button", disabled, title: why || null,
      onclick: handler }, label);

  const current = h("section", { class: "block" },
    h("h2", {}, "Save atual"),
    h("p", { class: "save-big" }, big),
    h("p", { class: "save-status" }, status),
    locked && h("p", { class: "hint" }, "O jogo está aberto. Feche o emulador para importar um save ou excluir save states."),
    h("div", { class: "tools" },
      tool("Exportar .sav", onExport, { disabled: !save.exists, why: "Ainda não há save." }),
      tool("Importar .sav", onImport, { disabled: locked, why: lockedWhy })));

  // Save states do emulador (mais recente primeiro). Não têm backup: o clique abre o jogo já carregando o state.
  const stateList = h("ul", { class: "rows" });
  for (const s of d.states) {
    const why = !g.ready ? "Baixe o jogo primeiro." : !d.can_play_state ? "O catálogo não diz como abrir um save state neste emulador." : lockedWhy;
    stateList.append(h("li", { class: "row" },
      h("div", { class: "row-main" },
        h("strong", {}, fmtAgo(s.modified)),
        h("span", { class: "row-meta" }, `${fmtDate(s.modified)}, ${stateLabel(s.slot)}, ${fmtKB(s.size)}`)),
      h("div", { class: "row-actions" },
        h("button", { class: "btn-small play", type: "button", disabled: locked || !g.ready || !d.can_play_state,
          title: why || null, onclick: () => onPlay(g.id, s.name) }, "Carregar e jogar"),
        tool("Excluir", () => onDeleteState(s), { disabled: locked, danger: true, why: lockedWhy }))));
  }
  const states = h("section", { class: "block" },
    h("h2", {}, d.states.length ? `Save states (${d.states.length})` : "Save states"),
    d.states.length
      ? stateList
      : h("p", { class: "save-status" }, "Nenhum save state ainda. Salve um state no emulador e ele aparece aqui."));

  // ações que apagam ficam juntas, num bloco só delas
  const riskRow = (title, text, button) => h("li", { class: "row" },
    h("div", { class: "row-main" }, h("strong", {}, title), h("span", { class: "row-meta" }, text)), button);
  const risk = h("section", { class: "block risk" },
    h("h2", {}, "Zona de risco"),
    h("ul", { class: "rows" },
      riskRow("Excluir jogo do PC",
        "Apaga a ROM para liberar espaço. Seus saves e save states continuam guardados.",
        tool("Excluir jogo", () => onDeleteGame(g), { danger: true, disabled: locked || !g.has_rom,
          why: locked ? lockedWhy : !g.has_rom ? "O jogo não está baixado." : "" }))));

  return h("section", { class: "saves" }, head, states, current, risk);
}

// ---------- ações dos saves ----------

/** Janela de confirmação do próprio app. Devolve true se o usuário confirmou. O foco começa em Cancelar. */
function confirmDialog({ title, body, confirm, danger = false }) {
  return new Promise((resolve) => {
    const dlg = h("dialog", { class: "confirm" },
      h("h2", {}, title),
      h("p", {}, body),
      h("div", { class: "confirm-actions" },
        h("button", { class: "btn btn-get", type: "button", onclick: () => dlg.close("no") }, "Cancelar"),
        h("button", { class: `btn ${danger ? "btn-danger" : "btn-play"}`, type: "button",
          onclick: () => dlg.close("yes") }, confirm)));
    dlg.addEventListener("close", () => { resolve(dlg.returnValue === "yes"); dlg.remove(); });
    document.body.append(dlg);
    dlg.showModal();
  });
}

async function onDeleteState(state) {
  const ok = await confirmDialog({
    title: "Excluir este save state?",
    body: `O save state de ${fmtDate(state.modified)} (${stateLabel(state.slot)}) será apagado de vez. Isso não pode ser desfeito.`,
    confirm: "Excluir", danger: true,
  });
  if (!ok) return;
  const res = await api().delete_state(route.gameId, state.name);
  if (res.error) return toast(res.error);
  toast("Save state excluído.", "ok");
  await reloadSaves();
}

/** Exclui a ROM de um jogo (pede confirmação). Funciona na biblioteca e na tela do jogo. */
async function onDeleteGame(game) {
  const ok = await confirmDialog({
    title: "Excluir o jogo do PC?",
    body: `A ROM de ${game.title} será apagada do seu computador para liberar espaço. `
      + "Seus saves e save states continuam guardados: se baixar o jogo de novo, você continua de onde parou.",
    confirm: "Excluir jogo", danger: true,
  });
  if (!ok) return;
  const res = await api().delete_game(game.id);
  if (res.error) return toast(res.error);
  toast("Jogo excluído. Dá para baixar de novo quando quiser.", "ok");
  await loadLibrary();   // a biblioteca passa a mostrar "Baixar" para este jogo
  if (route.view === "saves") await reloadSaves(); else render();
}

async function onExport() {
  const res = await api().export_save(route.gameId);
  if (res.error) return toast(res.error);
  if (res.cancelled) return;
  toast(`Save exportado para ${res.path}`, "ok");
}

async function onImport() {
  const pick = await api().pick_import_file();
  if (pick.error) return toast(pick.error);
  if (pick.cancelled) return;
  const fileName = pick.path.replace(/^.*[\\/]/, "");
  if (savesData.save.exists && !savesData.save.blank) {   // só pergunta se há progresso a substituir
    const ok = await confirmDialog({
      title: "Importar este save?",
      body: `O arquivo "${fileName}" vai substituir o save atual de ${savesData.game.title}. `
        + "Antes disso, o app guarda um backup do save atual.",
      confirm: "Importar",
    });
    if (!ok) return;
  }
  const res = await api().import_save(route.gameId, pick.path);
  if (res.error) return toast(res.error);
  toast("Save importado.", "ok");
  await reloadSaves();
}

// ---------- início ----------

// Tema claro/escuro: o script no <head> do index.html define o tema inicial; aqui só trocamos e guardamos.
function applyTheme(theme, save) {
  document.documentElement.dataset.theme = theme;
  $("#theme").setAttribute("aria-label", theme === "dark" ? "Trocar para o tema claro" : "Trocar para o tema escuro");
  if (save) savePref("theme", theme);
}
applyTheme(document.documentElement.dataset.theme || "light", false);
$("#theme").addEventListener("click", () =>
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark", true));
// Enquanto você não escolher um tema, acompanha o do Windows.
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) => {
  if (!loadPref("theme", "")) applyTheme(e.matches ? "dark" : "light", false);
});

$("#nav-home").addEventListener("click", () => go("home"));
$("#refresh").addEventListener("click", onRefresh);
document.addEventListener("keydown", (e) => {
  if (document.querySelector("dialog[open]")) return;  // Esc dentro de uma confirmação só fecha ela
  if (e.target instanceof HTMLElement && e.target.matches("input, textarea")) {
    // dentro da busca, Backspace apaga letras (não volta de tela) e Esc limpa o texto
    if (e.key === "Escape" && e.target.value) { e.target.value = ""; e.target.dispatchEvent(new Event("input")); }
    return;
  }
  if ((e.key === "Escape" || e.key === "Backspace") && route.view !== "home") goBack();
});

// Aviso de versão nova: roda em segundo plano e nunca atrapalha a abertura do app.
async function checkUpdate() {
  try {
    const info = await api().check_update();
    if (!info.available) return;
    const btn = $("#update");
    const label = $("#update-label");
    label.textContent = `Nova versão ${info.version}`;
    btn.hidden = false;
    btn.addEventListener("click", () => {
      if (info.can_install) installUpdate(info, btn, label);
      else api().open_url(info.url);   // rodando pelo código (sem instalador): abre a página da release
    });
  } catch (e) { /* sem internet: ignora */ }
}

/** Atualiza de dentro do app: confirma, baixa o instalador (progresso no botão) e o Python fecha o app. */
async function installUpdate(info, btn, label) {
  const ok = await confirmDialog({
    title: `Atualizar para a versão ${info.version}?`,
    body: "O app baixa a atualização, fecha, instala e abre de novo sozinho. "
      + "Seus jogos, saves e save states não são mexidos.",
    confirm: "Atualizar",
  });
  if (!ok) return;
  const start = await api().install_update();
  if (start.error) return toast(start.error);
  btn.disabled = true;
  const idle = `Nova versão ${info.version}`;
  for (;;) {   // acompanha até o Python fechar o app (a janela some) ou dar erro
    await new Promise((r) => setTimeout(r, 400));
    let s;
    try { s = await api().get_update_status(); } catch (e) { return; }   // app fechou: atualização em andamento
    if (s.state === "downloading") {
      label.textContent = s.total ? `Baixando… ${Math.min(99, Math.floor(100 * s.done / s.total))}%` : "Baixando…";
    } else if (s.state === "installing") {
      label.textContent = "Instalando…";
    } else if (s.state === "error") {
      label.textContent = idle;
      btn.disabled = false;
      return toast(`${s.error} Dá para baixar a versão nova na página da release.`);
    }
  }
}

/** Ao abrir, baixa o catálogo do Drive em segundo plano. Sem isso, uma instalação nova ficaria com o
 *  catálogo de reserva (IDs vazios) até alguém clicar em "Atualizar catálogo". Sem internet: segue com o cache. */
async function refreshCatalogOnStart() {
  try {
    const res = await api().refresh_catalog();
    if (res.error) return;
    coverCache = new Map();   // as capas anteriores vieram de um catálogo sem IDs
    await loadLibrary();
    render();
  } catch (e) { /* sem internet: ignora */ }
}

(async function init() {
  await whenReady();
  await loadLibrary();
  const params = new URLSearchParams(location.search);   // só usado pelo modo de desenvolvimento
  if (params.get("emu") && findEmu(params.get("emu"))) route = { view: "emulator", emuId: params.get("emu"), gameId: null };
  if (params.get("game") && route.view === "emulator") {
    route = { view: "saves", emuId: route.emuId, gameId: params.get("game") };
    await loadSaves();
  }
  if (window.__mockJobs) window.__mockJobs(jobs);  // idem: simula um download em andamento
  render();
  checkUpdate();
  if (!params.has("mock")) refreshCatalogOnStart();
  if (window.__mockReady) window.__mockReady();  // idem: abre uma confirmação para eu ver o visual
})();
