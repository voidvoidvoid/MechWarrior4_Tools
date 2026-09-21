# Map terrain import — R19

R19 imports textured terrain from the supplied `URBAN01.MW4`, `URBAN02.MW4`, and `URBAN05.MW4` archives. These normally live under `RESOURCE/MAPS` in a Mercenaries installation. Other maps are supported only when they use the same validated layout; unknown layouts produce an error.

## Import a map

1. Install the R19 add-on ZIP and restart Blender after upgrading.
2. Open the 3D View sidebar with **N**, select **MW4**, and click **Import from MW4 Installation**.
3. Select the installation directory, its `RESOURCE` directory, or a folder containing your map `.mw4` files.
4. In **Import MW4 Model Resources**, choose **Resource type → Map terrain**, **Category → Maps**, and the desired **Folder** (for example `maps/urban01`). Choose the map root and source archive in **Model / source archive**. Do not choose individual `AA.erf` zone files under Geometry resources.
5. Confirm the import. The selected terrain objects can be framed with **Numpad .** (View → Frame Selected). Use **Show Textures (Material Preview)** if necessary. R19 increases the viewport clipping distance to accommodate the map.

Selecting a maps folder from a resource type with no matching entries also switches to Map terrain automatically. Search still only filters the currently selected type.

The map appears as a **MW4 Terrain** parent with one mesh per supported zone. It uses native world positions with the same Y-up to Z-up conversion as other imported assets. Texture images are packed into the `.blend`. **Save resource bundle (.zip)** preserves the collected grid, zone geometry, selected base texture images, and report; **Import resource bundle (.zip)** can restore this terrain without an installation. Select the terrain parent or a child mesh for texture reload or bundle saving.

## Current scope

- Ground geometry and baked **base-level terrain textures** are imported. The three tested maps each produce 16 zone objects, 14,918 triangles, and 16 packed base textures, covering 5,120 × 5,120 native units.
- This is **not a complete mission/scene import**. Placed buildings, vegetation, units, mission logic, collision data, water effects, and runtime detail-texture blending are not reconstructed.
- Each supplied map contains 10 shapes with primitive class `0x67`. These are omitted with an explicit report; their rendering semantics have not been established. The operator reports the omission count. Remaining geometry uses validated Terrain2 class `0x68`.
- Texture LOD switching is not emulated. R19 uses the texture reference and its matching UV rectangle stored in each Terrain2 primitive. Fine detail may therefore look softer than the game at close range.
- Native map export is **not supported**. Terrain roots are excluded from the existing animation/ERF exporters. Those exporters continue to serve supported mech and other asset hierarchies.
- Original `.mw4` archives are read-only. No game data ships with this add-on.

Import diagnostics are stored in a Blender Text datablock named `<map> · MW4 resource report`. In Blender's Text Editor, select it to inspect `terrain_import.skipped_shapes`, texture lookup results, and source resources. If another map fails, provide its archive and the error/report. A map's root `.erf` alone is insufficient: it references separate zone resources and textures.

## Format evidence

The implementation uses the MW4 decompilation project and the actual three supplied archives, rather than treating mech ERFs as terrain.

- Root: ERF14 class `0x8c`, flags `5`; sphere, zero u16, two byte grid dimensions, two float cell sizes and two float origins. The tested grids are 4 × 4 with 1,280-unit zones.
- `<map>.erf{zones}`: three packed `(u16 database, u16 resource)` handles per zone, referring to ERF, BSP, and material resources. Geometry is resolved by resource ID **and map path in the selected archive**. Runtime database IDs are not archive indexes.
- Zone: ERF14 header followed by 64 serialized cells. Class `0x84` elements contain child records; some cells have nested groups and several shapes. Flag `0x400` introduces MLR state before the transform in this terrain layout. Bounds are never applied as object transforms.
- Shape: MLR18 class `0x4b`, byte primitive count. Terrain2 class `0x68` contains vertex/UV arrays, mode and material state, byte triangle indices, plane array, detail material/parameters, four cell/LOD bytes, eight UV rectangles, a reserved word, and an availability byte.
- MW4 `004483e0` registers class `0x68` as `MidLevelRenderer::MLR_Terrain2`; `00448530` reads its fields; `00448a20` writes the terrain-specific tail; `00448ad0` selects texture LOD; `00448b90` computes `U=(maxX-X)/width` and `V=(maxZ-Z)/depth`. Blender UVs additionally invert V, matching the existing image convention.
- Sources: [Terrain2 constructor](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/00448530.c), [serializer](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/00448a20.c), [UV calculation](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/00448b90.c). Access to the research repository is not required to run the add-on.

Shape lengths, finite coordinates, triangle indices, plane counts, UV bounds, nesting depth, grid handle counts, and exact zone endings are validated. Unsupported primitives are skipped only within their declared shape extent and are reported; corrupt extents are rejected. Maps use a separate reader, leaving the R18 mech ERF reader/writer and its Atlas length recovery unchanged.

## Validation

`tests/test_terrain.py` includes synthetic malformed-input, UV, and texture-archive-preference checks. With privately supplied archives it also exercises full Blender import, packed images, coordinate bounds, bundle reimport, and `.blend` save/reopen. Results are recorded in `validation/r19-maps.json`; the samples themselves are not included.

Run with a Python environment containing Blender 5.1's `bpy`:

```sh
python blender/tests/test_terrain.py /path/to/private/map_archives /tmp/map-report.json
```

Existing synthetic non-mech import/export, resource filter, and static texture regressions also pass in Blender 5.1. No live-game map export or full-mission validation is claimed.
