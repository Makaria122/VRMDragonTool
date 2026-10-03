# VRM → Dragon Engine / Lost Judgment (experimental)

> [!WARNING]
> **Work in progress and unstable.** Conversions can fail for some avatars, in-game results are unverified and the accessory-bone geometry check currently fails on every tested output. See the [warning in the main README](../README.md) for the full list of known problems.

Generates review-only replacement mod candidates from a VRM, using GMD files that **you extracted yourself from a game you own**. No game assets, VRMs, motion Actions or AI models are distributed. The tool never extracts game data and never installs anything into the game.

## Requirements

| What | Details |
|---|---|
| OS | **Windows 10/11** (developed and tested on Windows 11; the launcher, the Ollama download and some GUI buttons are Windows-only) |
| Python | **3.10 or newer, with Tkinter** (tested with 3.10). With the python.org installer keep "tcl/tk and IDLE" ticked. |
| Pillow | 10 to 12 (`Tool/requirements.txt`) |
| Blender | **4.5 LTS** (tested with 4.5.14). Not bundled: the tool can download the official portable build for you (see Installation), or you can use your own. |
| GMD add-on | Bundled in `Tool/vendor/yakuza-gmd-gmt-blender` (GPL v3, separate license; built on the work of TheTurboTurnip and mosamadeeb, see `THIRD_PARTY_NOTICES.md`). Nothing to install in Blender. |
| Your game data | A **Chara folder you extracted yourself** from your own copy of Lost Judgment. This project does not explain or provide extraction. The game does not have to be running or even installed to convert; it is only needed to try the result. |
| A VRM | A humanoid VRM you are allowed to use. It is read through Blender's glTF importer. |
| Disk space | Blender is about 1 GB. Each converted model keeps about 0.2 GB of working files in `Tool/userdata/outputs` (a full switch-target batch can reach several GB; clean up in the "Storage" tab). The detailed mode (local AI) adds about 1.8 GB for Ollama and about 4.4 GB for the model. |
| Memory | Not measured. Large avatars need several GB of RAM in Blender. The detailed mode loads a 7B model (about 5 GB), so keep roughly that much RAM/VRAM free. |
| Internet | Only for the explicit AI downloads of the detailed mode. Conversion itself works offline. |

## Installation

1. **Get the tool.** Either `git clone https://github.com/Makaria122/VRMDragonTool.git` or use "Code → Download ZIP" on GitHub and extract it. Put it in a normal folder (for example `D:/Tools/VRMDragonTool`), not inside the game folder or a mod manager's folder.
2. **Install Python 3.10+** from python.org. Tick "Add python.exe to PATH" and keep "tcl/tk and IDLE". Check it with `python -c "import tkinter"` in a terminal; if that prints an error, Tkinter is missing.
3. **Install Pillow** without touching your global Python: open a terminal in the tool folder and run `python -m pip install --target Tool/runtime/python-packages -r Tool/requirements.txt` (a plain `python -m pip install -r Tool/requirements.txt` also works).
4. **Blender 4.5 LTS.** Nothing to do by hand: when you first start the tool and no Blender is found, it asks whether to download Blender 4.5.14 (about 400 MB, about 1 GB unpacked) from the official server `download.blender.org`. The download is checked against a pinned SHA-256 checksum and installed only into `Tool/runtime/blender`; nothing is downloaded without your confirmation. You can also start or repeat it from the "Blender" tab, or choose a `blender.exe` you already have ("Choose my own blender.exe..."; the choice is remembered). The tool also finds Blender automatically at `Tool/runtime/blender/blender.exe` or `Blender/blender.exe` next to `Start-Tool.cmd`.
5. **Start the tool** by double-clicking `Start-Tool.cmd` (or run `python Tool/launch.py`). If it says Python 3.10+ with Tkinter was not found, repeat step 2.
6. **Optional, detailed mode only:** see "Setup for the detailed mode" below. The default simple mode needs no AI.

## Quick start

1. Start the tool (`Start-Tool.cmd`). You are on the "One-click mod" tab.
2. **Extracted Chara folder → "Browse / search...":** choose the Chara folder you extracted from the game. The tool searches it recursively for the registered GMD files.
3. **Target character:** pick the character whose model you want to replace. The tops/face/hair reference fields fill in by themselves. If the status line says references are missing, the folder does not contain that character's files.
4. **VRM (required) → "Browse...":** choose your VRM.
5. Check that the **Blender executable** and **GMD add-on folder** fields are filled (Blender is filled in after the download or when you choose it).
6. Leave **Profile creation** on "Simple" unless you want the local AI. Leave the switch-target checkbox on to also convert the character's other outfits and cutscene models, or turn it off to convert only the base model (faster, less disk space).
7. Press **"Create mod pack from VRM automatically (beta, no game install)"**. Progress appears in the status line at the bottom; expect a few minutes per model. Do not close the window while it runs.
8. When it finishes, Windows Explorer opens the finished mod folder: the one that contains `mod-meta.yaml` and `chara/`. It lives in a `ReviewPack/Mods/` folder under `Tool/userdata/outputs/VRM_<character>_<vrm name>_<date>/`. `MODLOG.md` inside it lists what was checked, and `VARIANT_REVIEW_WARNING.txt` appears when checks failed or were not run.

### Using the result

The tool never installs anything. The generated folder uses the Mods format (with `mod-meta.yaml`) that mod managers such as Shin Ryu Mod Manager read; this has not been verified by the project's tests. To try it, back up your game and mod setup, copy the generated mod folder into your mod manager's Mods folder yourself, enable it, and start the game. Enable only one mod per character and replacement target, because two mods that replace the same file conflict. Whether it looks right in the game is unverified; see the warning at the top.

### Troubleshooting

| Problem | What to do |
|---|---|
| `Start-Tool.cmd` says Python 3.10+ with Tkinter was not found | Install Python from python.org with "tcl/tk and IDLE", and make sure `python` is on PATH. |
| "Missing/duplicate references" in the status line | The selected Chara folder does not contain that character's registered GMD files, or two files with the same name differ. Pick the right folder or another character. |
| Blender or add-on field is empty | Open the "Blender" tab and download Blender, or choose your own `blender.exe`. The add-on folder is `Tool/vendor/yakuza-gmd-gmt-blender`. |
| The Blender download fails | Check your internet connection, proxy or firewall (the tool contacts only `download.blender.org`) and that about 2.5 GB are free. A failed or cancelled download leaves nothing half-installed. You can instead download Blender 4.5 LTS yourself and choose its `blender.exe`. |
| A conversion stops with an error | Read the message, then open the "Logs" tab, press "Create debug report" and attach the file when you report it (see "Reporting a problem"). |
| The disk fills up | Open the "Storage" tab and delete old output folders, or only their working `.blend` files. |
| It works but the result looks wrong in the game | Expected for now: see the warning at the top. Report it with the avatar's name and the character you replaced. |

## Profile modes

Choose the mode under "Profile creation" on the "One-click mod" tab. Your last choice is saved.

- **Simple (default, no AI):** mesh regions (tops/face/hair) come from the rule-based classification of the inspection step; head accessories the rules cannot classify become tops. A weight group that exists only in the VRM is assigned to the nearest matched ancestor bone in the VRM's bone hierarchy. The "detailed mode" setup below is not needed. If the rules cannot decide (a region is missing, or a bone has no matched ancestor) the tool stops and says why. The result goes through the same validation as the detailed mode.
- **Detailed (local AI):** the previous behaviour. A tool-owned Ollama/Qwen proposes the classification and bone mapping, and the result goes through the same validation. Set it up as follows.

## Setup for the detailed mode (local AI, optional)

1. Open the "AI setup" tab → "Set up Ollama" and confirm. The official Windows portable release is verified with SHA-256 and placed in `Tool/runtime/ollama`. It needs roughly 1.5 GB of download plus extraction/temporary space.
2. Press "Download Qwen". `qwen2.5-coder:7b` is about 5 GB, so make sure you have enough disk space and RAM/VRAM. Models are stored in `Tool/runtime/models`.

Downloads only happen on these explicit actions. Conversion never downloads Ollama or a model by itself, and the tool never connects to an existing global Ollama.

Ollama runs as a separate process started from the executable inside the tool folder, with a dedicated loopback port and storage, and model requests unload with `keep_alive: 0`. When the GUI/CLI exits, only processes the tool started are stopped. This is not an OS/GPU-driver sandbox.

## Generation steps

1. Select the **Chara folder** you extracted from your game. Registered GMD file names are searched recursively, whether the folder has the original layout, a per-model-ID layout or a flat layout.
2. Choose the target character; the tops/face/hair references are filled in automatically. Layouts such as a single GMD, or face+hair combined, are resolved by registered recipes.
3. If a reference is missing, the tool stops. It also stops when several GMDs share a name but differ in content; only identical duplicates are resolved deterministically. A different character or outfit is never substituted just because the bone count matches.
4. Select the VRM, Blender and the add-on, then press "Create mod pack from VRM automatically (beta, no game install)". This runs mesh classification and bone mapping (rules in simple mode, local AI in detailed mode), anatomical fitting, material assignment, GMD export and a strict re-import.
5. To also generate outfit/event/cutscene variants, turn on "Also validate and generate switch targets whose references were found (unverified in-game)". It is on by default and your choice is remembered. Finding a reference is not a validation pass; validation happens when each variant is generated.

Each conversion leaves its working files (large working `.blend` files in particular) in `Tool/userdata/outputs`. Use the "Storage" tab to see the sizes and delete selected output folders, or only their working `.blend` files while keeping the generated mods. Deleting cannot be undone.

References are read-only. Local settings, profiles and outputs are stored under `Tool/userdata` (not tracked by Git). Those files contain your paths and asset information, so do not publish them. Keep the extracted folder itself outside any Git-managed folder.

### Motion checks are optional

If you provide a motion Action `.blend`, each model is compared against its original GMD baseline. Without an Action the result is `motion_validation: MOTION_NOT_RUN`, and the tool never claims a motion-quality pass. A separate failing accessory-bone/geometry check is recorded as `GEOMETRY_CHECK_FAILED`. Output is always a review candidate. Even with an Action, anything other than the target character's native animation is only a proxy diagnostic.

### Supported targets and caveats

- Yagami, Kaito, and experimentally Sugiura, Tsukumo, Saori, Higashi, Tesso, Kuwana, Soma, Akutsu, Genda, Hoshino, Mafuyu and Sawa are registered.
- Some registered outfit, event and cutscene layouts are supported too. Kuwana includes the `c04bd01`, `c10bd01` and `army` tops, plus the user-approved young-era `c_cm_x_kuwana_30` (a single GMD that contains the face). Yagami also covers `c07bd01`, `c07bd02` and the seated `c07_chair` (for seated poses the legs are fitted to the target's bone directions). These were only checked up to the strict round trip; in-game posture, expression and switching are unverified. For Sawa, the user-approved `c_aw_sawa_18`, `c_aw_sawa_dead` and `c_aw_sawa_sit` are also part of switch-target generation, giving four layouts including the normal one, each written to its own GMD. The three extra Sawa layouts passed the reference strict round trip, but their in-game posture and expression for young/dead/seated states are unverified. The different character Amasawa is not included. Not every in-game model switch is covered.
- Avatars with unusual part names or poses: the head is also recognised by geometry (meshes entirely above the neck), arms that hang down are fitted to the target's raised arms, and a part the avatar lacks (for example hair) is only an error for targets that need a separate GMD for it. Such avatars are still review candidates; check the result carefully.
- Even for the same character and the same VRM, adjustments are shared only between groups whose measured bone names, parents and rest matrices match. Outfit-dependent ground contact is measured again every time, and materials, export and strict validation run per model.
- The ground plane is measured from vertices weighted at least 25% to the foot/toes, using the support surface below the ankle. A name such as "bandage" never decides the floor. If it cannot be measured, the tool stops for review.
- Diffuse maps are generated from the VRM (resampled so each side is a multiple of 4 and at most 4096 px; the original size is kept in `texture-map.json`). The four auxiliary slots (multi/normal/rt/rd) always get procedurally generated neutral DDS files. DDS and GMD references are separated into a namespace made from the target character plus the VRM content hash.
- Neutral DDS files use the same storage formats as the earlier dummy maps: multi is 4×4 DXT1/BC1 (3 mips), white is DXT1/BC1 (1 mip), and normal/rt are uncompressed BGRA8. Changing everything to RGBA would risk altering normal-map channel interpretation and material response, so it is not done. Colours are generated from our own constants and no game DDS is bundled. You can confirm this with `dummy_texture_format_policy: neutral-bc1-bgra-v2` in `texture-map.json`. Loading and colours are checked with Pillow/Blender, but whether the metallic look is gone in-game still has to be checked separately.
- The matte policy is kept: eye-surround decal materials are not reused on clothing or body. A strict-export success does not mean hair transparency, lighting, expressions, bone sway or native motion pass.
- Enabling several mods for the same replacement target of the same character conflicts. The multi-mod merge refuses same-named paths with different content.

## Characters from other Dragon Engine games (custom targets)

Besides the registered Lost Judgment characters you can add your own: choose **"Other (add your own GMD files)..."** in the target list. There are two ways:

### Whole character (recommended)

A character usually has many parts (outfits, hair styles, faces). This replaces all of them at once, so no scene falls back to the original model.

1. Choose the folder with the files you extracted (any folder; it is searched recursively, and it may even be inside a game folder because it is only read) and type the character name, for example `ichiban`.
2. The tool lists every GMD whose file name contains the name, split into body (tops), face and hair, and reads them all with Blender (read-only). Each file is checked for the skeleton the fitting needs. The plainest name of each kind becomes the **base set** (always added); every other usable file is an **extra part**.
3. Models that should not simply be replaced are **unticked by default**: undressed (`naked`, `nude`), swimwear, dead, other age, test and special-pose models, and files that cannot be read or have another skeleton. Click `[ ]` / `[x]` to change it, then press "Add this character". Private copies of the ticked files are stored in `Tool/userdata/targets/`.
4. Pick the character in the target list and convert as usual. With the switch-target checkbox on, **every part is converted** (only that part's file is exported, a few Blender jobs run in parallel, working `.blend` files are deleted as it goes) and everything ends up in one Mods-format folder; with it off only the base set is converted. "Parallel Blender jobs" (default 3) sets how many run at once.

### Single GMD files

Pick one body GMD (face and hair next to it in the usual `.../tops/<id>/<id>.gmd`, `.../face/...`, `.../hair/...` layout are found automatically and you are asked whether to add them) or choose the files by hand. Without face/hair everything goes into the one body GMD.

### How it works, and limits

- The tool reads the files once with Blender (read-only), checks that the skeleton has the bones its fitting needs (the Dragon Engine bone names such as `ketu_c_n`, `kubi_c_n`, `ude1_l_n`, `asi3_l_n`; finger bones are optional), then keeps **private copies** in `Tool/userdata/targets/` (SHA-256 checked on every use). The original files, even inside a game folder, are never changed and are not used again afterwards.
- The output keeps the game's layout: `chara/<tops|face|hair>/<name>/<name>.gmd`. Parts with a different bone count (extra cloth bones) are converted with their own bone count. "Remove custom target" deletes the copies.
- A skeleton with different bone names is refused with the list of missing bones. Materials and shaders of other games may differ, so in-game results are unverified.
- A body model without feet (for example a hands-only first-person model) is refused when you add the character, because the floor cannot be measured and it could not replace a full body.
- The author tried this with Like a Dragon 8 (Ichiban, 62 matching files, 42 ticked by default): all 40 outfits/hair styles/faces converted in about 7 minutes with 3 parallel jobs (16-core PC), and the batch folder stays around 160 MB because intermediate files are deleted as it goes. The GMDs sit correctly on the skeleton in Blender; nothing has been checked in the game.

## Reporting a problem

If a conversion fails or looks wrong, open the "Logs" tab and press "Create debug report", then attach the generated `debug-report-*.txt` (in `Tool/userdata/logs`) to your issue together with the avatar's name or where it came from. The report holds the tool version fingerprint, Python/OS/Blender information, the most recent failed runs and the newest log, including the full Blender output of the failing step.

Logs are kept on your machine only (about 12 MB at most). User names and home-folder paths are masked, but file names, avatar names and error text are not, so read the report before you post it. Do not attach your VRM, GMD or generated mod files.

## Building the public source

Do not upload the whole repository root as is.

```powershell
python Tool/export_public.py --output PublicRelease
python -m unittest discover -s Tool/tests -v
```

An explicit allowlist copies only source, tests, documents, the add-on and licenses, and generates a distribution manifest. `Tool/runtime`, `Tool/userdata`, private assets, generated mods and private history are excluded. An existing output folder is never overwritten. The script never pushes to GitHub.

Original code and documents are MIT licensed. Third-party parts such as `Tool/vendor/` follow their own licenses. Check `THIRD_PARTY_NOTICES.md` and the licenses of your dependencies before publishing. This does not grant any right to redistribute models, VRMs or game-derived files.
