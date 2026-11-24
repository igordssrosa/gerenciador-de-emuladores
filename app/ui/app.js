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
      .then((url) => resolve(url || null))
      .catch(() => resolve(null))
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
  route = { view, emuId, gameId };
  if (view === "saves") await loadSaves();
  render();
  $("#view").focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

/** Voltar um nível: saves -> jogos do emulador -> tela inicial. */
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
  $("#back").hidden = route.view === "home";
  $("#brand").hidden = route.view !== "home";

  if (!lib || lib.error) return view.replaceChildren(renderCatalogError());
  const emu = route.view !== "home" && findEmu(route.emuId);
  if (route.view !== "home" && !emu) route = { view: "home", emuId: null, gameId: null };
  if (route.view === "saves" && !savesData) route = { view: "emulator", emuId: route.emuId, gameId: null };
  $("#back-label").textContent = route.view === "saves" ? emu.name : "Emuladores";
  view.replaceChildren(route.view === "saves" ? renderSaves(emu)
    : route.view === "emulator" ? renderEmulator(emu) : renderHome());
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
    h("div", { class: "cover-wrap" }, glow,
      h("button", { class: "cover", type: "button", "aria-label": `Saves e backups de ${game.title}`,
        onclick: () => go("saves", emu.id, game.id) },
        placeholder, art, h("span", { class: "cover-hint", "aria-hidden": "true" }, "Saves e backups"))),
    h("div", { class: "meta" },
      h("h3", { class: "title" },
        h("button", { class: "title-btn", type: "button", onclick: () => go("saves", emu.id, game.id) }, game.title)),
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

async function onPlay(gameId) {
  const res = await api().play(gameId);
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

// ---------- tela de saves de um jogo ----------

function renderSaves(emu) {
  const d = savesData;
  const g = d.game;
  const save = d.save;
  const locked = d.running;   // com o jogo aberto, nada que troque ou apague o save

  const cover = h("div", { class: "saves-cover", style: `--hue:${hue(g.title)}` });
  loadCover(g.id).then((url) => { if (url) cover.replaceChildren(h("img", { src: url, alt: "" })); });

  const playButton = locked
    ? h("button", { class: "btn btn-playing", disabled: true }, "Jogando")
    : g.ready
      ? h("button", { class: "btn btn-play", onclick: () => onPlay(g.id) }, "Jogar")
      : h("button", { class: "btn btn-get", onclick: () => { onDownload(g.id); go("emulator", emu.id); } },
        "Baixar o jogo");   // começa o download e leva para a grade, onde o progresso aparece

  const head = h("header", { class: "saves-head" },
    cover,
    h("div", {},
      h("h1", { class: "saves-title" }, g.title),
      g.subtitle && h("p", { class: "sub-head" }, g.subtitle),
      h("div", { class: "saves-play" }, playButton)));

  const status = !save.exists
    ? "Ainda sem save. Jogue e salve dentro do jogo, ou importe um arquivo .sav."
    : save.blank
      ? "Save vazio: o jogo ainda não salvou nada."
      : `Salvo em ${fmtDate(save.modified)}, ${fmtKB(save.size)}.`;

  const tool = (label, handler, { disabled = false, why = "", danger = false } = {}) =>
    h("button", { class: `btn-small ${danger ? "danger" : ""}`, type: "button", disabled, title: why || null,
      onclick: handler }, label);
  const lockedWhy = locked ? "Feche o jogo no emulador primeiro." : "";

  const current = h("section", { class: "saves-block" },
    h("h2", {}, "Save atual"),
    h("p", { class: "save-status" }, status),
    locked && h("p", { class: "hint" }, "O jogo está aberto. Feche o emulador para restaurar, importar ou apagar saves."),
    h("div", { class: "tools" },
      tool("Fazer backup agora", onBackup, { disabled: !save.exists || save.blank, why: "Não há progresso para guardar." }),
      tool("Exportar .sav", onExport, { disabled: !save.exists, why: "Ainda não há save." }),
      tool("Importar .sav", onImport, { disabled: locked, why: lockedWhy }),
      tool("Apagar save", onDeleteSave, { disabled: !save.exists || locked, why: lockedWhy || "Ainda não há save.", danger: true })));

  const list = h("ul", { class: "backups" });
  for (const b of d.backups) {
    list.append(h("li", { class: "backup" },
      h("div", { class: "b-main" },
        h("strong", {}, fmtDate(b.created)),
        h("span", { class: "b-meta" }, `${b.reason}, ${fmtKB(b.size)}`)),
      h("div", { class: "b-actions" },
        h("button", { class: "btn-small play", type: "button", disabled: locked || !g.ready,
          title: !g.ready ? "Baixe o jogo primeiro." : lockedWhy || null, onclick: () => onRestore(b, true) }, "Carregar e jogar"),
        tool("Restaurar", () => onRestore(b, false), { disabled: locked, why: lockedWhy }),
        tool("Apagar", () => onDeleteBackup(b), { danger: true }))));
  }

  const backups = h("section", { class: "saves-block" },
    h("h2", {}, d.backups.length ? `Backups (${d.backups.length})` : "Backups"),
    d.backups.length
      ? list
      : h("p", { class: "save-status" },
        "Nenhum backup ainda. O app guarda um sozinho antes e depois de cada vez que você joga."));

  return h("section", {}, head, current, backups);
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

async function onBackup() {
  const res = await api().backup_save(route.gameId);
  if (res.error) return toast(res.error);
  if (res.created) toast("Backup feito.", "ok");
  else toast(res.why === "igual" ? "O save não mudou desde o último backup." : "Ainda não há save para guardar.", "info");
  await reloadSaves();
}

async function onRestore(backup, playAfter) {
  const title = savesData.game.title;
  const ok = await confirmDialog({
    title: playAfter ? "Carregar este save e jogar?" : "Restaurar este backup?",
    body: `O save atual de ${title} será trocado pelo de ${fmtDate(backup.created)}. `
      + "Antes disso, o app guarda um backup do save atual, então nada se perde."
      + (playAfter ? " Depois o jogo abre." : ""),
    confirm: playAfter ? "Carregar e jogar" : "Restaurar",
  });
  if (!ok) return;
  const res = await api().restore_backup(route.gameId, backup.name, playAfter);
  if (res.error) return toast(res.error);
  toast(playAfter ? "Save carregado. Abrindo o jogo." : "Save restaurado.", "ok");
  if (res.play_error) toast(res.play_error);
  await reloadSaves();
}

async function onDeleteBackup(backup) {
  const ok = await confirmDialog({
    title: "Apagar este backup?",
    body: `O backup de ${fmtDate(backup.created)} (${backup.reason.toLowerCase()}) será apagado de vez. Isso não pode ser desfeito.`,
    confirm: "Apagar backup", danger: true,
  });
  if (!ok) return;
  const res = await api().delete_backup(route.gameId, backup.name);
  if (res.error) return toast(res.error);
  toast("Backup apagado.", "ok");
  await reloadSaves();
}

async function onDeleteSave() {
  const ok = await confirmDialog({
    title: "Apagar o save atual?",
    body: `O save atual de ${savesData.game.title} será apagado. Antes, o app guarda um backup dele, `
      + "e você poderá restaurá-lo pela lista de backups.",
    confirm: "Apagar save", danger: true,
  });
  if (!ok) return;
  const res = await api().delete_save(route.gameId);
  if (res.error) return toast(res.error);
  toast("Save apagado. Dá para restaurá-lo pela lista de backups.", "ok");
  await reloadSaves();
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

$("#back").addEventListener("click", goBack);
$("#refresh").addEventListener("click", onRefresh);
document.addEventListener("keydown", (e) => {
  if (document.querySelector("dialog[open]")) return;  // Esc dentro de uma confirmação só fecha ela
  if ((e.key === "Escape" || e.key === "Backspace") && route.view !== "home") goBack();
});

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
  if (window.__mockReady) window.__mockReady();  // idem: abre uma confirmação para eu ver o visual
})();
