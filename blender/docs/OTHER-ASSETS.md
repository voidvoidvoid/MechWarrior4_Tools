# Buildings, ground vehicles and aircraft — R16

R16 removes the mech-directory restriction and adds standalone ERF import. Support is determined by binary layout, not whether an asset is called a mech, tank, helicopter or building. This is an initial extension of the tested ERF pipeline, not a claim that every non-mech asset format has been decoded.

## Import from an installation

1. Open the 3D View sidebar with **N**, select **MW4**, and click **Import from MW4 installation**.
2. Select your installation directory.
3. Choose **Resource type**:
   - **Model hierarchies (.contents)** lists hierarchies throughout the installation, including outside `mechs/`. Choose this for an assembled asset. Supported hierarchy records retain their original parent relationships and rigid transforms.
   - **Geometry resources (.erf)** lists individual ERFs throughout the installation. Choose this for standalone geometry, or when the asset's hierarchy is unsupported.
4. Search/select the original resource path and import. Installation imports use the existing archive decryption and texture lookup paths.

The browser lists candidates from archive indexes. Listing is not a guarantee that the binary layout is supported; unsupported elements are rejected with a diagnostic.

## Import an extracted ERF

Choose **N → MW4 → Import standalone ERF (.erf)** or **File → Import → MechWarrior 4 Geometry (.erf)**. Supply a decoded ERF14 file beginning with `#FRE`; encrypted archive payloads must be imported through the installation browser instead.

A standalone resource gets one `asset_root` bone as an export container. This is not a recovered turret/rotor joint. A standalone ERF does not provide the hierarchy needed to animate separate parts. Its resource report explicitly records this limitation, and animation collection is disabled for that import. The ERF element transform is retained, with the same native Y-up to Blender Z-up conversion as mech imports.

Textures are looked up in the saved MW4 installation when one is configured. An extracted file without an installation may have UVs and material references but no texture images. The basename of a loose ERF does not recover its archive path; use an installation import when exact replacement paths matter.

## Edit and export

Edit existing imported mesh objects, keeping their original rigid bone weights and material references. Return to Object Mode and use **N → MW4 → Native Geometry Export**:

- **Export selected part (.erf)** writes one native resource.
- **Export asset ERFs (.zip)** writes represented resources under their original paths, plus the export manifest.

The [ERF export rules](ERF-EXPORT.md) still apply: LOD0 edits only; original lower LODs retained; no archive packing; no hierarchy, collision, damage-state or texture-image export. Edited oriented-box-bound resources are rejected, while unchanged ones pass through byte-for-byte. Use an external resource packer to install replacements.

## Supported layouts and remaining work

| Input | R16 behavior |
| --- | --- |
| ERF14 elements `0x83` and `0x90`, MLR18 shape `0x4b`, primitive `0x66` | Standalone import and existing template-based export |
| Previously supported 280-byte `.contents` records | Assembled import anywhere in the archive; node names no longer require `joint_`/`site_` prefixes |
| Other record sizes, scaled/sheared/reflected hierarchy transforms | Explicit unsupported-layout error |
| Other ERF element or primitive classes, animated ERF transforms, EBF | Not newly decoded; explicit rejection |
| Game-driven turret aiming, helicopter flight, rotor behavior | No behavior synthesis; only supported supplied animation clips can be imported |
| New independent assets or changed game hierarchy | Not an authoring/registration pipeline |

Generic node names must be 1–63 ASCII letters, digits, spaces, underscores, periods or hyphens. This avoids silent Blender bone-name truncation and retains strict record/transform validation. Source-name animation matching remains exact.

## Validation and samples needed

Blender 5.1 regression checks cover synthetic building, vehicle and aircraft paths, generic node names, standalone and assembled imports, edited geometry export, unchanged byte preservation, actual import/export operators, save/reopen, and unsupported-class rejection before object creation. These synthetic fixtures exercise supported layouts; they are **not real building/tank/helicopter samples**.

The real Uller bundle still passes all 19 unchanged-ERF checks and native animation export. Existing Solitaire dependency/partial-mesh and no-animation regressions also pass. No live-game test has been performed.

To expand format coverage, provide one building, one ground vehicle and one aircraft resource bundle. Prefer **Save resource bundle (.zip)** after selecting each `.contents` asset, even if its hierarchy is unsupported: the decoded bundle/report is retained. If no hierarchy is listed, provide its original `.erf` files plus any associated `.contents`, `.data`, `.video`, named subresources, animation files and the resource report. Include the exact resource paths and game/MekTek version. Do not supply only screenshots; binary records are needed to distinguish new layouts from collection failures.
