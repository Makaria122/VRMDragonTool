"""Find every part of a character by name (checkbox list) and add characters from single GMD files."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from um import dragon_custom_targets as custom
from um import dragon_log
from um import dragon_theme as theme
from um.dragon_i18n import tr
from um.gui.widgets import WrapLabel, scrolled_tree


class CharacterPicker:
    """Folder + name -> list of matching GMDs with tick boxes -> 'Add this character'."""

    def __init__(self, app, on_added):
        self.app = app
        self.on_added = on_added
        self.name = tk.StringVar()
        self.label = tk.StringVar()
        self.state = tk.StringVar(value=tr('Example: ichiban'))
        self.data = {'cands': [], 'base': {}, 'inspections': {}, 'selected': set(), 'default': set()}
        self.buttons: list = []
        self.add_button = None
        self.tree = None

    # ---- layout ----------------------------------------------------------------------------------------
    def build(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text=tr('Folder with the extracted files')).grid(row=0, column=0, sticky='w', pady=3)
        ttk.Entry(frame, textvariable=self.app.game_folder).grid(row=0, column=1, sticky='ew', padx=6, pady=3)
        ttk.Button(frame, text=tr('Browse...'), command=self.browse_folder).grid(row=0, column=2, pady=3)
        ttk.Label(frame, text=tr('Character name')).grid(row=1, column=0, sticky='w', pady=3)
        name_row = ttk.Frame(frame)
        name_row.grid(row=1, column=1, sticky='w', padx=6, pady=3)
        entry = ttk.Entry(name_row, textvariable=self.name, width=28)
        entry.pack(side='left')
        entry.bind('<Return>', lambda e: self.search())
        self.search_button = ttk.Button(name_row, text=tr('Search'), command=self.search)
        self.search_button.pack(side='left', padx=8)
        self.buttons.append(self.search_button)
        WrapLabel(frame, textvariable=self.state, style='Muted.TLabel').grid(row=2, column=0, columnspan=3, sticky='ew', pady=(4, 6))
        columns = (('use', tr('Use'), 46), ('role', tr('Part'), 54), ('file', tr('File'), 240),
                   ('bones', tr('Bones'), 52), ('note', tr('Note'), 330))
        tree_frame, self.tree = scrolled_tree(frame, columns, height=7, selectmode='none')
        tree_frame.grid(row=3, column=0, columnspan=3, sticky='nsew')
        self.tree.bind('<Button-1>', self.toggle)
        ticks = ttk.Frame(frame)
        ticks.grid(row=4, column=0, columnspan=3, sticky='w', pady=(8, 0))
        for text, command in ((tr('Tick all usable'), self.tick_all), (tr('Untick all'), self.untick_all),
                              (tr('Default'), self.reset)):
            button = ttk.Button(ticks, text=text, command=command)
            button.pack(side='left', padx=(0, 6))
            self.buttons.append(button)
        adding = ttk.Frame(frame)
        adding.grid(row=5, column=0, columnspan=3, sticky='ew', pady=(8, 0))
        adding.columnconfigure(1, weight=1)
        ttk.Label(adding, text=tr('Name in the list')).grid(row=0, column=0, sticky='w')
        ttk.Entry(adding, textvariable=self.label).grid(row=0, column=1, sticky='ew', padx=8)
        self.add_button = ttk.Button(adding, text=tr('Add this character'), style='Accent.TButton',
                                     command=self.add, state='disabled')
        self.add_button.grid(row=0, column=2)
        return frame

    def set_busy(self, busy: bool) -> None:
        state = 'disabled' if busy else 'normal'
        for button in self.buttons:
            button.configure(state=state)
        if self.add_button is not None:
            self.add_button.configure(state='disabled' if busy or not self.data['base'].get('tops') else 'normal')

    def browse_folder(self) -> None:
        chosen = filedialog.askdirectory(title=tr('Folder with the extracted game files'), mustexist=True)
        if chosen:
            self.app.game_folder.set(chosen)
            self.app.save_settings()

    # ---- the list --------------------------------------------------------------------------------------
    def show(self) -> None:
        self.tree.delete(*self.tree.get_children())
        base_stems = {c['stem'] for c in self.data['base'].values()}
        for c in self.data['cands']:
            mark = '[x]' if c['stem'] in self.data['selected'] else ('[ ]' if c['ok'] else '[-]')
            reasons = [] if c['ok'] else [c['reason'].splitlines()[0][:70]]
            if c['flags']:
                reasons.append(', '.join(tr(flag) for flag in c['flags']))
            note = tr('base set (always added)') if c['stem'] in base_stems else '; '.join(r for r in reasons if r)
            self.tree.insert('', 'end', iid=c['stem'], values=(mark, tr(c['role']), c['stem'], c['bone_count'] or '', note))
        usable = sum(1 for c in self.data['cands'] if c['ok'])
        self.state.set(tr('{0} files found, {1} usable; {2} will be added (including the {3} files of the base set). '
                          'Click [ ] / [x] to change.', len(self.data['cands']), usable, len(self.data['selected']),
                          len(base_stems)))

    def toggle(self, event) -> None:
        if self.tree.identify_region(event.x, event.y) != 'cell' or self.tree.identify_column(event.x) != '#1':
            return
        stem = self.tree.identify_row(event.y)
        item = next((c for c in self.data['cands'] if c['stem'] == stem), None)
        if item is None or not item['ok'] or stem in {c['stem'] for c in self.data['base'].values()}:
            return
        self.data['selected'].symmetric_difference_update({stem})
        self.show()

    def tick_all(self) -> None:
        self.data['selected'] = {c['stem'] for c in self.data['cands'] if c['ok']}
        self.show()

    def untick_all(self) -> None:
        self.data['selected'] = {c['stem'] for c in self.data['base'].values()}
        self.show()

    def reset(self) -> None:
        self.data['selected'] = set(self.data['default'])
        self.show()

    # ---- search ----------------------------------------------------------------------------------------
    def search(self) -> None:
        root, text = self.app.game_folder.get().strip(), self.name.get().strip()
        if not root or not text:
            self.state.set(tr('Choose the folder and type the character name first.'))
            return
        if not self.app.blender_usable():
            messagebox.showinfo(tr('Blender'), tr('Set up Blender first (Setup page); it is needed to read the GMD files.'))
            return
        if self.app.tasks.busy:
            return
        self.state.set(tr('Searching...'))
        blender, addon = Path(self.app.paths['blender'].get().strip()), Path(self.app.paths['addon'].get().strip())

        def work(progress):
            cands = custom.scan_character(root, text)
            items = [(c['role'], c['path']) for c in cands if c['role'] in custom.ROLES]
            if not items:
                raise custom.CustomTargetError(tr('No body, face or hair GMD with "{0}" in its name was found in that folder.', text))
            inspections = custom.inspect_paths(
                items, blender, addon,
                progress=lambda done, total: progress(tr('Reading the GMD files with Blender... {0}/{1}', done, total)))
            custom.classify(cands, inspections)
            base = custom.suggest_base(cands)
            selected = custom.default_selection(cands, base)
            return {'cands': cands, 'inspections': inspections, 'base': base, 'selected': set(selected),
                    'default': set(selected)}
        self.app.tasks.run(work, on_done=self._found, on_error=self._failed, on_progress=self.state.set,
                           label='Character search')

    def _found(self, payload) -> None:
        self.data = payload
        self.show()
        if self.data['base'].get('tops'):
            if not self.label.get():
                self.label.set(tr('{0} (all parts)', self.name.get().strip().title()))
            self.add_button.configure(state='normal')
        else:
            self.add_button.configure(state='disabled')
            self.state.set(self.state.get() + ' ' + tr('No usable body (tops) file was found, so nothing can be added.'))

    def _failed(self, exc) -> None:
        text = str(exc)
        if isinstance(exc, custom.CustomTargetError):
            dragon_log.get_logger().error('Character search refused: %s', exc)
        else:
            text += '\n\n' + self.app.log_hint()
        self.state.set(text)
        messagebox.showerror(tr('Custom target'), text)

    # ---- add -------------------------------------------------------------------------------------------
    def add(self) -> None:
        base = self.data['base']
        if not base.get('tops') or self.app.tasks.busy:
            return
        files = {role: c['path'] for role, c in base.items()}
        base_inspections = {role: self.data['inspections'][str(Path(c['path']).resolve())] for role, c in base.items()}
        chosen = [c for c in self.data['cands'] if c['stem'] in self.data['selected']]
        target_id = custom.sanitize_id(base['tops']['stem'])
        from um.dragon_targets import target_ids
        replace = False
        if target_id in target_ids():
            if not messagebox.askokcancel(tr('Custom target'), tr('A custom target named {0} already exists. Replace it?', target_id)):
                return
            replace = True
        title = self.label.get().strip() or None
        self.state.set(tr('Copying the files into the private store...'))

        def work(progress):
            definition = custom.build_definition(files, base_inspections, label=title)
            definition, skipped = custom.add_parts(definition, chosen)
            saved = custom.import_and_save(definition, files, replace=replace,
                                           part_files={c['stem']: c['path'] for c in chosen})
            return saved, skipped
        self.app.tasks.run(work, on_done=self._added, on_error=self._failed, label='Add character')

    def _added(self, payload) -> None:
        saved, skipped = payload
        extra = tr('{0} extra parts.', len(saved['parts']))
        if skipped:
            extra += ' ' + tr('{0} left out: ', len(skipped)) + ', '.join(
                f"{s['stem']} ({s['reason'][:40]})" for s in skipped[:4]) + ('...' if len(skipped) > 4 else '')
        self.on_added(saved, extra)


def open_single_dialog(app, on_added) -> None:
    """Add a character from one to three GMD files chosen by hand (body required, face/hair optional)."""
    if not app.blender_usable():
        messagebox.showinfo(tr('Blender'), tr('Set up Blender first (Setup page); it is needed to read the GMD files.'))
        return
    win = tk.Toplevel(app.root)
    theme.register(win, 'toplevel')
    win.title(tr('Add from single GMD files'))
    win.transient(app.root)
    try:
        win.grab_set()
    except tk.TclError:
        pass  # not viewable yet; the dialog still works
    frame = ttk.Frame(win, padding=14)
    frame.pack(fill='both', expand=True)
    frame.columnconfigure(1, weight=1)
    WrapLabel(frame, text=tr('Use GMD files from any Dragon Engine game that you extracted yourself. The tool reads them once, '
                             'checks that their skeleton fits, and keeps private copies in Tool/userdata/targets. The game '
                             'folder is never changed. In-game results are unverified.'),
              style='Muted.TLabel').grid(row=0, column=0, columnspan=3, sticky='ew', pady=(0, 8))
    values = {role: tk.StringVar() for role in ('tops', 'face', 'hair')}
    name = tk.StringVar()

    def browse(role):
        chosen = filedialog.askopenfilename(parent=win, title=tr('Select the {0} GMD', tr(role)), filetypes=[('GMD', '*.gmd')])
        if not chosen:
            return
        values[role].set(chosen)
        if role == 'tops':
            for other, found in custom.find_siblings(chosen).items():
                if not values[other].get():
                    values[other].set(str(found))
            if not name.get():
                name.set(Path(chosen).stem)
    for row, (role, text) in enumerate((('tops', tr('Body GMD (tops, required)')), ('face', tr('Face GMD (optional)')),
                                         ('hair', tr('Hair GMD (optional)'))), start=1):
        ttk.Label(frame, text=text).grid(row=row, column=0, sticky='w', pady=3)
        ttk.Entry(frame, textvariable=values[role], width=58).grid(row=row, column=1, sticky='ew', padx=6, pady=3)
        ttk.Button(frame, text=tr('Browse...'), command=lambda r=role: browse(r)).grid(row=row, column=2, pady=3)
    ttk.Label(frame, text=tr('Name')).grid(row=4, column=0, sticky='w', pady=3)
    ttk.Entry(frame, textvariable=name, width=58).grid(row=4, column=1, sticky='ew', padx=6, pady=3)
    state = tk.StringVar(value=tr('Choose the body GMD; the face and hair GMDs next to it are found automatically.'))
    WrapLabel(frame, textvariable=state, style='Muted.TLabel').grid(row=5, column=0, columnspan=3, sticky='ew', pady=8)
    buttons = ttk.Frame(frame)
    buttons.grid(row=6, column=0, columnspan=3)
    add_button = ttk.Button(buttons, text=tr('Inspect and add'), style='Accent.TButton')
    add_button.pack(side='left', padx=6)
    ttk.Button(buttons, text=tr('Close'), command=win.destroy).pack(side='left', padx=6)

    def failed(exc):
        add_button.configure(state='normal')
        text = str(exc)
        if isinstance(exc, custom.CustomTargetError):
            dragon_log.get_logger().error('Custom target refused: %s', exc)
        else:
            text += '\n\n' + app.log_hint()
        state.set(text)
        messagebox.showerror(tr('Custom target'), text, parent=win)

    def done(saved):
        win.destroy()
        on_added(saved, '')

    def add():
        files = {role: Path(var.get().strip()) for role, var in values.items() if var.get().strip()}
        if 'tops' not in files:
            state.set(tr('Choose the body (tops) GMD first.'))
            return
        try:
            target_id = custom.sanitize_id(files['tops'].stem)
        except custom.CustomTargetError as exc:
            state.set(str(exc))
            return
        siblings = {role: found for role, found in custom.find_siblings(files['tops']).items() if role not in files}
        if siblings and messagebox.askyesno(
                tr('Custom target'), tr('The {0} GMD found next to the body GMD can be added too (recommended for a full '
                                        'character). Add them?', ' + '.join(tr(r) for r in siblings)), parent=win):
            files.update(siblings)
            for role, found in siblings.items():
                values[role].set(str(found))
        from um.dragon_targets import target_ids
        replace = False
        if target_id in target_ids():
            if not messagebox.askokcancel(tr('Custom target'), tr('A custom target named {0} already exists. Replace it?', target_id), parent=win):
                return
            replace = True
        add_button.configure(state='disabled')
        state.set(tr('Reading the GMD files with Blender...'))
        blender, addon = Path(app.paths['blender'].get().strip()), Path(app.paths['addon'].get().strip())
        label = name.get().strip() or None

        def work(progress):
            inspections = custom.inspect_files(files, blender, addon)
            definition = custom.build_definition(files, inspections, label=label)
            return custom.import_and_save(definition, files, replace=replace)
        app.tasks.run(work, on_done=done, on_error=failed, label='Custom target')
    add_button.configure(command=add)
