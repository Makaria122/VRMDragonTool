# ローカルAI用プロンプト：Lost Judgment キャラクターターゲット候補の調査

あなたは、ユーザーのローカル環境にある抽出済みGMDファイルを**読み取り専用で調査**し、VRMDragonToolに追加するキャラクターターゲット設定に必要な根拠を集める調査エージェントです。

## 目的

指定キャラクターに対応する可能性があるGMDを抽出済みフォルダから探し、ファイル名だけで決めつけず、GMD内部のリグ・骨・メッシュ・シェーダーなどを確認してください。最後に、Pi側の開発者が人手でレビューして`dragon_targets.py`等へ登録できるよう、候補と根拠を機械可読なJSONにまとめます。

この作業は**調査とレポート作成だけ**です。キャラクター追加のコード変更、GMDのコピー/改名/移動/変換、ゲームやMODの変更はしないでください。

## 対象キャラクター

1. Fumiya Sugiura
2. Makoto Tsukumo
3. Saori Shirosaki
4. Toru Higashi
5. Tesso
6. Jin Kuwana
7. Kazuki Soma
8. Daimu Akutsu
9. Ryuzo Genda
10. Issei Hoshino
11. Mafuyu Fujii
12. Yoko Sawa

## 入力場所

以下のプレースホルダーは利用者のローカルパスで置き換えてください。
- 抽出済みGMDルート：`<選択したCharaフォルダ>`
- VRMDragonTool：`<ツールの配置先>`
- Blender（GMD解析に必要な場合）：`<選択したBlender実行ファイル>`
- GMDアドオン：`Tool/vendor/yakuza-gmd-gmt-blender`
- 出力先：`Tool/userdata/TargetDiscovery`

抽出フォルダはモデルIDごとのサブフォルダを持ち、配下に`face`、`hair`、`tops`等の領域フォルダとGMDがある場合があります。実際の構造をまず確認してください。ファイルは多数ある可能性があるため、最初に全GMDの相対パス・サイズを索引化し、候補だけを深く解析してください。

## 必ず守ること

- **抽出データはユーザー専用の私用アセット**です。GMD本体やDDSを出力先、Git、配布物、外部サービスへコピーしないでください。
- GMD、Blenderファイル、モデルのバイナリ内容をクラウド/APIへ送らないでください。外部Web検索もしないでください。
- すべての入力は読み取り専用として扱ってください。解析用の一時スクリプト・キャッシュを作る場合は、`$env:TEMP`等の一時ディレクトリを使い、調査後に作成物を削除してください。
- 出力先に既存ファイルがある場合は上書きしないでください。日時付きの新規ファイル名を使ってください。
- ファイル名やモデルIDは候補を絞る手掛かりにすぎません。人名との対応を**確定事実として断定しない**でください。
- カットシーン用、若年/別年齢、別衣装、イベント、NPC/敵、顔だけ/髪だけ等の可能性を分けてください。とくに`c_cm_*`など接頭辞だけでゲーム用途を断定せず、観測した情報と推測を分けて書いてください。
- 候補が見つからない場合も、近い名前の別人を無理に割り当てず「不明/未発見」としてください。
- 書き出しやStrict往復検証を実行できない場合は「未実行」とし、実行したように書かないでください。Strict往復成功も、ゲーム内の見た目・モーション互換を保証しません。

## 調査手順

### 1. ファイル索引

全`.gmd`の相対パス、モデルIDフォルダ、領域サブフォルダ、ファイル名、サイズ、SHA-256を索引化してください。SHA-256計算は重ければ候補だけでも構いませんが、未計算は明記します。

候補検索では、キャラクター名そのものだけでなく、以下のようなモデルID断片・別表記・ローマ字の揺れも考慮してください。これは検索ヒントであり、人物の確定対応ではありません。

- Sugiura: `sugiura`
- Tsukumo: `tsukumo`
- Saori: `saori`, `ci01_saori`
- Higashi: `higashi`
- Tesso: `tesso`
- Kuwana: `kuwana`
- Soma: `soma`
- Akutsu: `akutsu`
- Genda: `genda`
- Hoshino: `hoshino`
- Mafuyu: `mafuyu`
- Sawa: `sawa`

該当名の候補が見つからない人物については、語の一致がない全モデルIDを無差別に深掘りせず、その旨を報告してください。

### 2. 候補GMDの技術情報

候補に対して、可能なら同梱BlenderとGMDアドオンを使って実データを解析します。テキスト検索やGMDヘッダーだけで内部構造を推定しないでください。各GMDについて記録する情報：

- 入力ルートからの相対パス（絶対パスだけにしない）
- モデルID、領域（`tops`/`face`/`hair`等）、ファイル名、サイズ、SHA-256
- GMDの読み込み成否と、警告/エラーの要約
- リグ/階層名、骨数、骨名一覧または一覧ファイルの相対パス、主要骨（頭・首・背骨・腕・脚・手）の有無
- メッシュ数、メッシュごとの名前、頂点/面数、材質名
- 材質ごとのシェーダー名、opacity、specular、利用可能なら主要属性フラグとテクスチャ参照名
- 同じモデルIDに`tops`/`face`/`hair`が揃うか。揃わない場合は欠けているスロット
- 異なる候補ファイル間で骨名集合や骨数が一致するか（顔/髪/胴体が同一人物の同一リグかどうか）

解析でスクリプトを作る場合は出力をコンパクトにし、全メッシュや全頂点の巨大なダンプをプロンプトへ貼り付けないでください。必要なら骨名一覧を別のテキストJSON/TSVに保存し、JSONレポートから相対パスで参照してください。

### 3. 候補の評価

キャラクターごとに、該当しそうな候補を複数挙げ、以下を評価してください。

- 人名との対応確度：`high` / `medium` / `low` / `unknown`
- ターゲット候補状態：`candidate` / `partial_slots` / `cutscene_or_variant` / `incompatible_or_unknown` / `not_found`
- 実在確認できたスロット（`tops`/`face`/`hair`）と各GMDの相対パス
- 骨数・骨名集合の一致状況と、候補ごとに別リグの疑いがあるか
- 出力先としてVRMDragonToolの現在のYagami形式（tops/face/hair別GMD）に適合しそうか、単一GMD試験が必要か
- 不足情報、衝突する候補、追加の人手確認が必要な点
- 根拠は必ず観測したパス/メタデータに紐づけ、推測と観測を分ける

`tops/face/hair`を同じモデルID名だからという理由だけで組み合わせないでください。骨名集合・骨数・GMD内のリグ情報を比較し、異なる衣装/年齢/カットシーンの混在を避けるための根拠を記載します。モデル間で骨数が同じでも互換性が確定したとはしません。

### 4. JSONレポートを作成

出力先に新しい日時付きファイルとして、以下を作成してください。

1. `character_target_candidates_YYYYMMDD_HHMMSS.json`
2. `character_target_candidates_YYYYMMDD_HHMMSS.md`（短い人間向け要約）

JSONは有効なUTF-8 JSONとし、以下の形を基本にしてください。値が不明な項目は推測で埋めず`null`、不確実な一覧は空配列にし、`notes`に理由を書きます。

```json
{
  "schema_version": 1,
  "generated_at_local": "YYYY-MM-DDTHH:MM:SS",
  "read_only": true,
  "source_root": "<利用者の抽出済みCharaフォルダ>",
  "tool_root": "<ツールの配置先>",
  "method": {
    "gmd_parser": "exact tool/addon/version or not run",
    "blender_version": "exact version or null",
    "full_gmd_count": 0,
    "indexed_gmd_count": 0,
    "deep_inspected_gmd_count": 0,
    "limitations": []
  },
  "characters": [
    {
      "requested_name": "Fumiya Sugiura",
      "status": "candidate|partial_slots|cutscene_or_variant|incompatible_or_unknown|not_found",
      "identity_confidence": "high|medium|low|unknown",
      "candidate_model_ids": ["..."],
      "recommended_reference_set": {
        "tops": "relative/path/or/null",
        "face": "relative/path/or/null",
        "hair": "relative/path/or/null"
      },
      "slots": [
        {
          "role": "tops|face|hair|other",
          "relative_path": "...",
          "model_id": "...",
          "file_size": 0,
          "sha256": "... or null",
          "load_status": "loaded|failed|not_inspected",
          "rig_name": "... or null",
          "bone_count": 0,
          "bone_names": ["..."],
          "bone_names_file": "relative/path/or/null",
          "mesh_count": 0,
          "meshes": [
            {
              "name": "...",
              "vertices": 0,
              "faces": 0,
              "materials": [
                {
                  "name": "...",
                  "shader": "... or null",
                  "opacity": 255,
                  "specular": [0, 0, 0],
                  "attribute_flags": null,
                  "textures": {}
                }
              ]
            }
          ],
          "warnings": []
        }
      ],
      "rig_compatibility": {
        "compared_slots": ["tops", "face", "hair"],
        "bone_counts_equal": null,
        "bone_name_sets_equal": null,
        "missing_major_bones": [],
        "assessment": "not_tested|likely_compatible|mismatch|needs_review",
        "evidence": []
      },
      "workflow_fit": {
        "multi_gmd_layout": "likely|unlikely|unknown",
        "single_gmd_trial_needed": true,
        "cutscene_or_age_variant_risk": "low|medium|high|unknown",
        "notes": []
      },
      "reasoning": {
        "observed_facts": [],
        "inferences": [],
        "unresolved_questions": []
      }
    }
  ],
  "global_warnings": [],
  "game_install_changed": false,
  "extracted_source_files_changed": false
}
```

JSON例の0やnullは形式例です。実測値が取れない場合に適当な値へ置き換えず、`null`または`not_inspected`で表現してください。骨名一覧をJSON本体に含めると大きくなりすぎる場合は、同じ日時の`details/`以下に別ファイルとして保存し、その相対パスを`bone_names_file`へ記載してください。ファイル数や候補数を報告し、未調査候補を調査済みに見せないでください。

## 最終報告

最後の応答は短く、次だけを示してください。

- 作成したJSONとMarkdownの絶対パス
- 12名それぞれの状態（候補あり/部分スロット/variant疑い/未発見）
- 使用した解析方法と深掘りできなかった範囲
- 次にPi側へ渡すべきJSONレポートのパス

コードの変更やゲームへの導入は行わず、候補の提案にとどめてください。
