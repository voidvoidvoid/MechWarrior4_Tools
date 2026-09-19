> Historical development notes. Instructions and limitations below describe their original releases and may be superseded. For current usage, see [the user guide](../README.md).

# MechWarrior 4 Animation Tools — R12

Blender **5.1+** add-on for native MW4ANIM animation import/export, armature and ERF mesh import, and texture image loading from your MW4 installation.

**This release contains no sample models, animations, textures, renders, or .blend projects.** Each user supplies their own game installation. The archive decoder and verified decryption profile remain included. Resource bundles and Blender projects created by importing the game contain that user's extracted assets; they are separate from this add-on distribution.

## R12: animation recovery and import diagnostics

Comparison with R10 (the release where switching was confirmed working) found no R11 changes to `rig.py`, `codec.py`, `animation_ui.py`, `archives.py`, or `animscript.py`. R11 changed texture loading/display and the surrounding UI. The supplied screenshot establishes no active Action and no compatible dropdown entries, but does not identify whether collection, import settings/errors, or compatibility rejected the clips. It also shows three textures loaded, one missing and one error; full diagnostic details are required to identify that resource conflict/failure.

For an existing textured model:

1. Select its armature or mesh, then open **N → MW4 → Animations · R12**.
2. Click **Load missing animations from bundle** to import the collected native clips onto this rig.
3. If none are available or shared clips are missing, click **Load missing animations from MW4** and choose the full game installation directory. This rescans the original model and follows shared animation dependencies (including Uller → Cougar).
4. Select an **Animation**, then click **Play / Pause**. Recovery automatically selects a walking/standing clip when available if there was no compatible active Action.
5. If still empty, use **Copy diagnostics**. It now includes import settings, source filenames, per-clip errors, dependency failures, archive scan errors/warnings, and Action compatibility inventory.

Recovery preserves existing compatible Actions, including edits, and does not rebuild meshes or materials. Repeating it does not duplicate Actions identified by their archive paths. Installation recovery checks the source hierarchy before importing. Differing archive copies remain reported as conflicts; the add-on does not invent game archive precedence.

New imports show source-clip and import-error counts. New model-selection dialogs explicitly default to importing animations; the checkbox can still be disabled intentionally. Older scenes show available Action counts immediately, with source counts populated after recovery. The screenshot's exact cause has not been reproduced from the screenshot alone; this release supplies recovery and evidence rather than claiming an unverified decoder fix.

Validation with external Uller/Cougar samples and real textures.mw4: on Blender 5.1/5.2, recover a textured zero-Action rig to 160 Actions; select/export all 160 byte-identically; recover a deleted Action from installation; preserve other Action identities and material assignments; repeat without duplicates; record a corrupt clip without losing the previous active Action. No game assets are included in the release.

## R11: visible texture controls and complete loading workflows

The sidebar tab is **MW4**, and the panel title is **MW4 Animation Tools**. It is not a tab named “MW4 Animations.”

1. Install R11, select the imported mech armature or one of its meshes, hover over the 3D Viewport, and press **N**.
2. Open **MW4**, then find **Textures · R11**.
3. Click **Load / Reload Textures from MW4** and select the installation folder containing `resources/textures.mw4` (the resource directory itself also works).
4. Read the texture/missing/error counts in that box. Successful loading switches viewports to Material Preview. **Show Textures (Material Preview)** remains available separately.

The texture controls always appear, with a selection/geometry explanation when unavailable. Reload now reads texture names directly from the mech materials and does not require the embedded resource bundle. This repairs older scenes that retain meshes but lack that bundle. No mesh geometry means there are no surfaces to texture; import a full model from the installation first.

Installation import collects textures automatically. Older resource-bundle imports now also fetch textures from the installation directory saved in add-on preferences, when one is configured. Otherwise use the reload button after import. Loading failure counts remain visible on the rig; **Copy diagnostics** provides the detailed report. Runtime camouflage composition remains unsupported.

Verified on Blender 5.1 and 5.2 using the supplied unmodified texture archive: installation import (real model records repacked into test archives), older bundle import using saved preferences, reload from mesh selection after removing the embedded bundle, panel draw with no selection and with no bundle, and automatic Material Preview. Each Uller imported four exterior texture resources. These checks do not establish which failure occurred in a user's existing scene; diagnostics are needed if it persists.

## R10: verified upgrade recovery and real textures

The reported `animation_ui has no attribute register_properties` enable error was reproduced by installing R9 over an enabled R8 in the same Blender session. Blender reloaded the package entry point but retained older submodules. R10 unregisters prior RNA state and reloads its own submodules in dependency order before registration. Registration rolls back if it fails. Recovery after the failed R9 upgrade, an enabled reinstall, and disable/re-enable all pass without restarting the process.

The same stale-module behavior was reproduced for textures: upgrading R6 to R8 left the R6 texture lookup active, so the real archive's `textures/@aulr0.tga` was still missed. Installing R10 in that same session reloaded the corrected lookup and decoded the actual image successfully.

The supplied textures.mw4 contains 13,223 indexed resources. Tests against the actual archive on Blender 5.1 and 5.2 resolve all six Uller image/hint pairs: @aulr0, @pilot, @team, RunningLight, cage1, and cdash1. The exterior uses four texture references; @pilot and @team have identical bytes and share one packed image datablock. No image lookup or decode errors occurred. All 160 Uller/Cougar Actions switched through the persistent selector and exported byte-identically. Packed images survived save/reopen, and exported resource-bundle image bytes matched the decoded originals. A real textured Uller render was visually inspected.

Pilot/team decal alpha is now connected as specified by their alpha-format hints. Body-detail alpha remains a camouflage mask rather than surface transparency. Runtime camouflage composition and player-selected insignia substitution remain outside this release's scope.

### Use R10

1. Install this ZIP and enable MechWarrior 4 Animation Tools. R10 refreshes its modules during upgrades.
2. Open your existing model and select its armature or a mesh part.
3. Click **Load textures from MW4 installation** and choose your game folder. This refreshes an older project's previously missing images. Fresh installation imports do it automatically.
4. Click **Show Textures (Material Preview)** in the MW4 sidebar; Solid shading does not show image textures.
5. Use the **Animation** dropdown to change clips, then Play/Pause.

The original archives are read-only. This public add-on ZIP contains no game model, animation, texture, or example-project assets.

## R9: persistent animation selector and failure diagnostics

The MW4 sidebar now uses an **Animation** Action dropdown instead of the dynamic search popup. Selecting an entry assigns that Action and its Object slot, restores Pose Position, sets playback timing, and refreshes the view. Previous/Next and Rest Pose keep the selector synchronized. Selection errors are shown in the sidebar. Muted NLA tracks no longer block selection. The retained search operator also handles absent callback context and retains its enum strings safely.

The actual property-update path is tested on Blender 5.1 and 5.2, including a rig in Rest Position, selection through a child mesh, invalid selection recovery, old projects, and save/reopen. These tests do not substitute for reproducing a user's mouse interaction in their Windows project; that failure's precise cause has not yet been confirmed.

**Copy diagnostics** copies a compact JSON report of the active/selected Action, compatible clip count, texture lookup report, actual material images, and viewport shading. A copy is also stored as a Text datablock for the selected rig. Use this when a dropdown appears empty, a selection has no visible effect, or textures remain missing.

**The continuing texture failure is not resolved in R9.** The available Uller R6 bundle has no images and predates archive-name diagnostics. No further naming/decoder guesses are made here. A current R8/R9 diagnostic report or resource bundle, plus the actual RESOURCE/textures.mw4 archive when necessary, is required to reproduce and finish the texture fix.

## R8: import stall fix

The embedded resource ZIP was previously written into a Blender Text datablock as a single base64 line. Blender's insertion cost grows quadratically with that line's length: a one-million-character line took about 17 seconds in a focused test, and larger texture bundles could appear frozen for minutes. R8 wraps the encoded bundle into short lines and formats Action metadata across lines. An approximately 8.3 MB wrapped payload wrote in about 0.02 seconds in Blender 5.1/5.2.

Existing one-line project payloads remain readable. Wrapped payloads survive save/reopen and export back to the same resource ZIP bytes. Use R8 when reopening projects saved with the new wrapping; older add-on releases expect a single-line payload. These timings measure the Text storage bottleneck, not your installation's disk scan, decryption, or total import time.

## R8: choose, preview, and export animations

Select the imported mech armature **or one of its mesh parts**, hover over the 3D Viewport, press **N**, and open **MW4**. The **Animations** box provides:

- **Animation dropdown**: select an imported clip for this mech. Type part of the name, such as `walk`, `stand`, or `getup`, then select a clip.
- **Previous / Next**: cycle through the clips in alphabetical order.
- **Play / Pause**: play the selected clip on the scene timeline.
- **Show rest pose**: clear the active animation without deleting clips.

Switching clips resets the timeline to frame 1 and sets its range and FPS from that clip. Keyed animation edits remain in their Actions. Unkeyed pose changes are cleared; insert keyframes before switching if you want to retain a pose edit. Playback uses Blender's scene-wide timeline, so changing its FPS/range also affects other objects in the scene. Mute NLA strips before using this direct Action preview workflow.

New imports associate clips with their rig. Existing projects without ownership tags list imported Actions whose stored rest-hierarchy fingerprint matches the selected rig. Identical legacy rig copies may consequently share the compatible list. Actions with a different rest hierarchy are excluded. This works with existing R3–R7 projects and does not require reimporting their clips.

**Export native animation (.mw4anim)** writes the active clip as native **MW4ANIM 2.1**. The file picker proposes the source clip filename when available. To edit, select the armature, enter Pose Mode, change a supported location/quaternion track, and insert keyframes. Unchanged Actions export byte-for-byte identically. Supported edited tracks are rebuilt while other source data is preserved. Bezier edits require **Bake edited tracks** in the export options, subject to the native 255-key-per-track limit. Unsupported operations produce an error instead of silently discarding edits.

This exports **animation files only**. It does not write ERF geometry, textures, skeleton changes, animscripts, or repacked .mw4 archives. Installing exported clips into game archives is a separate step; edited playback in the live game remains untested.

Blender 5.1/5.2 checks cover the picker operators, mesh-child selection, rig isolation, timeline and Action-slot assignment, retaining edits while cycling, rest pose, legacy projects, and save/reopen. Three source clips export byte-identically through the file-export operator. A leg rotation edit changes exactly one native track, and export/reimport reproduces the pose with maximum matrix-component error below 0.0000001.

## R7: texture archive path correction

R6 looked only for `content/textures/...` even though resource archives can store names relative to the content mount, as `textures/...`. R7 treats those two full paths as aliases, preserves the actual member path in collected bundles, and applies the same normalization to texture hint records and manual overrides. Conflicting alias entries remain explicit errors.

The supplied Uller R6 report confirms that RESOURCE/textures.mw4 was indexed, but all six requested texture resources were missing from lookup and no images entered the bundle. Its report did not include texture archive member names, so the exact on-disk naming cannot be confirmed from that bundle alone. R7 adds a small archive-name diagnostic sample for unresolved cases.

**Existing projects do not require reimporting the rig:** upgrade, restart Blender, select the Uller, then use **MW4 → Load textures from MW4 installation** and choose your game folder. Switch to **Material Preview**. The old bundle itself contains no images, so access to the installation is necessary once.

Path alias, cross-prefix hint, conflict, image packing, and material isolation tests pass on Blender 5.1 and 5.2. An integration check with the supplied Uller geometry and Cougar walk, using synthetic images under archive-relative texture names, resolves all six resources and textures its four visible materials without changing the animation. Actual game image appearance remains unverified until those images are supplied.

## R6: shared animation dependencies and predictable initial poses

The importer now reads static `!NAME=value` / `$(NAME)` definitions in the selected mech's `.animscript` and collects referenced clips from other mech directories. This matters for the **Uller**, whose script points to **Cougar** locomotion/standing animations. Its own supplied folder contains only seven fall/get-up clips. R5 missed those external dependencies and could leave the last get-up animation active.

R6 chooses the script's Walk or StandPose for the initial preview. If neither is available, it leaves the rig in its rest pose while preserving all imported Actions. Missing dependencies and conflicting archive resources are recorded explicitly. This is dependency discovery, not execution of the animation state machine or automatic skeleton retargeting.

**After upgrading, reimport the affected mech from your MW4 installation**, preferably into a new scene. An old project/resource bundle does not gain the missing shared clips merely by installing R6. Preserve any animation edits in the old project before replacing it.

The new Crab, Daishi, Uller, and Uziel samples were checked individually; no fixed Bushwacker skeleton is used. See `MULTI-MECH-REVIEW.md` for findings, validation, and the missing files needed to verify polygon alignment.

## Install and load textures on an existing model

1. Install `MW4-Blender-Animation-R12.zip` using **Edit → Preferences → Add-ons → Install from Disk**. Enable **MechWarrior 4 Animation Tools**. Restart Blender after upgrading to clear old modules.
2. Open your existing project and select the imported mech armature or one of its mesh parts.
3. Hover over the large **3D Viewport**, press **N**, and open the **MW4** tab on its right edge.
4. If necessary, select the armature and click **Add meshes from collected resources**.
5. Click **Load textures from MW4 installation** and select the game directory (or its Resource/Resources directory).
6. Switch the viewport to **Material Preview** using the third sphere at the top right, or **Z → Material Preview**. Solid shading does not show the texture materials.
7. Save your `.blend`. Images are packed inside it, so they remain available without the original game directory.

The texture button requires an embedded resource bundle from the installation/bundle importer (R3 or newer). A raw animation or skeleton-only import does not contain the mesh resources needed for automatic lookup.

## Import a new model

Use **File → Import → MechWarrior 4 from Installation**, select your game folder, then choose a model/source archive. Supported armatures, animation Actions, highest-detail intact ERF meshes, and referenced texture images are imported together. The directory scanner automatically finds `Resource/textures.mw4` or `Resources/textures.mw4`, regardless of capitalization, alongside the other `.mw4` archives. No external Python packages, manual extraction, or running game are required.

The folder path is remembered in add-on preferences. Archives are read-only. Backup/Backups folders and directories ending `.bak` are skipped. The importer does not infer patch/mod archive precedence: conflicting resources are reported instead of choosing an arbitrary copy.

**File → Import → MechWarrior 4 Resource Bundle (.zip)** also imports collected data. New bundles include successfully resolved texture images and their hint records. An older bundle without textures needs the installation once, using the texture button above. **Save resource bundle (.zip)** exports the collected bytes and a provenance/error report; the same bundle is embedded in the project.

## Texture support and current limits

- Resolves the engine's literal `content/textures/<reference>.tga` names, with `.png` fallback. The `@` prefix is preserved; it is part of names such as mech detail textures.
- Loads images through Blender, connects them to Principled materials using imported UVs, and packs their original bytes into the project. Materials are isolated per imported rig and identical images are reused.
- Reads `{hint}` records. Explicit keyed/alpha formats use image alpha on ordinary textures. Mech detail `@` texture alpha stays opaque because it is a camouflage mask, not surface transparency. Color-key synthesis and special engine shader effects are not reproduced.
- **Runtime camouflage compositing and team/pilot texture substitution are not implemented.** The imported detail texture can therefore differ from the game's final painted mech. This release does not claim an exact in-game appearance.
- The texture file picker offers **Texture overrides (JSON)** for known substitutions, e.g. `{"@team":"my_insignia"}`. Values are exact texture stems or full `textures/...` / `content/textures/...` TGA/PNG resource paths. Missing or conflicting references appear in the embedded resource report rather than being silently guessed.
- Only referenced images are decoded; the whole texture archive is not extracted. Existing decoder limits are 64 MiB per resource and 512 MiB per collected set.
- No texture, mesh, or archive export/repacking is implemented. Native export remains animation-only.

## Mesh and archive support

Supports ERF 14 / MLR 18 ShapeElement and ShapeLODElement with the observed MLR_I_L_TMesh primitive. Parts bind through hierarchy → model data → video shape reference → ERF, using rigid vertex groups and Armature modifiers. UVs, normals, and source texture names are preserved. Lower LODs and damaged variants remain in the resource bundle; automatic switching is not implemented. Cockpit geometry is optional in Add Meshes. Unsupported classes and nonidentity element/group transforms produce explicit errors.

Supports #VBD v4, raw members, MW4 LZW, and verified mektek/secure wrappers with CRC checks. `helm.py` preserves the supplied extractor; `crypto_profile.json` contains its verified key/table profile. No executable is bundled or executed. The optional Key source override accepts the extractor's supported recovered image.bin or unpacked analysis PE.

## Edit and export animations

Select the armature, choose an imported Action, and edit in **Pose Mode**. Insert location or quaternion rotation keyframes; unkeyed viewport adjustments are not exported. Keep Quaternion rotation mode. Use **Export active Action** in the MW4 sidebar, or **File → Export → MechWarrior 4 Animation**.

Native clip start maps to Blender frame 1. Default import FPS is 30 and is retained per Action, including subframe keys. Scene FPS changes do not redefine export timing. Change **Duration (seconds)** in the MW4 panel to extend the native clip; changing the scene timeline alone does not do so.

Unchanged imported clips export byte-for-byte identical, including after save/reopen. Edited tracks rebuild their key/time sections while retaining unedited payloads and unresolved metadata. There is a 255-key limit per track. For Bezier edits, enable **Bake edited tracks**; it samples the stored import FPS and keyed subframes within that limit.

Creating native tracks/clips from scratch, changing the rest skeleton, scale/Euler animation, constraints, drivers, active NLA strips and edits to default-only channels are unsupported and rejected. The exporter reads the active imported Action. Keep the embedded source Text datablocks and imported curve layout.

Root locomotion data and variant words are preserved as custom-property curves; root movement is not integrated into viewport displacement. `joint_missile` has no matching node in the supplied hierarchy and remains an unbound track. Blender interpolation and clip playback do not emulate the game's full animation state machine. Keep the original `.animscript`; archive repacking is separate.

## Validation and source

R5 texture integration is tested in Blender 5.1.0 and 5.2.0 LTS using synthetic TGA/PNG images and synthetic `.mw4` containers: exact-name lookup, PNG fallback, hint handling, material isolation, image deduplication, missing/conflicting resources, read-only archives, and packed-image save/reopen. **A real textures.mw4 archive was not supplied, so real game texture appearance remains unverified.**

The existing-project upgrade was also tested on the supplied mech with synthetic textures: all 26 mesh parts and 154 Actions remained, and the active animation still exported byte-identically.

Earlier geometry/animation validation used user-supplied assets: 38 ERFs, 190 LOD records, 26 visible mesh parts, and 154 Actions. Unchanged animation exports were byte-identical with meshes attached. Those assets are not distributed here. Historical test reports retain their original scope.

Source: `io_scene_mw4anim/`. Format/decomp references: `FORMAT.md`. Test results: `validation/`. Tests: `tests/`. Tests requiring game resources accept external paths; none are bundled.

```bash
blender --background --python tests/test_textures.py -- texture-results.json
blender --background --python tests/test_meshes.py -- /path/to/resource-bundle.zip /path/to/results
blender --background --python tests/test_rig.py -- /path/to/animations.zip /path/to/hierarchy.zip /path/to/results
python tests/test_codec.py /path/to/animations.zip
```
