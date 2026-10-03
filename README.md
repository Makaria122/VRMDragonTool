# VRMDragonTool (Only Lost Judgment is supported for now.)

> [!WARNING]
> # WORK IN PROGRESS (WIP): UNSTABLE
>
> **This project is unfinished and unstable.** Expect bugs, conversions that stop with an error, and results that look wrong in the game. Do not rely on it for anything important, and keep backups of your game files and mods. No guarantee of any kind is given.
>
> **Known unstable or unverified areas:**
>
> - **Conversion can fail for some avatars.** Only about ten avatars have been tried. VRMs that do not follow the usual layout can stop with an error: for example missing UVs, unweighted vertices, no measurable foot contact, non-humanoid bodies, missing bones, or a missing hair/face part for targets that need a separate GMD for it.
> - **In-game appearance is not verified.** Results are review candidates only. Native animation, expressions, hair transparency, bone sway and model switching have not been confirmed in the game, and the metallic-look fix is unconfirmed.
> - **The accessory-bone geometry check currently fails on every tested output** (`GEOMETRY_CHECK_FAILED`), so hair, tails, skirts and similar parts may look broken.
> - **Most characters and outfits are experimental.** Seated, young-era and dead-state models and unusual poses (for example avatars with hanging arms) have only been checked up to the export round trip.
> - **The detailed mode (local AI) has not been tested on a clean machine**, and the GUI, options and file formats may change without notice.

An experimental tool that generates VRM replacement mods for Lost Judgment. It does not install anything into the game and does not extract game data. Each user supplies the Chara folder extracted from a game they own, and a VRM they have the right to use.

**For setup, usage and limitations, see [Tool/README.md](Tool/README.md).**

- An AI-free simple mode (default) and a detailed mode that uses a tool-owned Ollama/Qwen. The tool never connects to a global Ollama.
- Looks up the reference GMDs of registered characters and outfits in your extracted folder, and can register your own GMD files from other Dragon Engine games as a custom target (experimental, see [Tool/README.md](Tool/README.md)).
- Per-skeleton-group adjustment, plus strict export and material validation for every model.
- Motion Actions are optional. Without one, output is a review candidate whose motion check was not run.

In-game appearance, native motion and every model switch are not guaranteed. Do not treat a failed or skipped motion check as a pass.

## Requirements

- **Windows 10/11** (tested on Windows 11), **Python 3.10+ with Tkinter**, **Pillow**, and **Blender 4.5 LTS** (not bundled: the tool offers to download the official build on first start, or you can use your own). The GMD add-on is bundled.
- A **Chara folder you extracted yourself** from your own copy of Lost Judgment (extraction is not covered here) and a humanoid **VRM** you may use.
- About 1 GB for Blender plus roughly 0.2 GB of working files per converted model. The optional detailed mode (local AI) adds about 6 GB.

## Install and run

1. Download this repository (`git clone https://github.com/Makaria122/VRMDragonTool.git` or "Code → Download ZIP") into a normal folder.
2. Install Python 3.10+ from python.org (tick "Add python.exe to PATH" and keep "tcl/tk and IDLE"), then run `python -m pip install --target Tool/runtime/python-packages -r Tool/requirements.txt` in the tool folder.
3. Double-click `Start-Tool.cmd`. If no Blender is found, the tool asks whether to download Blender 4.5.14 from the official server (about 400 MB, checksum-verified, installed inside the tool folder only), or you can pick your own `blender.exe`.
4. In the window: pick your extracted Chara folder, choose the target character, pick your VRM, then press "Create mod pack from VRM automatically". The finished mod folder opens when it is done; copy it into your mod manager yourself (the tool never installs anything).

Full instructions, troubleshooting and the optional local-AI mode are in [Tool/README.md](Tool/README.md).

## Credits

- GMD reading/writing is done by the bundled Blender add-on `yakuza-gmd-gmt-blender` (GPL v3), which builds on [yk_gmd_io](https://github.com/theturboturnip/yk_gmd_io) by Samuel Stark (TheTurboTurnip) and [yakuza-gmt-blender](https://github.com/mosamadeeb/yakuza-gmt-blender) by mosamadeeb. Thank you to their authors. Details and licenses: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Before publishing

`python Tool/export_public.py --output PublicRelease` creates a distribution folder with private data excluded. Do not upload your whole working folder.

Original code and documents are under the [MIT License](LICENSE); improvements, redistribution and commercial use are welcome. Third-party parts such as the bundled add-on keep their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). This grants no right to redistribute game assets, VRMs or AI models. This tool does not perform any GitHub publishing for you.
