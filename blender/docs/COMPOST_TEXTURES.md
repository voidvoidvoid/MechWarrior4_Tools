# Full terrain textures — R21

R21 builds the close-view terrain textures from the original map's `textures/composttexture` resources. R19/R20 only loaded the far-view images under `textures/maps/<map>`.

## Using it

For a **new map**, leave **Full close-view terrain textures** enabled in the installation import dialog. It is on by default for **Resource type: Map terrain**. Disable it for a faster import using the older baked far textures.

For a **map already imported in R19/R20**, install R21 and restart Blender. Select the terrain parent or a terrain mesh, then click **MW4 → Load / Reload Textures from MW4** and select the installation directory. This builds and assigns the close-view textures without replacing the geometry. Reload attempts full composition regardless of the original import checkbox.

The sidebar reports **Full terrain textures: 2048×2048** for the supplied Alpine and Urban samples. Use **Material Preview** to see them. Each image is packed into the `.blend`, and the resource bundle retains original composition inputs and generated images for import without the game installation.

This is more work than loading far textures. Native-resolution images take longer to build and substantially increase `.blend` and bundle size. The tested Alpine composites total approximately 74 MB of PNG data; Urban01 approximately 51 MB, before additional source resources and Blender storage. Full terrain textures use 64 times as many texels as the previous 256×256 zone textures. Compilation is CPU-side and uses NumPy included with Blender; no extra packages are needed.

## What is loaded

These resources are ingredients for a runtime compositor, not interchangeable finished images:

- `<map>.fgd`: feature definitions, ordered placements, sizes, texture offsets, mirror flags and blending modes.
- `textures/composttexture/<map>.index.tcf`: texture names, dimensions and BID pixel types.
- Referenced `.bid` files: padded full-resolution colors, masks and lighting, followed by mip levels where applicable.

The importer reconstructs the composition at the FGD's original pixel resolution, then bakes it into one texture per terrain UV region. The tested samples produce 2048×2048 zone images. It does **not** enlarge the old far-view images or place one grass/rock image over the whole map. Composed colors retain the terrain's existing UV layout and include authored mask transitions and lighting.

The first implementation supports the modes present in the supplied Alpine01 and Urban01/02/05 data: opaque RGB555, additive and multiplicative colors, scaled or direct 8-bit masks, RGBA4444 alpha, and a scaled RGB555 lightmap. Sampling preserves BID border texels and FGD color/mask mirror flags. Composition respects feature-table order and clips placements to each output region.

Individual source layers are retained in the resource bundle, but are **not** exposed as an editable stack of Blender shader nodes. Game-specific runtime detail-texture overlays, animated effects and native terrain texture export are not reproduced.

## Failure behavior

Unsupported FGD versions, operations or BID formats, malformed inputs, missing dependencies, and conflicting source resources are reported. The importer keeps the baked far-view textures as a fallback and labels that state in the sidebar; it does not claim that a partial composition is full detail. The selected map archive takes precedence when different archives contain the same texture paths.

Detailed results are under `terrain_composition` in the Blender Text datablock `<map> · MW4 resource report`, including source files, output sizes and hashes, composition dimensions and errors. Manual texture overrides on reload are preserved.

## Format evidence and validation

Implementation was derived from the MW4 decompilation and the supplied archives:

| Function | Relevant behavior |
| --- | --- |
| `006e7640`, `006e77f0` | Read FGD feature definitions |
| `006ded00`, `006de3e0` | Read placement grid and instances |
| `006df180` | Sort by feature-table index |
| `006dad40`, `006ddc50` | BID byte lengths, mip levels and pixel widths |
| `006de5b0` | Texture offsets, borders, mirror bits and scaled mask coordinates |
| `006df740` | Operation dispatch and RGB555 conversion |
| `006e0aa0`, `006e5100` | Interpolated and direct mask blending |
| `006e3cc0` | RGBA4444 blend formula |
| `006e1460` | Interpolated lightmap multiplication |

Sources are in [analysis/c](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/tree/main/analysis/c). No game binary, map data, or source images are distributed with this tool.

Synthetic checks cover BID lengths and channel layouts, integer blend formulas, mirrored/scaled sampling, cropped composition, PNG decoding and explicit fallback. Real-archive checks cover packed 2048×2048 materials, upgrading an existing map through the actual reload operator, resource-bundle restoration and `.blend` reopening. The old far-texture import remains available and has separate terrain regressions.

An additional image comparison downsampled the generated Alpine AA and Urban AA composites to the original 256×256 textures. Correlations were approximately 0.984 and 0.986, with mean absolute channel differences of 3.46 and 3.22 on a 0–255 scale. This checks spatial alignment and broad layer composition, not bit-identical reproduction of the game's mip generation or renderer. The full-resolution images were also inspected visually.
