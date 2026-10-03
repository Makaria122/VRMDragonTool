# Third-party notices / license check before publishing

The original code and documents of this project are provided under the MIT License in the root `LICENSE`. Improvement, redistribution and commercial use are permitted; the copyright notice and license text must be kept.

**`Tool/vendor/` and any third-party code or dependencies are excluded from the MIT grant.** They follow their own original licenses. The list below is a guide to the main dependencies and does not replace the original license of anything bundled or downloaded.

- **yakuza-gmd-gmt-blender**: vendored GMD add-on. Keep `Tool/vendor/yakuza-gmd-gmt-blender/LICENSE` and the copyright notices in its source. Check the GPL conditions and do not strip the bundled source.
- **Ollama**: https://github.com/ollama/ollama (MIT). The binary is not part of the GitHub source distribution; the official Windows portable release is downloaded only by an explicit setup action. Check the distributor for separate licenses (for example GPU-related libraries).
- **Qwen2.5-Coder-7B-Instruct**: https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct (Apache-2.0). Ollama's `qwen2.5-coder:7b` is downloaded only by an explicit action. Check the model's distributor, model card and terms of use. The model itself is not included in the GitHub repository.
- **Pillow**: https://python-pillow.org/ (HPND and others; see the LICENSE of the distribution). Installed separately as a dependency.
- **Python / Tkinter**: https://www.python.org/ . See each distributor for the Python and Tcl/Tk licenses. The interpreter is not bundled in the current source distribution.
- **Blender**: https://www.blender.org/ (GPL). Supplied separately by the user and not bundled in the current source distribution.

Lost Judgment GMD/DDS/Action files, VRMs, generated mods, private profiles and AI models are outside the public source. This project does not provide extraction procedures for game assets, circumvention of access controls, or redistribution.
