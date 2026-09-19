# Native mech ERF export — R15

R15 writes supported geometry edits from imported mech parts back into native **ERF14 / MLR18** resources. It can write one `.erf` file or a ZIP containing replacement `.erf` files under their original resource paths.

## What an ERF contains

An imported mech is assembled from several resources. An ERF generally contains geometry for a part, its rendering/material state, bounds, and sometimes multiple levels of detail. It is not a complete mech archive.

| Resource | Role | Written by this export? |
| --- | --- | --- |
| `.erf` | Part geometry, UVs, normals, material references, bounds, LODs | Yes, supported existing parts |
| `.contents` and model/video links | Hierarchy and references assembling the parts | No; original references retained |
| `.mw4anim` | Native animation clips | Separate animation export command |
| TGA/PNG texture resources | Images referenced by materials | No |
| `.mw4` | Game resource archive containing named resources and IDs | No; installation requires a resource packer |
| `.ebf` and other ERF element/primitive types | Other engine formats | Not newly supported by this release |

A geometry export does not include animation edits or modifications to texture images. The game still needs its original matching hierarchy, links, textures, and other resources.

## Workflow: edit an existing mech

1. Install R15 and import the mech from the complete MW4 installation. New imports store a geometry fingerprint for exact unchanged-file detection. Older projects with embedded resource bundles can also export; their original geometry is compared with small floating-point tolerances.
2. Save a working `.blend` copy.
3. Select an imported mesh part and edit it in **Edit Mode**. Vertex positions, topology and active UV-map edits are supported. Keep its original material and bone binding.
4. If you add vertices, ensure **every vertex** has weight **1.0** in the original bone vertex group and no other nonzero weights. The part is rigid, not a general skinned mesh. Keep the Armature modifier targeting the original rig.
5. Apply non-armature modeling modifiers deliberately before export. Do not apply the Armature modifier or bake a walking pose into the geometry. Constraints and shape keys are rejected.
6. Return to **Object Mode**.
7. Open **N → MW4 → Native Geometry Export**.
8. Choose either:
   - **Export selected part (.erf)**: select a mesh part; writes its complete original ERF resource, including edits to other imported primitives sharing that source ERF.
   - **Export mech ERFs (.zip)**: select the mech or a part; writes all original ERF resources represented by its imported mesh objects, with an export manifest.

Equivalent entries are in **File → Export**. Moving or posing the armature in the scene does not alter exported part coordinates. Mesh-object transforms relative to the armature are baked into the native vertices; mirrored/singular transforms are rejected. The exporter uses base mesh data rather than the evaluated animated mesh.

The output is prepared and validated before replacing the destination. An export-validation failure leaves an existing destination file untouched.

## Installing the output in the game

1. Export to a separate working directory.
2. For a ZIP export, extract it and read `_mw4_erf_export.json`. Each record gives the **exact original resource path**, original/export SHA-256 hashes, and whether that resource changed. For a single ERF, Blender's completion report identifies the original resource path.
3. Use your compatible MW4 resource editor/packer to replace that named ERF member in the matching game resource database, retaining its identity/resource ID so existing `.video` links still point to it. Archive packing, compression, encryption and patch precedence are responsibilities of that tool, not this exporter. No resource-packer executable is bundled.
4. Keep the matching model links, hierarchy, texture resources and animations. Test the replacement on a backup/test installation, both near and far from the camera.

**The ZIP is a transfer package, not a `.mw4` archive.** Renaming it to `.mw4`, or dropping raw ERFs into an arbitrary folder, is not an installation method implemented by this add-on. If your mod setup has an established loose-resource override mechanism, use that mechanism's documented path/mount rules.

## What is preserved, rebuilt, or rejected

- Unchanged supported resources are returned byte-for-byte. New R15 imports use their stored geometry fingerprint; older projects use a source-geometry comparison.
- Only **LOD0** geometry is edited. Other LOD records remain byte-identical, including their distance thresholds. As a result, the original model can reappear at distance. This release does not generate replacement low-detail meshes.
- Original material-state bytes, texture names, unedited primitive bytes, element transforms and source resource paths are retained. Changing a material's native texture reference or assigning multiple materials to one imported part is rejected.
- Edited polygons are triangulated for export. UV seams and split normals become separate native vertices. Meshes exceeding the **256 addressable vertices per byte-indexed primitive** are split into multiple primitives. A LOD may contain at most **255 primitives**; exceeding that is an explicit error.
- Triangle planes use the engine's `dot(normal, point) = distance` convention. Zero-area triangles and nonfinite values are rejected. Corner normals are transformed back into ERF space, and UV V-flipping reverses the import conversion.
- Sphere bounds are recomputed conservatively over all retained LODs. **Edited oriented-box-bound ERFs are currently rejected**; unchanged ones can pass through. In the reviewed Uller sample, `ulr_rgun.erf` has this bound type.
- Edits to meshes carrying nonuniform packed native vertex colors are rejected rather than losing that data. Uniform colors are preserved. The reviewed Uller geometry has no packed vertex-color arrays.
- Existing rigid bone assignments and the rest hierarchy must remain unchanged. Shared source resources cannot receive conflicting edits from different instances.
- New independent mesh objects have no original resource binding and are rejected. To replace a part's topology, edit the existing imported object. Deleting an imported object does not instruct the game to delete its resource; unrepresented source primitives remain original. This is not a new-mech authoring pipeline.
- Damage variants, unimported components and separate game collision/OBB resources are not regenerated. Only ERFs represented by imported mesh objects are emitted. Large shape changes can require corresponding external changes to higher-level collision or culling resources.
- Unsupported ERF/MLR classes remain unsupported; this does not add terrain, tree, weapon or animated-EBF authoring.

## Evidence and tests

The user supplied three archives:

- `Original source.rar`: Pascal units credited to **RISC**. `TMW4Mesh.Save` and `TMW4LOD.Save` establish vertex/UV arrays, byte triangle indices for mech parts, plane/normal arrays and LOD record sizes. `CalcPlaneEQ` establishes the positive-distance plane convention. `TERFObj.Save` distinguishes mech-part and cage layouts.
- `Erf_Builder.rar`: VB builder source corroborates `#FRE` version 14, element 144, flags 5, `#RLM` version 18, material/state payloads and UV conversion. Its hard-coded fields are reference evidence, not copied as universal format rules.
- `truespace_plugin.rar`: compiled plugin and path configuration only; it was not executed. Its presence does not validate additional formats.

Reference tool source and binaries are not redistributed in the installer. The exporter retains existing rendering-state bytes instead of inventing defaults from incomplete legacy field names.

Validation on Blender 5.1 and 5.2 with the external Uller resource bundle:

- 19 represented ERFs exported byte-identically with no edits.
- Vertex/UV edits affect only their intended resource; lower LOD records remain unchanged.
- Recomputed bounds enclose all LOD vertices; plane distances agree with exported triangle positions.
- A 300-vertex retopology fixture splits into supported primitives.
- Current animation and armature world placement do not bake into geometry.
- Single-file and ZIP operators, failure-before-overwrite, and save/reopen stability pass.
- A native walking clip still exports byte-identically after geometry export.

**No live-game test has been performed.** Format round trips and reference-source agreement establish the tested serializer behavior, not universal compatibility with every MW4/MekTek build. Test scripts require externally supplied game resources; none are distributed. See `tests/test_erf_export.py` and `validation/erf-export51.json` / `erf-export52.json`.
