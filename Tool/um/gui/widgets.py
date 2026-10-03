"""Small reusable Tk widgets for the GUI."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from um import dragon_theme as theme
from um.dragon_i18n import tr


class WrapLabel(ttk.Label):
    """A label whose text wraps to the width it is given."""

    def __init__(self, parent, text='', style='TLabel', **kwargs):
        super().__init__(parent, text=text, style=style, justify='left', **kwargs)
        self._width = 0
        self.bind('<Configure>', self._fit)

    def _fit(self, event):
        # Only react to real width changes: re-wrapping changes the height, which must not trigger another round.
        if abs(event.width - self._width) < 12:
            return
        self._width = event.width
        self.configure(wraplength=max(140, event.width - 6))


class ScrollFrame(ttk.Frame):
    """A vertically scrolling area; put the content into `.inner`."""

    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        theme.register(self.canvas, 'canvas')
        self.scroll = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor='nw')
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.scroll.pack(side='right', fill='y')
        self.inner.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        self.bind('<Enter>', lambda e: self.bind_all('<MouseWheel>', self._wheel))
        self.bind('<Leave>', lambda e: self.unbind_all('<MouseWheel>'))

    def _wheel(self, event):
        if event.widget.winfo_class() in ('Treeview', 'Text', 'Listbox', 'TCombobox'):
            return  # these scroll themselves
        self.canvas.yview_scroll(int(-event.delta / 120), 'units')


class Collapsible(ttk.Frame):
    """A heading that shows or hides its `.body` frame."""

    def __init__(self, parent, title: str, opened: bool = False):
        super().__init__(parent)
        self._title = title
        self._opened = opened
        self.header = ttk.Button(self, style='Link.TButton', command=self.toggle)
        self.header.pack(anchor='w')
        self.body = ttk.Frame(self)
        self._sync()

    def toggle(self):
        self._opened = not self._opened
        self._sync()

    def set_open(self, opened: bool):
        self._opened = opened
        self._sync()

    def _sync(self):
        self.header.configure(text=('▾ ' if self._opened else '▸ ') + self._title)
        if self._opened:
            self.body.pack(fill='x', pady=(4, 0))
        else:
            self.body.pack_forget()


def card(parent, title: str) -> ttk.LabelFrame:
    """A titled group box."""
    return ttk.LabelFrame(parent, text=title, padding=(12, 8, 12, 12))


def path_row(parent, label: str, var: tk.StringVar, browse=None, label_width: int = 26, button_text: str | None = None):
    """label + entry + optional Browse button, returned as a frame (grid inside the parent as you like)."""
    frame = ttk.Frame(parent)
    frame.columnconfigure(1, weight=1)
    ttk.Label(frame, text=label, width=label_width).grid(row=0, column=0, sticky='w', pady=3)
    ttk.Entry(frame, textvariable=var).grid(row=0, column=1, sticky='ew', padx=6, pady=3)
    if browse is not None:
        ttk.Button(frame, text=button_text or tr('Browse...'), command=browse).grid(row=0, column=2, pady=3)
    return frame


def themed_text(parent, height: int = 8, **kwargs) -> tk.Text:
    widget = tk.Text(parent, height=height, wrap='word', borderwidth=0, padx=8, pady=6,
                     font=('Consolas', 9), **kwargs)
    theme.register(widget, 'text')
    return widget


def scrolled_tree(parent, columns, height: int = 8, selectmode: str = 'browse'):
    """A Treeview with a scrollbar. columns: [(key, heading, width)]. Returns (frame, tree)."""
    frame = ttk.Frame(parent)
    tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show='headings', height=height, selectmode=selectmode)
    for key, title, width in columns:
        tree.heading(key, text=title)
        tree.column(key, width=width, anchor='w')
    scroll = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.pack(side='left', fill='both', expand=True)
    scroll.pack(side='right', fill='y')
    return frame, tree
