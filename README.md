# MechWarrior 4 Tools

Tools for inspecting and editing MechWarrior 4 resources.

## Blender add-on — R17 (0.16.0)

Import mech skeletons, supported polygon meshes, textures, and animations from a local MW4 installation into **Blender 5.1 or newer**. Preview and edit imported animations, then export native `.mw4anim` clips and supported edited mech `.erf` parts.

- **[Get the source ZIP](https://github.com/voidvoidvoid/MechWarrior4_Tools/archive/refs/heads/main.zip)**, extract it, then build the installer as described below.
- **[Installation and complete user guide](blender/README.md)**
- **[Native ERF geometry export guide](blender/docs/ERF-EXPORT.md)**
- [Format research and support boundaries](blender/FORMAT.md)
- [Multi-mech rig validation](blender/MULTI-MECH-REVIEW.md)
- [Developer guide and tests](blender/docs/DEVELOPMENT.md)

Build the add-on ZIP using the command below, then install it through Blender's **Edit → Preferences → Add-ons → Install from Disk**. Do not install GitHub's whole-repository **Code → Download ZIP** as a Blender add-on.

Game assets are not included. Supply your own MW4 installation or previously exported resource bundle. The add-on reads game archives without modifying them. Export supports native animations and replacement ERF geometry; it does not write game archives or texture images.

## Repository layout

| Path | Contents |
| --- | --- |
| `blender/io_scene_mw4anim/` | Blender add-on and format/archive readers |
| `blender/docs/` | Developer guide and historical development notes |
| `blender/tests/` | Synthetic and external-asset regression scripts |
| `blender/validation/` | Recorded test results; each retains its original scope |
| `downloads/` | Locally generated installer output (created by the build script) |
| `scripts/build_blender_addon.py` | Reproducible source-only ZIP builder |

Build the installer with Python 3:

```powershell
python scripts/build_blender_addon.py
```

The repository is associated with the [MW4 Mercenaries decompilation project](https://github.com/voidvoidvoid/MW4_Mercs_Decomp). Access to that separate repository is not required to use the Blender add-on.

## R16: other asset import/export

The installation browser now includes non-mech `.contents` hierarchies and a separate `.erf` geometry list. Standalone ERFs can also be imported directly. Existing ERF export works on supported imported resources from buildings, vehicles and aircraft. Support is format-dependent; real non-mech samples and live-game validation are still needed.

See [other asset workflows and support boundaries](blender/docs/OTHER-ASSETS.md).

## R17: resource filters and static texture lookup

The Import Resources dialog now has **Category**, **Folder**, and **Search paths** filters in addition to Resource type. Categories and folders come from actual archive paths (ignoring an optional `content/` mount prefix); counts in category/folder labels include both resource types. The matching-resource count reflects all active filters. Search matches all words anywhere in the path. Empty results cannot import an old selection.

Textures now retain explicitly qualified paths, recognize TGA/PNG/DDS extensions, and can resolve a bare name in a nested folder when only one matching path exists. Ambiguous basenames are reported instead of choosing an arbitrary material. Existing texture overrides still support exact paths.

For an existing untextured object, select it and click **MW4 → Load / Reload Textures from MW4**, then select the installation directory. If textures remain missing, use **Copy diagnostics** and **Save resource bundle (.zip)** and supply both. The reported air-control-tower ERF has not been supplied, so its specific failure is not yet reproduced. The supplied archive's `bdmct1.tga` decodes and assigns successfully; the real jump-cradle asset also imports textured.
