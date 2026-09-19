# MechWarrior 4 Tools

Tools for inspecting and editing MechWarrior 4 resources.

## Blender add-on — R14 (0.14.0)

Import mech skeletons, supported polygon meshes, textures, and animations from a local MW4 installation into **Blender 5.1 or newer**. Preview and edit imported animations, then export native `.mw4anim` clips.

- **[Get the source ZIP](https://github.com/voidvoidvoid/MechWarrior4_Tools/archive/refs/heads/main.zip)**, extract it, then build the installer as described below.
- **[Installation and complete user guide](blender/README.md)**
- [Format research and support boundaries](blender/FORMAT.md)
- [Multi-mech rig validation](blender/MULTI-MECH-REVIEW.md)
- [Developer guide and tests](blender/docs/DEVELOPMENT.md)

Build the add-on ZIP using the command below, then install it through Blender's **Edit → Preferences → Add-ons → Install from Disk**. Do not install GitHub's whole-repository **Code → Download ZIP** as a Blender add-on.

Game assets are not included. Supply your own MW4 installation or previously exported resource bundle. The add-on reads game archives without modifying them. Export supports animations; it does not write game archives, mesh geometry, or textures.

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
