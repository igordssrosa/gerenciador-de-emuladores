"""Teclas dos emuladores: tradução de teclas e edição do arquivo de configuração.

Nada aqui conhece um emulador específico: o catálogo diz qual arquivo, seção e chave usar.
Este módulo não importa `catalog` (é o `catalog` que importa daqui), para não criar ciclo.
"""
import os
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # só para as anotações: importar de verdade criaria um ciclo com catalog.py
    from .catalog import Controls


class ControlsError(Exception):
    """Mapeamento de teclas inválido ou arquivo que não deu para gravar (a mensagem vai para o usuário)."""


# ---------- tabela de teclas ----------
# Chave = `event.code` do navegador (posição física da tecla, igual em qualquer layout).
# Valor = código de tecla do Qt, que é o que o mGBA e o melonDS gravam nos arquivos.
# Só entram teclas cujo código não muda com o layout do teclado (por isso sem pontuação nem teclado numérico).
DOM_TO_QT: dict[str, int] = {}
for _c in range(ord("A"), ord("Z") + 1):
    DOM_TO_QT[f"Key{chr(_c)}"] = _c          # letras: o Qt usa o código ASCII maiúsculo
for _d in range(10):
    DOM_TO_QT[f"Digit{_d}"] = ord("0") + _d  # dígitos da fileira de cima
for _n in range(1, 13):
    DOM_TO_QT[f"F{_n}"] = 0x01000030 + _n - 1
DOM_TO_QT.update({
    "Tab": 0x01000001, "Backspace": 0x01000003, "Enter": 0x01000004, "Space": 0x20,
    "ArrowLeft": 0x01000012, "ArrowUp": 0x01000013, "ArrowRight": 0x01000014, "ArrowDown": 0x01000015,
})

_QT_TO_DOM = {qt: code for code, qt in DOM_TO_QT.items()}

_LABELS = {"Space": "Espaço", "ArrowUp": "↑", "ArrowDown": "↓", "ArrowLeft": "←", "ArrowRight": "→"}


def qt_to_code(value: int) -> str | None:
    """Código do Qt -> `event.code`. Valores fora da tabela (-1, Shift...) viram None ("sem tecla")."""
    return _QT_TO_DOM.get(value)


def code_label(code: str) -> str:
    """Texto curto para mostrar na interface: KeyW -> W, Space -> Espaço, ArrowUp -> ↑."""
    if code in _LABELS:
        return _LABELS[code]
    if code.startswith("Key") and len(code) == 4:
        return code[3]
    if code.startswith("Digit") and len(code) == 6:
        return code[5]
    return code


# ---------- editor do arquivo ----------
# Editamos por linhas, sem configparser/tomllib: eles reescreveriam o arquivo inteiro (perdendo comentários,
# ordem e estilo), e o emulador também lê esse arquivo. Só as linhas que pedimos mudam.

def _read_text(path: Path) -> str | None:
    try:
        return path.read_bytes().decode("utf-8", errors="surrogateescape")
    except FileNotFoundError:
        return None


def _section_range(lines: list[str], section: str) -> tuple[int, int] | None:
    """(linha do título, linha onde a seção acaba) ou None se a seção não existe."""
    header = f"[{section}]"
    for i, line in enumerate(lines):
        if line.strip() == header:
            end = len(lines)
            for j in range(i + 1, len(lines)):
                if lines[j].lstrip().startswith("["):
                    end = j
                    break
            return i, end
    return None


def _key_pattern(key: str) -> re.Pattern:
    return re.compile(r"^(\s*" + re.escape(key) + r"\s*=\s*)(.*?)\s*$")


def read_values(path: Path, section: str, keys: list[str]) -> dict[str, int | None]:
    """Valor inteiro de cada chave na seção. None = arquivo, seção ou chave ausente (ou valor que não é número)."""
    result: dict[str, int | None] = {k: None for k in keys}
    text = _read_text(path)
    if text is None:
        return result
    lines = text.splitlines()
    found = _section_range(lines, section)
    if found is None:
        return result
    start, end = found
    for key in keys:
        pattern = _key_pattern(key)
        for line in lines[start + 1:end]:
            m = pattern.match(line)
            if m:
                try:
                    result[key] = int(m.group(2))
                except ValueError:
                    pass
                break
    return result


def write_values(path: Path, section: str, values: dict[str, int], sep: str) -> None:
    """Grava as chaves na seção, mexendo só nelas. `sep` ("=" ou " = ") vale só para linhas novas.
    Mantém o fim de linha do arquivo, faz uma cópia `.bak` na primeira gravação e troca o arquivo de uma vez."""
    text = _read_text(path)
    eol = "\r\n" if text and "\r\n" in text else "\n"
    lines = (text or "").splitlines()

    found = _section_range(lines, section)
    if found is None:
        if lines:
            lines.append("")
        lines.append(f"[{section}]")
        lines.extend(f"{k}{sep}{v}" for k, v in values.items())
    else:
        start, end = found
        new_keys: list[str] = []
        for key, value in values.items():
            pattern = _key_pattern(key)
            for i in range(start + 1, end):
                m = pattern.match(lines[i])
                if m:
                    lines[i] = f"{m.group(1)}{value}"
                    break
            else:
                new_keys.append(key)
        # chaves novas entram logo depois da última linha com conteúdo da seção (as linhas em branco ficam depois)
        at = end
        while at > start + 1 and not lines[at - 1].strip():
            at -= 1
        lines[at:at] = [f"{k}{sep}{values[k]}" for k in new_keys]

    data = (eol.join(lines) + eol).encode("utf-8", errors="surrogateescape")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        bak = path.with_name(path.name + ".bak")
        if text is not None and not bak.exists():
            shutil.copy2(path, bak)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except OSError as exc:
        raise ControlsError(f"Não consegui gravar {path.name}: {exc.strerror or exc}") from exc


# ---------- mapeamento de botões ----------

def load_mapping(cfg: "Controls", base_dir: Path) -> dict[str, str | None]:
    """Tecla atual de cada botão do catálogo (id -> `event.code`, ou None se estiver sem tecla)."""
    values = read_values(base_dir / cfg.file, cfg.section, [b.key for b in cfg.buttons])
    return {b.id: (qt_to_code(values[b.key]) if values[b.key] is not None else None) for b in cfg.buttons}


def save_mapping(cfg: "Controls", base_dir: Path, mapping: dict[str, str | None]) -> None:
    """Grava as teclas (id -> `event.code` ou None). Confere tudo antes de mexer no arquivo."""
    by_id = {b.id: b for b in cfg.buttons}
    for button_id, code in mapping.items():
        if button_id not in by_id:
            raise ControlsError(f"Botão desconhecido: '{button_id}'.")
        if code is not None and code not in DOM_TO_QT:
            raise ControlsError(f"A tecla '{code}' não pode ser usada.")
    used = [code for code in mapping.values() if code is not None]
    if len(used) != len(set(used)):
        raise ControlsError("Duas teclas iguais: cada botão precisa de uma tecla diferente.")
    # sem tecla = -1, o valor que os emuladores usam para "não atribuído"
    values = {by_id[i].key: (DOM_TO_QT[code] if code else -1) for i, code in mapping.items()}
    write_values(base_dir / cfg.file, cfg.section, values, "=" if cfg.format == "ini" else " = ")
