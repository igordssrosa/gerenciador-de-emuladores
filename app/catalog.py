"""Ler, validar e atualizar o catálogo.

Ordem de leitura: cache local (última versão baixada do Drive) -> catalog.json do projeto.
Adicionar jogo/emulador = editar o catálogo no Drive; nenhum código muda.
"""
import json
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import controls as keymap, paths, settings


class CatalogError(Exception):
    """Catálogo inválido ou impossível de carregar (a mensagem é mostrada ao usuário)."""


@dataclass
class Game:
    id: str
    title: str
    subtitle: str
    rom_file_id: str
    rom_filename: str
    cover_file_id: str


@dataclass
class ControlButton:
    id: str
    label: str
    group: str    # só organiza o desenho do popup: dpad | face | shoulder | system
    key: str      # nome da chave no arquivo de configuração do emulador (ex.: "keyA" no mGBA, "A" no melonDS)
    default: str  # tecla padrão, como `event.code` do navegador (ex.: "KeyK")


@dataclass
class Controls:
    """Onde ficam as teclas do emulador, para o popup de Controles ler e gravar."""
    file: str            # relativo à pasta do emulador
    format: str          # "ini" (chave=valor) ou "toml" (chave = valor)
    section: str
    key_encoding: str    # como o valor é gravado; por enquanto só "qt" (código de tecla do Qt)
    buttons: list[ControlButton]


@dataclass
class Emulator:
    id: str
    name: str
    platform: str
    icon_file_id: str
    download_file_id: str
    download_type: str  # "7z" ou "zip"
    executable: str
    args: list[str]
    rom_extensions: list[str]
    save_extensions: list[str]
    games: list[Game] = field(default_factory=list)
    # Arquivos a criar na pasta do emulador depois de extrair (nome -> conteúdo).
    # Ex.: {"portable.ini": ""} liga o modo portátil do mGBA, sem código específico dele.
    setup_files: dict[str, str] = field(default_factory=dict)
    # "default" = janela normal do emulador; "borderless" = janela sem título e sem bordas, do mesmo tamanho, centralizada.
    window_mode: str = "default"
    # Save states do emulador (arquivos ao lado da ROM, ex.: [".ss1", ".ss2"]) e a linha de comando que abre
    # o jogo já carregando um deles (ex.: ["-t", "{state}", "{rom}"]). Opcionais: sem eles não há lista de states.
    state_extensions: list[str] = field(default_factory=list)
    state_args: list[str] = field(default_factory=list)
    # Teclas do emulador (popup "Controles"). Opcional: sem isso o emulador não tem o botão.
    controls: Controls | None = None


@dataclass
class Catalog:
    version: int
    emulators: list[Emulator]

    def emulator(self, emulator_id: str) -> Emulator:
        for e in self.emulators:
            if e.id == emulator_id:
                return e
        raise CatalogError(f"Emulador '{emulator_id}' não existe no catálogo.")


def _req(d: dict, key: str, where: str):
    """Pega um campo obrigatório ou explica exatamente o que falta."""
    if key not in d:
        raise CatalogError(f"Campo '{key}' faltando em {where}.")
    return d[key]


_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def _check_id(value: str, where: str) -> str:
    """IDs viram nomes de pasta no disco, então só aceitamos letras, números, . _ -"""
    if not isinstance(value, str) or not _SAFE_ID.match(value) or value in (".", ".."):
        raise CatalogError(f"ID inválido em {where}: '{value}' (use só letras, números, - _ .).")
    return value


def _check_setup_files(files: dict, where: str) -> dict[str, str]:
    for name in files:
        p = Path(name)
        if p.is_absolute() or ".." in p.parts:
            raise CatalogError(f"setup_files do {where} tem caminho inválido: '{name}'.")
    return {str(k): str(v) for k, v in files.items()}


def _check_window_mode(value: str, where: str) -> str:
    if value not in ("default", "borderless"):
        raise CatalogError(f"window_mode do {where} deve ser 'default' ou 'borderless' (veio '{value}').")
    return value


def _file_id(d: dict, key: str, where: str) -> str:
    # Os IDs podem estar vazios enquanto o arquivo não foi enviado ao Drive.
    return str(d.get(key, {}).get("file_id", ""))


def parse(raw: dict) -> Catalog:
    """Valida o JSON e converte para objetos. Levanta CatalogError se algo estiver errado."""
    if not isinstance(raw, dict):
        raise CatalogError("O catálogo precisa ser um objeto JSON.")
    emulators, seen_emus = [], set()
    seen_games: set[str] = set()  # ID de jogo é único no catálogo todo (vira nome de pasta em games/)
    for e in _req(raw, "emulators", "catálogo"):
        eid = _check_id(_req(e, "id", "emulador"), "emulador")
        where = f"emulador '{eid}'"
        if eid in seen_emus:
            raise CatalogError(f"ID de emulador repetido: '{eid}'.")
        seen_emus.add(eid)
        args = list(_req(e, "args", where))
        if not any("{rom}" in a for a in args):
            raise CatalogError(f"Os args do {where} precisam ter o marcador {{rom}}.")
        games = []
        for g in e.get("games", []):
            gid = _check_id(_req(g, "id", f"jogo do {where}"), f"jogo do {where}")
            if gid in seen_games:
                raise CatalogError(f"ID de jogo repetido: '{gid}'.")
            seen_games.add(gid)
            gwhere = f"jogo '{gid}'"
            filename = _req(_req(g, "rom", gwhere), "filename", gwhere)
            # Segurança: o nome vira um arquivo no disco, então não pode ter pastas.
            if Path(filename).name != filename:
                raise CatalogError(f"Nome de arquivo inválido no {gwhere}: '{filename}'.")
            games.append(Game(
                id=gid,
                title=_req(g, "title", gwhere),
                subtitle=g.get("subtitle", ""),
                rom_file_id=_file_id(g, "rom", gwhere),
                rom_filename=filename,
                cover_file_id=_file_id(g, "cover", gwhere),
            ))
        emulators.append(Emulator(
            id=eid,
            name=_req(e, "name", where),
            platform=e.get("platform", ""),
            icon_file_id=_file_id(e, "icon", where),
            download_file_id=_file_id(e, "download", where),
            download_type=e.get("download", {}).get("type", "zip"),
            executable=_req(e, "executable", where),
            args=args,
            rom_extensions=[x.lower() for x in e.get("rom_extensions", [])],
            save_extensions=[x.lower() for x in e.get("save_extensions", [])],
            games=games,
            setup_files=_check_setup_files(e.get("setup_files", {}), where),
            window_mode=_check_window_mode(e.get("window_mode", "default"), where),
            state_extensions=[x.lower() for x in e.get("state_extensions", [])],
            state_args=_check_state_args(list(e.get("state_args", [])), where),
            controls=_parse_controls(e.get("controls"), where),
        ))
    return Catalog(version=int(raw.get("version", 1)), emulators=emulators)


def _parse_controls(raw: dict | None, where: str) -> Controls | None:
    if raw is None:
        return None
    here = f"controls do {where}"
    file = str(_req(raw, "file", here))
    _check_setup_files({file: ""}, here)  # mesma regra de caminho seguro: nada absoluto nem com ".."
    fmt = _req(raw, "format", here)
    if fmt not in ("ini", "toml"):
        raise CatalogError(f"format do {here} deve ser 'ini' ou 'toml' (veio '{fmt}').")
    encoding = raw.get("key_encoding", "qt")
    if encoding != "qt":
        raise CatalogError(f"key_encoding do {here} deve ser 'qt' (veio '{encoding}').")
    buttons, seen = [], set()
    for b in _req(raw, "buttons", here):
        bid = _req(b, "id", here)
        if bid in seen:
            raise CatalogError(f"Botão repetido em {here}: '{bid}'.")
        seen.add(bid)
        group = b.get("group", "face")
        if group not in ("dpad", "face", "shoulder", "system"):
            raise CatalogError(f"group do botão '{bid}' em {here} deve ser dpad, face, shoulder ou system.")
        default = _req(b, "default", here)
        if default not in keymap.DOM_TO_QT:
            raise CatalogError(f"Tecla padrão '{default}' do botão '{bid}' em {here} não é uma tecla aceita.")
        buttons.append(ControlButton(id=bid, label=_req(b, "label", here), group=group,
                                     key=_req(b, "key", here), default=default))
    if not buttons:
        raise CatalogError(f"{here} precisa de pelo menos um botão.")
    return Controls(file=file, format=fmt, section=_req(raw, "section", here), key_encoding=encoding, buttons=buttons)


def _check_state_args(args: list[str], where: str) -> list[str]:
    if args and not any("{state}" in a for a in args):
        raise CatalogError(f"Os state_args do {where} precisam ter o marcador {{state}}.")
    return args


def _read(path: Path) -> Catalog:
    try:
        return parse(json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as exc:
        raise CatalogError(f"JSON inválido em {path.name}: {exc}") from exc


def load() -> Catalog:
    """Carrega o catálogo local (cache, ou o do projeto se ainda não há cache)."""
    if paths.CATALOG_CACHE.exists():
        try:
            return _read(paths.CATALOG_CACHE)
        except CatalogError:
            pass  # cache corrompido: cai para o catálogo do projeto
    if paths.BUNDLED_CATALOG.exists():
        return _read(paths.BUNDLED_CATALOG)
    raise CatalogError("Nenhum catálogo encontrado. Configure o ID do catálogo e atualize.")


def refresh() -> Catalog:
    """Baixa o catalog.json do Drive e guarda como cache. Só substitui o cache se for válido."""
    file_id = settings.load().get("catalog_file_id", "")
    if not file_id:
        raise CatalogError("O ID do catálogo no Drive ainda não foi configurado (settings.json).")
    import gdown  # importado aqui para o app abrir mesmo sem rede/gdown em outros usos

    paths.ensure_dirs()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_file = Path(tmp) / "catalog.json"
        try:
            result = gdown.download(id=file_id, output=str(tmp_file), quiet=True)
        except Exception as exc:  # o texto do gdown traz o link com o ID; não repassamos
            raise CatalogError("Não foi possível baixar o catálogo (sem internet ou link privado?).") from exc
        if not result or not tmp_file.exists():
            raise CatalogError("Não foi possível baixar o catálogo (sem internet ou link privado?).")
        catalog = _read(tmp_file)  # valida antes de substituir o cache bom
        shutil.copyfile(tmp_file, paths.CATALOG_CACHE)
    return catalog
