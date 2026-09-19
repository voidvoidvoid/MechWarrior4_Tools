# MW4 Blender Animation Tools — R13

**Blender 5.1+; add-on version 0.13.0.** Tested with Blender 5.1.0 and 5.2.0. Future Blender versions have not all been tested.

The add-on imports a mech's recovered hierarchy, supported rigid mesh parts, detail textures, and animation clips. Imported clips are Blender Actions. Native animation export preserves unchanged clips byte-for-byte and supports editing existing position/quaternion tracks within the limits below.

## R13: MekTek-reported import crash

Fixed the screenshot-reported `AttributeError: 'NoneType' object has no attribute 'action'` in the no-preview fallback. A newly created Blender armature has no AnimData until explicitly created or keyed. If no animation files were collected, or all clips failed validation before key insertion, the fallback crashed before attaching meshes and saving the diagnostic report.

R13 explicitly initializes AnimData before importing clips, records missing bundle entries as per-clip errors, and correctly reports when no usable Actions exist. This fixes the reproduced crash; it does **not** prove that every MekTek asset format or encryption variant is supported. The decoder and its CRC validation are unchanged.

Asset-free regressions reproduced the original error and verified absent, invalid, missing, and simulated upstream decode-error cases on Blender 5.1 and 5.2. Actual affected MekTek assets were not provided. If a mech imports without animations, use **Copy diagnostics** and inspect `resource_errors`, `animation_dependencies`, and `animation_import`. A CRC/decryption error needs the failing resource/affected archive to investigate; missing dependencies or unsupported animation versions need different fixes. Provide the full diagnostic report and the affected mech name, ideally with an exported resource bundle. If collection failed to decode a resource, it will be absent from that bundle, so the original affected archive may also be needed.

## 1. Install or upgrade

1. Download this repository using **Code → Download ZIP** and extract it. Open a terminal in the extracted repository folder and run `python scripts/build_blender_addon.py` (Python 3 required for this packaging step). This creates `downloads/MW4-Blender-Animation-R13.zip`. Alternatively, without Python, ZIP the **`blender/io_scene_mw4anim` folder itself**, keeping `io_scene_mw4anim/__init__.py` inside the ZIP. Do not ZIP its contents without the containing folder.
2. In Blender, open **Edit → Preferences → Add-ons**. Open the drop-down menu in that area and choose **Install from Disk**.
3. Select the downloaded add-on ZIP. Enable **MechWarrior 4 Animation Tools** if it is not already enabled.
4. Return to the main window. Put the pointer over the **3D Viewport** (the area displaying the scene) and press **N**.
5. Open the **MW4** tab along the sidebar's right edge. The panel is named **MW4 Animation Tools**. The **Animation** tab is a separate Blender tab, not this add-on's panel.

R13 shows **Textures · R13** and **Animations · R13**. If an older version remains visible, save your project and restart Blender. R10 and later also refresh cached add-on submodules during installation to address earlier upgrade failures.

No separate Python installation, external Python packages, manual resource extraction, or running game is needed for normal use.

## 2. Import a mech from the game

1. Click **Import from MW4 installation** in the MW4 panel. Alternatively use **File → Import → MechWarrior 4 from Installation**.
2. Select the full game installation directory. The scanner searches recursively for `.mw4` archives, including `Resource`/`Resources` folders and `textures.mw4`. Selecting the resource directory itself also works if it contains all required archives.
3. After scanning, select the desired **Model / source archive** entry.
4. Leave **Import animation Actions** enabled. R13 defaults it to enabled when opening the model-selection dialog.
5. Leave **Timeline FPS** at 30 unless you have a specific reason to change the sampling timeline. Confirm the import.
6. Select the imported armature or one of its mesh parts to expose that mech's animation tools.

The importer remembers the directory and attempts to load the hierarchy, highest-detail intact mesh parts, animation clips, and referenced textures together. A walk/stand clip is selected when found; playback is separate. Check the displayed counts and Blender's completion message rather than assuming every resource succeeded.

Archives are read-only. Backup/Backups directories, `.bak` directories, and symlink folders are skipped. Differing copies of a resource can be reported as conflicts: the add-on does not infer the game's mod/patch archive precedence. Shared clip references in `.animscript` files are followed, so the installation needs the animation archives as well as geometry and textures.

## 3. Display or reload textures

Successful texture loading switches existing 3D views to **Material Preview**. Solid shading does not show these image materials.

For an existing imported mech:

1. Select its armature or a mesh belonging to it.
2. Open **N → MW4 → Textures · R13**.
3. Click **Load / Reload Textures from MW4** and select the installation directory containing `resources/textures.mw4` (capitalization is not significant).
4. Read the texture, missing-resource, and error counts. Click **Show Textures (Material Preview)** if needed.
5. Save the `.blend`; successfully loaded images are packed inside it.

Reload uses stored texture names on the mesh materials and does not require an embedded resource bundle. An armature alone has no surfaces to texture. If geometry resources were collected but not attached, select the armature and use **Add meshes from collected resources**. Its operator settings also support the optional cockpit cage.

Texture names beginning with `@` are literal resource references. Body detail alpha is a camouflage mask, not surface transparency. Runtime camouflage blending and pilot/team substitutions are not implemented, so the result can differ from the final in-game paint scheme. The file picker exposes **Texture overrides (JSON)** for explicit reference substitutions, for example `{"@team":"my_insignia"}`. This requires a matching image resource in the scanned archives.

## 4. Choose and play animations

1. Select the mech armature or one of its mesh parts.
2. Open **N → MW4 → Animations · R13**; scroll down in the sidebar if needed.
3. Check **compatible animations available**.
4. Click the **Animation** field and choose a clip. **Previous** and **Next** cycle compatible imported Actions.
5. Click **Play / Pause**. The Timeline frame number should advance.

Choosing an Action restores Pose Position, sets its frame range/FPS, and moves to frame 1. It does not automatically start playback. Stand/pose clips can be stationary. **Show rest pose** clears the active Action without deleting the imported clips.

The Uller uses many **Cougar** animations in the original scripts; those names are expected. A walking mech may walk in place: the importer preserves root-motion channels but does not run the game's locomotion integration or animation state machine.

### Empty animation list or missing clips

Installing an update does not retroactively import missing Actions into an existing scene.

1. Click **Load missing animations from bundle**. This reads native clips already embedded with the selected mech.
2. If no clips are found, or shared clips are missing, click **Load missing animations from MW4** and choose the full installation directory.
3. Check the available/source/import-error counts, then choose an animation and press **Play / Pause**.
4. If this fails, click **Copy diagnostics** and include the result in a GitHub issue.

Recovery adds missing clips while retaining existing compatible Actions, including edits, and leaves mesh materials in place. Repeating recovery does not duplicate clips identified by their archive paths. Installation recovery validates the source hierarchy first. It does not overwrite an existing edited Action with the original game clip.

## 5. Edit and export a native animation

1. Save a working `.blend` copy.
2. Select the **armature** and choose the clip in the MW4 Animation field.
3. Switch the armature to **Pose Mode**.
4. Edit bone locations or quaternion rotations and insert keyframes. Unkeyed viewport adjustments are not exported. Retain Quaternion rotation mode.
5. Return to the MW4 sidebar and click **Export native animation (.mw4anim)**. The equivalent File menu entry is **File → Export → MechWarrior 4 Animation**.
6. Choose the destination file. Export reads the active imported Action.

Native clip start maps to Blender frame 1. Each Action retains its import FPS and subframe timing. Changing scene FPS alone does not redefine export timing. To extend a clip, change **Duration (seconds)** in the MW4 panel; extending the Timeline alone is insufficient.

Unchanged clips export byte-for-byte identical. Edited existing tracks rebuild their time/key data while preserving unedited payloads. There is a **255-key limit per native track**. For Bezier curves, enable **Bake edited tracks** in the export options; it samples the stored import FPS and keyed subframes, subject to that limit.

The exporter rejects unsupported changes such as altered rest skeletons, scale/Euler animation, constraints, drivers, active NLA strips, and modifications to default-only channels. It does not create arbitrary new native tracks or complete new clips from scratch. Retain the imported source Text datablocks and curve layout. Some source channels do not bind to a bone and are preserved as custom-property curves.

The output is a native `.mw4anim` file, not a patched `.mw4` archive. Repacking and testing edited clips in the game is a separate workflow; the included validation does not establish every edited clip's in-game behavior. Mesh and texture export are not supported.

## 6. Save projects and resource bundles

- Save `.blend` normally to retain the rig, meshes, Actions, packed images, and embedded source data.
- **Save resource bundle (.zip)** exports collected resource bytes and a provenance/error report. It is not a substitute for exporting edited Actions: collected original animation bytes remain original.
- **Import resource bundle (.zip)** imports such a bundle without rescanning all model archives. If a saved installation directory is configured, it can fetch textures absent from older bundles.
- **Import armature (.zip / .contents)** is for extracted hierarchies, not full model import.
- **Import animation onto rig** adds an individually extracted native clip to the selected armature.
- **Import raw channels (diagnostic)** creates a channel-editing representation, not a textured mech.

The embedded bundle and source metadata are needed for recovery, provenance, and native export. Avoid deleting MW4 Text datablocks during project cleanup. Game resource bundles can contain game assets; they are not included in this repository or the installer.

## Troubleshooting

| Symptom | Check/action |
| --- | --- |
| No MW4 tab | Enable the add-on; hover over the 3D Viewport and press N. |
| Animation controls missing | Select the imported mech armature or one of its parented mesh parts. |
| Empty animation list | Use the bundle/installation recovery buttons; check counts and Copy diagnostics. |
| No motion | Choose a moving clip and press Play / Pause; check whether Timeline frames advance. |
| “Rest pose” displayed | Select an Animation; Show rest pose deliberately clears the active Action. |
| Actions rejected | Copy diagnostics; inspect hierarchy/Action ownership, source metadata, and active NLA strips. |
| Gray surfaces | Use Material Preview; check texture counts and reload from the installation. |
| Missing or conflicting resources | Copy diagnostics for exact archive/member errors; supply the complete matching installation. |
| No mesh | Use full installation import; animation files alone do not contain polygons. |
| Upgrade error mentioning `register_properties` | Install R13; save and restart Blender if an older add-on remains loaded. |
| Export rejected | Read the error; keep the original hierarchy, supported channels and interpolation, and key-count limits. |

**Copy diagnostics** copies JSON to the clipboard and also stores it in a Blender Text datablock. It includes version information, Action counts/compatibility, animation collection/import failures, texture lookup results, and material image state. Reports can include local filesystem paths; review them before posting publicly. For a bug report, include Blender/add-on versions, the import route, mech name, exact error, and diagnostics.

## Supported scope and validation

- Native animation layout: **MW4ANIM 2.1**.
- Archives: **#VBD v4**, raw/LZW members and verified mektek/secure wrappers with CRC checks.
- Geometry: observed **ERF 14 / MLR 18** ShapeElement/ShapeLODElement and MLR_I_L_TMesh layout; rigid joint binding; UVs and normals; highest intact LOD.
- Textures: exact reference lookup, optional `content/` prefix normalization, TGA then PNG, supported hint interpretation, packed images and private per-rig materials.
- Not implemented: general skinning, mesh/texture/archive export, dynamic damaged/LOD switching, camouflage compositing, runtime animation blending/state logic, procedural aiming, or root locomotion integration.
- Unsupported geometry classes and nonidentity element/group transforms are reported rather than guessed.
- Decode limits: 64 MiB per resource and 512 MiB per collected set.

External samples covered Bushwacker, Crab, Daishi, Uller and Uziel with scope varying by sample. R12 recovery tests on Blender 5.1/5.2 recovered 160 Uller/Cougar clips on a textured zero-Action rig, verified switching and unchanged native exports, and preserved other Actions/materials during recovery. The supplied real texture archive was used for texture validation. Test inputs are not distributed.

See [FORMAT.md](FORMAT.md), [MULTI-MECH-REVIEW.md](MULTI-MECH-REVIEW.md), [validation reports](validation/), and the [developer guide](docs/DEVELOPMENT.md). Historical development notes are retained separately and are not current installation instructions.
