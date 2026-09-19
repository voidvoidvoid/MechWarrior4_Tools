# Development and validation

## Source structure

| Module | Responsibility |
| --- | --- |
| `__init__.py` | Registration, MW4 sidebar, raw-channel import and native export operators |
| `codec.py` | Native MW4ANIM 2.1 parsing/writing |
| `hierarchy.py` | Recovered `.contents` hierarchy records and local transforms |
| `rig.py` | Blender armatures, Action curves, native animation export |
| `animation_ui.py` | Per-rig Action selection, recovery, diagnostics |
| `archives.py` | Read-only archive catalog, resource resolution and bundles |
| `helm.py` | Supplied Helm extractor's decompression/decryption implementation |
| `crypto_profile.json` | Verified resource-decoder key/table profile |
| `animscript.py` | Static macro/path discovery; no script execution |
| `erf.py` / `meshes.py` | Supported ERF records, rigid mesh bindings, resource-bundle import |
| `textures.py` | Exact resource lookup, image decoding, packed Blender materials |
| `embedded.py` | Wrapped base64 storage for embedded bundles |
| `game_import.py` | Installation selection and import orchestration |

`codec.py`, hierarchy/archive readers and script parsing can be used without Blender when loaded appropriately. Importing the top-level add-on package requires `bpy`. Blender integration tests need Blender 5.1+ or a matching Python runtime with the corresponding `bpy` module.

## Build the installable ZIP

From the repository root:

```powershell
python scripts/build_blender_addon.py
```

Optional custom output:

```powershell
python scripts/build_blender_addon.py --output downloads/test-build.zip
```

The builder derives the R-number from the add-on's `bl_info` version and uses fixed ZIP timestamps and file permissions. It includes an explicit list of source/documentation/report types; it does not recursively scoop up game assets, `.blend` projects, Python caches, or unrelated ZIP files. It retains the `io_scene_mw4anim/` package at the archive root for Blender's legacy add-on installer.

The repository contains the same runtime add-on source as the working R12 release, with reorganized public documentation. The installer is generated locally rather than stored in GitHub. To publish a changed runtime release, update `bl_info`, the guide/version links, and validation scope together before rebuilding.

## Run tests

Run commands from `blender/`. Put results outside the repository or deliberately review them before committing. These are scripts, not a blanket pytest suite: several require specific external samples.

Synthetic texture/archive checks (no game assets required):

```powershell
blender --background --python tests/test_textures.py -- ../texture-test-results.json
```

Real resource bundle + extracted `textures.mw4` directory:

```powershell
blender --background --python tests/test_real_textures.py -- "C:/MW4-test/Uller Resource Bundle.zip" "C:/MW4-test/textures" ../real-texture-results.json
```

That Uller-specific regression expects the reviewed bundle with 25 exterior mesh objects, 160 Uller/Cougar Actions, and four exterior texture references. It checks packed images, alpha behavior, all clip selections/unchanged exports, save/reopen, and bundle image bytes. Arbitrary other mech bundles do not satisfy its fixture assertions.

Animation recovery regression:

```powershell
blender --background --python tests/test_animation_recovery.py -- "C:/MW4-test/Uller Resource Bundle.zip" "C:/MW4-test/textures/textures.mw4" ../animation-recovery-results.json
```

The recovery/workflow tests repack supplied model records into temporary test VBD containers and hard-link the real texture archive. Their temporary directory must be on the same filesystem as the texture archive; configure the process temporary-directory environment accordingly if needed. The real texture archive is read-only. Results distinguish this fixture from a complete original installation.

Other scripts' docstrings describe their required inputs. Historical reports under `validation/` are evidence for the versions and fixtures named in each report, not a claim that every test was rerun against every release or every mech. See `FORMAT.md` and `MULTI-MECH-REVIEW.md` for the recovered layouts and scope.

## Changes and regressions

- Keep source resource bytes and metadata required for exact native round trips.
- Preserve per-rig Action ownership and materials when recovering clips or reloading textures.
- Verify both direct operator execution and the actual selection callback when changing animation UI.
- Test ZIP installation over an already-enabled previous version when changing module registration.
- Use wrapped base64 for embedded bundles; a single multi-megabyte Blender Text line caused severe import slowdowns.
- Preserve exact resource names and report conflicts; do not guess by basename or silently invent archive load order.
- Keep game assets/executables, sample `.blend` projects and generated renders outside commits and installer ZIPs.

For bug reports, the R12 **Copy diagnostics** command includes Action ownership/compatibility, collection/import failures, and texture resolution. It saves a Text datablock as well as copying JSON to the clipboard. Local paths can be present in diagnostics.
