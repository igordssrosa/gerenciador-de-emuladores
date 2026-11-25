"""O pywebview desenha a janela com o WebView2 da Microsoft. O Windows 11 já traz;
alguns Windows 10 não. Aqui checamos e, se faltar, oferecemos instalar."""
import ctypes
import subprocess
import tempfile
import urllib.request
import winreg
from pathlib import Path

# GUID do runtime "Evergreen" do WebView2 (valor documentado pela Microsoft)
_KEY = r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
# Instalador oficial pequeno ("bootstrapper"): baixa e instala o runtime
_BOOTSTRAPPER_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"


def is_installed() -> bool:
    for hive, view in ((winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
                       (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
                       (winreg.HKEY_CURRENT_USER, 0)):
        try:
            with winreg.OpenKey(hive, _KEY, 0, winreg.KEY_READ | view) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
                if version and version != "0.0.0.0":
                    return True
        except OSError:
            continue
    return False


def _message_box(text: str, flags: int) -> int:
    return ctypes.windll.user32.MessageBoxW(0, text, "Gerenciador de Emuladores", flags)


def ensure_installed() -> bool:
    """True se o app pode abrir a janela. Se faltar o WebView2, pergunta e instala."""
    if is_installed():
        return True
    answer = _message_box(
        "Falta um componente gratuito da Microsoft (WebView2) para mostrar a janela do app.\n\n"
        "Posso baixar e instalar agora? (leva cerca de 1 minuto e precisa de internet)",
        0x04 | 0x20)  # botões Sim/Não + ícone de pergunta
    if answer != 6:  # 6 = Sim
        return False
    try:
        installer = Path(tempfile.mkdtemp()) / "MicrosoftEdgeWebview2Setup.exe"
        urllib.request.urlretrieve(_BOOTSTRAPPER_URL, installer)
        subprocess.run([str(installer), "/silent", "/install"], check=False, timeout=600)
    except Exception as exc:
        _message_box(f"Não consegui instalar sozinho ({exc}).\n\nBaixe em:\n"
                     "https://developer.microsoft.com/microsoft-edge/webview2/", 0x10)
        return False
    return is_installed()
