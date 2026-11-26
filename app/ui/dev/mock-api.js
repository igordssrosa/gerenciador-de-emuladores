/* SÓ PARA DESENVOLVIMENTO: simula o Python para eu ver as telas no navegador.
   Só carrega com ?mock na URL (ex.: index.html?mock=many&emu=mgba). Dentro do app de verdade não é usado.
   Modos: two (padrão, 2 jogos) | many (30 jogos) | fresh (emulador ainda não baixado) | dl (um download a 42%) */
"use strict";
(function () {
  const params = new URLSearchParams(location.search);
  const mode = params.get("mock") || "two";
  const covers = params.get("cov") || "";   // pasta com fr.jpg e em.png

  const real = [
    ["pokemon-firered-ptbr", "Pokémon FireRed", "", true],
    ["pokemon-emerald-ptbr", "Pokémon Emerald", "PT-BR", false],
  ];
  const extra = ["Ruby", "Sapphire", "LeafGreen", "Mother 3", "Metroid Fusion", "Advance Wars", "Golden Sun",
    "Fire Emblem", "Kirby Nightmare", "Wario Ware", "Castlevania Aria", "Zelda Minish Cap", "Sonic Advance",
    "Mario Kart Super Circuit", "Drill Dozer", "Final Fantasy VI", "Harvest Moon", "Mega Man Zero",
    "Pokémon Pinball", "Yoshi's Island", "Boktai", "Astro Boy", "Dragon Ball Z", "Tactics Ogre",
    "Mario & Luigi", "Rhythm Tengoku", "Kuru Kuru Kururin", "Gunstar Super Heroes"];

  let games = real.map(([id, title, subtitle, has]) => ({ id, title, subtitle, has_rom: has }));
  if (mode === "many") {
    games = games.concat(extra.map((t, i) => ({ id: `g${i}`, title: t, subtitle: i % 3 ? "" : "PT-BR", has_rom: i % 4 === 0 })));
  }
  const installed = mode !== "fresh";

  const coverFor = (id) => {
    if (!covers || /^g\d*[05]$/.test(id)) return null;          // alguns sem capa, para ver o espaço reservado
    return covers + (id === "pokemon-firered-ptbr" || /\d*[0-4]$/.test(id) ? "fr.jpg" : "em.png");
  };

  const savesMode = params.get("saves") || "some";
  const now = Date.now() / 1000;
  const saveState = { exists: savesMode !== "none", blank: savesMode === "blank", modified: now - 3600 * 5 };
  let backups = savesMode === "some" || savesMode === "open" ? [
    { name: "b1", created: now - 3600 * 5, size: 131072, auto: true, reason: "Depois de jogar" },
    { name: "b2", created: now - 3600 * 5.4, size: 131072, auto: true, reason: "Antes de jogar" },
    { name: "b3", created: now - 86400 * 2, size: 131072, auto: false, reason: "Backup manual" },
    { name: "b4", created: now - 86400 * 3, size: 131072, auto: false, reason: "Antes de restaurar" },
    { name: "b5", created: now - 86400 * 9, size: 131072, auto: true, reason: "Depois de jogar" },
  ] : [];
  const live = {};   // downloads simulados
  const playing = new Set();
  const mockControls = new Map();   // teclas "salvas" nesta sessão do mock
  window.pywebview = { api: {
    get_library: async () => ({ emulators: [{ id: "mgba", name: "mGBA", platform: "Game Boy Advance", installed, has_controls: true, games }] }),
    check_update: async () => ({ available: params.has("upd"), version: "1.1.6", url: "", can_install: true }),   // ?upd mostra o botão de versão nova
    get_cover: async (id) => { await new Promise((r) => setTimeout(r, 150)); return coverFor(id); },
    get_emulator_icon: async () => null,
    start_download: async (id) => { live[id] = { t0: Date.now() }; return { ok: true }; },
    get_jobs: async () => {
      const out = {};
      for (const [id, j] of Object.entries(live)) {
        const f = Math.min(1, (Date.now() - j.t0) / 6000);
        out[id] = { stage: f < .3 ? "emulador" : "rom", fraction: f, done: f * 16.8e6, total: 16.8e6, finished: f >= 1, error: null, cancelled: false };
        if (f >= 1) { delete live[id]; const g = games.find((x) => x.id === id); if (g) g.has_rom = true; }
      }
      return out;
    },
    cancel_download: async () => ({ ok: true }),
    refresh_catalog: async () => ({ error: "O ID do catálogo no Drive ainda não foi configurado (settings.json)." }),
    play: async (id) => { playing.add(id); setTimeout(() => playing.delete(id), 4000); return { ok: true }; },
    get_running: async () => ({ running: [...playing], errors: {} }),

    // ---- saves (simulados em memória; ?saves=none|some|blank|open) ----
    // Controles: ?mock=...&pad=ds mostra X/Y, &running mostra o aviso de jogo aberto.
    get_controls: async () => {
      const ds = params.get("pad") === "ds";
      const b = (id, label, group, code) => ({ id, label, group, code, display: "", default_code: code });
      const list = [b("Up", "Cima", "dpad", "KeyW"), b("Down", "Baixo", "dpad", "KeyS"), b("Left", "Esquerda", "dpad", "KeyA"),
        b("Right", "Direita", "dpad", "KeyD"), b("A", "A", "face", "KeyK"), b("B", "B", "face", "KeyJ"),
        ...(ds ? [b("X", "X", "face", "KeyI"), b("Y", "Y", "face", "KeyU")] : []),
        b("L", "L", "shoulder", "KeyQ"), b("R", "R", "shoulder", "KeyE"), b("Start", "Start", "system", "Enter"),
        b("Select", "Select", "system", "Space")];
      mockControls.forEach((code, id) => { const x = list.find((i) => i.id === id); if (x) x.code = code; });
      return { available: true, installed, running: params.has("running"), buttons: list };
    },
    save_controls: async (id, mapping) => { Object.entries(mapping).forEach(([k, v]) => mockControls.set(k, v)); return { ok: true }; },
    get_saves: async (id) => {
      const g = games.find((x) => x.id === id);
      if (!g) return { error: "Jogo não existe." };
      return {
        game: { id: g.id, title: g.title, subtitle: g.subtitle, ready: g.has_rom && installed, has_rom: g.has_rom },
        emulator: { id: "mgba", name: "mGBA" },
        save: saveState.exists ? { exists: true, blank: saveState.blank, size: 131072, modified: saveState.modified }
          : { exists: false, blank: false, size: 0, modified: null },
        backups: backups.map((b) => ({ ...b })),
        states: [{ name: "firered.ss2", slot: "ss2", modified: Date.now() / 1000 - 600, size: 410000 },
          { name: "firered.ss1", slot: "ss1", modified: Date.now() / 1000 - 86400, size: 410000 }],
        can_play_state: true,
        running: savesMode === "open" || playing.has(id),
      };
    },
    backup_save: async () => ({ ok: true, created: true }),
    restore_backup: async (id, name, play) => { if (play) playing.add(id); return { ok: true }; },
    delete_backup: async (id, name) => { backups = backups.filter((b) => b.name !== name); return { ok: true }; },
    delete_save: async () => { saveState.exists = false; return { ok: true }; },
    delete_game: async (id) => { const g = games.find((x) => x.id === id); if (g) g.has_rom = false; return { ok: true }; },
    pick_import_file: async () => ({ path: "C:\\Users\\voce\\Downloads\\firered-100pct.sav" }),
    import_save: async () => ({ ok: true }),
    export_save: async () => ({ ok: true, path: "C:\\Users\\voce\\Desktop\\firered.sav" }),
  } };

  if (params.has("dialog")) {
    window.__mockReady = () => confirmDialog({
      title: "Apagar o save atual?",
      body: "O save atual de Pokémon FireRed será apagado. Antes, o app guarda um backup dele, e você poderá restaurá-lo pela lista de backups.",
      confirm: "Apagar save", danger: true });
  }

  if (mode === "dl") {
    window.__mockJobs = (jobs) => {
      jobs.set("pokemon-emerald-ptbr", { stage: "rom", fraction: 0.42, done: 7.05e6, total: 16.8e6, pending: false });
    };
  }
})();
