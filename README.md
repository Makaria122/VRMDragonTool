# VRMDragonTool

An experimental tool that generates VRM replacement mods for Lost Judgment. It does not install anything into the game and does not extract game data. Each user supplies the Chara folder extracted from a game they own, and a VRM they have the right to use.

**For setup, usage and limitations, see [Tool/README.md](Tool/README.md).** (The GUI itself is currently in Japanese.)

- An AI-free simple mode (default) and a detailed mode that uses a tool-owned Ollama/Qwen. The tool never connects to a global Ollama.
- Looks up the reference GMDs of registered characters and outfits in your extracted folder.
- Per-skeleton-group adjustment, plus strict export and material validation for every model.
- Motion Actions are optional. Without one, output is a review candidate whose motion check was not run.

In-game appearance, native motion and every model switch are not guaranteed. Do not treat a failed or skipped motion check as a pass.

## Before publishing

`python Tool/export_public.py --output PublicRelease` creates a distribution folder with private data excluded. Do not upload your whole working folder.

Original code and documents are under the [MIT License](LICENSE); improvements, redistribution and commercial use are welcome. Third-party parts such as the bundled add-on keep their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). This grants no right to redistribute game assets, VRMs or AI models. This tool does not perform any GitHub publishing for you.
