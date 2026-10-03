"""Setup page: Blender (download or choose) and the optional local AI."""
from __future__ import annotations

import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from um import dragon_log
from um.dragon_i18n import tr
from um.gui.tasks import Cancelled
from um.gui.widgets import ScrollFrame, WrapLabel, card


class SetupPage:
    def __init__(self, app):
        self.app = app
        self.blender_status = tk.StringVar()
        self.blender_progress = tk.StringVar()
        self.ai_status = tk.StringVar(value=tr('Not checked'))
        self.cancel = threading.Event()
        self.installing = False
        self.buttons: list = []

    # ---- layout ----------------------------------------------------------------------------------------
    def build(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent)
        scroll = ScrollFrame(frame)
        scroll.pack(fill='both', expand=True)
        body = scroll.inner
        body.columnconfigure(0, weight=1)
        ttk.Label(body, text=tr('Setup'), style='Title.TLabel').grid(row=0, column=0, sticky='w', padx=24, pady=(20, 10))

        box = card(body, tr('Blender'))
        box.grid(row=1, column=0, sticky='ew', padx=24, pady=6)
        box.columnconfigure(0, weight=1)
        WrapLabel(box, text=tr('The tool needs Blender 4.5 LTS. If you do not have it, it can be downloaded from the official '
                               'server (download.blender.org) when you press the button. The download is checked against a '
                               'pinned SHA-256 checksum and installed only inside Tool/runtime/blender. Nothing is downloaded '
                               'without your confirmation. You can also choose a blender.exe you already have.'),
                  style='Muted.TLabel').grid(row=0, column=0, sticky='ew')
        WrapLabel(box, textvariable=self.blender_status).grid(row=1, column=0, sticky='ew', pady=(8, 4))
        self.bar = ttk.Progressbar(box, mode='determinate', maximum=100)
        self.bar.grid(row=2, column=0, sticky='ew', pady=4)
        ttk.Label(box, textvariable=self.blender_progress, style='Muted.TLabel').grid(row=3, column=0, sticky='w')
        row = ttk.Frame(box)
        row.grid(row=4, column=0, sticky='w', pady=(8, 0))
        self.install_button = ttk.Button(row, text=tr('Download and set up Blender'), style='Accent.TButton', command=self.install)
        self.install_button.pack(side='left', padx=(0, 8))
        self.cancel_button = ttk.Button(row, text=tr('Cancel'), command=self.cancel_install, state='disabled')
        self.cancel_button.pack(side='left', padx=(0, 8))
        self.choose_button = ttk.Button(row, text=tr('Choose my own blender.exe...'), command=self.choose)
        self.choose_button.pack(side='left')

        ai = card(body, tr('Local AI (detailed profile mode only)'))
        ai.grid(row=2, column=0, sticky='ew', padx=24, pady=6)
        ai.columnconfigure(0, weight=1)
        WrapLabel(ai, text=tr('Only needed for the detailed mode (local AI). Not needed for the simple mode.') + '\n'
                  + tr('Ollama, models and caches are stored in Tool/runtime.') + '\n'
                  + tr('An existing Ollama is never contacted. Qwen is about 5 GB and Ollama about 1.5 GB to download.') + '\n'
                  + tr('Python 3.10+ (with Tkinter/Pillow) and Blender are required separately.'),
                  style='Muted.TLabel').grid(row=0, column=0, sticky='ew')
        WrapLabel(ai, textvariable=self.ai_status).grid(row=1, column=0, sticky='ew', pady=(8, 4))
        row = ttk.Frame(ai)
        row.grid(row=2, column=0, sticky='w', pady=(6, 0))
        self.ai_buttons = []
        for label, operation in ((tr('Set up Ollama'), 'setup'), (tr('Download Qwen'), 'download'), (tr('Check status'), 'status')):
            button = ttk.Button(row, text=label, command=lambda op=operation: self.ai_action(op))
            button.pack(side='left', padx=(0, 8))
            self.ai_buttons.append(button)
        self.refresh()
        return frame

    def on_busy(self, busy: bool) -> None:
        state = 'disabled' if busy else 'normal'
        for button in (self.choose_button, *self.ai_buttons):
            button.configure(state=state)
        self.install_button.configure(state='disabled' if busy or self.app.blender_usable() else 'normal')
        self.cancel_button.configure(state='normal' if busy and self.installing else 'disabled')

    # ---- Blender ---------------------------------------------------------------------------------------
    def refresh(self) -> None:
        from um.dragon_blender_setup import BLENDER_SIZE, BLENDER_VERSION
        if self.app.blender_usable():
            self.blender_status.set(tr('Blender is set: {0}', dragon_log.redact(self.app.paths['blender'].get())))
            if hasattr(self, 'install_button') and not self.app.tasks.busy:
                self.install_button.configure(state='disabled')
        else:
            self.blender_status.set(tr('Blender was not found. Download Blender {0} (about {1} MB) from the official server, '
                                       'or choose a blender.exe you already have.', BLENDER_VERSION, round(BLENDER_SIZE / 1e6)))

    def first_run(self) -> None:
        """Offer to set Blender up when none is found (asked once per start)."""
        if self.app.blender_usable() or self.app.tasks.busy:
            return
        from um.dragon_blender_setup import BLENDER_SIZE, BLENDER_VERSION
        answer = messagebox.askyesnocancel(
            tr('Blender not found'),
            tr('This tool needs Blender 4.5 LTS to convert avatars, but none was found.') + '\n\n'
            + tr('Download Blender {0} (about {1} MB, about 1 GB after unpacking) from the official server download.blender.org '
                 'now? It is verified with a SHA-256 checksum and installed only inside the tool folder.',
                 BLENDER_VERSION, round(BLENDER_SIZE / 1e6)) + '\n\n'
            + tr('Yes: download it.  No: choose a blender.exe you already have.  Cancel: decide later (see the Setup page).'))
        self.app.show_page('setup')
        if answer is True:
            self.install()
        elif answer is False:
            self.choose()

    def set_path(self, path) -> None:
        self.app.paths['blender'].set(str(path))
        self.app.save_settings()
        self.refresh()

    def choose(self) -> None:
        if self.app.tasks.busy:
            return
        chosen = filedialog.askopenfilename(title=tr('Select blender.exe'),
                                            filetypes=[(tr('Blender executable'), 'blender.exe'), (tr('All files'), '*.*')])
        if not chosen:
            return
        if Path(chosen).name.lower() != 'blender.exe':
            messagebox.showerror(tr('Blender'), tr('Please select blender.exe (not another file).'))
            return
        self.set_path(chosen)

    def install(self) -> None:
        if self.app.tasks.busy:
            return
        if self.app.blender_usable():
            messagebox.showinfo(tr('Blender'), tr('Blender is already set. Choose another blender.exe if you want to change it.'))
            return
        from um.dragon_blender_setup import BLENDER_SIZE, BLENDER_VERSION, BlenderInstaller, BlenderSetupError
        if not messagebox.askokcancel(
                tr('Download Blender'),
                tr('Download Blender {0} (about {1} MB) from download.blender.org and install it in Tool/runtime/blender?',
                   BLENDER_VERSION, round(BLENDER_SIZE / 1e6)) + '\n' + tr('It needs about 2.5 GB of free disk space while installing.')):
            return
        self.cancel = threading.Event()
        self.installing = True
        self.bar.configure(value=0)
        self.blender_progress.set(tr('Starting...'))

        def work(progress):
            try:
                return str(BlenderInstaller().install(progress=progress, cancel=self.cancel))
            except BlenderSetupError as exc:
                if 'Cancelled' in str(exc):
                    raise Cancelled(str(exc)) from exc
                raise
        self.app.tasks.run(work, on_done=self._installed, on_error=self._install_failed,
                           on_progress=self._install_progress, label='Blender setup')
        self.cancel_button.configure(state='normal')

    def cancel_install(self) -> None:
        self.cancel.set()
        self.blender_progress.set(tr('Cancelling...'))

    def _install_progress(self, event) -> None:
        total, current = event.get('total'), event.get('current')
        message = self.translate_progress(event['message'])
        if total and current is not None:
            self.bar.configure(value=100 * current / total)
            if total > 10 ** 6:
                self.blender_progress.set(f'{message}: {current / 1e6:.0f} / {total / 1e6:.0f} MB')
            else:
                self.blender_progress.set(f'{message}: {current} / {total}')
        else:
            self.blender_progress.set(message)

    @staticmethod
    def translate_progress(text: str) -> str:
        """The installer reports English text with the version inside; map it onto the translated templates."""
        import re
        match = re.fullmatch(r'Downloading Blender (.+)', text)
        if match:
            return tr('Downloading Blender {0}', match.group(1))
        match = re.fullmatch(r'Blender (.+) is ready', text)
        if match:
            return tr('Blender {0} is ready', match.group(1))
        return tr(text)

    def _installed(self, path) -> None:
        self.installing = False
        self.bar.configure(value=100)
        self.blender_progress.set(tr('Done.'))
        self.set_path(path)
        messagebox.showinfo(tr('Blender'), tr('Blender is installed and ready to use.'))

    def _install_failed(self, exc) -> None:
        self.installing = False
        self.bar.configure(value=0)
        if isinstance(exc, Cancelled):
            self.blender_progress.set(tr('Cancelled. Nothing was installed.'))
        else:
            self.blender_progress.set(tr('Failed.'))
            messagebox.showerror(tr('Blender setup failed'), str(exc) + '\n\n' + self.app.log_hint())
        self.refresh()

    # ---- local AI --------------------------------------------------------------------------------------
    def ai_action(self, operation: str) -> None:
        from um.dragon_local_ai import get_runtime
        if self.app.tasks.busy:
            return
        if operation == 'status':
            self.ai_status.set(json.dumps(get_runtime().status(), ensure_ascii=False))
            return
        if not messagebox.askokcancel(tr('Confirm download'),
                                      tr('This downloads into the tool-owned environment and needs several GB of free space '
                                         'and bandwidth.') + '\n' + tr('An existing Ollama is not modified. Continue?')):
            return

        def work(progress):
            runtime = get_runtime()
            return runtime.setup(progress, install=True) if operation == 'setup' else runtime.download_model(progress)

        def on_progress(data):
            suffix = f" {data['current'] / 1024 ** 2:.1f} MiB" if data.get('current') is not None else ''
            if data.get('total'):
                suffix += f" / {data['total'] / 1024 ** 2:.1f} MiB"
            self.ai_status.set(data['message'] + suffix)
        self.app.tasks.run(work, on_done=lambda result: self.ai_status.set(str(result)),
                           on_error=self._ai_failed, on_progress=on_progress, label='AI setup')

    def _ai_failed(self, exc) -> None:
        self.ai_status.set(str(exc))
        messagebox.showerror(tr('AI setup'), str(exc))
