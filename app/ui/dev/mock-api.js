/* SÓ PARA DESENVOLVIMENTO: simula o Python para eu ver as telas no navegador.
   Só carrega com ?mock na URL (ex.: index.html?mock=many&emu=mgba). Dentro do app de verdade não é usado.
   Modos: two (padrão, 2 jogos) | many (30 jogos) | fresh (emulador ainda não baixado) | dl (um download a 42%) */
"use strict";
(function () {
  const params = new URLSearchParams(location.search);
  const mode = params.get("mock") || "two";
  const covers = params.get("cov") || "";   // pasta com fr.jpg e em.png

  const real = [
    ["pokemon-firered-ptbr", "Pokémon FireRed", "PT-BR (English moves)", true],
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

  const live = {};   // downloads simulados
  const playing = new Set();
  window.pywebview = { api: {
    get_library: async () => ({ emulators: [{ id: "mgba", name: "mGBA", platform: "Game Boy Advance", installed, games }] }),
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
  } };

  if (mode === "dl") {
    window.__mockJobs = (jobs) => {
      jobs.set("pokemon-emerald-ptbr", { stage: "rom", fraction: 0.42, done: 7.05e6, total: 16.8e6, pending: false });
    };
  }
})();
