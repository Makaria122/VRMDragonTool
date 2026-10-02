# Changes

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
