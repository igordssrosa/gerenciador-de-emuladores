"""Ponto de entrada: python -m app          -> abre a janela
                    python -m app --catalog -> só imprime o catálogo no terminal (útil para depurar)"""
import sys

from . import catalog, paths


def print_catalog() -> None:
    try:
        cat = catalog.load()
    except catalog.CatalogError as exc:
        print(f"Erro no catálogo: {exc}")
        raise SystemExit(1)
    print(f"Pasta de dados: {paths.DATA_DIR}")
    for emu in cat.emulators:
        print(f"\n{emu.name} ({emu.platform}) - {len(emu.games)} jogo(s)")
        for g in emu.games:
            print(f"  - {g.title} [{g.subtitle}] -> {g.rom_filename}")


def open_window() -> None:
    from . import webview2

    if not webview2.ensure_installed():  # sem WebView2 não há janela; a função já explicou o motivo
        raise SystemExit(1)

    import webview  # import tardio: o modo --catalog não precisa dele

    from .api import Api

    # Centraliza na tela principal (sem isso o Windows posiciona a janela em cascata, às vezes cortada)
    width, height = 1180, 780
    screen = webview.screens[0]
    x = max(0, (screen.width - width) // 2)
    y = max(0, (screen.height - height) // 2 - 20)  # um pouco acima do centro: a barra de tarefas ocupa a base

    window = webview.create_window(
        "Gerenciador de Emuladores",
        url=str(paths.resource_dir() / "app" / "ui" / "index.html"),
        js_api=Api(),
        width=width, height=height, x=x, y=y, min_size=(760, 560),
        background_color="#1B1650",  # mesma cor do fundo: evita um flash branco ao abrir
        text_select=False,
    )
    webview.start()


def selftest() -> None:
    """Confere se o app empacotado (.exe) tem tudo que precisa. O .exe não tem console,
    então o resultado vai para selftest.txt na pasta de dados. Uso: GerenciadorEmuladores.exe --selftest"""
    lines, ok = [], True

    def check(name: str, fn) -> None:
        nonlocal ok
        try:
            lines.append(f"OK    {name}: {fn() or ''}")
        except Exception as exc:  # qualquer falha aparece no relatório
            ok = False
            lines.append(f"FALHA {name}: {type(exc).__name__}: {exc}")

    def ui_files():
        ui = paths.resource_dir() / "app" / "ui"
        missing = [f for f in ("index.html", "style.css", "app.js", "fonts/space-grotesk.woff2") if not (ui / f).is_file()]
        assert not missing, f"faltando {missing}"
        if getattr(sys, "frozen", False):  # só no .exe: a pasta dev/ (simulador) não deve ir no pacote
            assert not (ui / "dev").exists(), "a pasta dev/ não deveria ir no pacote"

    def imports():
        import gdown, webview, py7zr, clr  # noqa: F401  (clr = pythonnet, usado pelo pywebview)
        return "gdown, pywebview, py7zr, pythonnet"

    def bundled_catalog():
        return f"{len(catalog.parse(__import__('json').loads(paths.BUNDLED_CATALOG.read_text(encoding='utf-8'))).emulators)} emulador(es)"

    def drive():
        cat = catalog.refresh()  # baixa o catalog.json do Drive de verdade (testa gdown + certificados)
        return f"baixou e validou: {sum(len(e.games) for e in cat.emulators)} jogo(s)"

    def winmode_ok():
        from . import winmode
        assert winmode.user32.IsWindow(0) == 0
        return "ctypes/user32 ok"

    check("arquivos da interface", ui_files)
    check("bibliotecas", imports)
    check("catálogo embutido", bundled_catalog)
    check("catálogo do Drive", drive)
    check("modo sem bordas (Windows)", winmode_ok)
    lines.append("RESULTADO: " + ("tudo certo" if ok else "com falhas"))
    (paths.DATA_DIR / "selftest.txt").write_text("\n".join(lines), encoding="utf-8")
    raise SystemExit(0 if ok else 1)


def main() -> None:
    paths.ensure_dirs()
    if "--selftest" in sys.argv:
        selftest()
    elif "--version" in sys.argv:
        from .version import VERSION
        print(VERSION)
    elif "--catalog" in sys.argv:
        print_catalog()
    else:
        open_window()


if __name__ == "__main__":
    main()
