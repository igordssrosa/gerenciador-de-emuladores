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
    import webview  # import tardio: o modo --catalog não precisa dele

    from .api import Api

    window = webview.create_window(
        "Gerenciador de Emuladores",
        url=str(paths.resource_dir() / "app" / "ui" / "index.html"),
        js_api=Api(),
        width=1180, height=780, min_size=(760, 560),
        background_color="#1B1650",  # mesma cor do fundo: evita um flash branco ao abrir
        text_select=False,
    )
    webview.start()


def main() -> None:
    paths.ensure_dirs()
    if "--catalog" in sys.argv:
        print_catalog()
    else:
        open_window()


if __name__ == "__main__":
    main()
