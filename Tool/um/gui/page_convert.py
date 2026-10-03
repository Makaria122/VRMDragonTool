"""The main page: choose a character, choose a VRM, convert."""
from __future__ import annotations

import json
import re
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from um import dragon_custom_targets as custom
from um import dragon_log
from um.dragon_i18n import tr
from um.gui import results
from um.gui.character_picker import CharacterPicker, open_single_dialog
from um.gui.widgets import Collapsible, ScrollFrame, WrapLabel, card, path_row, themed_text


CUSTOM_NOTE = 'Custom target from your own GMD files; compatibility with the game and in-game appearance are unverified.'


class ConvertPage:
    def __init__(self, app):
        self.app = app
        self.picker = None
        self.character_ids: dict = {}
        self.character_label = tk.StringVar()
        self.info = tk.StringVar()
        self.convert_button = None
        self.open_button = None
        self.save_button = None
        self.remove_button = None
        self.last_output: Path | None = None
        self.details = None

    # ---- layout ----------------------------------------------------------------------------------------
    def build(self, parent) -> ttk.Frame:
        app = self.app
        frame = ttk.Frame(parent)
        scroll = ScrollFrame(frame)
        scroll.pack(fill='both', expand=True)
        body = scroll.inner
        body.columnconfigure(0, weight=1)
        ttk.Label(body, text=tr('Convert a VRM'), style='Title.TLabel').grid(row=0, column=0, sticky='w', padx=24, pady=(20, 2))
        WrapLabel(body, text=tr('Replace a game character with your own VRM avatar. Nothing is installed into the game: '
                                'the result is a Mods-format folder that you copy yourself.'),
                  style='Muted.TLabel').grid(row=1, column=0, sticky='ew', padx=24, pady=(0, 14))

        # 1. character -------------------------------------------------------------------------------------
        box = card(body, tr('1. Character'))
        box.grid(row=2, column=0, sticky='ew', padx=24, pady=6)
        box.columnconfigure(0, weight=1)
        kinds = ttk.Frame(box)
        kinds.grid(row=0, column=0, sticky='w', pady=(0, 8))
        ttk.Radiobutton(kinds, text=tr('Any Dragon Engine game: find a character by name'), value='other',
                        variable=app.source_kind, command=self.on_kind_change).pack(anchor='w')
        ttk.Radiobutton(kinds, text=tr('Lost Judgment: built-in characters'), value='builtin',
                        variable=app.source_kind, command=self.on_kind_change).pack(anchor='w', pady=(2, 0))
        self.other = ttk.Frame(box)
        self.builtin = ttk.Frame(box)
        self.build_other(self.other)
        self.build_builtin(self.builtin)
        WrapLabel(box, textvariable=self.info, style='Muted.TLabel').grid(row=3, column=0, sticky='ew', pady=(8, 0))

        # 2. avatar ----------------------------------------------------------------------------------------
        avatar = card(body, tr('2. Avatar'))
        avatar.grid(row=3, column=0, sticky='ew', padx=24, pady=6)
        avatar.columnconfigure(0, weight=1)
        path_row(avatar, tr('VRM avatar (required)'), app.paths['vrm'], browse=lambda: self.browse('vrm'),
                 label_width=22).grid(row=0, column=0, sticky='ew')

        # 3. options ---------------------------------------------------------------------------------------
        options = card(body, tr('3. Options'))
        options.grid(row=4, column=0, sticky='ew', padx=24, pady=6)
        options.columnconfigure(0, weight=1)
        ttk.Checkbutton(options, text=tr('Also convert every other part of the character (other outfits, hair styles, faces)'),
                        variable=app.include_variants).grid(row=0, column=0, sticky='w')
        modes = ttk.Frame(options)
        modes.grid(row=1, column=0, sticky='w', pady=(8, 0))
        ttk.Label(modes, text=tr('Profile creation'), width=22).grid(row=0, column=0, sticky='w')
        ttk.Radiobutton(modes, text=tr('Simple (no AI, rule-based)'), value='simple',
                        variable=app.profile_mode).grid(row=0, column=1, sticky='w', padx=(0, 18))
        ttk.Radiobutton(modes, text=tr('Detailed (local AI, needs setup)'), value='detailed',
                        variable=app.profile_mode).grid(row=0, column=2, sticky='w')
        jobs = ttk.Frame(options)
        jobs.grid(row=2, column=0, sticky='w', pady=(8, 0))
        ttk.Label(jobs, text=tr('Parallel Blender jobs'), width=22).pack(side='left')
        ttk.Spinbox(jobs, from_=1, to=8, width=4, textvariable=app.parallel_jobs).pack(side='left')
        ttk.Label(jobs, text=tr('more is faster but needs more memory'), style='Muted.TLabel').pack(side='left', padx=10)

        # advanced paths -----------------------------------------------------------------------------------
        advanced = Collapsible(body, tr('Advanced: reference files and paths'))
        advanced.grid(row=5, column=0, sticky='ew', padx=24, pady=(6, 0))
        rows = (('tops', tr('Body GMD (tops)')), ('face', tr('Face GMD')), ('hair', tr('Hair GMD')))
        for index, (role, label) in enumerate(rows):
            path_row(advanced.body, label, app.paths[role], browse=lambda r=role: self.browse(r)).grid(row=index, column=0, sticky='ew')
        path_row(advanced.body, tr('Blender executable'), app.paths['blender'],
                 browse=lambda: self.browse('blender')).grid(row=3, column=0, sticky='ew')
        path_row(advanced.body, tr('GMD add-on folder'), app.paths['addon'],
                 browse=lambda: self.browse('addon')).grid(row=4, column=0, sticky='ew')
        path_row(advanced.body, tr('Motion-check Action (optional)'), app.action_blend,
                 browse=self.choose_action).grid(row=5, column=0, sticky='ew')
        advanced.body.columnconfigure(0, weight=1)

        # convert ------------------------------------------------------------------------------------------
        actions = ttk.Frame(body)
        actions.grid(row=6, column=0, sticky='ew', padx=24, pady=(16, 6))
        self.convert_button = ttk.Button(actions, text=tr('Convert'), style='Accent.TButton', command=self.start_convert)
        self.convert_button.pack(side='left')
        self.open_button = ttk.Button(actions, text=tr('Open output folder'), command=self.open_output, state='disabled')
        self.open_button.pack(side='left', padx=10)
        self.save_button = ttk.Button(actions, text=tr('Save report...'), command=self.save_report, state='disabled')
        self.save_button.pack(side='left')
        details = Collapsible(body, tr('Details (JSON report)'))
        details.grid(row=7, column=0, sticky='ew', padx=24, pady=(6, 24))
        self.details = themed_text(details.body, height=12)
        self.details.pack(fill='both', expand=True)
        self.details.configure(state='disabled')

        self.refresh_characters()
        self.on_kind_change()
        return frame

    def build_other(self, frame) -> None:
        app = self.app
        frame.columnconfigure(0, weight=1)
        row = ttk.Frame(frame)
        row.grid(row=0, column=0, sticky='ew')
        row.columnconfigure(1, weight=1)
        ttk.Label(row, text=tr('Saved characters'), width=22).grid(row=0, column=0, sticky='w')
        self.character_box = ttk.Combobox(row, textvariable=self.character_label, state='readonly')
        self.character_box.grid(row=0, column=1, sticky='ew', padx=6)
        self.character_box.bind('<<ComboboxSelected>>', self.select_target)
        self.remove_button = ttk.Button(row, text=tr('Remove'), command=self.remove_character)
        self.remove_button.grid(row=0, column=2)
        ttk.Separator(frame).grid(row=1, column=0, sticky='ew', pady=10)
        self.add_box = Collapsible(frame, tr('Add a character (search by name)'), opened=not custom.list_ids())
        self.add_box.grid(row=2, column=0, sticky='ew')
        holder = self.add_box.body
        holder.columnconfigure(0, weight=1)
        WrapLabel(holder, text=tr('Choose the folder with the files you extracted from the game and type the character name: '
                                 'every body, face and hair file whose name contains it is found and checked. Undressed, '
                                 'swimwear, dead, other-age, test and special-pose models are left unticked. The game '
                                 'folder is only read, never changed. In-game results are unverified.'),
                  style='Muted.TLabel').grid(row=0, column=0, sticky='ew', pady=(2, 8))
        self.picker = CharacterPicker(app, self.on_added)
        self.picker.build(holder).grid(row=1, column=0, sticky='ew')
        ttk.Button(holder, text=tr('Add from single GMD files...'), style='Link.TButton',
                   command=lambda: open_single_dialog(app, self.on_added)).grid(row=2, column=0, sticky='w', pady=(8, 0))

    def build_builtin(self, frame) -> None:
        app = self.app
        from um.dragon_targets import builtin_ids
        frame.columnconfigure(0, weight=1)
        row = ttk.Frame(frame)
        row.grid(row=0, column=0, sticky='ew')
        ttk.Label(row, text=tr('Character'), width=22).pack(side='left')
        box = ttk.Combobox(row, textvariable=app.builtin_target, state='readonly', values=list(builtin_ids()), width=20)
        box.pack(side='left')
        box.bind('<<ComboboxSelected>>', self.select_target)
        ttk.Button(row, text=tr('Targets and exclusions'), command=self.show_variants).pack(side='left', padx=10)
        source = path_row(frame, tr('Extracted Chara folder'), app.source_root, browse=self.choose_source, label_width=22)
        source.grid(row=1, column=0, sticky='ew', pady=(6, 0))
        WrapLabel(frame, text=tr('Additional characters are experimental and need in-game checks'),
                  style='Muted.TLabel').grid(row=2, column=0, sticky='ew')

    # ---- character selection -----------------------------------------------------------------------------
    def on_kind_change(self) -> None:
        if self.app.source_kind.get() == 'other':
            self.builtin.grid_remove()
            self.other.grid(row=1, column=0, sticky='ew')
        else:
            self.other.grid_remove()
            self.builtin.grid(row=1, column=0, sticky='ew')
        self.select_target()

    def refresh_characters(self, select_id: str | None = None) -> None:
        from um.dragon_targets import get_target, target_ids
        labels: dict = {}
        for target_id in (i for i in target_ids() if i.startswith('custom_')):
            try:
                label = get_target(target_id).label
            except ValueError:
                label = f"{target_id} ({tr('unreadable')})"
            if label in labels:
                label = f'{label} [{target_id}]'
            labels[label] = target_id
        self.character_ids = labels
        self.character_box.configure(values=list(labels))
        wanted = select_id or self.app.last_character
        chosen = next((label for label, target_id in labels.items() if target_id == wanted), None)
        self.character_label.set(chosen or (next(iter(labels), '')))

    def current_target(self) -> str:
        if self.app.source_kind.get() == 'other':
            return self.character_ids.get(self.character_label.get(), '')
        return self.app.builtin_target.get()

    def select_target(self, _event=None) -> None:
        from um.dragon_targets import get_target, target_references
        app = self.app
        target_id = self.current_target()
        app.target_id.set(target_id)
        for role in ('tops', 'face', 'hair'):
            app.paths[role].set('')
        if self.remove_button is not None:
            self.remove_button.configure(state='normal' if target_id.startswith('custom_') else 'disabled')
        if not target_id:
            self.info.set(tr('No saved character yet. Search for one below (folder + name) and add it.'))
            return
        try:
            target = get_target(target_id)
        except ValueError as exc:
            self.info.set(str(exc))
            return
        if target.custom_references is not None:
            app.last_character = target_id
            try:
                for role, file in target_references(target.id).items():
                    app.paths[role].set(file)
                extra = tr('{0} extra parts (outfits, hair, faces).', len(target.custom_parts)) if target.custom_parts else ''
                note = target.motion_note.replace(CUSTOM_NOTE, tr('Custom target from your own GMD files; compatibility with the game and in-game appearance are unverified.'))
                self.info.set(tr('{0}: {1} bones. {2} {3}', target.label, target.bone_count, extra, note).replace('  ', ' '))
            except (OSError, ValueError) as exc:
                self.info.set(str(exc))
            app.save_settings()
            return
        root = app.source_root.get().strip()
        if not root:
            self.info.set(tr('Select the extracted Chara folder.'))
            return
        try:
            for role, file in target_references(target.id, source_root=root).items():
                app.paths[role].set(file)
            self.info.set(tr('{0}: {1} bones. Reference discovery and strict validation happen at generation time. {2}',
                             target.label, target.bone_count, target.motion_note))
        except (OSError, ValueError) as exc:
            self.info.set(tr('Missing/duplicate references: {0}', exc))

    def on_added(self, saved: dict, extra: str = '') -> None:
        self.refresh_characters(saved['id'])
        self.add_box.set_open(False)
        self.app.source_kind.set('other')
        self.on_kind_change()
        notes = ('\n\n' + '\n'.join(saved['warnings'][:5])) if saved.get('warnings') else ''
        messagebox.showinfo(tr('Custom target'), tr('Added: {0}', saved['label']) + '\n'
                            + tr('{0} bones, layout {1}.', saved['bone_count'], saved['layout']) + (' ' + extra if extra else '') + notes)

    def remove_character(self) -> None:
        target_id = self.current_target()
        if not target_id.startswith('custom_'):
            return
        if not messagebox.askokcancel(tr('Remove custom target'),
                                      tr('Remove {0}? Its private GMD copies are deleted. Mods you already generated and the '
                                         'game files are not affected.', target_id)):
            return
        try:
            custom.delete_target(target_id)
        except Exception as exc:  # noqa: BLE001
            dragon_log.log_exception('Removing a custom target failed', exc)
            messagebox.showerror(tr('Custom target'), str(exc))
            return
        self.app.last_character = ''
        self.refresh_characters()
        self.select_target()

    def show_variants(self) -> None:
        from um.dragon_variants import availability
        app = self.app
        if not app.source_root.get().strip():
            messagebox.showerror(tr('Missing references'), tr('Select the extracted Chara folder.'))
            return
        try:
            rows = availability(app.builtin_target.get(), source_root=app.source_root.get().strip())
        except (OSError, ValueError) as exc:
            messagebox.showerror(tr('Reference search'), str(exc))
            return
        text = '\n'.join(r['id'] + (tr(' [reference found; validated at generation]') if r['ready'] else tr(' [missing] ') + r['reason'])
                         for r in rows)
        text += '\n\n' + tr('Only registered layouts are covered. Unregistered young, dead or special-posture models are never replaced automatically.')
        if app.builtin_target.get() == 'sawa':
            text += '\n' + tr('For Sawa, the approved age-18, dead and seated candidates are included. In-game posture and expression are unverified.')
        messagebox.showinfo(tr('Model switch targets (in-game switching unverified)'), text)

    # ---- paths -----------------------------------------------------------------------------------------
    def choose_source(self) -> None:
        path = filedialog.askdirectory(title=tr('Chara folder extracted from your game (read-only)'), mustexist=True)
        if path:
            self.app.source_root.set(path)
            self.select_target()
            self.app.save_settings()

    def choose_action(self) -> None:
        path = filedialog.askopenfilename(title=tr('Optional: motion Action .blend you provide'), filetypes=[('Blender', '*.blend')])
        if path:
            self.app.action_blend.set(path)

    def browse(self, name: str) -> None:
        if name == 'addon':
            path = filedialog.askdirectory()
        else:
            kinds = {'vrm': ('VRM', '*.vrm'), 'blender': ('Blender', '*.exe')}
            path = filedialog.askopenfilename(filetypes=[kinds.get(name, ('GMD', '*.gmd')), (tr('All files'), '*.*')])
        if path:
            self.app.paths[name].set(path)
            if name == 'blender':
                self.app.save_settings()

    # ---- conversion ------------------------------------------------------------------------------------
    def require_ai(self) -> bool:
        if self.app.profile_mode.get() != 'detailed':
            return True  # simple mode is rule-based and never touches the local AI
        from um.dragon_local_ai import get_runtime
        info = get_runtime().status()
        if not info['installed'] or not info['model_available']:
            messagebox.showerror(tr('AI setup missing'),
                                 tr('Install Ollama and Qwen on the Setup page. An existing global Ollama is never used.'))
            return False
        return True

    def start_convert(self) -> None:
        app = self.app
        values = {key: var.get().strip() for key, var in app.paths.items()}
        target_id = self.current_target()
        if not target_id:
            messagebox.showinfo(tr('Character'), tr('Add a character first, or choose one from the saved characters.'))
            return
        if any(not values[key] for key in ('vrm', 'tops', 'face', 'hair', 'blender', 'addon')):
            if not values['blender']:
                messagebox.showerror(tr('Missing input'), tr('Blender was not found. Set it up on the Setup page.'))
            else:
                messagebox.showerror(tr('Missing input'), tr('Choose a VRM avatar and a character first.'))
            return
        if not self.require_ai():
            return
        action = app.action_blend.get().strip() or None
        app.save_settings()
        app.private_output_parent.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r'[^A-Za-z0-9_-]+', '_', Path(values['vrm']).stem).strip('_')[:32] or 'avatar'
        folder = app.private_output_parent / ('VRM_' + target_id + '_' + stem + '_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
        if folder.exists():
            messagebox.showerror(tr('Output folder'), tr('A private output with the same name exists. Wait a moment and retry.'))
            return
        from um.dragon_targets import get_target
        spec = get_target(target_id)
        is_custom = spec.custom_references is not None
        use_variants = app.include_variants.get() and (not is_custom or bool(spec.custom_parts))
        profile_mode, jobs = app.profile_mode.get(), app.jobs_value()
        source_root = app.source_root.get().strip()
        if use_variants:
            from um.dragon_variants import availability
            if not is_custom and not source_root:
                messagebox.showerror(tr('Missing references'), tr('Specify the extracted Chara folder to generate switch targets.'))
                return
            try:
                count = sum(r['ready'] for r in availability(target_id, source_root=None if is_custom else source_root))
            except (OSError, ValueError) as exc:
                messagebox.showerror(tr('Reference search'), str(exc))
                return
            if not messagebox.askokcancel(tr('Convert switch targets too'),
                                          tr('Converts {0} model(s) individually. In-game support is unverified.', count) + '\n' + tr('Continue?')):
                return
        refs = {role: values[role] for role in ('tops', 'face', 'hair')}
        self.last_output = folder
        app.report = None
        self.save_button.configure(state='disabled')
        self.open_button.configure(state='disabled')
        app.set_status(tr('Inspecting the VRM and creating a mod pack candidate...'))

        def work(progress):
            if use_variants:
                from um.dragon_variants import run_batch as run
            else:
                from um.dragon_oneclick import run
            return run(values['vrm'], refs, values['blender'], values['addon'], action, None, folder, None,
                       progress=progress, target_id=target_id, profile_mode=profile_mode,
                       **({'source_root': None if is_custom else source_root, 'workers': jobs} if use_variants else {}))
        app.tasks.run(work, on_done=self.finished, on_error=self.failed, on_progress=self.progress, label='Conversion')

    def progress(self, text) -> None:
        dragon_log.get_logger().info('progress: %s', text)
        self.app.set_status(str(text))

    def failed(self, exc) -> None:
        self.app.set_status(tr('Stopped: {0}', exc))
        messagebox.showerror(tr('Processing error'), str(exc) + '\n\n' + self.app.log_hint())

    def finished(self, result) -> None:
        app = self.app
        app.report = result
        self.save_button.configure(state='normal')
        folder = results.result_folder(result)
        if folder is not None:
            self.last_output = folder
            self.open_button.configure(state='normal')
            results.open_folder(folder)
        app.set_status(results.describe(result))
        self.details.configure(state='normal')
        self.details.delete('1.0', 'end')
        self.details.insert('1.0', results.report_text(result))
        self.details.configure(state='disabled')

    def open_output(self) -> None:
        if self.last_output is not None and self.last_output.is_dir():
            results.open_folder(self.last_output)

    def save_report(self) -> None:
        app = self.app
        if app.report is None:
            return
        selected = filedialog.asksaveasfilename(defaultextension='.json', initialfile='dragon_report.json', filetypes=[('JSON', '*.json')])
        if not selected:
            return
        target = Path(selected)
        if target.exists():
            messagebox.showwarning(tr('Not saved'), tr('Existing files are never overwritten. Choose a different name.'))
            return
        try:
            with target.open('x', encoding='utf-8') as stream:
                json.dump(app.report, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
        except OSError as exc:
            messagebox.showerror(tr('Save error'), str(exc))
            return
        app.set_status(tr('Report saved: {0}', target))

    def on_busy(self, busy: bool) -> None:
        state = 'disabled' if busy else 'normal'
        self.convert_button.configure(state=state)
        if self.remove_button is not None:
            self.remove_button.configure(state='disabled' if busy else (
                'normal' if self.current_target().startswith('custom_') else 'disabled'))
        if self.picker is not None:
            self.picker.set_busy(busy)
