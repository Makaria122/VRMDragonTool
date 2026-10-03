"""Storage & logs page: clean up generated outputs, create a debug report."""
from __future__ import annotations

import os
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from um import dragon_log
from um.dragon_i18n import tr
from um.gui.widgets import ScrollFrame, WrapLabel, card, scrolled_tree


class StoragePage:
    def __init__(self, app):
        self.app = app
        self.status = tk.StringVar(value=tr('Press "Refresh" to list the outputs.'))
        self.logs_status = tk.StringVar()
        self.rows: dict = {}
        self.buttons: list = []

    def build(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent)
        scroll = ScrollFrame(frame)
        scroll.pack(fill='both', expand=True)
        body = scroll.inner
        body.columnconfigure(0, weight=1)
        ttk.Label(body, text=tr('Storage & logs'), style='Title.TLabel').grid(row=0, column=0, sticky='w', padx=24, pady=(20, 10))

        box = card(body, tr('Generated outputs'))
        box.grid(row=1, column=0, sticky='ew', padx=24, pady=6)
        box.columnconfigure(0, weight=1)
        WrapLabel(box, text=tr('Each conversion keeps its working files in Tool/userdata/outputs. Large working .blend files can '
                               'fill the disk quickly. Deleting cannot be undone. Your extracted game files, installed mods and '
                               'the Mods you copied elsewhere are never touched.'),
                  style='Muted.TLabel').grid(row=0, column=0, sticky='ew', pady=(0, 8))
        columns = (('name', tr('Output folder'), 360), ('size', tr('Size'), 90), ('blend', tr('Working .blend'), 110),
                   ('date', tr('Modified'), 130))
        tree_frame, self.tree = scrolled_tree(box, columns, height=10, selectmode='extended')
        tree_frame.grid(row=1, column=0, sticky='nsew')
        WrapLabel(box, textvariable=self.status, style='Muted.TLabel').grid(row=2, column=0, sticky='ew', pady=6)
        row = ttk.Frame(box)
        row.grid(row=3, column=0, sticky='w')
        self.buttons = []
        for label, command in ((tr('Refresh'), self.refresh), (tr('Select all'), self.select_all),
                               (tr('Delete working .blend files only'), self.delete_blends),
                               (tr('Delete selected folders...'), self.delete_folders),
                               (tr('Open outputs folder'), self.open_outputs)):
            button = ttk.Button(row, text=label, command=command)
            button.pack(side='left', padx=(0, 6))
            self.buttons.append(button)

        logs = card(body, tr('Logs and debug report'))
        logs.grid(row=2, column=0, sticky='ew', padx=24, pady=(6, 24))
        logs.columnconfigure(0, weight=1)
        WrapLabel(logs, text=tr('The tool keeps a log of what it does, including the full output of Blender when a step fails, in '
                                'Tool/userdata/logs (capped at about 12 MB, never uploaded). If something goes wrong, press '
                                '"Create debug report" and attach the file to your bug report. User names and home-folder paths '
                                'are masked, but file names, avatar names and error text are not: read the report before you '
                                'post it.'), style='Muted.TLabel').grid(row=0, column=0, sticky='ew')
        WrapLabel(logs, textvariable=self.logs_status).grid(row=1, column=0, sticky='ew', pady=6)
        row = ttk.Frame(logs)
        row.grid(row=2, column=0, sticky='w')
        for label, command in ((tr('Create debug report'), self.logs_report), (tr('Open logs folder'), self.logs_open),
                               (tr('Delete all logs'), self.logs_delete)):
            ttk.Button(row, text=label, command=command).pack(side='left', padx=(0, 6))
        self.logs_refresh()
        return frame

    def on_show(self) -> None:
        if not self.rows:
            self.logs_refresh()

    def on_busy(self, busy: bool) -> None:
        for button in self.buttons:
            button.configure(state='disabled' if busy else 'normal')

    # ---- outputs ---------------------------------------------------------------------------------------
    def refresh(self) -> None:
        from um.dragon_output_cleanup import list_outputs
        root = self.app.private_output_parent
        self.status.set(tr('Measuring...'))
        self.app.tasks.run(lambda progress: list_outputs(root), on_done=self.show, on_error=self.failed, label='List outputs')

    def failed(self, exc) -> None:
        self.status.set(tr('Failed: {0}', exc))
        messagebox.showerror(tr('Storage'), str(exc))

    def show(self, rows) -> None:
        from um.dragon_output_cleanup import format_size
        self.rows = {row['name']: row for row in rows}
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            self.tree.insert('', 'end', iid=row['name'], values=(
                row['name'], format_size(row['bytes']), format_size(row['blend_bytes']),
                datetime.fromtimestamp(row['mtime']).strftime('%Y-%m-%d %H:%M')))
        total = sum(row['bytes'] for row in rows)
        blends = sum(row['blend_bytes'] for row in rows)
        self.status.set(tr('{0} folder(s), {1} in total; {2} of it is working .blend files.',
                           len(rows), format_size(total), format_size(blends)))

    def select_all(self) -> None:
        self.tree.selection_set(self.tree.get_children())

    def selection(self) -> list:
        names = list(self.tree.selection())
        if not names:
            messagebox.showinfo(tr('Storage'), tr('Select one or more output folders first.'))
        return names

    def delete_folders(self) -> None:
        names = self.selection()
        if not names or self.app.tasks.busy:
            return
        from um.dragon_output_cleanup import delete_outputs, format_size
        size = sum(self.rows[n]['bytes'] for n in names if n in self.rows)
        if not messagebox.askokcancel(
                tr('Delete output folders'),
                tr('Permanently delete {0} output folder(s) ({1})?', len(names), format_size(size)) + '\n'
                + tr('This also deletes the generated mods inside them. It cannot be undone.') + '\n'
                + tr('Mods you already copied elsewhere and the game are not affected.')):
            return
        root = self.app.private_output_parent
        self.status.set(tr('Deleting...'))
        self.app.tasks.run(lambda progress: delete_outputs(root, names), on_done=self.deleted, on_error=self.failed,
                           label='Delete outputs')

    def delete_blends(self) -> None:
        names = self.selection()
        if not names or self.app.tasks.busy:
            return
        from um.dragon_output_cleanup import delete_working_blends, format_size
        size = sum(self.rows[n]['blend_bytes'] for n in names if n in self.rows)
        if not messagebox.askokcancel(
                tr('Delete working .blend files'),
                tr('Delete the working .blend files of {0} output folder(s) ({1})?', len(names), format_size(size)) + '\n'
                + tr('Generated mods, reports and textures are kept. It cannot be undone.')):
            return
        root = self.app.private_output_parent
        self.status.set(tr('Deleting...'))
        self.app.tasks.run(lambda progress: delete_working_blends(root, names), on_done=self.deleted, on_error=self.failed,
                           label='Delete working files')

    def deleted(self, result) -> None:
        from um.dragon_output_cleanup import format_size
        count = len(result.get('deleted', result.get('cleaned', [])))
        text = tr('Done: {0} folder(s) processed, {1} freed.', count, format_size(result['freed_bytes']))
        if result['errors']:
            text += ' ' + tr('{0} could not be processed: ', len(result['errors'])) + '; '.join(
                f"{e['name']} ({e['error']})" for e in result['errors'][:3])
        self.status.set(text)
        self.refresh()

    def open_outputs(self) -> None:
        folder = self.app.private_output_parent
        folder.mkdir(parents=True, exist_ok=True)
        if os.name == 'nt':
            os.startfile(str(folder))

    # ---- logs ------------------------------------------------------------------------------------------
    def logs_refresh(self) -> None:
        size = dragon_log.log_files_size()
        self.logs_status.set(tr('Log folder: {0}  ({1} KB in use)', dragon_log.redact(str(dragon_log.log_dir())), round(size / 1024)))

    def logs_report(self) -> None:
        try:
            dragon_log.get_logger().info('debug report requested')
            path = dragon_log.create_debug_report(outputs=self.app.private_output_parent)
        except Exception as exc:  # noqa: BLE001
            dragon_log.log_exception('Debug report failed', exc)
            messagebox.showerror(tr('Logs'), str(exc))
            return
        self.logs_status.set(tr('Debug report saved: {0}', path.name))
        messagebox.showinfo(tr('Debug report'), tr('Saved {0} in the logs folder.', path.name) + '\n'
                            + tr('It masks user names and home-folder paths, but not file names, avatar names or error text. '
                                 'Read it before sharing.'))
        self.logs_open()

    def logs_open(self) -> None:
        folder = dragon_log.log_dir()
        folder.mkdir(parents=True, exist_ok=True)
        if os.name == 'nt':
            os.startfile(str(folder))

    def logs_delete(self) -> None:
        if not messagebox.askokcancel(tr('Delete all logs'), tr('Delete all log files and debug reports? This cannot be undone.')):
            return
        count = dragon_log.delete_logs()
        dragon_log.setup_logging()  # logging continues in a fresh file
        self.logs_status.set(tr('Deleted {0} file(s).', count))
        self.logs_refresh()
