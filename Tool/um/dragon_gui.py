"""Local, read-only desktop preflight for the Dragon Engine avatar pipeline."""
from __future__ import annotations

import json
import os
import queue
import re
from datetime import datetime
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from um import dragon_log
from um.dragon import inspect, inspect_blender, roundtrip_gmd


OTHER_ENTRY = 'Other (add your own GMD files)...'
LOG_HINT = 'Details were saved to the log. Open the Logs tab and create a debug report to share.'


class DragonWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("VRM → Dragon Engine | Generic VRM Offline Beta")
        root.minsize(760, 550)
        self.paths = {name: tk.StringVar() for name in ("vrm", "tops", "face", "hair", "blender", "addon")}
        bundle = Path(__file__).resolve().parents[2]
        self.bundle = bundle
        self.target_id = tk.StringVar(value='yagami')
        blender = bundle / 'Tool' / 'runtime' / 'blender' / 'blender.exe'
        if not blender.is_file():
            blender = bundle / 'Blender' / 'blender.exe'  # existing private installation compatibility
        addon = bundle / "Tool" / "vendor" / "yakuza-gmd-gmt-blender"
        if blender.is_file():
            self.paths['blender'].set(str(blender))
        if (addon/'yk_gmd_blender'/'__init__.py').is_file():
            self.paths['addon'].set(str(addon))
        self.user_data = bundle / 'Tool' / 'userdata'
        self.beta_profile_default = self.user_data / 'Profiles' / 'beta-profile.json'
        self.private_output_parent = self.user_data / 'outputs'
        self.source_root = tk.StringVar()
        self.action_blend = tk.StringVar()
        self.settings_file = self.user_data / 'settings.json'
        saved_include_variants = True  # default ON; the last choice is restored from settings.json
        saved_profile_mode = 'simple'
        if self.settings_file.is_file():
            try:
                settings=json.loads(self.settings_file.read_text(encoding='utf-8'))
                self.source_root.set(settings.get('source_root',''))
                saved_blender=settings.get('blender')
                if saved_blender and (Path(saved_blender).is_file() or not self.paths['blender'].get()):
                    self.paths['blender'].set(saved_blender)
                if isinstance(settings.get('include_variants'),bool):
                    saved_include_variants = settings['include_variants']
                if settings.get('profile_mode') in ('simple','detailed'):
                    saved_profile_mode = settings['profile_mode']
            except (OSError,ValueError):
                pass
        self.messages: queue.Queue = queue.Queue()
        self.report: dict | None = None
        hint = 'Select the extracted Chara folder and a VRM. AI setup is only needed for the detailed mode. Nothing is installed into the game.'
        self.status = tk.StringVar(value=hint)
        self.notebook=ttk.Notebook(root)
        self.notebook.pack(fill='both',expand=True)
        frame = ttk.Frame(self.notebook, padding=14)
        self.notebook.add(frame,text='One-click mod')
        ttk.Label(frame, text="VRM → Dragon Engine / Lost Judgment β", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Inspect → fit candidates → GMD validation → Mods format with mod-meta.yaml in one run. Nothing is installed into the game.",
                  foreground="#854d0e").pack(anchor="w", pady=(4, 12))
        target_row=ttk.Frame(frame);target_row.pack(fill='x',pady=(0,8))
        ttk.Label(target_row,text='Target character',width=30).pack(side='left')
        from um.dragon_targets import target_ids
        self.last_target='yagami'
        target_box=ttk.Combobox(target_row,textvariable=self.target_id,state='readonly',
                                values=list(target_ids())+[OTHER_ENTRY],width=30)
        target_box.pack(side='left',padx=4)
        target_box.bind('<<ComboboxSelected>>',self.select_target)
        self.target_box=target_box
        self.remove_target_button=ttk.Button(target_row,text='Remove custom target',command=self.remove_custom_target,
                                             state='disabled')
        self.remove_target_button.pack(side='left',padx=4)
        ttk.Label(target_row,text='Additional characters are experimental and need in-game checks').pack(side='left',padx=8)
        source_row=ttk.Frame(frame);source_row.pack(fill='x',pady=3)
        ttk.Label(source_row,text='Extracted Chara folder',width=30).pack(side='left')
        ttk.Entry(source_row,textvariable=self.source_root).pack(side='left',fill='x',expand=True,padx=4)
        ttk.Button(source_row,text='Browse / search...',command=self.choose_source).pack(side='left')
        ttk.Button(source_row,text='Search again',command=self.select_target).pack(side='left',padx=4)
        action_row=ttk.Frame(frame);action_row.pack(fill='x',pady=3)
        ttk.Label(action_row,text='Motion-check Action (optional)',width=30).pack(side='left')
        ttk.Entry(action_row,textvariable=self.action_blend).pack(side='left',fill='x',expand=True,padx=4)
        ttk.Button(action_row,text='Browse...',command=self.choose_action).pack(side='left')
        mode_row=ttk.Frame(frame);mode_row.pack(fill='x',pady=(0,3))
        self.profile_mode=tk.StringVar(value=saved_profile_mode)
        self.profile_mode.trace_add('write',lambda *_:self.save_settings())
        ttk.Label(mode_row,text='Profile creation',width=30).pack(side='left')
        ttk.Radiobutton(mode_row,text='Simple (no AI, rule-based)',value='simple',
                        variable=self.profile_mode).pack(side='left')
        ttk.Radiobutton(mode_row,text='Detailed (local AI, needs setup)',value='detailed',
                        variable=self.profile_mode).pack(side='left',padx=8)
        variant_row=ttk.Frame(frame);variant_row.pack(fill='x',pady=(0,6))
        self.include_variants=tk.BooleanVar(value=saved_include_variants)
        self.include_variants.trace_add('write',lambda *_:self.save_settings())
        ttk.Checkbutton(variant_row,text='Also validate and generate switch targets whose references were found (unverified in-game)',
                        variable=self.include_variants).pack(side='left')
        ttk.Button(variant_row,text='Targets and exclusions',command=self.show_variants).pack(side='left',padx=6)
        for name, label, kind in (
            ("vrm", "VRM (required)", "VRM files (*.vrm)",),
            ("tops", "Torso tops.gmd (required)", "GMD files (*.gmd)"),
            ("face", "Face face.gmd (optional)", "GMD files (*.gmd)"),
            ("hair", "Hair hair.gmd (optional)", "GMD files (*.gmd)"),
            ("blender", "Blender executable (for detailed inspection)", "Blender executable (*.exe)"),
            ("addon", "GMD add-on folder", "folder"),
        ):
            row = ttk.Frame(frame)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=label, width=30).pack(side="left")
            ttk.Entry(row, textvariable=self.paths[name]).pack(side="left", fill="x", expand=True, padx=4)
            ttk.Button(row, text="Browse...", command=lambda key=name, desc=kind: self.browse(key, desc)).pack(side="left")
        primary = ttk.Frame(frame)
        primary.pack(fill='x', pady=(13, 8))
        self.oneclick_button = ttk.Button(primary, text='Create mod pack from VRM automatically (beta, no game install)',
                                          command=self.start_all)
        self.oneclick_button.pack(fill='x')
        self.advanced = ttk.Frame(frame)
        menu = tk.Menu(root)
        menu.add_command(label='Show/hide advanced features', command=self.toggle_advanced)
        root.configure(menu=menu)
        actions = ttk.Frame(self.advanced)
        actions.pack(fill="x", pady=(4, 8))
        self.inspect_button = ttk.Button(actions, text="Quick inspection", command=self.start)
        self.inspect_button.pack(side="left")
        self.deep_button = ttk.Button(actions, text="Detailed inspection in Blender", command=lambda: self.start(deep=True))
        self.deep_button.pack(side="left", padx=8)
        self.prepare_button = ttk.Button(actions, text="Working .blend + bone mapping", command=lambda: self.start(prepare=True))
        self.prepare_button.pack(side="left")
        self.roundtrip_button = ttk.Button(actions, text="Torso GMD round-trip test", command=lambda: self.start(roundtrip=True))
        self.roundtrip_button.pack(side="left", padx=8)
        self.texture_button = ttk.Button(actions, text="VRM → DDS", command=lambda: self.start(textures=True))
        self.texture_button.pack(side="left")
        self.save_button = ttk.Button(actions, text="Save JSON report...", command=self.save, state="disabled")
        self.save_button.pack(side="left", padx=8)
        review = ttk.Frame(self.advanced)
        review.pack(fill="x", pady=(0, 8))
        self.candidate_button = ttk.Button(review, text="Show why the private draft failed (read-only)", command=self.start_candidate)
        self.candidate_button.pack(side="left")
        self.beta_button = ttk.Button(review, text="Create beta candidate (profile required, no game install)", command=self.start_beta)
        self.beta_button.pack(side="left", padx=12)
        self.combine_button=ttk.Button(review,text='Merge several VRM mods after a compatibility check',command=self.start_combine_mods)
        self.combine_button.pack(side='left',padx=8)
        ttk.Label(frame, textvariable=self.status, wraplength=720).pack(anchor="w", pady=(0, 8))
        output = ttk.Frame(frame)
        output.pack(fill="both", expand=True)
        self.text = tk.Text(output, wrap="word", state="disabled", font=("Consolas", 10))
        scroll = ttk.Scrollbar(output, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.profile_tab=ttk.Frame(self.notebook,padding=14)
        self.notebook.add(self.profile_tab,text='VRM profile')
        ttk.Label(self.profile_tab,text='Create and save a per-VRM profile (simple/detailed follows the mode on the conversion tab)',
                  font=('Segoe UI',14,'bold')).pack(anchor='w',pady=(0,6))
        ttk.Label(self.profile_tab,text='Records the mesh regions, accessory-bone mapping and the ground offset. Existing profiles are reused by the one-click creation.',
                  wraplength=700).pack(anchor='w',pady=(0,10))
        for name,label,kind in (
            ('vrm','VRM','VRM files (*.vrm)'),
            ('tops','Torso tops.gmd','GMD files (*.gmd)'),
            ('face','Face face.gmd','GMD files (*.gmd)'),
            ('hair','Hair hair.gmd','GMD files (*.gmd)'),
            ('blender','Blender executable','Blender executable (*.exe)'),
            ('addon','GMD add-on folder','folder')):
            row=ttk.Frame(self.profile_tab);row.pack(fill='x',pady=3)
            ttk.Label(row,text=label,width=30).pack(side='left')
            ttk.Entry(row,textvariable=self.paths[name]).pack(side='left',fill='x',expand=True,padx=4)
            ttk.Button(row,text='Browse...',command=lambda key=name,desc=kind:self.browse(key,desc)).pack(side='left')
        self.profile_button=ttk.Button(self.profile_tab,text='Create profile',command=self.start_profile)
        self.profile_button.pack(fill='x',pady=(12,5))
        self.profile_status=tk.StringVar(value='The simple mode needs no AI. For the detailed mode, install the dedicated Ollama and Qwen in the AI setup tab.')
        ttk.Label(self.profile_tab,textvariable=self.profile_status,wraplength=700).pack(anchor='w')
        ai_tab=ttk.Frame(self.notebook,padding=14);self.notebook.add(ai_tab,text='AI setup')
        ttk.Label(ai_tab,text='Tool-owned local AI',font=('Segoe UI',14,'bold')).pack(anchor='w')
        ttk.Label(ai_tab,text='Only needed for the detailed mode (local AI). Not needed for the simple mode.\nOllama, models and caches are stored in Tool/runtime.\nAn existing Ollama is never contacted. Qwen is about 5 GB and Ollama about 1.5 GB to download.\nPython 3.10+ (with Tkinter/Pillow) and Blender are required separately.',wraplength=700).pack(anchor='w',pady=10)
        self.ai_status=tk.StringVar(value='Not checked');ttk.Label(ai_tab,textvariable=self.ai_status,wraplength=700).pack(anchor='w')
        self.ai_buttons=[]
        for label,operation in [('Set up Ollama','setup'),('Download Qwen','download'),('Check status','status')]:
            b=ttk.Button(ai_tab,text=label,command=lambda op=operation:self.ai_action(op));b.pack(fill='x',pady=5);self.ai_buttons.append(b)
        blender_tab=ttk.Frame(self.notebook,padding=14);self.notebook.add(blender_tab,text='Blender')
        self.blender_tab=blender_tab
        ttk.Label(blender_tab,text='Blender',font=('Segoe UI',14,'bold')).pack(anchor='w')
        ttk.Label(blender_tab,text='The tool needs Blender 4.5 LTS. If you do not have it, it can be downloaded from the official '
                  'server (download.blender.org) when you press the button. The download is checked against a pinned SHA-256 '
                  'checksum and installed only inside Tool/runtime/blender. Nothing is downloaded without your confirmation. '
                  'You can also choose a blender.exe you already have.',wraplength=700).pack(anchor='w',pady=(4,8))
        self.blender_status=tk.StringVar(value='')
        ttk.Label(blender_tab,textvariable=self.blender_status,wraplength=700).pack(anchor='w',pady=4)
        self.blender_bar=ttk.Progressbar(blender_tab,mode='determinate',maximum=100);self.blender_bar.pack(fill='x',pady=6)
        self.blender_progress=tk.StringVar(value='')
        ttk.Label(blender_tab,textvariable=self.blender_progress).pack(anchor='w')
        blender_row=ttk.Frame(blender_tab);blender_row.pack(fill='x',pady=8)
        self.blender_install_button=ttk.Button(blender_row,text='Download and set up Blender',command=self.blender_install)
        self.blender_install_button.pack(side='left',padx=(0,6))
        self.blender_cancel_button=ttk.Button(blender_row,text='Cancel',command=self.blender_cancel_install,state='disabled')
        self.blender_cancel_button.pack(side='left',padx=(0,6))
        self.blender_choose_button=ttk.Button(blender_row,text='Choose my own blender.exe...',command=self.blender_choose)
        self.blender_choose_button.pack(side='left')
        self.blender_queue=queue.Queue();self.blender_busy=False;self.blender_cancel=threading.Event()
        self.blender_refresh()
        storage_tab=ttk.Frame(self.notebook,padding=14);self.notebook.add(storage_tab,text='Storage')
        ttk.Label(storage_tab,text='Generated outputs',font=('Segoe UI',14,'bold')).pack(anchor='w')
        ttk.Label(storage_tab,text='Each conversion keeps its working files in Tool/userdata/outputs. Large working .blend files can '
                  'fill the disk quickly. Deleting cannot be undone. Your extracted game files, installed mods and the Mods you copied '
                  'elsewhere are never touched.',wraplength=700).pack(anchor='w',pady=(4,8))
        self.storage_tree=ttk.Treeview(storage_tab,columns=('size','blend','date'),selectmode='extended',height=12)
        for column,title,width in (('#0','Output folder',330),('size','Size',90),('blend','Working .blend',110),('date','Modified',130)):
            self.storage_tree.heading(column,text=title);self.storage_tree.column(column,width=width,anchor='w' if column=='#0' else 'e')
        self.storage_tree.pack(fill='both',expand=True)
        self.storage_status=tk.StringVar(value='Press "Refresh" to list the outputs.')
        ttk.Label(storage_tab,textvariable=self.storage_status,wraplength=700).pack(anchor='w',pady=6)
        storage_row=ttk.Frame(storage_tab);storage_row.pack(fill='x')
        self.storage_queue=queue.Queue()
        self.storage_buttons=[]
        for label,command in (('Refresh',self.storage_refresh),('Select all',self.storage_select_all),
                              ('Delete working .blend files only',self.storage_delete_blends),
                              ('Delete selected folders...',self.storage_delete_folders),
                              ('Open outputs folder',self.storage_open)):
            button=ttk.Button(storage_row,text=label,command=command);button.pack(side='left',padx=(0,6));self.storage_buttons.append(button)
        logs_tab=ttk.Frame(self.notebook,padding=14);self.notebook.add(logs_tab,text='Logs')
        ttk.Label(logs_tab,text='Logs and debug report',font=('Segoe UI',14,'bold')).pack(anchor='w')
        ttk.Label(logs_tab,text='The tool keeps a log of what it does, including the full output of Blender when a step fails, '
                  'in Tool/userdata/logs (capped at about 12 MB, never uploaded). If something goes wrong, press "Create debug report" '
                  'and attach the file to your bug report. User names and home-folder paths are masked, but file names, avatar names '
                  'and error text are not: read the report before you post it.',wraplength=700).pack(anchor='w',pady=(4,8))
        self.logs_status=tk.StringVar(value='')
        ttk.Label(logs_tab,textvariable=self.logs_status,wraplength=700).pack(anchor='w',pady=6)
        logs_row=ttk.Frame(logs_tab);logs_row.pack(fill='x')
        for label,command in (('Create debug report',self.logs_report),('Open logs folder',self.logs_open),
                              ('Delete all logs',self.logs_delete)):
            ttk.Button(logs_row,text=label,command=command).pack(side='left',padx=(0,6))
        self.logs_refresh()
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        if self.source_root.get():
            self.select_target()
        self.root.after(600,self.blender_first_run)

    def select_target(self, _event=None):
        from um.dragon_targets import get_target, target_references
        if self.target_id.get()==OTHER_ENTRY:
            self.target_id.set(self.last_target)
            self.custom_target_dialog()
            return
        self.last_target=self.target_id.get()
        target=get_target(self.target_id.get())
        for role in ('tops','face','hair'):
            self.paths[role].set('')
        self.remove_target_button.configure(state='normal' if target.custom_references is not None else 'disabled')
        if target.custom_references is not None:
            try:
                for role,file in target_references(target.id).items():
                    self.paths[role].set(file)
                self.status.set(f'{target.label}: {target.bone_count} bones. {target.motion_note}')
            except (OSError,ValueError) as exc:
                self.status.set(str(exc))
            return
        if not self.source_root.get().strip():
            self.status.set('Select the extracted Chara folder.')
            return
        try:
            refs=target_references(target.id,source_root=self.source_root.get().strip())
            for role,path in refs.items():
                self.paths[role].set(path)
            self.status.set(f'{target.label}: {target.bone_count} bones. Reference discovery and strict validation happen at generation time. {target.motion_note}')
        except (OSError,ValueError) as exc:
            self.status.set(f'Missing/duplicate references: {exc}')

    def show_variants(self):
        from um.dragon_variants import availability
        if not self.source_root.get().strip():
            messagebox.showerror('Missing references','Select the extracted Chara folder.');return
        try:
            rows=availability(self.target_id.get(),source_root=self.source_root.get().strip())
        except (OSError,ValueError) as exc:
            messagebox.showerror('Reference search',str(exc));return
        text='\n'.join(r['id']+(' [reference found; validated at generation]' if r['ready'] else ' [missing] '+r['reason']) for r in rows)
        text+='\n\nOnly registered layouts are covered. Unregistered young, dead or special-posture models are never replaced automatically.'
        if self.target_id.get()=='sawa':
            text+='\nFor Sawa, the approved age-18, dead and seated candidates are included. In-game posture and expression are unverified.'
        messagebox.showinfo('Model switch targets (in-game switching unverified)',text)

    def choose_source(self):
        path=filedialog.askdirectory(title='Chara folder extracted from your game (read-only)',mustexist=True)
        if path:
            self.source_root.set(path);self.select_target();self.save_settings()

    def choose_action(self):
        path=filedialog.askopenfilename(title='Optional: motion Action .blend you provide',filetypes=[('Blender','*.blend')])
        if path:self.action_blend.set(path)

    def save_settings(self):
        self.user_data.mkdir(parents=True,exist_ok=True)
        data={'source_root':self.source_root.get().strip(),'blender':self.paths['blender'].get().strip(),
              'include_variants':self.include_variants.get(),'profile_mode':self.profile_mode.get()}
        temp=self.settings_file.with_suffix('.tmp')
        temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(self.settings_file)

    def require_ai(self):
        if self.profile_mode.get()!='detailed':
            return True  # simple mode is rule-based and never touches the local AI
        from um.dragon_local_ai import get_runtime
        info=get_runtime().status()
        if not info['installed'] or not info['model_available']:
            messagebox.showerror('AI setup missing','Install Ollama and Qwen in the AI setup tab. An existing global Ollama is never used.');return False
        return True

    def ai_action(self, operation):
        from um.dragon_local_ai import get_runtime
        if getattr(self,'ai_busy',False):return
        if operation=='status':
            self.ai_status.set(json.dumps(get_runtime().status(),ensure_ascii=False));return
        if not messagebox.askokcancel('Confirm download','This downloads into the tool-owned environment and needs several GB of free space and bandwidth.\nAn existing Ollama is not modified. Continue?'):return
        self.ai_busy=True
        for b in self.ai_buttons:b.configure(state='disabled')
        self.ai_queue=queue.Queue()
        def worker():
            try:
                runtime=get_runtime()
                progress=lambda item:self.ai_queue.put(('progress',item))
                result=runtime.setup(progress,install=True) if operation=='setup' else runtime.download_model(progress)
                self.ai_queue.put(('ok',result))
            except Exception as exc:
                dragon_log.log_exception('AI setup failed', exc)
                self.ai_queue.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start();self.root.after(100,self.poll_ai)

    def poll_ai(self):
        try:kind,data=self.ai_queue.get_nowait()
        except queue.Empty:self.root.after(100,self.poll_ai);return
        if kind=='progress':
            suffix=f" {data['current']/1024**2:.1f} MiB" if data.get('current') is not None else ''
            if data.get('total'):suffix+=f" / {data['total']/1024**2:.1f} MiB"
            self.ai_status.set(data['message']+suffix);self.root.after(100,self.poll_ai);return
        self.ai_busy=False
        for b in self.ai_buttons:b.configure(state='normal')
        self.ai_status.set(str(data))
        if kind=='error':messagebox.showerror('AI setup',str(data))

    def logs_refresh(self):
        size=dragon_log.log_files_size()
        self.logs_status.set(f'Log folder: {dragon_log.redact(str(dragon_log.log_dir()))}  ({size/1024:.0f} KB in use)')

    def logs_report(self):
        try:
            dragon_log.get_logger().info('debug report requested')
            path=dragon_log.create_debug_report(outputs=self.private_output_parent)
        except Exception as exc:
            dragon_log.log_exception('Debug report failed',exc);messagebox.showerror('Logs',str(exc));return
        self.logs_status.set(f'Debug report saved: {path.name}')
        messagebox.showinfo('Debug report',f'Saved {path.name} in the logs folder.'+chr(10)+'It masks user names and home-folder paths, '
                            'but not file names, avatar names or error text. Read it before sharing.')
        self.logs_open()

    def logs_open(self):
        folder=dragon_log.log_dir();folder.mkdir(parents=True,exist_ok=True)
        if os.name=='nt':
            os.startfile(str(folder))

    def logs_delete(self):
        if not messagebox.askokcancel('Delete all logs','Delete all log files and debug reports? This cannot be undone.'):return
        count=dragon_log.delete_logs()
        dragon_log.setup_logging()  # logging continues in a fresh file
        self.logs_status.set(f'Deleted {count} file(s).')
        self.logs_refresh()

    def refresh_target_list(self):
        from um.dragon_targets import target_ids
        self.target_box.configure(values=list(target_ids())+[OTHER_ENTRY])

    def custom_target_dialog(self):
        from um import dragon_custom_targets as custom
        from um.dragon_targets import target_ids
        if not self.blender_usable():
            messagebox.showinfo('Blender','Set up Blender first (see the Blender tab); it is needed to read the GMD files.')
            return
        nl=chr(10)
        win=tk.Toplevel(self.root);win.title('Add a custom target');win.transient(self.root)
        try:win.grab_set()
        except tk.TclError:pass  # not viewable yet; the dialog still works
        win.columnconfigure(1,weight=1)
        ttk.Label(win,text='Use GMD files from any Dragon Engine game that you extracted yourself. The tool reads them once, '
                  'checks that their skeleton fits, and keeps private copies in Tool/userdata/targets. The game folder is never '
                  'changed. In-game results are unverified.',wraplength=560).grid(row=0,column=0,columnspan=3,sticky='w',padx=10,pady=(10,6))
        values={role:tk.StringVar() for role in ('tops','face','hair')}
        name=tk.StringVar()
        def browse(role):
            chosen=filedialog.askopenfilename(parent=win,title=f'Select the {role} GMD',filetypes=[('GMD files','*.gmd')])
            if not chosen:return
            values[role].set(chosen)
            if role=='tops':
                for other,found in custom.find_siblings(chosen).items():
                    if not values[other].get():values[other].set(str(found))
                if not name.get():name.set(Path(chosen).stem)
        for row,(role,label) in enumerate((('tops','Body GMD (tops, required)'),('face','Face GMD (optional)'),
                                           ('hair','Hair GMD (optional)')),start=1):
            ttk.Label(win,text=label).grid(row=row,column=0,sticky='w',padx=10,pady=3)
            ttk.Entry(win,textvariable=values[role],width=60).grid(row=row,column=1,sticky='we',pady=3)
            ttk.Button(win,text='Browse...',command=lambda r=role:browse(r)).grid(row=row,column=2,padx=10)
        ttk.Label(win,text='Name').grid(row=4,column=0,sticky='w',padx=10,pady=3)
        ttk.Entry(win,textvariable=name,width=60).grid(row=4,column=1,sticky='we',pady=3)
        state=tk.StringVar(value='Choose the body GMD; the face and hair GMDs next to it are found automatically.')
        ttk.Label(win,textvariable=state,wraplength=560).grid(row=5,column=0,columnspan=3,sticky='w',padx=10,pady=8)
        result_queue=queue.Queue()
        buttons=ttk.Frame(win);buttons.grid(row=6,column=0,columnspan=3,pady=(0,10))
        add_button=ttk.Button(buttons,text='Inspect and add');add_button.pack(side='left',padx=6)
        ttk.Button(buttons,text='Close',command=win.destroy).pack(side='left',padx=6)
        def finish():
            try:kind,data=result_queue.get_nowait()
            except queue.Empty:
                win.after(150,finish);return
            add_button.configure(state='normal')
            if kind=='error':
                state.set(data);messagebox.showerror('Custom target',data,parent=win);return
            self.refresh_target_list()
            self.target_id.set(data['id']);self.select_target()
            note=(nl+nl+nl.join(data['warnings'])) if data['warnings'] else ''
            messagebox.showinfo('Custom target',f"Added: {data['label']}{nl}{data['bone_count']} bones, layout {data['layout']}.{note}",parent=win)
            win.destroy()
        def add():
            files={role:Path(var.get().strip()) for role,var in values.items() if var.get().strip()}
            if 'tops' not in files:
                state.set('Choose the body (tops) GMD first.');return
            try:target_id=custom.sanitize_id(files['tops'].stem)
            except custom.CustomTargetError as exc:
                state.set(str(exc));return
            siblings={role:found for role,found in custom.find_siblings(files['tops']).items() if role not in files}
            if siblings and messagebox.askyesno('Custom target','The '+' and '.join(siblings)+' GMD found next to the body GMD '
                                                 'can be added too (recommended for a full character). Add them?',parent=win):
                files.update(siblings)
                for role,found in siblings.items():values[role].set(str(found))
            replace=False
            if target_id in target_ids():
                if not messagebox.askokcancel('Custom target','A custom target named '+target_id+' already exists. Replace it?',parent=win):return
                replace=True
            add_button.configure(state='disabled');state.set('Reading the GMD files with Blender...')
            blender=Path(self.paths['blender'].get().strip());addon=Path(self.paths['addon'].get().strip())
            label=name.get().strip() or None
            def work():
                try:
                    inspections=custom.inspect_files(files,blender,addon)
                    definition=custom.build_definition(files,inspections,label=label)
                    result_queue.put(('ok',custom.import_and_save(definition,files,replace=replace)))
                except custom.CustomTargetError as exc:
                    result_queue.put(('error',str(exc)))
                except Exception as exc:
                    dragon_log.log_exception('Custom target failed',exc)
                    result_queue.put(('error',str(exc)+nl+nl+LOG_HINT))
            threading.Thread(target=work,daemon=True).start()
            win.after(150,finish)
        add_button.configure(command=add)

    def remove_custom_target(self):
        from um import dragon_custom_targets as custom
        target_id=self.target_id.get()
        if not target_id.startswith('custom_'):
            return
        if not messagebox.askokcancel('Remove custom target',f'Remove {target_id}? Its private GMD copies are deleted. '
                                      'Mods you already generated and the game files are not affected.'):
            return
        try:
            custom.delete_target(target_id)
        except Exception as exc:
            dragon_log.log_exception('Removing a custom target failed',exc)
            messagebox.showerror('Custom target',str(exc));return
        self.refresh_target_list()
        self.target_id.set('yagami');self.select_target()

    def blender_usable(self):
        value=self.paths['blender'].get().strip()
        return bool(value) and Path(value).is_file()

    def blender_refresh(self):
        from um.dragon_blender_setup import BLENDER_SIZE,BLENDER_VERSION
        if self.blender_usable():
            self.blender_status.set('Blender is set: '+dragon_log.redact(self.paths['blender'].get()))
        else:
            self.blender_status.set(f'Blender was not found. Download Blender {BLENDER_VERSION} (about {BLENDER_SIZE/1e6:.0f} MB) '
                                    'from the official server, or choose a blender.exe you already have.')

    def blender_first_run(self):
        if self.blender_usable() or self.blender_busy:
            return
        from um.dragon_blender_setup import BLENDER_SIZE,BLENDER_VERSION
        nl=chr(10)
        answer=messagebox.askyesnocancel('Blender not found',
            'This tool needs Blender 4.5 LTS to convert avatars, but none was found.'+nl+nl+
            f'Download Blender {BLENDER_VERSION} (about {BLENDER_SIZE/1e6:.0f} MB, about 1 GB after unpacking) from the official '
            'server download.blender.org now? It is verified with a SHA-256 checksum and installed only inside the tool folder.'+nl+nl+
            'Yes: download it.  No: choose a blender.exe you already have.  Cancel: decide later (see the Blender tab).')
        self.notebook.select(self.blender_tab)
        if answer is True:
            self.blender_install()
        elif answer is False:
            self.blender_choose()

    def blender_set_path(self,path):
        self.paths['blender'].set(str(path))
        self.save_settings()
        self.blender_refresh()

    def blender_choose(self):
        if self.blender_busy:
            return
        chosen=filedialog.askopenfilename(title='Select blender.exe',filetypes=[('Blender executable','blender.exe'),('All files','*.*')])
        if not chosen:
            return
        if Path(chosen).name.lower()!='blender.exe':
            messagebox.showerror('Blender','Please select blender.exe (not another file).');return
        self.blender_set_path(chosen)

    def blender_install(self):
        if self.blender_busy:
            return
        if self.blender_usable():
            messagebox.showinfo('Blender','Blender is already set. Choose another blender.exe if you want to change it.');return
        from um.dragon_blender_setup import BLENDER_SIZE,BLENDER_VERSION,BlenderInstaller
        nl=chr(10)
        if not messagebox.askokcancel('Download Blender',
                f'Download Blender {BLENDER_VERSION} (about {BLENDER_SIZE/1e6:.0f} MB) from download.blender.org and install it in '
                'Tool/runtime/blender?'+nl+'It needs about 2.5 GB of free disk space while installing.'):
            return
        self.blender_busy=True
        self.blender_cancel=threading.Event()
        self.blender_install_button.configure(state='disabled');self.blender_choose_button.configure(state='disabled')
        self.blender_cancel_button.configure(state='normal')
        self.blender_bar.configure(value=0);self.blender_progress.set('Starting...')
        def work():
            try:
                exe=BlenderInstaller().install(progress=lambda event:self.blender_queue.put(('progress',event)),
                                               cancel=self.blender_cancel)
                self.blender_queue.put(('done',str(exe)))
            except Exception as exc:
                if 'Cancelled' not in str(exc):
                    dragon_log.log_exception('Blender setup failed',exc)
                self.blender_queue.put(('error',str(exc)))
        threading.Thread(target=work,daemon=True).start()
        self.root.after(100,self.blender_poll)

    def blender_cancel_install(self):
        self.blender_cancel.set()
        self.blender_progress.set('Cancelling...')

    def blender_poll(self):
        finished=False
        while True:
            try:kind,data=self.blender_queue.get_nowait()
            except queue.Empty:break
            if kind=='progress':
                total=data.get('total');current=data.get('current')
                if total and current is not None:
                    self.blender_bar.configure(value=100*current/total)
                    unit='MB' if total>10**6 else 'items'
                    scale=1e6 if unit=='MB' else 1
                    self.blender_progress.set(f"{data['message']}: {current/scale:.0f} / {total/scale:.0f} {unit}")
                else:
                    self.blender_progress.set(data['message'])
            else:
                finished=True
                self.blender_busy=False
                self.blender_install_button.configure(state='normal');self.blender_choose_button.configure(state='normal')
                self.blender_cancel_button.configure(state='disabled')
                if kind=='done':
                    self.blender_bar.configure(value=100);self.blender_progress.set('Done.')
                    self.blender_set_path(data)
                    messagebox.showinfo('Blender','Blender is installed and ready to use.')
                else:
                    self.blender_bar.configure(value=0)
                    if 'Cancelled' in str(data):
                        self.blender_progress.set('Cancelled. Nothing was installed.')
                    else:
                        self.blender_progress.set('Failed.')
                        messagebox.showerror('Blender setup failed',str(data)+chr(10)+chr(10)+LOG_HINT)
                    self.blender_refresh()
        if not finished:
            self.root.after(100,self.blender_poll)

    def storage_busy(self):
        if self.oneclick_button.instate(['disabled']) or getattr(self,'ai_busy',False) or self.blender_busy:
            messagebox.showwarning('Busy','Please wait for the current task to finish.');return True
        return False

    def storage_run(self,work,done):
        for button in self.storage_buttons:button.configure(state='disabled')
        def runner():
            try:self.storage_queue.put((done,work(),None))
            except Exception as exc:self.storage_queue.put((done,None,exc))
        threading.Thread(target=runner,daemon=True).start()
        self.root.after(100,self.storage_poll)

    def storage_poll(self):
        try:done,result,error=self.storage_queue.get_nowait()
        except queue.Empty:
            self.root.after(100,self.storage_poll);return
        for button in self.storage_buttons:button.configure(state='normal')
        if error is not None:
            self.storage_status.set(f'Failed: {error}');messagebox.showerror('Storage',str(error));return
        done(result)

    def storage_refresh(self):
        from um.dragon_output_cleanup import list_outputs
        self.storage_status.set('Measuring...')
        self.storage_run(lambda:list_outputs(self.private_output_parent),self.storage_show)

    def storage_show(self,rows):
        from um.dragon_output_cleanup import format_size
        self.storage_rows={row['name']:row for row in rows}
        self.storage_tree.delete(*self.storage_tree.get_children())
        for row in rows:
            self.storage_tree.insert('', 'end', iid=row['name'], text=row['name'],
                values=(format_size(row['bytes']),format_size(row['blend_bytes']),
                        datetime.fromtimestamp(row['mtime']).strftime('%Y-%m-%d %H:%M')))
        total=sum(row['bytes'] for row in rows);blends=sum(row['blend_bytes'] for row in rows)
        self.storage_status.set(f'{len(rows)} folder(s), {format_size(total)} in total; '
                                f'{format_size(blends)} of it is working .blend files.')

    def storage_select_all(self):
        self.storage_tree.selection_set(self.storage_tree.get_children())

    def storage_selection(self):
        names=list(self.storage_tree.selection())
        if not names:
            messagebox.showinfo('Storage','Select one or more output folders first.')
        return names

    def storage_delete_folders(self):
        names=self.storage_selection()
        if not names or self.storage_busy():return
        from um.dragon_output_cleanup import delete_outputs,format_size
        size=sum(self.storage_rows[n]['bytes'] for n in names if n in self.storage_rows)
        if not messagebox.askokcancel('Delete output folders',
                f'Permanently delete {len(names)} output folder(s) ({format_size(size)})?\n'
                'This also deletes the generated mods inside them. It cannot be undone.\n'
                'Mods you already copied elsewhere and the game are not affected.'):return
        self.storage_status.set('Deleting...')
        self.storage_run(lambda:delete_outputs(self.private_output_parent,names),self.storage_deleted)

    def storage_delete_blends(self):
        names=self.storage_selection()
        if not names or self.storage_busy():return
        from um.dragon_output_cleanup import delete_working_blends,format_size
        size=sum(self.storage_rows[n]['blend_bytes'] for n in names if n in self.storage_rows)
        if not messagebox.askokcancel('Delete working .blend files',
                f'Delete the working .blend files of {len(names)} output folder(s) ({format_size(size)})?\n'
                'Generated mods, reports and textures are kept. It cannot be undone.'):return
        self.storage_status.set('Deleting...')
        self.storage_run(lambda:delete_working_blends(self.private_output_parent,names),self.storage_deleted)

    def storage_deleted(self,result):
        from um.dragon_output_cleanup import format_size
        count=len(result.get('deleted',result.get('cleaned',[])))
        text=f'Done: {count} folder(s) processed, {format_size(result["freed_bytes"])} freed.'
        if result['errors']:
            text+=f' {len(result["errors"])} could not be processed: '+'; '.join(
                f"{e['name']} ({e['error']})" for e in result['errors'][:3])
        self.storage_status.set(text)
        self.storage_refresh()

    def storage_open(self):
        self.private_output_parent.mkdir(parents=True,exist_ok=True)
        if os.name=='nt':
            os.startfile(str(self.private_output_parent))

    def close(self):
        if getattr(self,'ai_busy',False) or self.blender_busy or self.oneclick_button.instate(['disabled']):
            messagebox.showwarning('Busy','Please wait for the current task to finish before quitting.');return
        from um.dragon_local_ai import get_runtime
        get_runtime().close();self.save_settings();self.root.destroy()

    def toggle_advanced(self):
        if self.advanced.winfo_manager():
            self.advanced.pack_forget()
        else:
            self.advanced.pack(fill='x', before=self.text.master)

    def start_profile(self):
        values={key:var.get().strip() for key,var in self.paths.items()}
        required=('vrm','tops','face','hair','blender','addon')
        if any(not values[key] for key in required):
            messagebox.showerror('Missing input','Specify the VRM, the tops/face/hair reference GMDs, Blender and the add-on.')
            return
        if not self.require_ai():
            return
        profile_root=self.private_output_parent.parent/'Profiles'
        self.profile_running=True
        self.profile_button.configure(state='disabled')
        self.oneclick_button.configure(state='disabled')
        self.profile_status.set('Inspecting and creating the profile with the local AI...' if self.profile_mode.get()=='detailed'
                                else 'Inspecting and creating the profile with rules (simple mode)...')
        refs={role:values[role] for role in ('tops','face','hair')}
        target_id=self.target_id.get()
        profile_mode=self.profile_mode.get()
        def worker():
            try:
                from um.dragon_profile_workflow import create_avatar_profile
                result=create_avatar_profile(values['vrm'],refs,values['blender'],values['addon'],
                    profile_root,progress=lambda text:self.messages.put(('progress',text)),
                    target_id=target_id,profile_mode=profile_mode)
                self.messages.put(('ok',result))
            except Exception as exc:
                dragon_log.log_exception('Task failed', exc)
                self.messages.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()
        self.root.after(80,self.poll)

    def start_all(self):
        values = {key: var.get().strip() for key, var in self.paths.items()}
        if any(not values[key] for key in ('vrm','tops','face','hair','blender','addon')):
            messagebox.showerror('Missing input', 'Select the VRM, the original tops/face/hair GMDs, Blender and the add-on.')
            return
        if not self.require_ai():
            return
        action=self.action_blend.get().strip() or None
        baseline=None
        dummy_dir=None
        self.save_settings()
        self.private_output_parent.mkdir(parents=True,exist_ok=True)
        target_id=self.target_id.get()
        stem=re.sub(r'[^A-Za-z0-9_-]+','_',Path(values['vrm']).stem).strip('_')[:32] or 'avatar'
        folder=self.private_output_parent / ('VRM_'+target_id+'_'+stem+'_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
        if folder.exists():
            messagebox.showerror('Output folder', 'A private output with the same name exists. Wait a moment and retry.')
            return
        from um.dragon_targets import get_target as _target_of
        use_variants=self.include_variants.get() and _target_of(target_id).custom_references is None
        profile_mode=self.profile_mode.get()
        if use_variants:
            from um.dragon_variants import availability
            if not self.source_root.get().strip():
                messagebox.showerror('Missing references','Specify the extracted Chara folder to generate switch targets.');return
            try:
                count=sum(r['ready'] for r in availability(target_id,source_root=self.source_root.get().strip()))
            except (OSError,ValueError) as exc:
                messagebox.showerror('Reference search',str(exc));return
            if not messagebox.askokcancel('Convert switch targets too',f'Converts {count} layout(s) individually. In-game support is unverified.\nContinue?'):
                return
        source_root=self.source_root.get().strip()
        self.last_run_dir=folder
        self.report=None
        self.save_button.configure(state='disabled')
        for button in (self.oneclick_button,self.profile_button,self.inspect_button,self.deep_button,self.prepare_button,
                       self.roundtrip_button,self.texture_button,self.candidate_button,self.beta_button):
            button.configure(state='disabled')
        self.status.set('Inspecting the VRM and creating a mod pack candidate...')
        def worker():
            try:
                if use_variants:
                    from um.dragon_variants import run_batch as run
                else:
                    from um.dragon_oneclick import run
                report=run(values['vrm'],{role:values[role] for role in ('tops','face','hair')},
                           values['blender'],values['addon'],action,baseline,folder,dummy_dir,
                           progress=lambda text:self.messages.put(('progress',text)),
                           target_id=target_id,profile_mode=profile_mode,
                           **({'source_root':source_root} if use_variants else {}))
                self.messages.put(('ok',report))
            except Exception as exc:
                dragon_log.log_exception('Task failed', exc)
                self.messages.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()
        self.root.after(80,self.poll)

    def browse(self, name: str, label: str):
        if name == "addon":
            path = filedialog.askdirectory()
        else:
            suffix = "*.vrm" if name == "vrm" else "*.exe" if name == "blender" else "*.gmd"
            path = filedialog.askopenfilename(filetypes=[(label, suffix), ("All files", "*.*")])
        if path:
            self.paths[name].set(path)

    def start_beta(self):
        values = {key: var.get().strip() for key, var in self.paths.items()}
        if not values['vrm'] or not values['blender'] or not values['addon']:
            messagebox.showerror('Missing input', 'Specify the VRM, Blender and the GMD add-on.')
            return
        profile = filedialog.askopenfilename(title='Select the private beta profile that matches the chosen VRM',
                                             initialdir=str(self.beta_profile_default.parent),
                                             initialfile=self.beta_profile_default.name,
                                             filetypes=[('JSON', '*.json')])
        if not profile:
            return
        self.private_output_parent.mkdir(parents=True,exist_ok=True)
        output = self.private_output_parent / ('VRM_Beta_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
        if output.exists():
            messagebox.showerror('Output folder', 'A candidate folder with the same name exists. Wait a moment and retry.')
            return
        if not messagebox.askokcancel('Offline beta',
                                     'A private candidate is generated only when the selected VRM matches the profile. GMDs remain even if the motion check fails, but nothing is installed into the game. Continue?'):
            return
        self.report = None
        self.save_button.configure(state='disabled')
        self.oneclick_button.configure(state='disabled')
        self.profile_button.configure(state='disabled')
        for button in (self.inspect_button, self.deep_button, self.prepare_button,
                       self.roundtrip_button, self.texture_button, self.candidate_button, self.beta_button):
            button.configure(state='disabled')
        self.status.set('Generating the private beta candidate and running the 4 motion checks...')
        def worker():
            try:
                from um.dragon_beta import build
                result = build(profile, values['vrm'], output, values['blender'], values['addon'],
                               progress=lambda text: self.messages.put(('progress', text)))
                self.messages.put(('ok', result))
            except (OSError, ValueError, KeyError) as exc:
                dragon_log.log_exception('Task failed', exc)
                self.messages.put(('error',str(exc)))
        threading.Thread(target=worker, daemon=True).start()
        self.root.after(80, self.poll)

    def start_combine_mods(self):
        sources=[]
        initial=str(self.bundle/'ModOutputs')
        while True:
            folder=filedialog.askdirectory(title='Select an existing VRM mod folder (read-only)',
                                           initialdir=initial,mustexist=True)
            if not folder:
                break
            sources.append(folder)
            initial=folder
            if not messagebox.askyesno('Add input mod','Add another mod folder?'):
                break
        if len(sources)<2:
            if sources:
                messagebox.showwarning('Too few mods','Merging needs two or more different mod folders.')
            return
        self.private_output_parent.mkdir(parents=True,exist_ok=True)
        output=self.private_output_parent/('VRM_Merged_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
        if output.exists():
            messagebox.showerror('Output folder','An output folder with the same name already exists. Please retry.')
            return
        title='VRM Combined '+datetime.now().strftime('%Y%m%d_%H%M%S')
        if not messagebox.askokcancel('Check compatibility and merge',
                f'Inspects {len(sources)} mod(s) by relative path. It stops if different content shares a path '
                'and only de-duplicates identical content. Nothing is installed into the game and no existing file is changed. Continue?'):
            return
        self.combine_button.configure(state='disabled')
        self.status.set('Checking file collisions between mods and creating a new merged package...')
        def worker():
            try:
                from um.dragon_mod_package import combine_mod_folders
                result=combine_mod_folders(sources,output,title)
                self.messages.put(('ok',result))
            except Exception as exc:
                dragon_log.log_exception('Task failed', exc)
                self.messages.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()
        self.root.after(80,self.poll)

    def start_candidate(self):
        folder = filedialog.askdirectory(title="Private candidate folder (where status.json is)")
        if not folder:
            return
        self.report = None
        self.save_button.configure(state="disabled")
        self.oneclick_button.configure(state="disabled")
        self.profile_button.configure(state="disabled")
        self.candidate_button.configure(state="disabled")
        self.beta_button.configure(state="disabled")
        self.status.set("Reading the offline candidate's validation results...")
        def worker():
            try:
                from um.dragon_candidate import check_draft
                self.messages.put(("ok", check_draft(folder)))
            except (OSError, ValueError) as exc:
                dragon_log.log_exception('Task failed', exc)
                self.messages.put(("error",str(exc)))
        threading.Thread(target=worker, daemon=True).start()
        self.root.after(80, self.poll)

    def start(self, deep=False, prepare=False, roundtrip=False, textures=False):
        deep = deep or prepare
        values = {key: var.get().strip() for key, var in self.paths.items()}
        if (not roundtrip and not values["vrm"]) or (not textures and not values["tops"]):
            messagebox.showerror("Missing input", "Specify the VRM and the torso GMD.")
            return
        if (deep or roundtrip) and (not values["blender"] or not values["addon"]):
            messagebox.showerror("Missing input", "Specify Blender and the local GMD add-on folder.")
            return
        workspace = None
        copy_path = None
        texture_dir = None
        if textures:
            parent = filedialog.askdirectory(title="Parent folder for a new DDS folder (outside the game)")
            if not parent:
                return
            texture_dir = Path(parent) / (Path(values["vrm"]).stem + "_DDS")
            if texture_dir.exists():
                messagebox.showerror("Output folder", "A DDS folder with the same name already exists. Choose a different parent folder.")
                return
        target_id=self.target_id.get()
        if roundtrip:
            from um.dragon_targets import get_target
            initial_gmd=get_target(target_id).slots[0].stem+'.gmd'
            chosen = filedialog.asksaveasfilename(defaultextension=".gmd",
                                                  initialfile=initial_gmd,
                                                  filetypes=[("GMD", "*.gmd")])
            if not chosen:
                return
            copy_path = Path(chosen)
            if copy_path.exists():
                messagebox.showerror("Output folder", "Original GMDs and existing files are never overwritten. Choose a different name.")
                return
        if prepare:
            chosen = filedialog.asksaveasfilename(defaultextension=".blend",
                                                  initialfile="VRM_LJ_Reference.blend",
                                                  filetypes=[("Blender", "*.blend")])
            if not chosen:
                return
            workspace = Path(chosen)
            if workspace.exists():
                messagebox.showerror("Output folder", "An existing .blend is never overwritten. Choose a new file name.")
                return
        self.report = None
        self.save_button.configure(state="disabled")
        self.inspect_button.configure(state="disabled")
        self.deep_button.configure(state="disabled")
        self.prepare_button.configure(state="disabled")
        self.roundtrip_button.configure(state="disabled")
        self.texture_button.configure(state="disabled")
        self.oneclick_button.configure(state="disabled")
        self.profile_button.configure(state="disabled")
        self.candidate_button.configure(state="disabled")
        self.beta_button.configure(state="disabled")
        self.status.set("Generating private DDS files..." if textures else
                        "Round-trip checking the torso GMD on a private copy..." if roundtrip else
                        "Preparing the offline working .blend..." if prepare else
                        "Running the detailed inspection in Blender..." if deep else "Running the quick inspection... (no game files are changed)")
        def worker():
            try:
                if textures:
                    from um.dragon_textures import extract
                    result = extract(values["vrm"], texture_dir)
                elif roundtrip:
                    from um.dragon_targets import get_target
                    result = roundtrip_gmd(values["tops"], values["blender"], values["addon"], copy_path,
                                           expected_bone_count=get_target(target_id).bone_count)
                elif deep:
                    result = inspect_blender(values["vrm"], values["tops"], values["blender"],
                                             values["addon"], values["face"] or None,
                                             values["hair"] or None, workspace=workspace,
                                             target_id=target_id)
                else:
                    result = inspect(values["vrm"], values["tops"], values["face"] or None,
                                     values["hair"] or None)
                self.messages.put(("ok", result))
            except (ValueError, OSError, ImportError) as exc:
                dragon_log.log_exception('Task failed', exc)
                self.messages.put(("error",str(exc)))
        threading.Thread(target=worker, daemon=True).start()
        self.root.after(80, self.poll)

    def poll(self):
        try:
            kind, result = self.messages.get_nowait()
        except queue.Empty:
            self.root.after(80, self.poll)
            return
        if kind == 'progress':
            dragon_log.get_logger().info('progress: %s', result)
            self.status.set(result)
            if getattr(self,'profile_running',False):
                self.profile_status.set(result)
            self.root.after(80, self.poll)
            return
        self.profile_running=False
        self.oneclick_button.configure(state='normal')
        self.profile_button.configure(state='normal')
        self.inspect_button.configure(state="normal")
        self.deep_button.configure(state="normal")
        self.prepare_button.configure(state="normal")
        self.roundtrip_button.configure(state="normal")
        self.texture_button.configure(state="normal")
        self.candidate_button.configure(state="normal")
        self.beta_button.configure(state="normal")
        self.combine_button.configure(state="normal")
        if kind == "error":
            self.profile_status.set(f'Profile creation error: {result}')
            self.status.set(f"Stopped: {result}")
            messagebox.showerror("Processing error", str(result) + chr(10) + chr(10) + LOG_HINT)
            return
        self.report = result
        self.save_button.configure(state="normal")
        mod_folder=result.get('mod_folder') or result.get('private_output')
        if mod_folder and os.name=='nt':
            folder=Path(mod_folder).resolve()
            if folder.is_dir():
                try:
                    os.startfile(str(folder))
                except OSError as exc:
                    messagebox.showwarning('Output folder',f'Output finished but the folder could not be opened: {exc}\n{folder}')
        if result.get('avatar_profile_path'):
            self.profile_status.set(f"Saved: {result['avatar_profile_path']}")
        self.status.set('Some switch candidates could not be converted (see failed_variants in variant-coverage.json). The rest were written as review candidates.'
                        if result.get('status')=='VARIANT_PACK_PARTIAL' else
                        'The accessory-bone/geometry check failed. This is a review candidate whose motion check was not run.'
                        if result.get('candidate_status')=='GEOMETRY_CHECK_FAILED' else
                        'The motion check was not run. A review candidate that needs in-game checks was written.'
                        if result.get('candidate_status')=='MOTION_NOT_RUN' or result.get('status')=='VARIANT_PACK_MOTION_NOT_RUN' else
                        'Switch candidates were written but the motion check failed. See variant-coverage.json.'
                        if result.get('status')=='VARIANT_PACK_MOTION_CHECK_FAILED' else
                        f"VRM profile created: {result['avatar_profile_path']}" if result.get('avatar_profile_path') else
                        f"Mods-format folder created: {result['mod_folder']}" if result.get('mod_folder') else
                        f"Saved the beta candidate and validation results: {result['private_output']}" if result.get('profile') else
                        "Validation results are incomplete. Showing the failure reasons and unverified items." if result.get('status') in ('BLOCKED','QUALITY_CHECK_FAILED') else
                        "A candidate was created. Please review the validation results." if result.get('status') == 'MANUAL_REVIEW_REQUIRED' else
                        "DDS generation finished. Assignment to GMD materials and in-game checks were not done." if result.get("dds_format") else
                        "Round-trip check of the original torso GMD finished. This is not a pass of the VRM port." if result.get("strict_roundtrip") else
                        "Working .blend saved. The bone mapping is only a proposal; nothing has been ported." if "fit_plan" in result
                        else "Pre-inspection finished. This does not guarantee a successful port or GMD import/export compatibility.")
        text = json.dumps(result, ensure_ascii=False, indent=2)
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)
        self.text.configure(state="disabled")

    def save(self):
        if self.report is None:
            return
        selected = filedialog.asksaveasfilename(defaultextension=".json", initialfile="dragon_preflight.json",
                                                 filetypes=[("JSON", "*.json")])
        if not selected:
            return
        target = Path(selected)
        if target.exists():
            messagebox.showwarning("Not saved", "Existing files are never overwritten. Choose a different name.")
            return
        try:
            with target.open("x", encoding="utf-8") as f:
                json.dump(self.report, f, ensure_ascii=False, indent=2)
                f.write("\n")
        except OSError as exc:
            messagebox.showerror("Save error", str(exc))
            return
        self.status.set(f"Report saved: {target}")


def main():
    dragon_log.setup_logging()
    dragon_log.log_environment()
    root = tk.Tk()
    root.report_callback_exception = lambda kind, value, trace: dragon_log.get_logger().error(
        'Uncaught error in a GUI callback', exc_info=(kind, value, trace))
    DragonWindow(root)
    root.mainloop()
