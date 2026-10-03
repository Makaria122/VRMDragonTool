# Changes

## Custom targets: GMD files from other Dragon Engine games
- New "Other (add your own GMD files)..." entry in the target list: pick a body GMD (face/hair next to it are found automatically), the tool inspects it in Blender (read-only), checks the skeleton and registers a custom target in `Tool/userdata/targets/` with private copies of the files (SHA-256 checked on every use; the originals, even inside a game folder, are never changed). Layouts: body only (single GMD), body+face, or body+face+hair; output keeps `chara/<region>/<name>/<name>.gmd`. A skeleton without the required bones is refused with the names of the missing bones. No switch targets for custom targets.
- First real case: Like a Dragon 8 Ichiban (297 bones, all 51 expected bone names present): a VRM converted to three GMDs and fits the skeleton in Blender. In-game behaviour is unverified.
- "Remove custom target" button. 19 new tests.

## Fixes found by a fresh GitHub download
- The shader file the bundled GMD add-on needs (`yakuza_shader.blend`) was missing from the public repository; it is now exported byte for byte (every other `.blend` stays private) and `.blend` is marked binary in `.gitattributes`.
- Avatars with textures whose size is not a multiple of 4 (for example the common 2x2 flat-colour images) no longer stop the conversion: images are resampled so each side is a multiple of 4, textures larger than 4096 px are scaled down to at most 4096 (sources up to 8192 px are accepted), and WebP images are accepted too. Resampling keeps the 0..1 UV mapping valid; the original size is recorded as `resized_from` in `texture-map.json`.
- Error dialogs and messages show the real error lines of a failed Blender step instead of the tail of unrelated output.

## Optional Blender download
- When no Blender is found at start-up, the tool asks whether to download the pinned official portable Blender 4.5.14 (about 400 MB) from `download.blender.org`; new "Blender" tab with progress, cancel and "choose my own blender.exe". Nothing is downloaded without a confirmation.
- The archive must match the reviewed size and SHA-256, the host must be `download.blender.org` over HTTPS (redirects elsewhere are refused), the zip is unpacked into a staging folder with strict path/symlink/size checks, moved into `Tool/runtime/blender` in one step and started once (`--version`) to confirm it is the expected Blender; any failure or cancel leaves nothing behind, and an existing non-empty `Tool/runtime/blender` is never overwritten. A stale saved Blender path no longer hides an auto-detected one.

## Log files and debug report
- The tool now writes a log to `Tool/userdata/logs/vrmdragon.log` (rotating, about 12 MB at most): environment information at start-up, progress messages, error tracebacks, uncaught GUI errors, and for every Blender step the command line plus its exit code; when a step fails the full Blender output (clipped to 100 KB) is kept, where the error dialog only shows the tail. User names and home-folder paths are masked as lines are written. Logging never raises into the application.
- New "Logs" tab: "Create debug report" writes a redacted text file (environment, tool fingerprint, recent failed runs, newest log) to share in a bug report; "Open logs folder"; "Delete all logs". Error dialogs point to it. Logs stay on the machine and are never uploaded.

## Storage tab: clean up generated outputs
- New "Storage" tab lists the folders in `Tool/userdata/outputs` with their size and how much of it is working `.blend` files, and can delete selected folders or only their working `.blend` files (generated mods, reports and textures are kept). A confirmation shows the amount first.
- Safety: only direct child folders of `Tool/userdata/outputs` can be deleted; links and junctions are never followed or removed, path tricks such as `..` are rejected, nothing is deleted while a conversion is running, and failures are reported per folder.

## Foreign / unusual avatars
- Head detection no longer depends on mesh names: if no mesh is labelled face (e.g. a part called `SWSkull`), meshes lying entirely above the neck become face. A region is now only required when the target has a separate GMD slot for it, so a hairless or faceless avatar converts for single-GMD targets (e.g. Tesso) and stops with a clear message for targets that need a separate hair/face GMD.
- Avatars whose arms hang down (A-pose) no longer stop at the 50 cm correction limit: when the arm pose differs a lot from the target's, the upper arm is fitted as well, the move limit is 1 m, and accessory/twist groups (e.g. `lowerarm_twist_01`) follow the segment of the bone they are mapped to. Avatars with matching arms keep the previous recipe unchanged.
- Verified on an Unreal-style skeleton avatar (SkeletonWarrior, Tesso target): clean T-pose result after the fix (it previously stopped, then showed detached hands before the twist-group fix). In-game appearance is unverified.

## English UI
- The GUI, progress messages and error messages are now in English (previously Japanese). The Japanese keywords the inventory uses to recognise VRM mesh names (for example hair/face/tail labels) are kept on purpose.

## Profile modes: simple (rules) and detailed (local AI)
- New AI-free "simple" profile mode, now the GUI default (last choice is saved). Mesh regions come from the inventory classification (ambiguous head accessories become tops); unmatched VRM weight groups follow the nearest matched ancestor bone. Same schema and the same validation as the AI profile; undecidable cases stop with a hint to use detailed mode instead of guessing.
- "Detailed" mode keeps the managed local Ollama/Qwen path unchanged and never reuses a rule-based cached profile. Simple mode never starts or contacts the local AI; the AI setup is only required for detailed mode.
- On the 13 earlier AI profiles (173 meshes) the AI never disagreed with the inventory regions except where the inventory had no answer; a real Kuwana run produced an identical profile in simple mode.
- The inventory now records the VRM bone parents (`source_bone_parents`).

## Pose-independent leg fit and sturdier variant batches
- Leg proportion correction no longer fails for bent-leg targets (e.g. seated): when standing proportions do not apply, thigh/shin/foot/toe segments are rotated and scaled to the target's bone directions (move limit 1 m in this mode). Standing targets keep the previous height remap; unordered landmarks (bad floor, kneeling/lying) still stop for review.
- A variant batch now skips a failing non-default variant, records it in `failed_variants` (status `VARIANT_PACK_PARTIAL`, warning file in the pack) and packs the rest. A failing default model still stops the batch.
- New switch targets: Yagami `c07bd01`/`c07bd02`/`c07_chair`, Kuwana `army` and the approved young-era `30` (single GMD containing the face). Strict roundtrip passed; in-game behaviour (posture, expression, switching) is unverified.
- "Include switch targets" is ON by default and remembered.

## Sawa special switch targets
- Added explicitly approved age18/dead/sitting recipes for c_aw_sawa_18, c_aw_sawa_dead and c_aw_sawa_sit. Normal-only mode is unchanged; enable switch-target generation to include found references.
- Four separate 182-bone single-GMD targets; no renamed copies, no Amasawa mixing. Actual current skeleton measurements still determine whether preparation can be shared.
- Additional references passed strict roundtrip, not in-game acceptance. Sitting/dead native posture and expressions require runtime review. Other unregistered special/young targets remain excluded.

## Neutral DDS format regression fix
- Keep independent procedural pixels, but restore legacy storage layouts: BC1/DXT1 multi with three mip levels, BC1 white, BGRA8 normal/rt. Do not reinterpret normal maps as RGBA8.
- Add layout/mipmap/channel-byte regression tests and `neutral-bc1-bgra-v2` provenance in texture manifests. Existing generated/installed mods are not modified; regenerate after restarting.
- Material matte/specular policy remains unchanged. In-game appearance still needs confirmation.

## Permissive license
- Original project code and documentation are MIT licensed. Vendored and other third-party material keeps its original license; GPL addon is not relicensed.
- Public exporter includes the root LICENSE and third-party notices.

## Public-source migration
- Added Tool-owned Ollama runtime, private model/home/cache/log paths, dedicated loopback endpoint and explicit setup/model download buttons.
- Pinned the official Ollama Windows portable release and checksum; staged, checked installation. No automatic runtime/model download during conversion.
- Added recursive registered-basename GMD resolution from a user-selected extracted Chara folder. Differing-content duplicates and missing references fail closed; found is not strict-validated.
- Removed mandatory private Action/baseline/dummy texture configuration from the GUI. No Action means MOTION_NOT_RUN with manual review required, never a motion quality pass.
- Added procedural neutral DDS, local ignored user-data storage, allowlisted public source exporter and dependency/license instructions.
- Retained explicit variant ownership, measured skeleton-group reuse, per-model strict/material checks and foot-weighted support-floor measurement.

## Known limitations
- Python/Tkinter and Blender remain separately supplied prerequisites. Ollama runs as an app-owned subprocess, not an OS sandbox.
- New runtime/model installation needs a real download validation on a clean machine; mocked isolation/lifecycle tests do not prove that.
- Corrected procedural DDS game-loader behavior and native motion/runtime model-switch appearance remain unverified.
- Public distribution must retain third-party licenses, including the vendored GPL addon. No automatic GitHub push.
