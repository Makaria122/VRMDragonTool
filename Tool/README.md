# VRM → Dragon Engine / Lost Judgment (experimental)

> [!WARNING]
> **Work in progress and unstable.** Conversions can fail for some avatars, in-game results are unverified and the accessory-bone geometry check currently fails on every tested output. See the [warning in the main README](../README.md) for the full list of known problems.

Generates review-only replacement mod candidates from a VRM, using GMD files that **you extracted yourself from a game you own**. No game assets, VRMs, motion Actions or AI models are distributed. The tool never extracts game data and never installs anything into the game.

## First-time setup (Windows)

1. Prepare Python 3.10+ (with Tkinter) and Blender 4.5.x. Python/Tkinter must currently be installed separately. Blender can be selected in the GUI, or placed at `Tool/runtime/blender/blender.exe`.
2. Pillow is required. Example that does not touch your global environment: `python -m pip install --target Tool/runtime/python-packages -r Tool/requirements.txt`.
3. Start the tool with `Start-Tool.cmd`.

### Profile modes

Choose the mode under "Profile creation" on the "One-click mod" tab. Your last choice is saved.

- **Simple (default, no AI):** mesh regions (tops/face/hair) come from the rule-based classification of the inspection step; head accessories the rules cannot classify become tops. A weight group that exists only in the VRM is assigned to the nearest matched ancestor bone in the VRM's bone hierarchy. The "detailed mode" setup below is not needed. If the rules cannot decide (a region is missing, or a bone has no matched ancestor) the tool stops and says why. The result goes through the same validation as the detailed mode.
- **Detailed (local AI):** the previous behaviour. A tool-owned Ollama/Qwen proposes the classification and bone mapping, and the result goes through the same validation. Set it up as follows.

Setup for the detailed mode only:

4. Open the "AI setup" tab → "Set up Ollama" and confirm. The official Windows portable release is verified with SHA-256 and placed in `Tool/runtime/ollama`. It needs roughly 1.5 GB of download plus extraction/temporary space.
5. Press "Download Qwen". `qwen2.5-coder:7b` is about 5 GB, so make sure you have enough disk space and RAM/VRAM. Models are stored in `Tool/runtime/models`.

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
- Diffuse maps are generated from the VRM. The four auxiliary slots (multi/normal/rt/rd) always get procedurally generated neutral DDS files. DDS and GMD references are separated into a namespace made from the target character plus the VRM content hash.
- Neutral DDS files use the same storage formats as the earlier dummy maps: multi is 4×4 DXT1/BC1 (3 mips), white is DXT1/BC1 (1 mip), and normal/rt are uncompressed BGRA8. Changing everything to RGBA would risk altering normal-map channel interpretation and material response, so it is not done. Colours are generated from our own constants and no game DDS is bundled. You can confirm this with `dummy_texture_format_policy: neutral-bc1-bgra-v2` in `texture-map.json`. Loading and colours are checked with Pillow/Blender, but whether the metallic look is gone in-game still has to be checked separately.
- The matte policy is kept: eye-surround decal materials are not reused on clothing or body. A strict-export success does not mean hair transparency, lighting, expressions, bone sway or native motion pass.
- Enabling several mods for the same replacement target of the same character conflicts. The multi-mod merge refuses same-named paths with different content.

## Building the public source

Do not upload the whole repository root as is.

```powershell
python Tool/export_public.py --output PublicRelease
python -m unittest discover -s Tool/tests -v
```

An explicit allowlist copies only source, tests, documents, the add-on and licenses, and generates a distribution manifest. `Tool/runtime`, `Tool/userdata`, private assets, generated mods and private history are excluded. An existing output folder is never overwritten. The script never pushes to GitHub.

Original code and documents are MIT licensed. Third-party parts such as `Tool/vendor/` follow their own licenses. Check `THIRD_PARTY_NOTICES.md` and the licenses of your dependencies before publishing. This does not grant any right to redistribute models, VRMs or game-derived files.
