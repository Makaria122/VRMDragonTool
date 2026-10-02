# Changes

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
- Procedural RGBA DDS game-loader compatibility and native motion/runtime model-switch appearance remain unverified.
- Public distribution must retain third-party licenses, including the vendored GPL addon. No automatic GitHub push.
