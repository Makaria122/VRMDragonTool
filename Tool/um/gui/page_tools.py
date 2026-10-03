"""Advanced tools: single pipeline steps, profile creation, merging mods."""
from __future__ import annotations

import json
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from um import dragon_log
from um.dragon_i18n import tr
from um.gui import results
from um.gui.widgets import ScrollFrame, WrapLabel, card, themed_text


class ToolsPage:
    def __init__(self, app):
        self.app = app
        self.buttons: list = []
        self.save_button = None
        self.text = None

    def build(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent)
        scroll = ScrollFrame(frame)
        scroll.pack(fill='both', expand=True)
        body = scroll.inner
        body.columnconfigure(0, weight=1)
        ttk.Label(body, text=tr('Advanced tools'), style='Title.TLabel').grid(row=0, column=0, sticky='w', padx=24, pady=(20, 2))
        WrapLabel(body, text=tr('Single steps of the pipeline for diagnosis. They use the VRM, the character files and the paths '
                                'chosen on the Convert page. Nothing is installed into the game.'),
                  style='Muted.TLabel').grid(row=1, column=0, sticky='ew', padx=24, pady=(0, 10))

        steps = card(body, tr('Pipeline steps'))
        steps.grid(row=2, column=0, sticky='ew', padx=24, pady=6)
        self.add_buttons(steps, (
            (tr('Quick inspection'), self.quick), (tr('Detailed inspection in Blender'), lambda: self.inspect(deep=True)),
            (tr('Working .blend + bone mapping'), lambda: self.inspect(prepare=True)),
            (tr('Torso GMD round-trip test'), self.roundtrip), (tr('VRM → DDS'), self.textures)))

        profile = card(body, tr('VRM profile'))
        profile.grid(row=3, column=0, sticky='ew', padx=24, pady=6)
        profile.columnconfigure(0, weight=1)
        WrapLabel(profile, text=tr('Records the mesh regions, accessory-bone mapping and the ground offset. Existing profiles are '
                                   'reused by the one-click creation.'), style='Muted.TLabel').grid(row=0, column=0, sticky='ew')
        self.add_buttons(profile, ((tr('Create profile'), self.create_profile),), row=1)

        candidates = card(body, tr('Candidates and mods'))
        candidates.grid(row=4, column=0, sticky='ew', padx=24, pady=6)
        self.add_buttons(candidates, (
            (tr('Show why the private draft failed (read-only)'), self.candidate),
            (tr('Create beta candidate (profile required, no game install)'), self.beta),
            (tr('Merge several VRM mods after a compatibility check'), self.combine)))

        output = card(body, tr('Result'))
        output.grid(row=5, column=0, sticky='ew', padx=24, pady=(6, 24))
        output.columnconfigure(0, weight=1)
        self.text = themed_text(output, height=14)
        self.text.grid(row=0, column=0, sticky='ew')
        self.text.configure(state='disabled')
        self.save_button = ttk.Button(output, text=tr('Save JSON report...'), command=self.save, state='disabled')
        self.save_button.grid(row=1, column=0, sticky='w', pady=(8, 0))
        return frame

    def add_buttons(self, parent, items, row: int = 0) -> None:
        holder = ttk.Frame(parent)
        holder.grid(row=row, column=0, sticky='w', pady=(6, 0))
        for text, command in items:
            button = ttk.Button(holder, text=text, command=command)
            button.pack(side='left', padx=(0, 8), pady=2)
            self.buttons.append(button)

    def on_busy(self, busy: bool) -> None:
        for button in self.buttons:
            button.configure(state='disabled' if busy else 'normal')

    # ---- running a tool ----------------------------------------------------------------------------------
    def values(self) -> dict:
        return {key: var.get().strip() for key, var in self.app.paths.items()}

    def run_tool(self, work, status: str) -> None:
        app = self.app
        app.report = None
        self.save_button.configure(state='disabled')
        app.set_status(status)

        def progress(text):
            dragon_log.get_logger().info('progress: %s', text)
            app.set_status(str(text))
        app.tasks.run(work, on_done=self.done, on_error=self.failed, on_progress=progress, label='Tool')

    def failed(self, exc) -> None:
        self.app.set_status(tr('Stopped: {0}', exc))
        messagebox.showerror(tr('Processing error'), str(exc) + '\n\n' + self.app.log_hint())

    def done(self, result) -> None:
        app = self.app
        app.report = result
        self.save_button.configure(state='normal')
        folder = results.result_folder(result) if isinstance(result, dict) else None
        if folder is not None:
            results.open_folder(folder)
        if result.get('avatar_profile_path'):
            app.set_status(tr('Saved: {0}', result['avatar_profile_path']))
        else:
            app.set_status(results.describe(result))
        self.text.configure(state='normal')
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', results.report_text(result))
        self.text.configure(state='disabled')

    def target(self) -> str | None:
        target_id = self.app.target_id.get()
        if not target_id:
            messagebox.showinfo(tr('Character'), tr('Choose a character on the Convert page first.'))
            return None
        return target_id

    # ---- the tools -----------------------------------------------------------------------------------------
    def quick(self) -> None:
        from um.dragon import inspect
        v = self.values()
        if not v['vrm'] or not v['tops']:
            messagebox.showerror(tr('Missing input'), tr('Specify the VRM and the torso GMD.'))
            return
        self.run_tool(lambda progress: inspect(v['vrm'], v['tops'], v['face'] or None, v['hair'] or None),
                      tr('Running the quick inspection... (no game files are changed)'))

    def inspect(self, deep: bool = True, prepare: bool = False) -> None:
        from um.dragon import inspect_blender
        v = self.values()
        if not v['vrm'] or not v['tops']:
            messagebox.showerror(tr('Missing input'), tr('Specify the VRM and the torso GMD.'))
            return
        if not v['blender'] or not v['addon']:
            messagebox.showerror(tr('Missing input'), tr('Specify Blender and the local GMD add-on folder.'))
            return
        target_id = self.target()
        if target_id is None:
            return
        workspace = None
        if prepare:
            chosen = filedialog.asksaveasfilename(defaultextension='.blend', initialfile='VRM_Reference.blend',
                                                  filetypes=[('Blender', '*.blend')])
            if not chosen:
                return
            workspace = Path(chosen)
            if workspace.exists():
                messagebox.showerror(tr('Output folder'), tr('An existing .blend is never overwritten. Choose a new file name.'))
                return
        self.run_tool(lambda progress: inspect_blender(v['vrm'], v['tops'], v['blender'], v['addon'], v['face'] or None,
                                                        v['hair'] or None, workspace=workspace, target_id=target_id),
                      tr('Preparing the offline working .blend...') if prepare else tr('Running the detailed inspection in Blender...'))

    def roundtrip(self) -> None:
        from um.dragon import roundtrip_gmd
        from um.dragon_targets import get_target
        v = self.values()
        if not v['tops'] or not v['blender'] or not v['addon']:
            messagebox.showerror(tr('Missing input'), tr('Specify Blender and the local GMD add-on folder.'))
            return
        target_id = self.target()
        if target_id is None:
            return
        spec = get_target(target_id)
        chosen = filedialog.asksaveasfilename(defaultextension='.gmd', initialfile=spec.slots[0].stem + '.gmd',
                                              filetypes=[('GMD', '*.gmd')])
        if not chosen:
            return
        copy_path = Path(chosen)
        if copy_path.exists():
            messagebox.showerror(tr('Output folder'), tr('Original GMDs and existing files are never overwritten. Choose a different name.'))
            return
        self.run_tool(lambda progress: roundtrip_gmd(v['tops'], v['blender'], v['addon'], copy_path,
                                                      expected_bone_count=spec.bone_count),
                      tr('Round-trip checking the torso GMD on a private copy...'))

    def textures(self) -> None:
        from um.dragon_textures import extract
        v = self.values()
        if not v['vrm']:
            messagebox.showerror(tr('Missing input'), tr('Specify the VRM and the torso GMD.'))
            return
        parent = filedialog.askdirectory(title=tr('Parent folder for a new DDS folder (outside the game)'))
        if not parent:
            return
        texture_dir = Path(parent) / (Path(v['vrm']).stem + '_DDS')
        if texture_dir.exists():
            messagebox.showerror(tr('Output folder'), tr('A DDS folder with the same name already exists. Choose a different parent folder.'))
            return
        self.run_tool(lambda progress: extract(v['vrm'], texture_dir), tr('Generating private DDS files...'))

    def create_profile(self) -> None:
        app = self.app
        v = self.values()
        if any(not v[key] for key in ('vrm', 'tops', 'face', 'hair', 'blender', 'addon')):
            messagebox.showerror(tr('Missing input'), tr('Specify the VRM, the tops/face/hair reference GMDs, Blender and the add-on.'))
            return
        target_id = self.target()
        if target_id is None:
            return
        if app.profile_mode.get() == 'detailed':
            from um.dragon_local_ai import get_runtime
            info = get_runtime().status()
            if not info['installed'] or not info['model_available']:
                messagebox.showerror(tr('AI setup missing'), tr('Install Ollama and Qwen on the Setup page. An existing global Ollama is never used.'))
                return
        refs = {role: v[role] for role in ('tops', 'face', 'hair')}
        profile_root = app.private_output_parent.parent / 'Profiles'
        mode = app.profile_mode.get()

        def work(progress):
            from um.dragon_profile_workflow import create_avatar_profile
            return create_avatar_profile(v['vrm'], refs, v['blender'], v['addon'], profile_root, progress=progress,
                                         target_id=target_id, profile_mode=mode)
        self.run_tool(work, tr('Inspecting and creating the profile with the local AI...') if mode == 'detailed'
                      else tr('Inspecting and creating the profile with rules (simple mode)...'))

    def candidate(self) -> None:
        folder = filedialog.askdirectory(title=tr('Private candidate folder (where status.json is)'))
        if not folder:
            return

        def work(progress):
            from um.dragon_candidate import check_draft
            return check_draft(folder)
        self.run_tool(work, tr("Reading the offline candidate's validation results..."))

    def beta(self) -> None:
        app = self.app
        v = self.values()
        if not v['vrm'] or not v['blender'] or not v['addon']:
            messagebox.showerror(tr('Missing input'), tr('Specify the VRM, Blender and the GMD add-on.'))
            return
        default = app.user_data / 'Profiles' / 'beta-profile.json'
        profile = filedialog.askopenfilename(title=tr('Select the private beta profile that matches the chosen VRM'),
                                             initialdir=str(default.parent), initialfile=default.name,
                                             filetypes=[('JSON', '*.json')])
        if not profile:
            return
        app.private_output_parent.mkdir(parents=True, exist_ok=True)
        output = app.private_output_parent / ('VRM_Beta_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
        if output.exists():
            messagebox.showerror(tr('Output folder'), tr('A candidate folder with the same name exists. Wait a moment and retry.'))
            return
        if not messagebox.askokcancel(tr('Offline beta'),
                                      tr('A private candidate is generated only when the selected VRM matches the profile. GMDs '
                                         'remain even if the motion check fails, but nothing is installed into the game. Continue?')):
            return

        def work(progress):
            from um.dragon_beta import build
            return build(profile, v['vrm'], output, v['blender'], v['addon'], progress=progress)
        self.run_tool(work, tr('Generating the private beta candidate and running the 4 motion checks...'))

    def combine(self) -> None:
        app = self.app
        sources: list = []
        initial = str(app.bundle / 'ModOutputs')
        while True:
            folder = filedialog.askdirectory(title=tr('Select an existing VRM mod folder (read-only)'), initialdir=initial, mustexist=True)
            if not folder:
                break
            sources.append(folder)
            initial = folder
            if not messagebox.askyesno(tr('Add input mod'), tr('Add another mod folder?')):
                break
        if len(sources) < 2:
            if sources:
                messagebox.showwarning(tr('Too few mods'), tr('Merging needs two or more different mod folders.'))
            return
        app.private_output_parent.mkdir(parents=True, exist_ok=True)
        output = app.private_output_parent / ('VRM_Merged_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
        if output.exists():
            messagebox.showerror(tr('Output folder'), tr('An output folder with the same name already exists. Please retry.'))
            return
        title = 'VRM Combined ' + datetime.now().strftime('%Y%m%d_%H%M%S')
        if not messagebox.askokcancel(tr('Check compatibility and merge'),
                                      tr('Inspects {0} mod(s) by relative path. It stops if different content shares a path and '
                                         'only de-duplicates identical content. Nothing is installed into the game and no '
                                         'existing file is changed. Continue?', len(sources))):
            return

        def work(progress):
            from um.dragon_mod_package import combine_mod_folders
            return combine_mod_folders(sources, output, title)
        self.run_tool(work, tr('Checking file collisions between mods and creating a new merged package...'))

    def save(self) -> None:
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
