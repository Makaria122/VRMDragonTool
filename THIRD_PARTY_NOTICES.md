# Third-party notices / 公開前のライセンス確認

本プロジェクトの自己作成コード・文書はルートの`LICENSE`にあるMITライセンスで提供します。改良・再配布・商用利用を許可し、著作権表示とライセンス文の保持を求めます。

**MITの適用対象から`Tool/vendor/`および第三者由来のコード・依存物を除外します。** それらは各々の元ライセンスに従います。以下は主要依存の案内であり、同梱物・ダウンロード物の元ライセンスを置き換えません。

- **yakuza-gmd-gmt-blender**: vendored GMD addon。`Tool/vendor/yakuza-gmd-gmt-blender/LICENSE`とソース内の著作権表記を保持します。GPL条件を確認し、同梱ソースを削らないでください。
- **Ollama**: https://github.com/ollama/ollama （MIT）。本体はGitHub配布ソースに含めず、明示的なセットアップで公式Windows portable版をダウンロードします。GPU関連ライブラリ等の別ライセンスも配布元で確認してください。
- **Qwen2.5-Coder-7B-Instruct**: https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct （Apache-2.0）。Ollamaの`qwen2.5-coder:7b`を明示的にダウンロードします。モデルの配布元・モデルカード・利用条件を確認してください。モデル本体はGitHubに同梱しません。
- **Pillow**: https://python-pillow.org/ （HPND等、配布物のLICENSEを参照）。別途インストールする依存です。
- **Python / Tkinter**: https://www.python.org/ 。PythonとTcl/Tkのライセンスは各配布元を参照してください。現在のソース配布には本体を同梱しません。
- **Blender**: https://www.blender.org/ （GPL）。利用者が別途用意します。現在のソース配布には本体を同梱しません。

Lost JudgmentのGMD／DDS／Action、VRM、生成MOD、私用プロファイル、AIモデルは公開ソースの対象外です。ゲーム資産の抽出手順・権限回避・再配布を提供しません。

開発に生成AI支援を使用しています。生成した中立DDSは独自の定数レシピで作成し、ゲームDDSを配布元としてコピーしません。
