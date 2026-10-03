"""The desktop GUI (Tk): sidebar window with Convert, Advanced tools, Setup, Storage & logs and Settings."""
from __future__ import annotations

import tkinter as tk


def main():
    from um import dragon_log
    dragon_log.setup_logging()
    dragon_log.log_environment()
    try:  # crisp text on high-DPI screens
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001 - not Windows or already set
        pass
    root = tk.Tk()
    root.report_callback_exception = lambda kind, value, trace: dragon_log.get_logger().error(
        'Uncaught error in a GUI callback', exc_info=(kind, value, trace))
    from um.gui.app import DragonApp
    DragonApp(root)
    root.mainloop()
