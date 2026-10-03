"""Light and dark appearance for the Tk GUI (ttk 'clam' theme plus colours for the plain Tk widgets)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

PALETTES = {
    'light': {'bg': '#f3f4f6', 'surface': '#ffffff', 'sidebar': '#e8eaee', 'fg': '#1f2328', 'muted': '#5b6370',
              'border': '#cfd4db', 'accent': '#2563eb', 'accent_fg': '#ffffff', 'accent_hover': '#1d4ed8',
              'button': '#e6e9ee', 'button_hover': '#d9dde4', 'field': '#ffffff', 'select_bg': '#cfe0ff',
              'select_fg': '#0b1b3a', 'warn': '#9a6700', 'danger': '#b42318', 'ok': '#1a7f37', 'nav_active': '#d4defa'},
    'dark': {'bg': '#17191e', 'surface': '#1f2229', 'sidebar': '#111318', 'fg': '#e6e9ef', 'muted': '#9aa3b2',
             'border': '#3a404b', 'accent': '#4c8dff', 'accent_fg': '#08101f', 'accent_hover': '#6aa0ff',
             'button': '#2b303a', 'button_hover': '#363c48', 'field': '#252932', 'select_bg': '#2f4a7d',
             'select_fg': '#ffffff', 'warn': '#e3b341', 'danger': '#ff7b72', 'ok': '#56d364', 'nav_active': '#26324d'},
}
MODES = ('system', 'light', 'dark')
_state = {'mode': 'light', 'palette': PALETTES['light']}
_registry: list = []


def system_prefers_dark() -> bool:
    """True when Windows is set to dark app mode."""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize')
        value, _ = winreg.QueryValueEx(key, 'AppsUseLightTheme')
        return value == 0
    except Exception:  # noqa: BLE001 - not Windows or value missing
        return False


def resolve(mode: str) -> str:
    if mode == 'system':
        return 'dark' if system_prefers_dark() else 'light'
    return mode if mode in ('light', 'dark') else 'light'


def palette() -> dict:
    return _state['palette']


def current_mode() -> str:
    return _state['mode']


def register(widget, kind: str) -> None:
    """Remember a plain Tk widget (text, canvas, toplevel, listbox) so it follows the theme."""
    _registry.append((widget, kind))
    recolor(widget, kind)


def recolor(widget, kind: str) -> None:
    p = _state['palette']
    try:
        if kind in ('text', 'listbox'):
            widget.configure(bg=p['field'], fg=p['fg'], insertbackground=p['fg'], selectbackground=p['select_bg'],
                             selectforeground=p['select_fg'], highlightbackground=p['border'],
                             highlightcolor=p['accent'], relief='flat', highlightthickness=1)
        elif kind == 'canvas':
            widget.configure(bg=p['bg'])
        elif kind == 'toplevel':
            widget.configure(bg=p['bg'])
    except tk.TclError:
        pass


def recolor_all() -> None:
    alive = []
    for widget, kind in _registry:
        try:
            if widget.winfo_exists():
                recolor(widget, kind)
                alive.append((widget, kind))
        except tk.TclError:
            pass
    _registry[:] = alive


def apply(root: tk.Misc, mode: str = 'system') -> str:
    """Configure the ttk styles for the mode and recolour registered widgets. Returns 'light' or 'dark'."""
    actual = resolve(mode)
    p = PALETTES[actual]
    _state.update(mode=mode, palette=p)
    style = ttk.Style(root)
    try:
        style.theme_use('clam')
    except tk.TclError:
        pass
    base = ('Segoe UI', 10)
    root.configure(bg=p['bg'])
    style.configure('.', background=p['bg'], foreground=p['fg'], fieldbackground=p['field'], bordercolor=p['border'],
                    lightcolor=p['border'], darkcolor=p['border'], troughcolor=p['sidebar'], focuscolor=p['accent'],
                    selectbackground=p['select_bg'], selectforeground=p['select_fg'], font=base)
    style.configure('TFrame', background=p['bg'])
    style.configure('Card.TFrame', background=p['surface'])
    style.configure('Sidebar.TFrame', background=p['sidebar'])
    style.configure('TLabel', background=p['bg'], foreground=p['fg'])
    style.configure('Muted.TLabel', background=p['bg'], foreground=p['muted'])
    style.configure('Warn.TLabel', background=p['bg'], foreground=p['warn'])
    style.configure('Title.TLabel', background=p['bg'], foreground=p['fg'], font=('Segoe UI', 16, 'bold'))
    style.configure('Heading.TLabel', background=p['bg'], foreground=p['fg'], font=('Segoe UI', 11, 'bold'))
    style.configure('Brand.TLabel', background=p['sidebar'], foreground=p['fg'], font=('Segoe UI', 13, 'bold'))
    style.configure('SidebarMuted.TLabel', background=p['sidebar'], foreground=p['muted'], font=('Segoe UI', 9))
    style.configure('Status.TLabel', background=p['sidebar'], foreground=p['fg'])
    style.configure('TLabelframe', background=p['bg'], bordercolor=p['border'], relief='solid', borderwidth=1)
    style.configure('TLabelframe.Label', background=p['bg'], foreground=p['fg'], font=('Segoe UI', 10, 'bold'))
    style.configure('TButton', background=p['button'], foreground=p['fg'], bordercolor=p['border'], padding=(10, 5),
                    relief='flat', focusthickness=1)
    style.map('TButton', background=[('disabled', p['bg']), ('pressed', p['button_hover']), ('active', p['button_hover'])],
              foreground=[('disabled', p['muted'])])
    style.configure('Accent.TButton', background=p['accent'], foreground=p['accent_fg'], bordercolor=p['accent'],
                    padding=(16, 8), font=('Segoe UI', 11, 'bold'))
    style.map('Accent.TButton', background=[('disabled', p['border']), ('pressed', p['accent_hover']), ('active', p['accent_hover'])],
              foreground=[('disabled', p['muted'])])
    style.configure('Nav.TButton', background=p['sidebar'], foreground=p['fg'], bordercolor=p['sidebar'], anchor='w',
                    padding=(14, 9), relief='flat', font=('Segoe UI', 10))
    style.map('Nav.TButton', background=[('active', p['button_hover'])])
    style.configure('NavActive.TButton', background=p['nav_active'], foreground=p['fg'], bordercolor=p['nav_active'],
                    anchor='w', padding=(14, 9), relief='flat', font=('Segoe UI', 10, 'bold'))
    style.map('NavActive.TButton', background=[('active', p['nav_active'])])
    style.configure('Link.TButton', background=p['bg'], foreground=p['accent'], bordercolor=p['bg'], padding=(2, 2),
                    relief='flat')
    style.map('Link.TButton', background=[('active', p['bg'])], foreground=[('active', p['accent_hover'])])
    for name in ('TEntry', 'TCombobox', 'TSpinbox'):
        style.configure(name, fieldbackground=p['field'], background=p['button'], foreground=p['fg'],
                        insertcolor=p['fg'], bordercolor=p['border'], arrowcolor=p['fg'], padding=4)
        style.map(name, fieldbackground=[('readonly', p['field']), ('disabled', p['bg'])],
                  foreground=[('disabled', p['muted'])], arrowcolor=[('disabled', p['muted'])])
    for name in ('TCheckbutton', 'TRadiobutton'):
        style.configure(name, background=p['bg'], foreground=p['fg'], indicatorbackground=p['field'],
                        indicatorforeground=p['fg'], indicatormargin=(0, 0, 6, 0))
    for name in ('TCheckbutton', 'TRadiobutton'):
        style.map(name, background=[('active', p['bg'])], indicatorcolor=[('selected', p['accent']), ('!selected', p['field'])],
                  foreground=[('disabled', p['muted'])])
    style.configure('Treeview', background=p['field'], fieldbackground=p['field'], foreground=p['fg'],
                    bordercolor=p['border'], rowheight=24)
    style.map('Treeview', background=[('selected', p['select_bg'])], foreground=[('selected', p['select_fg'])])
    style.configure('Treeview.Heading', background=p['button'], foreground=p['fg'], bordercolor=p['border'],
                    relief='flat', font=('Segoe UI', 9, 'bold'), padding=4)
    style.map('Treeview.Heading', background=[('active', p['button_hover'])])
    style.configure('Horizontal.TProgressbar', background=p['accent'], troughcolor=p['sidebar'], bordercolor=p['border'],
                    lightcolor=p['accent'], darkcolor=p['accent'])
    style.configure('TScrollbar', background=p['button'], troughcolor=p['bg'], bordercolor=p['bg'], arrowcolor=p['fg'])
    style.map('TScrollbar', background=[('active', p['button_hover'])])
    style.configure('TSeparator', background=p['border'])
    root.option_add('*TCombobox*Listbox.background', p['field'])
    root.option_add('*TCombobox*Listbox.foreground', p['fg'])
    root.option_add('*TCombobox*Listbox.selectBackground', p['select_bg'])
    root.option_add('*TCombobox*Listbox.selectForeground', p['select_fg'])
    root.option_add('*Menu.background', p['surface'])
    root.option_add('*Menu.foreground', p['fg'])
    recolor_all()
    return actual
