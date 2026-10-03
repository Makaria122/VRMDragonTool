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
- Looks up the reference GMDs of registered characters and outfits in your extracted folder.
- Per-skeleton-group adjustment, plus strict export and material validation for every model.
- Motion Actions are optional. Without one, output is a review candidate whose motion check was not run.

In-game appearance, native motion and every model switch are not guaranteed. Do not treat a failed or skipped motion check as a pass.

## Before publishing

`python Tool/export_public.py --output PublicRelease` creates a distribution folder with private data excluded. Do not upload your whole working folder.

Original code and documents are under the [MIT License](LICENSE); improvements, redistribution and commercial use are welcome. Third-party parts such as the bundled add-on keep their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). This grants no right to redistribute game assets, VRMs or AI models. This tool does not perform any GitHub publishing for you.
