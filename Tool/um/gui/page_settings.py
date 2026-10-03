"""Settings page: language and theme, plus a short About."""
from __future__ import annotations

import platform
import tkinter as tk
from tkinter import ttk

from um import dragon_log
from um import dragon_theme as theme
from um.dragon_i18n import get_language, tr
from um.gui.widgets import ScrollFrame, WrapLabel, card

LANGUAGE_CHOICES = (('auto', 'Automatic (follow Windows)'), ('en', 'English'), ('ja', '日本語'))
THEME_CHOICES = (('system', 'Follow Windows'), ('light', 'Light'), ('dark', 'Dark'))


class SettingsPage:
    def __init__(self, app):
        self.app = app

    def build(self, parent) -> ttk.Frame:
        app = self.app
        frame = ttk.Frame(parent)
        scroll = ScrollFrame(frame)
        scroll.pack(fill='both', expand=True)
        body = scroll.inner
        body.columnconfigure(0, weight=1)
        ttk.Label(body, text=tr('Settings'), style='Title.TLabel').grid(row=0, column=0, sticky='w', padx=24, pady=(20, 10))

        look = card(body, tr('Appearance'))
        look.grid(row=1, column=0, sticky='ew', padx=24, pady=6)
        look.columnconfigure(1, weight=1)
        ttk.Label(look, text=tr('Language'), width=18).grid(row=0, column=0, sticky='w', pady=6)
        self.language_box = self.choice_box(look, LANGUAGE_CHOICES, app.language, 'language')
        self.language_box.grid(row=0, column=1, sticky='w', padx=6)
        ttk.Label(look, text=tr('Theme'), width=18).grid(row=1, column=0, sticky='w', pady=6)
        self.theme_box = self.choice_box(look, THEME_CHOICES, app.theme, 'theme')
        self.theme_box.grid(row=1, column=1, sticky='w', padx=6)
        WrapLabel(look, text=tr('Changing the language or theme rebuilds the window; it is applied immediately. '
                                'The engine messages of the conversion itself (errors from Blender or the checks) stay in English.'),
                  style='Muted.TLabel').grid(row=2, column=0, columnspan=2, sticky='ew', pady=(8, 0))

        about = card(body, tr('About'))
        about.grid(row=2, column=0, sticky='ew', padx=24, pady=(6, 24))
        about.columnconfigure(0, weight=1)
        info = [(tr('Tool version fingerprint'), dragon_log.tool_fingerprint()),
                (tr('Python'), platform.python_version()),
                (tr('Language in use'), get_language()),
                (tr('Theme in use'), theme.resolve(app.theme.get()))]
        for row, (label, value) in enumerate(info):
            ttk.Label(about, text=label, width=26, style='Muted.TLabel').grid(row=row, column=0, sticky='w')
            ttk.Label(about, text=value).grid(row=row, column=1, sticky='w')
        about.columnconfigure(1, weight=1)
        WrapLabel(about, text=tr('VRMDragonTool is open source (MIT). It never installs anything into the game and never changes '
                                 'the files you extracted. See THIRD_PARTY_NOTICES.md for the licenses of the parts it builds on.'),
                  style='Muted.TLabel').grid(row=len(info), column=0, columnspan=2, sticky='ew', pady=(10, 0))
        return frame

    def choice_box(self, parent, choices, variable: tk.StringVar, setting: str) -> ttk.Combobox:
        labels = [tr(text) if code != 'ja' else text for code, text in choices]
        box = ttk.Combobox(parent, state='readonly', values=labels, width=30)
        codes = [code for code, _ in choices]
        current = variable.get() if variable.get() in codes else codes[0]
        box.set(labels[codes.index(current)])

        def changed(_event=None):
            code = codes[labels.index(box.get())]
            previous = variable.get()
            if code == previous:
                return
            variable.set(code)
            self.app.change_appearance(setting, previous)
        box.bind('<<ComboboxSelected>>', changed)
        return box
