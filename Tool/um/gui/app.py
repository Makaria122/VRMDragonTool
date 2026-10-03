"""Main window: sidebar navigation, shared state, settings, language and theme."""
from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from um import dragon_log
from um import dragon_theme as theme
from um.dragon_i18n import set_language, tr
from um.gui.tasks import TaskRunner

PAGES = (('convert', 'Convert'), ('tools', 'Advanced tools'), ('setup', 'Setup'),
         ('storage', 'Storage & logs'), ('settings', 'Settings'))


class DragonApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title('VRMDragonTool')
        root.minsize(1000, 680)
        root.geometry('1140x780')
        self.bundle = Path(__file__).resolve().parents[3]
        self.user_data = self.bundle / 'Tool' / 'userdata'
        self.settings_file = self.user_data / 'settings.json'
        self.private_output_parent = self.user_data / 'outputs'
        self.settings = self._load_settings()
        s = self.settings

        self.paths = {name: tk.StringVar() for name in ('vrm', 'tops', 'face', 'hair', 'blender', 'addon')}
        blender = self.bundle / 'Tool' / 'runtime' / 'blender' / 'blender.exe'
        if not blender.is_file():
            blender = self.bundle / 'Blender' / 'blender.exe'  # existing private installation compatibility
        addon = self.bundle / 'Tool' / 'vendor' / 'yakuza-gmd-gmt-blender'
        if blender.is_file():
            self.paths['blender'].set(str(blender))
        if (addon / 'yk_gmd_blender' / '__init__.py').is_file():
            self.paths['addon'].set(str(addon))
        saved_blender = s.get('blender')
        if saved_blender and (Path(saved_blender).is_file() or not self.paths['blender'].get()):
            self.paths['blender'].set(saved_blender)

        self.source_root = tk.StringVar(value=s.get('source_root', ''))
        self.game_folder = tk.StringVar(value=s.get('game_folder', s.get('source_root', '')))
        self.action_blend = tk.StringVar()
        self.source_kind = tk.StringVar(value=s.get('source_kind') if s.get('source_kind') in ('other', 'builtin') else 'other')
        self.builtin_target = tk.StringVar(value=s.get('builtin_target', 'yagami'))
        self.last_character = s.get('last_character', '')
        self.target_id = tk.StringVar(value='')  # the target the next conversion uses (set by the Convert page)
        self.include_variants = tk.BooleanVar(value=s['include_variants'] if isinstance(s.get('include_variants'), bool) else True)
        self.profile_mode = tk.StringVar(value=s.get('profile_mode') if s.get('profile_mode') in ('simple', 'detailed') else 'simple')
        jobs = s.get('parallel_jobs')
        self.parallel_jobs = tk.IntVar(value=jobs if isinstance(jobs, int) and 1 <= jobs <= 8 else 3)
        self.language = tk.StringVar(value=s.get('language') if s.get('language') in ('auto', 'en', 'ja') else 'auto')
        self.theme = tk.StringVar(value=s.get('theme') if s.get('theme') in theme.MODES else 'system')
        self.status = tk.StringVar(value='')
        self.report = None
        self.tasks = TaskRunner(root)
        self.pages: dict = {}
        self.frames: dict = {}
        self.nav: dict = {}
        self.current = 'convert'
        for var in (self.include_variants, self.profile_mode, self.parallel_jobs, self.source_kind, self.builtin_target):
            var.trace_add('write', lambda *_: self.save_settings())
        root.protocol('WM_DELETE_WINDOW', self.close)
        set_language(self.language.get())
        theme.apply(root, self.theme.get())
        self.build_shell()
        root.after(700, self.first_run_checks)

    # ---- settings ------------------------------------------------------------------------------------
    def _load_settings(self) -> dict:
        try:
            data = json.loads(self.settings_file.read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def jobs_value(self) -> int:
        try:
            return max(1, min(8, int(self.parallel_jobs.get())))
        except (tk.TclError, ValueError):
            return 3

    def save_settings(self) -> None:
        data = dict(self.settings)  # keep keys this version does not know
        data.update(source_root=self.source_root.get().strip(), blender=self.paths['blender'].get().strip(),
                    include_variants=self.include_variants.get(), profile_mode=self.profile_mode.get(),
                    parallel_jobs=self.jobs_value(), language=self.language.get(), theme=self.theme.get(),
                    source_kind=self.source_kind.get(), builtin_target=self.builtin_target.get(),
                    last_character=self.last_character, game_folder=self.game_folder.get().strip())
        try:
            self.user_data.mkdir(parents=True, exist_ok=True)
            temp = self.settings_file.with_suffix('.tmp')
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            temp.replace(self.settings_file)
            self.settings = data
        except OSError as exc:
            dragon_log.get_logger().warning('settings could not be saved: %s', exc)

    # ---- shell ---------------------------------------------------------------------------------------
    def build_shell(self) -> None:
        from um.gui.page_convert import ConvertPage
        from um.gui.page_settings import SettingsPage
        from um.gui.page_setup import SetupPage
        from um.gui.page_storage import StoragePage
        from um.gui.page_tools import ToolsPage
        for child in self.root.winfo_children():
            child.destroy()
        self.tasks.listeners.clear()
        outer = ttk.Frame(self.root)
        outer.pack(fill='both', expand=True)
        side = ttk.Frame(outer, style='Sidebar.TFrame', width=212)
        side.pack(side='left', fill='y')
        side.pack_propagate(False)
        ttk.Label(side, text='VRMDragonTool', style='Brand.TLabel').pack(anchor='w', padx=18, pady=(20, 0))
        ttk.Label(side, text=tr('VRM to Dragon Engine'), style='SidebarMuted.TLabel').pack(anchor='w', padx=18, pady=(0, 18))
        self.nav = {}
        for key, label in PAGES:
            button = ttk.Button(side, text=tr(label), style='Nav.TButton', command=lambda k=key: self.show_page(k))
            button.pack(fill='x', padx=8, pady=1)
            self.nav[key] = button
        right = ttk.Frame(outer)
        right.pack(side='left', fill='both', expand=True)
        bar = ttk.Frame(right, style='Sidebar.TFrame')
        bar.pack(side='bottom', fill='x')
        self.status_label = ttk.Label(bar, textvariable=self.status, style='Status.TLabel', anchor='w')
        self.status_label.pack(side='left', fill='x', expand=True, padx=14, pady=7)
        self.progress = ttk.Progressbar(bar, mode='indeterminate', length=150)
        content = ttk.Frame(right)
        content.pack(fill='both', expand=True)
        self.pages = {}
        self.frames = {}
        for key, cls in (('convert', ConvertPage), ('tools', ToolsPage), ('setup', SetupPage),
                         ('storage', StoragePage), ('settings', SettingsPage)):
            page = cls(self)
            frame = page.build(content)
            frame.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.pages[key] = page
            self.frames[key] = frame
        self.tasks.on_change(self._busy_changed)
        for page in self.pages.values():
            if hasattr(page, 'on_busy'):
                self.tasks.on_change(page.on_busy)
        self.show_page(self.current)
        if not self.status.get():
            self.status.set(tr('Ready. Nothing is ever installed into the game.'))

    def show_page(self, key: str) -> None:
        self.current = key
        self.frames[key].tkraise()
        for name, button in self.nav.items():
            button.configure(style='NavActive.TButton' if name == key else 'Nav.TButton')
        page = self.pages.get(key)
        if page is not None and hasattr(page, 'on_show'):
            page.on_show()

    def _busy_changed(self, busy: bool) -> None:
        if busy:
            self.progress.pack(side='right', padx=14)
            self.progress.start(14)
        else:
            self.progress.stop()
            self.progress.pack_forget()

    def set_status(self, text: str) -> None:
        self.status.set(text)

    def log_hint(self) -> str:
        return tr('Details were saved to the log. Open "Storage & logs" and create a debug report to share.')

    def blender_usable(self) -> bool:
        value = self.paths['blender'].get().strip()
        return bool(value) and Path(value).is_file()

    # ---- appearance ----------------------------------------------------------------------------------
    def change_appearance(self, setting: str, previous: str) -> None:
        """Called by the Settings page after the language or theme variable changed."""
        if self.tasks.busy:
            messagebox.showinfo(tr('Settings'), tr('Please wait for the current task to finish, then change this setting.'))
            (self.language if setting == 'language' else self.theme).set(previous)
            return
        set_language(self.language.get())
        theme.apply(self.root, self.theme.get())
        self.save_settings()
        self.status.set('')
        self.build_shell()
        self.show_page('settings')

    # ---- lifecycle -----------------------------------------------------------------------------------
    def first_run_checks(self) -> None:
        setup = self.pages.get('setup')
        if setup is not None:
            setup.first_run()

    def close(self) -> None:
        if self.tasks.busy:
            messagebox.showwarning(tr('Busy'), tr('Please wait for the current task to finish before quitting.'))
            return
        try:
            from um.dragon_local_ai import get_runtime
            get_runtime().close()
        except Exception as exc:  # noqa: BLE001 - never block quitting
            dragon_log.get_logger().warning('closing the local AI runtime failed: %s', exc)
        self.save_settings()
        self.root.destroy()
