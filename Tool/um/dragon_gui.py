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

from um.dragon import inspect, inspect_blender, roundtrip_gmd


class DragonWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("VRM → Dragon Engine | 汎用VRMオフラインβ")
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
        if self.settings_file.is_file():
            try:
                settings=json.loads(self.settings_file.read_text(encoding='utf-8'))
                self.source_root.set(settings.get('source_root',''))
                self.paths['blender'].set(settings.get('blender',self.paths['blender'].get()))
            except (OSError,ValueError):
                pass
        self.messages: queue.Queue = queue.Queue()
        self.report: dict | None = None
        hint = '抽出済みCharaフォルダとVRMを選択し、AIセットアップを行ってください。ゲームへの導入は行いません。'
        self.status = tk.StringVar(value=hint)
        self.notebook=ttk.Notebook(root)
        self.notebook.pack(fill='both',expand=True)
        frame = ttk.Frame(self.notebook, padding=14)
        self.notebook.add(frame,text='一括Mod作成')
        ttk.Label(frame, text="VRM → Dragon Engine / Lost Judgment β", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(frame, text="1回で点検→補正候補→GMD検証→mod-meta.yaml付きMods形式へ。ゲーム導入はしません。",
                  foreground="#854d0e").pack(anchor="w", pady=(4, 12))
        target_row=ttk.Frame(frame);target_row.pack(fill='x',pady=(0,8))
        ttk.Label(target_row,text='対象キャラクター',width=23).pack(side='left')
        from um.dragon_targets import target_ids
        target_box=ttk.Combobox(target_row,textvariable=self.target_id,state='readonly',
                                values=target_ids(),width=16)
        target_box.pack(side='left',padx=4)
        target_box.bind('<<ComboboxSelected>>',self.select_target)
        ttk.Label(target_row,text='追加人物は実験対応・ゲーム内確認が必要').pack(side='left',padx=8)
        source_row=ttk.Frame(frame);source_row.pack(fill='x',pady=3)
        ttk.Label(source_row,text='抽出済みCharaフォルダ',width=23).pack(side='left')
        ttk.Entry(source_row,textvariable=self.source_root).pack(side='left',fill='x',expand=True,padx=4)
        ttk.Button(source_row,text='選択・検索…',command=self.choose_source).pack(side='left')
        ttk.Button(source_row,text='再検索',command=self.select_target).pack(side='left',padx=4)
        action_row=ttk.Frame(frame);action_row.pack(fill='x',pady=3)
        ttk.Label(action_row,text='動作検査Action（任意）',width=23).pack(side='left')
        ttk.Entry(action_row,textvariable=self.action_blend).pack(side='left',fill='x',expand=True,padx=4)
        ttk.Button(action_row,text='参照…',command=self.choose_action).pack(side='left')
        variant_row=ttk.Frame(frame);variant_row.pack(fill='x',pady=(0,6))
        self.include_variants=tk.BooleanVar(value=False)
        ttk.Checkbutton(variant_row,text='参照が見つかった切替先も個別検証・生成（ゲーム内未確認）',
                        variable=self.include_variants).pack(side='left')
        ttk.Button(variant_row,text='対象と除外理由',command=self.show_variants).pack(side='left',padx=6)
        for name, label, kind in (
            ("vrm", "VRM（必須）", "VRM files (*.vrm)",),
            ("tops", "胴体 tops.gmd（必須）", "GMD files (*.gmd)"),
            ("face", "顔 face.gmd（任意）", "GMD files (*.gmd)"),
            ("hair", "髪 hair.gmd（任意）", "GMD files (*.gmd)"),
            ("blender", "Blender本体（詳細点検用）", "Blender executable (*.exe)"),
            ("addon", "GMDアドオンのフォルダ", "folder"),
        ):
            row = ttk.Frame(frame)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=label, width=23).pack(side="left")
            ttk.Entry(row, textvariable=self.paths[name]).pack(side="left", fill="x", expand=True, padx=4)
            ttk.Button(row, text="参照…", command=lambda key=name, desc=kind: self.browse(key, desc)).pack(side="left")
        primary = ttk.Frame(frame)
        primary.pack(fill='x', pady=(13, 8))
        self.oneclick_button = ttk.Button(primary, text='VRMからModパックを自動作成（β・ゲーム非導入）',
                                          command=self.start_all)
        self.oneclick_button.pack(fill='x')
        self.advanced = ttk.Frame(frame)
        menu = tk.Menu(root)
        menu.add_command(label='詳細機能を表示/非表示', command=self.toggle_advanced)
        root.configure(menu=menu)
        actions = ttk.Frame(self.advanced)
        actions.pack(fill="x", pady=(4, 8))
        self.inspect_button = ttk.Button(actions, text="簡易点検", command=self.start)
        self.inspect_button.pack(side="left")
        self.deep_button = ttk.Button(actions, text="Blenderで詳細点検", command=lambda: self.start(deep=True))
        self.deep_button.pack(side="left", padx=8)
        self.prepare_button = ttk.Button(actions, text="作業用.blend＋骨対応", command=lambda: self.start(prepare=True))
        self.prepare_button.pack(side="left")
        self.roundtrip_button = ttk.Button(actions, text="胴体GMD往復試験", command=lambda: self.start(roundtrip=True))
        self.roundtrip_button.pack(side="left", padx=8)
        self.texture_button = ttk.Button(actions, text="VRM→DDS", command=lambda: self.start(textures=True))
        self.texture_button.pack(side="left")
        self.save_button = ttk.Button(actions, text="JSONレポートを保存…", command=self.save, state="disabled")
        self.save_button.pack(side="left", padx=8)
        review = ttk.Frame(self.advanced)
        review.pack(fill="x", pady=(0, 8))
        self.candidate_button = ttk.Button(review, text="私用ドラフトの失敗理由を確認（読取専用）", command=self.start_candidate)
        self.candidate_button.pack(side="left")
        self.beta_button = ttk.Button(review, text="β候補を作成（プロファイル要・ゲーム非導入）", command=self.start_beta)
        self.beta_button.pack(side="left", padx=12)
        self.combine_button=ttk.Button(review,text='複数VRM Modを互換チェックして統合',command=self.start_combine_mods)
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
        self.notebook.add(self.profile_tab,text='VRMプロファイル作成')
        ttk.Label(self.profile_tab,text='ローカルAIでVRM別プロフィールを作成・保存',
                  font=('Segoe UI',14,'bold')).pack(anchor='w',pady=(0,6))
        ttk.Label(self.profile_tab,text='メッシュ領域・補助骨の対応案と接地差を記録します。既存プロフィールは一括作成時に再利用します。',
                  wraplength=700).pack(anchor='w',pady=(0,10))
        for name,label,kind in (
            ('vrm','VRM','VRM files (*.vrm)'),
            ('tops','胴体 tops.gmd','GMD files (*.gmd)'),
            ('face','顔 face.gmd','GMD files (*.gmd)'),
            ('hair','髪 hair.gmd','GMD files (*.gmd)'),
            ('blender','Blender本体','Blender executable (*.exe)'),
            ('addon','GMDアドオンのフォルダ','folder')):
            row=ttk.Frame(self.profile_tab);row.pack(fill='x',pady=3)
            ttk.Label(row,text=label,width=23).pack(side='left')
            ttk.Entry(row,textvariable=self.paths[name]).pack(side='left',fill='x',expand=True,padx=4)
            ttk.Button(row,text='参照…',command=lambda key=name,desc=kind:self.browse(key,desc)).pack(side='left')
        self.profile_button=ttk.Button(self.profile_tab,text='ローカルAIでプロフィールを作成',command=self.start_profile)
        self.profile_button.pack(fill='x',pady=(12,5))
        self.profile_status=tk.StringVar(value='AIセットアップタブから専用OllamaとQwenを導入してください。')
        ttk.Label(self.profile_tab,textvariable=self.profile_status,wraplength=700).pack(anchor='w')
        ai_tab=ttk.Frame(self.notebook,padding=14);self.notebook.add(ai_tab,text='AIセットアップ')
        ttk.Label(ai_tab,text='Tool専用ローカルAI',font=('Segoe UI',14,'bold')).pack(anchor='w')
        ttk.Label(ai_tab,text='Ollama本体・モデル・キャッシュはTool/runtime内に保存します。\n既存のOllamaには接続しません。Qwenは約5GB、本体は約1.5GBのダウンロードです。\nPython 3.10+（Tkinter/Pillow付き）とBlenderは別途必要です。',wraplength=700).pack(anchor='w',pady=10)
        self.ai_status=tk.StringVar(value='未確認');ttk.Label(ai_tab,textvariable=self.ai_status,wraplength=700).pack(anchor='w')
        self.ai_buttons=[]
        for label,operation in [('Ollamaをセットアップ','setup'),('Qwenをダウンロード','download'),('状態確認','status')]:
            b=ttk.Button(ai_tab,text=label,command=lambda op=operation:self.ai_action(op));b.pack(fill='x',pady=5);self.ai_buttons.append(b)
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        if self.source_root.get():
            self.select_target()

    def select_target(self, _event=None):
        from um.dragon_targets import get_target, target_references
        target=get_target(self.target_id.get())
        for role in ('tops','face','hair'):
            self.paths[role].set('')
        if not self.source_root.get().strip():
            self.status.set('抽出済みCharaフォルダを選択してください。')
            return
        try:
            refs=target_references(target.id,source_root=self.source_root.get().strip())
            for role,path in refs.items():
                self.paths[role].set(path)
            self.status.set(f'{target.label}: {target.bone_count}骨。参照発見・strict検証は生成時。{target.motion_note}')
        except (OSError,ValueError) as exc:
            self.status.set(f'参照不足/重複: {exc}')

    def show_variants(self):
        from um.dragon_variants import availability
        if not self.source_root.get().strip():
            messagebox.showerror('参照不足','抽出済みCharaフォルダを選択してください。');return
        try:
            rows=availability(self.target_id.get(),source_root=self.source_root.get().strip())
        except (OSError,ValueError) as exc:
            messagebox.showerror('参照検索',str(exc));return
        text='\n'.join(r['id']+(' [参照発見・検証は生成時]' if r['ready'] else ' [不足] '+r['reason']) for r in rows)
        text+='\n\n登録した構成だけが対象です。未登録の若年・死亡・特殊姿勢等のモデルは自動置換しません。'
        if self.target_id.get()=='sawa':
            text+='\nSawaは承認済みの18歳用候補・死亡用候補・座り用候補も対象です。ゲーム内の姿勢・表情は未確認です。'
        messagebox.showinfo('モデル切替対象（ゲーム内切替は未確認）',text)

    def choose_source(self):
        path=filedialog.askdirectory(title='所有ゲームから抽出済みのCharaフォルダ（読取専用）',mustexist=True)
        if path:
            self.source_root.set(path);self.select_target();self.save_settings()

    def choose_action(self):
        path=filedialog.askopenfilename(title='任意：利用者が用意した動作Action .blend',filetypes=[('Blender','*.blend')])
        if path:self.action_blend.set(path)

    def save_settings(self):
        self.user_data.mkdir(parents=True,exist_ok=True)
        data={'source_root':self.source_root.get().strip(),'blender':self.paths['blender'].get().strip()}
        temp=self.settings_file.with_suffix('.tmp')
        temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(self.settings_file)

    def require_ai(self):
        from um.dragon_local_ai import get_runtime
        info=get_runtime().status()
        if not info['installed'] or not info['model_available']:
            messagebox.showerror('AIセットアップ不足','AIセットアップタブでOllama本体とQwenを導入してください。既存のグローバルOllamaは使用しません。');return False
        return True

    def ai_action(self, operation):
        from um.dragon_local_ai import get_runtime
        if getattr(self,'ai_busy',False):return
        if operation=='status':
            self.ai_status.set(json.dumps(get_runtime().status(),ensure_ascii=False));return
        if not messagebox.askokcancel('ダウンロード確認','Tool内の専用環境へダウンロードします。数GBの空き容量と通信量が必要です。\n既存のOllamaは変更しません。続けますか？'):return
        self.ai_busy=True
        for b in self.ai_buttons:b.configure(state='disabled')
        self.ai_queue=queue.Queue()
        def worker():
            try:
                runtime=get_runtime()
                progress=lambda item:self.ai_queue.put(('progress',item))
                result=runtime.setup(progress,install=True) if operation=='setup' else runtime.download_model(progress)
                self.ai_queue.put(('ok',result))
            except Exception as exc:self.ai_queue.put(('error',str(exc)))
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
        if kind=='error':messagebox.showerror('AIセットアップ',str(data))

    def close(self):
        if getattr(self,'ai_busy',False) or self.oneclick_button.instate(['disabled']):
            messagebox.showwarning('処理中','現在の処理が終わってから終了してください。');return
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
            messagebox.showerror('入力不足','VRM、tops/face/hair参照GMD、Blender、アドオンを指定してください。')
            return
        if not self.require_ai():
            return
        profile_root=self.private_output_parent.parent/'Profiles'
        self.profile_running=True
        self.profile_button.configure(state='disabled')
        self.oneclick_button.configure(state='disabled')
        self.profile_status.set('点検・ローカルAIプロフィール作成中…')
        refs={role:values[role] for role in ('tops','face','hair')}
        target_id=self.target_id.get()
        def worker():
            try:
                from um.dragon_profile_workflow import create_avatar_profile
                result=create_avatar_profile(values['vrm'],refs,values['blender'],values['addon'],
                    profile_root,progress=lambda text:self.messages.put(('progress',text)),
                    target_id=target_id)
                self.messages.put(('ok',result))
            except Exception as exc:
                self.messages.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()
        self.root.after(80,self.poll)

    def start_all(self):
        values = {key: var.get().strip() for key, var in self.paths.items()}
        if any(not values[key] for key in ('vrm','tops','face','hair','blender','addon')):
            messagebox.showerror('入力不足', 'VRMとtops/face/hairの元GMD、Blender、アドオンを選択してください。')
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
            messagebox.showerror('保存先', '同名の私用出力があります。少し待って再試行してください。')
            return
        use_variants=self.include_variants.get()
        if use_variants:
            from um.dragon_variants import availability
            if not self.source_root.get().strip():
                messagebox.showerror('参照不足','切替先の生成には抽出済みCharaフォルダを指定してください。');return
            try:
                count=sum(r['ready'] for r in availability(target_id,source_root=self.source_root.get().strip()))
            except (OSError,ValueError) as exc:
                messagebox.showerror('参照検索',str(exc));return
            if not messagebox.askokcancel('切替先も個別変換',f'{count}構成を個別に変換します。ゲーム内対応は未確認です。\n続けますか？'):
                return
        source_root=self.source_root.get().strip()
        self.last_run_dir=folder
        self.report=None
        self.save_button.configure(state='disabled')
        for button in (self.oneclick_button,self.profile_button,self.inspect_button,self.deep_button,self.prepare_button,
                       self.roundtrip_button,self.texture_button,self.candidate_button,self.beta_button):
            button.configure(state='disabled')
        self.status.set('VRMを点検してModパック候補を作成中…')
        def worker():
            try:
                if use_variants:
                    from um.dragon_variants import run_batch as run
                else:
                    from um.dragon_oneclick import run
                report=run(values['vrm'],{role:values[role] for role in ('tops','face','hair')},
                           values['blender'],values['addon'],action,baseline,folder,dummy_dir,
                           progress=lambda text:self.messages.put(('progress',text)),
                           target_id=target_id,**({'source_root':source_root} if use_variants else {}))
                self.messages.put(('ok',report))
            except Exception as exc:
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
            messagebox.showerror('入力不足', 'VRM、Blender、GMDアドオンを指定してください。')
            return
        profile = filedialog.askopenfilename(title='選んだVRMに対応する私用βプロファイルを選択',
                                             initialdir=str(self.beta_profile_default.parent),
                                             initialfile=self.beta_profile_default.name,
                                             filetypes=[('JSON', '*.json')])
        if not profile:
            return
        self.private_output_parent.mkdir(parents=True,exist_ok=True)
        output = self.private_output_parent / ('VRM_Beta_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
        if output.exists():
            messagebox.showerror('保存先', '同名の候補フォルダがあります。少し待って再試行してください。')
            return
        if not messagebox.askokcancel('オフラインβ',
                                     '選択VRMとプロファイルが一致する場合のみ私用候補を生成します。動作不合格でもGMDが残りますが、ゲームへ導入しません。続けますか？'):
            return
        self.report = None
        self.save_button.configure(state='disabled')
        self.oneclick_button.configure(state='disabled')
        self.profile_button.configure(state='disabled')
        for button in (self.inspect_button, self.deep_button, self.prepare_button,
                       self.roundtrip_button, self.texture_button, self.candidate_button, self.beta_button):
            button.configure(state='disabled')
        self.status.set('私用β候補の生成と4動作点検を実行中…')
        def worker():
            try:
                from um.dragon_beta import build
                result = build(profile, values['vrm'], output, values['blender'], values['addon'],
                               progress=lambda text: self.messages.put(('progress', text)))
                self.messages.put(('ok', result))
            except (OSError, ValueError, KeyError) as exc:
                self.messages.put(('error', str(exc)))
        threading.Thread(target=worker, daemon=True).start()
        self.root.after(80, self.poll)

    def start_combine_mods(self):
        sources=[]
        initial=str(self.bundle/'ModOutputs')
        while True:
            folder=filedialog.askdirectory(title='既存のVRM Modフォルダを選択（読取専用）',
                                           initialdir=initial,mustexist=True)
            if not folder:
                break
            sources.append(folder)
            initial=folder
            if not messagebox.askyesno('入力Modを追加','もう1つのModフォルダを追加しますか？'):
                break
        if len(sources)<2:
            if sources:
                messagebox.showwarning('Mod数不足','統合には異なるModフォルダが2つ以上必要です。')
            return
        self.private_output_parent.mkdir(parents=True,exist_ok=True)
        output=self.private_output_parent/('VRM_Merged_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
        if output.exists():
            messagebox.showerror('保存先','同名の出力先が既にあります。再試行してください。')
            return
        title='VRM Combined '+datetime.now().strftime('%Y%m%d_%H%M%S')
        if not messagebox.askokcancel('互換チェックして統合',
                f'{len(sources)}個のModを相対パス単位で検査します。異なる内容が同じパスにある場合は停止し、'
                '同一内容だけ重複排除します。ゲームへの導入・既存ファイル変更は行いません。続けますか？'):
            return
        self.combine_button.configure(state='disabled')
        self.status.set('Mod間のファイル衝突を検査して新しい統合パッケージを作成中…')
        def worker():
            try:
                from um.dragon_mod_package import combine_mod_folders
                result=combine_mod_folders(sources,output,title)
                self.messages.put(('ok',result))
            except Exception as exc:
                self.messages.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()
        self.root.after(80,self.poll)

    def start_candidate(self):
        folder = filedialog.askdirectory(title="私用の候補フォルダ（status.jsonがある場所）")
        if not folder:
            return
        self.report = None
        self.save_button.configure(state="disabled")
        self.oneclick_button.configure(state="disabled")
        self.profile_button.configure(state="disabled")
        self.candidate_button.configure(state="disabled")
        self.beta_button.configure(state="disabled")
        self.status.set("オフライン候補の検証結果を読んでいます…")
        def worker():
            try:
                from um.dragon_candidate import check_draft
                self.messages.put(("ok", check_draft(folder)))
            except (OSError, ValueError) as exc:
                self.messages.put(("error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()
        self.root.after(80, self.poll)

    def start(self, deep=False, prepare=False, roundtrip=False, textures=False):
        deep = deep or prepare
        values = {key: var.get().strip() for key, var in self.paths.items()}
        if (not roundtrip and not values["vrm"]) or (not textures and not values["tops"]):
            messagebox.showerror("入力不足", "VRMと胴体GMDを指定してください。")
            return
        if (deep or roundtrip) and (not values["blender"] or not values["addon"]):
            messagebox.showerror("入力不足", "Blender本体とローカルGMDアドオンのフォルダを指定してください。")
            return
        workspace = None
        copy_path = None
        texture_dir = None
        if textures:
            parent = filedialog.askdirectory(title="DDSの新規フォルダを作る親フォルダ（ゲーム外）")
            if not parent:
                return
            texture_dir = Path(parent) / (Path(values["vrm"]).stem + "_DDS")
            if texture_dir.exists():
                messagebox.showerror("保存先", "同名のDDSフォルダは既にあります。別の親フォルダを選んでください。")
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
                messagebox.showerror("保存先", "元のGMDや既存ファイルは上書きしません。別の名前を選んでください。")
                return
        if prepare:
            chosen = filedialog.asksaveasfilename(defaultextension=".blend",
                                                  initialfile="VRM_LJ_Reference.blend",
                                                  filetypes=[("Blender", "*.blend")])
            if not chosen:
                return
            workspace = Path(chosen)
            if workspace.exists():
                messagebox.showerror("保存先", "既存の.blendは上書きしません。新しいファイル名を選んでください。")
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
        self.status.set("個人用DDSを生成中…" if textures else
                        "私用コピーで胴体GMDを往復検証中…" if roundtrip else
                        "オフライン作業用.blendを準備中…" if prepare else
                        "Blenderで詳細点検中…" if deep else "簡易点検中…（ゲームファイルの変更はありません）")
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
                self.messages.put(("error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()
        self.root.after(80, self.poll)

    def poll(self):
        try:
            kind, result = self.messages.get_nowait()
        except queue.Empty:
            self.root.after(80, self.poll)
            return
        if kind == 'progress':
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
            self.profile_status.set(f'プロフィール作成エラー: {result}')
            self.status.set(f"処理停止: {result}")
            messagebox.showerror("処理エラー", result)
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
                    messagebox.showwarning('出力フォルダ',f'出力は完了しましたがフォルダを開けませんでした: {exc}\n{folder}')
        if result.get('avatar_profile_path'):
            self.profile_status.set(f"保存しました: {result['avatar_profile_path']}")
        self.status.set('補助骨などの形状検査が不合格です。動作検査も未実施のレビュー候補です。'
                        if result.get('candidate_status')=='GEOMETRY_CHECK_FAILED' else
                        '動作検査は未実施です。ゲーム内確認が必要なレビュー候補を出力しました。'
                        if result.get('candidate_status')=='MOTION_NOT_RUN' or result.get('status')=='VARIANT_PACK_MOTION_NOT_RUN' else
                        '切替先候補を出力しましたが動作検査は不合格です。variant-coverage.jsonを確認してください。'
                        if result.get('status')=='VARIANT_PACK_MOTION_CHECK_FAILED' else
                        f"VRMプロフィールを作成: {result['avatar_profile_path']}" if result.get('avatar_profile_path') else
                        f"Mods形式を作成しました: {result['mod_folder']}" if result.get('mod_folder') else
                        f"β候補と検証結果を保存: {result['private_output']}" if result.get('profile') else
                        "検証結果に不足があります。失敗理由と未検証項目を表示します。" if result.get('status') in ('BLOCKED','QUALITY_CHECK_FAILED') else
                        "候補を作成しました。検証結果を確認してください。" if result.get('status') == 'MANUAL_REVIEW_REQUIRED' else
                        "DDS生成完了。GMD材質への割当・ゲーム確認は未実施です。" if result.get("dds_format") else
                        "元の胴体GMDの往復検証完了。VRM移植の合格ではありません。" if result.get("strict_roundtrip") else
                        "作業用.blend保存完了。骨対応は提案のみで、移植済みではありません。" if "fit_plan" in result
                        else "事前点検完了。これは移植成功やGMDの入出力互換性を保証しません。")
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
            messagebox.showwarning("保存しませんでした", "既存ファイルは上書きしません。別の名前を選んでください。")
            return
        try:
            with target.open("x", encoding="utf-8") as f:
                json.dump(self.report, f, ensure_ascii=False, indent=2)
                f.write("\n")
        except OSError as exc:
            messagebox.showerror("保存エラー", str(exc))
            return
        self.status.set(f"レポートを保存しました: {target}")


def main():
    root = tk.Tk()
    DragonWindow(root)
    root.mainloop()
