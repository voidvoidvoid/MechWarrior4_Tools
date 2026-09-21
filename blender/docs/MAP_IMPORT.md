# Map terrain import — R21

R21 imports textured terrain from the supplied `ALPINE01.MW4`, `URBAN01.MW4`, `URBAN02.MW4`, and `URBAN05.MW4` archives. These normally live under `RESOURCE/MAPS` in a Mercenaries installation. Other maps are supported only when they use the same validated layout; unknown layouts produce an error.

## Import a map

1. Install the R21 add-on ZIP and restart Blender after upgrading.
2. Open the 3D View sidebar with **N**, select **MW4**, and click **Import from MW4 Installation**.
3. Select the installation directory, its `RESOURCE` directory, or a folder containing your map `.mw4` files.
4. In **Import MW4 Model Resources**, choose **Resource type → Map terrain**, **Category → Maps**, and the desired **Folder** (for example `maps/urban01`). Choose the map root and source archive in **Model / source archive**. Do not choose individual `AA.erf` zone files under Geometry resources.
5. Leave **Full close-view terrain textures** enabled for native-resolution composition from `composttexture`, or disable it for a faster far-texture import. Confirm the import. The selected terrain objects can be framed with **Numpad .** (View → Frame Selected). Use **Show Textures (Material Preview)** if necessary. R19 increases the viewport clipping distance to accommodate the map.

Selecting a maps folder from a resource type with no matching entries also switches to Map terrain automatically. Search still only filters the currently selected type.

The map appears as a **MW4 Terrain** parent with one mesh per supported zone. It uses native world positions with the same Y-up to Z-up conversion as other imported assets. Texture images are packed into the `.blend`. **Save resource bundle (.zip)** preserves the collected grid, zone geometry, selected base texture images, and report; **Import resource bundle (.zip)** can restore this terrain without an installation. Select the terrain parent or a child mesh for texture reload or bundle saving.

## Current scope

- Ground geometry and **full close-view terrain textures** are imported by default in R21. The optional far-texture mode retains the earlier behavior. Alpine produces 9 zone objects, 40,374 triangles and 9 packed base textures. Each Urban sample produces 16 zone objects, 14,918 triangles, and 16 packed base textures, covering 5,120 × 5,120 native units.
- This is **not a complete mission/scene import**. Placed buildings, vegetation, units, mission logic, collision data, water effects, and runtime detail-texture blending are not reconstructed.
- Non-terrain records are omitted and reported by class. MW4 identifies shape `0x74` as `MLRCulturShape` and primitive `0x67` as `MLR_Water`. Alpine contains 454 culture shape records and 36 water shape records; each Urban sample contains 10 water shape records. These counts refer to serialized records, not individual trees or objects. Ground geometry uses Terrain2 class `0x68`.
- Texture LOD switching is not emulated. R21 composes the native-resolution FGD layers into textures matching the existing terrain UV rectangles; [full texture details](COMPOST_TEXTURES.md). Disabling full textures uses the stored baked base-level image.
- Native map export is **not supported**. Terrain roots are excluded from the existing animation/ERF exporters. Those exporters continue to serve supported mech and other asset hierarchies.
- Original `.mw4` archives are read-only. No game data ships with this add-on.

Import diagnostics are stored in a Blender Text datablock named `<map> · MW4 resource report`. In Blender's Text Editor, select it to inspect `terrain_import.skipped_shapes`, texture lookup results, and source resources. If another map fails, provide its archive and the error/report. A map's root `.erf` alone is insufficient: it references separate zone resources and textures.

## Format evidence

The implementation uses the MW4 decompilation project and the actual supplied archives, rather than treating mech ERFs as terrain.

- Root: ERF14 class `0x8c`, flags `5`; sphere, zero u16, two byte grid dimensions, two float cell sizes and two float origins. The tested grids are 4 × 4 with 1,280-unit zones.
- `<map>.erf{zones}`: three packed `(u16 database, u16 resource)` handles per zone, referring to ERF, BSP, and material resources. Geometry is resolved by resource ID **and map path in the selected archive**. Runtime database IDs are not archive indexes.
- Zone: ERF14 header followed by 64 serialized cells. Class `0x84` elements contain child records; some cells have nested groups and several shapes. Flag `0x400` introduces MLR state before the transform in this terrain layout. Bounds are never applied as object transforms.
- Shape: MLR18 class `0x4b`, byte primitive count. Terrain2 class `0x68` contains vertex/UV arrays, mode and material state, byte triangle indices, plane array, detail material/parameters, four cell/LOD bytes, eight UV rectangles, a reserved word, and an availability byte.
- MW4 `004483e0` registers class `0x68` as `MidLevelRenderer::MLR_Terrain2`; `00448530` reads its fields; `00448a20` writes the terrain-specific tail; `00448ad0` selects texture LOD; `00448b90` computes `U=(maxX-X)/width` and `V=(maxZ-Z)/depth`. Blender UVs additionally invert V, matching the existing image convention.
- Sources: [Terrain2 constructor](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/00448530.c), [serializer](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/00448a20.c), [UV calculation](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/00448b90.c). Access to the research repository is not required to run the add-on.

Shape lengths, finite coordinates, triangle indices, plane counts, UV bounds, nesting depth, grid handle counts, and exact zone endings are validated. Non-terrain shape classes are skipped using their declared byte extent, with class IDs and offsets recorded. Every mesh shape is parsed through a reader bounded to that extent, so corrupt arrays cannot read into the following element. Unsupported primitives and the remainder of their shape are omitted and reported; terrain primitives already decoded before them are retained. Corrupt extents are rejected. Maps use a separate reader, leaving the R18 mech ERF reader/writer and its Atlas length recovery unchanged.

## Validation

`tests/test_terrain.py` includes synthetic malformed-input, UV, and texture-archive-preference checks. With privately supplied archives it also exercises full Blender import, packed images, coordinate bounds, bundle reimport, and `.blend` save/reopen. Results are recorded in `validation/r20-maps.json` (with the earlier R19 results retained separately); the samples themselves are not included.

Run with a Python environment containing Blender 5.1's `bpy`:

```sh
python blender/tests/test_terrain.py /path/to/private/map_archives /tmp/map-report.json
```

Existing synthetic non-mech import/export, resource filter, and static texture regressions also pass in Blender 5.1. No live-game map export or full-mission validation is claimed.

## R20: Alpine and mixed shape classes

R19 assumed every terrain-zone shape was the triangle-mesh container `0x4b`. Alpine includes valid culture containers `0x74` alongside the terrain, so that assumption aborted all nine zones with “Unsupported terrain shape class.” Decryption succeeded; the failure was at shape dispatch.

R20 separates non-terrain shape records from terrain decoding using each record's declared extent. The ground imports even when culture or water records are present. Both the sidebar and operator report identify omitted classes. This does not add vegetation or water rendering. Other maps using these mixed records should benefit, but only Alpine and the three Urban archives have been tested.

Class identification is grounded in the decompilation initializers: [`0042bae0`](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/0042bae0.c) registers `0x74` as `MLRCulturShape`; [`0042df30`](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/0042df30.c) registers `0x67` as `MLR_Water`.

Regression coverage includes culture records before, between and after terrain cells; invalid shape sizes; unchanged Urban triangle counts; Alpine packed textures; portable bundle restoration; and `.blend` reopening. No game assets are included in the repository or installer.
