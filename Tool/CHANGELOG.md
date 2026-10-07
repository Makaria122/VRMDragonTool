# Changes

## Fix: colour factors were ignored (gold/dark parts turned white or grey)
- A glTF material can colour a texture with `baseColorFactor` (for example a grey 2x2 texture times an orange factor is gold, times 0.02 is nearly black). The tool used the texture alone, so those parts came out grey or white (shoe ribbons and jewels of a VRChat avatar). Each material whose factor is not white now gets its own tinted copy of the texture (factor in linear colour, texture in sRGB, like a viewer does); materials without a factor still share one file.
- Flat-colour materials (no texture) are now written as sRGB; the linear factor was used as if it were already sRGB, which made them too dark.
- 3 new tests.

## Fix: stretched face and missing hair parts with VRMs exported without Avatar Optimizer
- **Vertex positions now come from the VRM file.** Blender's glTF importer does not reproduce every VRM: for the head mesh of one avatar it posed some bones (cheeks, tongue) with a 90 degree rotation and a 1.5 m offset, which stretched the face down to the chest in the game. The preview now reads the VRM itself and places every vertex where the glTF specification puts it (weight x joint world x inverse bind x position; checked against Blender on all meshes of the test avatar: identical except the broken head mesh). This replaces the earlier "bake Blender's pose" step, which stays only as a fallback when the VRM cannot be read.
- **Parts with their own skeleton are converted too.** A twintail on its own 62 bones, a ribbon, a hairpin and a ring (props on bones) used to be dropped silently because they were not skinned to the main skeleton. They are now attached to the main skeleton through the nearest ancestor bone (a twintail follows the head). The conversion says which parts were attached and warns, naming them, about any mesh of the VRM that was left out.
- New module `um/dragon_vrm_skin.py` (numpy, no Blender needed to test it) with 5 tests.

## New: warning for bones whose pose cannot be stored in a VRM (hair lock sticking out)
- Before converting, the tool now checks the skin of the VRM without Blender: for every joint the world matrix times the inverse bind matrix must be the same across a skin. A bone with a non-uniform scale that is also rotated has a sheared world matrix in Unity, which glTF cannot store; viewers and this tool then pose the bone and its children differently from Unity (found with a hair lock sticking out: bone `Front_Route.002` had a scale of 1.31 on one axis, its five bones deviated by up to 9.5 cm). The conversion shows a warning with the bones and the fix (reset their scale to 1 in the avatar tool and export again). Avatars without the problem (rurune) give no warning. 3 new tests.

## Fix: outfits turned black and hair parts went missing in the game (found with a VRChat avatar)
- **Meshes with several materials exported only their first material.** Clearing the material slots reset every polygon's material index to 0, so a mesh with seven materials (shirt, skirt, ribbon, metal parts...) was written to the GMD with only the first one (in the Ame test: the outfit used the black ribbon texture everywhere). The indices are now restored, and the export is checked: every diffuse texture the avatar really uses must be present in the exported GMD, otherwise the conversion stops with the names of the lost materials. Conversions made before this fix of avatars with multi-material meshes (for example the rurune / Kiryu mods) should be regenerated.
- **Meshes whose bones are posed differently from their bind pose were placed wrongly.** Avatars exported from Unity can contain parts (hair added with its own armature, props on bones, hand-adjusted bones) whose bone pose differs from the stored bind pose. Viewers show the posed shape, but the tool read the raw vertices: a twintail ended up two metres away and a hairpin at the feet. The preview now bakes the armature pose into the vertices (and returns the rig to its rest pose); meshes whose pose equals the bind pose do not change. Such parts above the neck are now classified as head parts (face/hair slot) instead of body.

## Fix: avatars whose root object is scaled (for example 1.3)
- Conversion stopped with "Unexpected source world scale for PREVIEW_ONLY_...". VRChat avatars often keep a scale on the root object (Unity avatar scale). The fit itself was already correct, because heights are measured in world space; only the sanity check assumed the imported meshes had scale 1. The alignment now records `source_world_scale` and the check expects fit scale x source scale. An avatar root with a non-uniform scale is refused with a clear message (apply the scale in Unity first). Checked with a 1.3-scaled Booth/VRChat avatar converted to Kuwana (tops and face GMDs, Mods folder created).

## Fix: bodies looked black in dark scenes
- Clothing materials now copy the plain opaque shader (`sd_o1dzt`) of the target character when it has one. Before, the first opaque non-skin material was copied, which for Kiryu is the suit shader (`sd_o1dzt_m2dzt_h2dz`) with its own roughness/reflection maps (rm/refl) kept; with a dark VRM texture this turned black in dim cutscenes. Confirmed in game with Kiryu replaced by an avatar with a black coat; raising the specular color (0.039) or brightening dark textures changed little. Characters without a plain shader fall back to the old choice. Hair and face templates are unchanged. 4 new tests.

## New GUI: any Dragon Engine game by default, dark theme, Japanese
- Rebuilt window with a sidebar (Convert, Advanced tools, Setup, Storage & logs, Settings). "Any Dragon Engine game: find a character by name" is now the default; the built-in Lost Judgment characters are the second choice. The "Lost Judgment beta" wording is gone.
- Convert page in three steps (character, avatar, options); reference files, paths and the JSON report are folded away. Long work (searching, Blender) runs in the background so the window stays responsive.
- Settings: language (Automatic, English, Japanese) and theme (Follow Windows, Light, Dark), applied immediately and remembered. Conversion engine messages (Blender and check errors) stay in English.
- Setup page: Blender download/choice and local AI in one place; Storage & logs page: outputs table with cleanup, log folder and debug report.
- Crisper text on high-DPI screens. Tests: translation coverage (every GUI text has a Japanese entry with matching placeholders), theme contrast, and GUI start-up/language/theme/busy-state checks.

## Custom targets: whole characters at once
- New "Whole character" tab in the custom-target dialog: choose a folder and type a character name; every GMD whose name contains it is found, inspected in Blender (read-only), and listed with tick boxes (base set always added; undressed, swimwear, dead, other-age, test and special-pose models, unreadable files, other skeletons and body models without feet are left out by default and explained). Registered as one custom target whose extra parts (other outfits, hair styles, faces) become variants: with the switch-target checkbox on, one conversion replaces every part of the character.
- Faster batches: a variant exports only its own slot, parts with a different bone count use their own (per-slot bone counts), a few Blender jobs run in parallel ("Parallel Blender jobs", default 3, also used for the Lost Judgment variants), and for batches of more than six models the working .blend files, textures and review copies are deleted as each model finishes (a 40-part character: about 7 minutes and 160 MB instead of an estimated hours and 8 GB).
- Fixes: the character search no longer follows Windows junctions; a batch where only one model survives keeps a usable mod folder after the cleanup; validation errors of the custom-target dialog are written to the log.
- Like a Dragon 8 Ichiban: 62 matching files, 40 converted without failures. 27 new tests.

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
