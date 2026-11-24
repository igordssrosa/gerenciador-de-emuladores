"""Modo "janela sem bordas" para qualquer emulador (Windows).

Emuladores como o mGBA só têm janela normal ou tela cheia. Aqui o app espera a janela aparecer,
tira a moldura (título e bordas), mantém o tamanho do conteúdo e centraliza no monitor.
Funciona para qualquer emulador: no catálogo basta "window_mode": "borderless".
"""
import sys
import time

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

GWL_STYLE, GWL_EXSTYLE = -16, -20
# bits de estilo da moldura: título, borda de redimensionar, botões da barra de título
FRAME_STYLE = 0x00C00000 | 0x00040000 | 0x00080000 | 0x00020000 | 0x00010000
FRAME_EXSTYLE = 0x1 | 0x100 | 0x200 | 0x20000
SWP_FRAMECHANGED, SWP_NOOWNERZORDER, SWP_SHOWWINDOW = 0x20, 0x200, 0x40


def _find_main_window(pid: int):
    """Maior janela visível (sem dona) do processo, ou None se ainda não apareceu."""
    best = []

    def visit(hwnd, _):
        owner_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
        if owner_pid.value == pid and user32.IsWindowVisible(hwnd) and not user32.GetWindow(hwnd, 4):  # 4 = GW_OWNER
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            w, h = r.right - r.left, r.bottom - r.top
            if w >= 200 and h >= 150:
                best.append((w * h, hwnd))
        return True

    user32.EnumWindows(WNDENUMPROC(visit), 0)
    return max(best)[1] if best else None


def _center_on_monitor(hwnd, width: int, height: int) -> None:
    mon = user32.MonitorFromWindow(hwnd, 2)  # 2 = o monitor onde a janela está
    info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    user32.GetMonitorInfoW(mon, ctypes.byref(info))
    work = info.rcWork  # área útil: não passa por baixo da barra de tarefas
    x = work.left + ((work.right - work.left) - width) // 2
    y = work.top + ((work.bottom - work.top) - height) // 2
    user32.SetWindowPos(hwnd, None, x, y, width, height, SWP_FRAMECHANGED | SWP_NOOWNERZORDER | SWP_SHOWWINDOW)


def _apply(hwnd, last_size):
    """Tira a moldura mantendo o tamanho útil e centraliza. Devolve o tamanho atual.
    Só mexe na janela se a moldura voltou ou o tamanho mudou (evita piscar)."""
    style = user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
    exstyle = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    has_frame = bool(style & FRAME_STYLE) or bool(exstyle & FRAME_EXSTYLE)
    if has_frame:
        client = wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(client))  # tamanho do conteúdo, sem título e bordas
        user32.SetWindowLongPtrW(hwnd, GWL_STYLE, style & ~FRAME_STYLE)
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, exstyle & ~FRAME_EXSTYLE)
        _center_on_monitor(hwnd, client.right, client.bottom)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    size = (rect.right - rect.left, rect.bottom - rect.top)
    if size != last_size and not has_frame:   # o emulador redimensionou (ao carregar o jogo): recentraliza
        _center_on_monitor(hwnd, *size)
    return size


def make_borderless(pid: int, appear_timeout: float = 20.0, enforce_for: float = 12.0) -> bool:
    """Espera a janela do processo aparecer e a deixa sem bordas. Roda em thread (bloqueia).

    Continua reaplicando por `enforce_for` segundos porque o emulador redimensiona a própria
    janela quando carrega o jogo (aí recentralizamos). Depois disso larga a janela em paz.
    """
    if sys.platform != "win32":
        return False
    try:  # coordenadas em pixels reais, iguais às do emulador (que é "DPI aware")
        ctypes.windll.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        pass

    hwnd, deadline = None, time.monotonic() + appear_timeout
    while hwnd is None and time.monotonic() < deadline:
        hwnd = _find_main_window(pid)
        if hwnd is None:
            time.sleep(0.1)
    if hwnd is None:
        return False

    end, size = time.monotonic() + enforce_for, None
    while time.monotonic() < end and user32.IsWindow(hwnd):
        size = _apply(hwnd, size)
        time.sleep(0.25)
    return True
