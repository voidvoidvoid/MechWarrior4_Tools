# MW4ANIM 2.1 — engine-backed format findings

This specification combines the canonical Mercenaries decompilation with the
154 Bushwacker files supplied for this task. It describes the supported sample
encoding, not every hypothetical extension. All integers and floats are little
endian. The exporter preserves unresolved metadata.

## Header and sections

A zero byte precedes the header. Offsets below are relative to the start of the
header, **one byte after the beginning of the file**.

| Header offset | Type | Meaning |
| --- | --- | --- |
| `0x00` | u32 | Major version = 2 |
| `0x04` | u32 | Minor version = 1 |
| `0x08` | float32 | Clip start time |
| `0x0C` | float32 | Clip end time |
| `0x10` | u32 | End offset; file length minus prefix byte |
| `0x14` | u32 | Unresolved; retained |
| `0x18` | u32 | Channel records offset |
| `0x1C` | u32 | Name bytes offset |
| `0x20` | u32 | Keyframe value bytes offset |
| `0x24` | u32 | Keyframe time bytes offset |
| `0x28` | u32 | Track descriptor bytes offset |
| `0x2C..0x63` | bytes | Clip name followed by padding in the samples; retained |

The samples use a 100-byte header and have contiguous sections. Each section's
length is the next offset minus its own; the final section ends at `0x10`.
The reader rejects descending or out-of-range offsets. The original mapper has
no equivalent local bounds checks; loader acceptance alone is not validation.

The byte before the version is verified zero by the mapper. No claim is made
that nonzero values are encryption or compression flags.

## Channel record — 12 bytes

| Offset | Type | Meaning |
| --- | --- | --- |
| `+0` | u32 | Offset into name section |
| `+4` | u32 | First track descriptor index, sample-validated |
| `+8` | u8 | Number of track descriptors, sample-validated |
| `+9..11` | bytes | Unresolved/padding; preserved exactly |

Each descriptor also names its owning channel by index; the parser checks
agreement with the channel's descriptor range. The original factory resolves
channel names against the model, producing a separate runtime mapping array.
Animation channel order is therefore **not a skeleton hierarchy**.

Names are NUL-terminated text or the three-byte sequence `'#', 0x80+id, 0`.
The 47-entry table at native address `0x008246A0` maps IDs to joint names; it was
read from the unpacked, SHA-verified input executable. Examples:

| Encoded bytes before NUL | Name |
| --- | --- |
| `23 AD` | `joint_vel` |
| `23 A3` | `joint_root` |
| `23 96` | `joint_luleg` |
| `23 A7` | `joint_ruleg` |

Literal names include `site_lfoot`, `site_rfoot`, and `joint_missile`.

## Track descriptor — 16 bytes

| Offset | Type | Meaning |
| --- | --- | --- |
| `+0` | u32 | Bytes per key value |
| `+4` | u32 | Offset into keyframe value section |
| `+8` | u32 | Offset into float32 keyframe time section |
| `+12` | u8 | Key count |
| `+13` | u8 | Track type |
| `+14` | u8 | Auxiliary selector/flag; retained, full meaning unresolved |
| `+15` | u8 | Channel index |

Values are an array of `key_count` records of the stated stride. Times are a
parallel array of `key_count` float32 values. They are absolute within the
header's native start/end range; Blender maps `time-start` into its timeline.

| Type | Stride | Stored value | Observed +14 |
| --- | --- | --- | --- |
| 0 | 24 | Position XYZ, linear-motion XYZ | 3 |
| 1 | 12 | Position XYZ | 0 |
| 2 | 16 | Quaternion XYZW | 1 |
| 3 | 4 | Opaque variant/bit word | 2 |
| 4 | 28 | Quaternion XYZW, angular-motion XYZ | 4 |

The samples contain 3,448 type-2 tracks, 154 type-4 tracks, 154 type-1 tracks,
80 type-0 tracks, and 60 type-3 tracks. Maximum observed counts are 25 channels,
29 tracks, and 61 keys in one track.

The type-3 routine returns a raw 32-bit word; the blend accumulator ORs words
and the channel callback forwards the result as a variant identifier. Foot-site
samples use `0x40000000` and zero. Their higher-level meaning is not proven by
this investigation; retain bits without a guessed float/int conversion.

## Timing, interpolation, and playback boundaries

`006A79C0` seeks in seconds relative to clip start, adds the stored start, and
searches the time table. Interior indices identify the next key; `0xFF` means
past the final key. Its end-clamp helper `006A7920` explicitly chooses the last
key index rather than `0xFF`. The pointer accessors implement these boundary
cases, which were verified on the supplied files under emulation.

Position interpolation in `006A7D40` is linear. Quaternion type 2 routes through
`006A7E30` and `00420390`; the latter applies a hemisphere test, component
interpolation, and the engine's quaternion repair routine. It should **not**
be casually described as conventional normalized lerp or SLERP. The exported
pseudocode has suspicious-looking negative-dot assignments, and this release
does not reproduce that routine in Blender. Type 4 uses a different quaternion
path (`006A7F10`, `00420210`).

The auxiliary linear/angular-motion vector interpolation routines `006A7DF0`
and `006A7E10` copy the next key's vector. Type 3 selects the previous key's raw
word within a segment. The add-on preserves samples and track types; its
viewport does not implement a full playback engine emulator.

`00603F60` applies flagged outputs to model parts. If a channel lacks a position
or orientation, the callback reads the default from model data. Motion tracks
also update owner movement fields rather than simply becoming part locations.
This confirms why a faithful rig cannot be reconstructed from these clips alone.

The `.animscript` adds another layer: state selection, transitions, and blends
based on `CurrentSpeedMPS`, `LocalGroundPitch`, and `LocalGroundRoll`. Blender
Actions represent individual clips, not this runtime state machine.

## Primary evidence

All code paths are from `voidvoidvoid/MW4_Mercs_Decomp`, canonical `analysis/c`.

- [Version mapper, 006802E0](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/006802e0.c)
- [Pass 118 format evidence and bounds](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/pass118/PROGRESS.md)
- [Pass 117 channel mapping and byte-sized counts](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/pass117/PROGRESS.md)
- [Compact-name resolver, 006805D0](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/006805d0.c)
- [Model name mapping, 00604280](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/00604280.c)
- [Track dispatch, 006121B0](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/006121b0.c)
- [Value pointer access, 006A76C0](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/006a76c0.c)
- [Previous value pointer, 006A7700](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/006a7700.c)
- [Time pointer access, 006A77D0](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/006a77d0.c)
- [Time seek, 006A79C0](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/006a79c0.c)
- [Position interpolation, 006A7D40](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/006a7d40.c)
- [Quaternion interpolation, 006A7E30](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/006a7e30.c)
- [Model output callback, 00603F60](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/00603f60.c)
- [SHA-guarded unpacker](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/scripts/unpack.py)

Packed EXE SHA256:
`72bbb1ba3e5e5e7dc7607ca403f3d9aca301d0b16814a6b577bda7ec5c922b41`.
The unpacker stops at the original entry-point handoff; it does not launch the
game. Native probes use the resulting mapped image and do not alter game code.


## R2 hierarchy resources and Blender binding

The additional `bushwacker2.zip` supplies 41 unique hierarchy nodes. The main
`.contents` file defines the top-level node; sibling filenames of the form
`.contents[parent_name]{armature}` identify the parent for their child records.
Each resource has a two-byte prefix followed by length-prefixed records. The
prefix is skipped by `006083F0`; it is **not interpreted as a record count**.
All observed child records are 280 bytes long, including their DWORD length.

| Record offset | Encoding | Meaning |
| --- | --- | --- |
| `0x00` | u32 | Record length, 280 in supplied resources |
| `0x1C` | 12 float32 | Row-major affine 3-by-4 local transform |
| `0x28`, `0x38`, `0x48` | float32 | Translation X, Y, Z within that matrix |
| `0x98` | NUL-terminated ASCII | Node name |

Bytes after the name terminator include stale buffer contents and must not be
interpreted as additional resource paths. The parser validates names, parents,
cycles, rigid transforms and record lengths. The small `armaturevideo` files
refer to rendering resources; the supplied archive has no polygon payload.
`joint_missile` appears in clips but not in this hierarchy and remains unbound.

Native global rest matrices are composed down the recovered parent chain.
Blender Edit Bone axes introduce a rotation correction C for each bone:
`C = inverse(native_global_rest) * blender_global_rest` (rotation part).
With native local default translation T0 and rotation Q0, conversion is:

- `pose_location = inverse(Q0 * C) * (native_translation - T0)`
- `pose_rotation = inverse(C) * inverse(Q0) * native_rotation * C`
- `native_translation = T0 + (Q0 * C) * pose_location`
- `native_rotation = Q0 * C * pose_rotation * inverse(C)`

The armature object rotates native Y-up into Blender Z-up; that display
conversion is outside the internal bone transforms. Bone tails are chosen for
visibility and do not constitute additional recovered mesh or pivot data.
Ordinary position and quaternion tracks drive the bones. Motion-bearing types
remain raw custom-property tracks, consistent with the callback's distinction
between model pose and owner movement outputs. Missing ordinary tracks use
constant default pose curves, preventing stale poses when switching Actions.

Additional primary decomp evidence:

- [Child-record reader, 006083F0](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/006083f0.c): skips the prefix, walks record lengths and registers children.
- [Property-to-record writer, 004F1C60](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/004f1c60.c): places the 3-by-4 transform at DWORD 7.
- [Record prefix writer, 004CB220](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/004cb220.c): copies the 12 transform components.


## R3 archive and geometry-reference integration

The archive reader is the supplied `mw4_extract.py` v1.0.0, retained as `helm.py`.
It parses #VBD v4 physical records while importing only declared-index entries,
and decodes raw, 9–12-bit LZW, and `mektek`/`secure` wrappers. Wrapper plaintext
is CRC32-checked. The separate bundled key/table profile is hash-pinned to the
same material fingerprint expected by the supplied extractor; the optional
key-source override retains its original checks. Keys are not read from an
arbitrary executable or assumed compatible with other builds.

`.video` resources begin with a DWORD record count and length-prefixed component
records. For class `0x21e` (`Adept::ShapeComponent`), record offsets +9 and +11
hold the 16-bit database and resource IDs after the byte at +8 (`Unique`).
The supplied Bushwacker files reference database 0, resource IDs 137–174.
These are geometry resource references, not the `#FRE` and `#RLM` header values:
those latter headers carry ERF version 14 and MLR version 18 respectively.

The directory reader resolves matching resource IDs only when their ERF names
also contain the selected model's directory component. It reports ambiguity;
it does not infer runtime database registration or game archive load order.
All files in the selected model subtree are also collected, so even unresolved
bindings may have their geometry bytes available for investigation. This is
resource acquisition and provenance, not a verified complete renderer dependency
closure. No ERF polygon interpretation is performed in R3.

Primary references:

- [ShapeComponent class ID](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/004e2550.c)
- [Geometry property compiler](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/004f4d70.c)
- [Packed resource-handle reader](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/004c5500.c)
- [ERF version reader](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/004a2ae0.c)
- [MLR version reader](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/00424f40.c)


## R4 ERF geometry decoder and rigid binding

The real Bushwacker bundle contains 38 ERFs. All use ERF 14 and MLR 18;
37 use `ShapeLODElement` class 0x90 and the cockpit cage uses `ShapeElement`
class 0x83. All observed primitives are class 0x66 (`MLR_I_L_TMesh`).
The parser consumes all 190 LOD records and checks exact shape and file extents.
It is deliberately limited to these verified classes and versions.

ERF prefix: `#FRE`, u32 version, u32 element class, u32 flags. Flag bit 0
omits the identity 3-by-4 transform; otherwise 12 floats follow. Bounds are
16 bytes for a sphere, or 64 bytes when bit 0x20 selects an oriented box.
The current parser rejects animated-transform bit 0x400. Class 0x90 then has
a u16 LOD count. Both classes contain `#RLM` plus u32 MLR version.
For each LOD, class 0x90 has two distance floats, then a u32 shape byte length;
class 0x83 has just the length. Shapes begin with class 0x4B and a u8 primitive
count. Each primitive has its class ID and the following observed MLR18 data:

1. u32 vertex count, then float32 XYZ vertices.
2. u32 UV count, then float32 UV pairs.
3. One mode byte, then six u32 render-state words.
4. If state word 0 has a nonzero low 14-bit field: u32 name length, that many
   texture-name bytes plus a NUL terminator, then four texture hint bytes.
5. u32 index count, then **byte** indices, grouped in triangles.
6. u32 plane count, then four floats per triangle plane.
7. u32 color count and one packed u32 per color.
8. u32 normal count and three floats per normal.

The winding of the source triangles agrees with the supplied normals and is
preserved. UV V is inverted for Blender. Colors and render states are decoded
for layout fidelity but not used to claim game-equivalent shading.

Node model handles are at hierarchy-record offset 0x54. Supplied `.data`
resources contain three packed handles; the second links the `.video` resource.
ShapeComponent records (0x21E) carry geometry handles at +9 and local 3-by-4
matrices at +21. The exact link chain places hip geometry on `joint_hipabove`,
feet on the `joint_*belowankle` nodes and torso geometry on `joint_torsoabove`.
The default exterior view excludes `_dam.erf` resources and the cockpit cage;
repeated identical component bindings are deduplicated. This is an intact
preview selection, not an implementation of runtime damage/component switching.

A source vertex is transformed by native global rest * component local * ERF
local. The resulting vertex is weighted 1.0 to the corresponding Blender bone.
The Armature modifier then produces native animated rigid-part motion, while
the existing armature-object rotation applies Y-up to Z-up conversion.
Independent reconstruction checked 5,568 evaluated vertices at four walk poses.

Primary implementation evidence:

- [ERF base element](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/004b9c60.c)
- [ShapeLOD reader](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/004a61a0.c)
- [Single-shape reader](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/004b4e20.c)
- [MLR shape reader](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/0047e670.c)
- [Primitive vertices, UVs and state](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/00477e80.c)
- [MLR18 byte indices](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/004772d0.c)
- [Triangle planes](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/00456aa0.c)
- [Vertex colors](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/00450070.c)
- [Vertex normals](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/0044cef0.c)
- [Texture render-state reader](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/004887d0.c)
- [Hierarchy model handle writer](https://github.com/voidvoidvoid/MW4_Mercs_Decomp/blob/main/analysis/c/004f1c60.c)


## R5 texture resource lookup

Primary engine references in voidvoidvoid/MW4_Mercs_Decomp, analysis/c/:

- `004cd390.c`: resolve `content\textures\` + name + `.tga`, fallback `.png`, plus `{hint}`; resolution variants are a separate quality option. R5 uses base images.
- `004cd790.c`: resourcify raw TGA/PNG bytes and a DWORD hint. Format byte at bits 16–23: solid=0, keyed=1, alpha=2, normal=4.
- `004cd680.c`: literal `@` names are loaded directly. A name whose second character is @ and first character is not @ instead loads `skin<first character>0` and the @ detail texture, then composites them. Double @ escapes one prefix.
- `00488170.c` / `00488220.c`: skin/detail CPU composition. For detail alpha zero, copy skin RGB. Otherwise RGB=(skin*(255-alpha)+detail*alpha)>>8. R5 does not implement this composition or the preceding runtime callback that selects team/pilot/skin names.

R5 preserves @ in exact resource names. It does not strip @, infer camouflage variants, or infer archive precedence. Original image bytes and hint sidecars are included in user-generated resource bundles, and Blender images are packed. Alpha is not linked for @ detail textures because it controls skin blending rather than mesh opacity. Unknown transparency modes and color-key generation are not reconstructed.


## R6 multi-mech animation dependencies

The provided Uller animscript expands all 153 animation dependency paths under content/mechs/cougar/animation. Its local supplied directory has seven Uller fall/get-up clips. Static macro expansion and collection now follow exact full referenced paths across archives; optional content/ is the only database-root alias. No basename or resource-ID guess is used for animation dependencies. Unknown/cyclic macros and conflicting bytes produce diagnostics. This parser does not execute the game's state machine.

Initial preview selection uses declared Walk then StandPose; generic filename suffixes are fallback choices. With no suitable preview, pose channels reset to rest and no Action remains active. All imported Actions are retained. Multi-mech transform regression and limits are in MULTI-MECH-REVIEW.md and validation/multi-mech*.json.


## R7 texture content-mount alias

Texture lookup normalizes the optional leading content/ mount prefix for index keys, as animation dependency lookup already does. The original normalized archive name is retained for decoded bytes and resource provenance. Hint sidecars have a separate reference-to-member mapping because their index spelling may use a different prefix from the image. TGA precedence over PNG remains unchanged, and conflicting bytes among full-path aliases are rejected by Catalog.unique. No arbitrary basename matching or @ stripping is introduced. Reports include textures.mw4 member counts and up to 16 image resource names to diagnose remaining naming differences.


## R8 animation UI and embedded payloads

New rigs and their imported Actions carry an ownership UUID. The picker filters by owner and stored hierarchy fingerprint; untagged legacy Actions fall back to the fingerprint. Switching explicitly selects the imported Object slot and updates timeline duration/FPS. It resets unkeyed pose residue without rewriting F-curves or discarding Actions. Native export continues to use the verified MW4ANIM 2.1 writer.

Resource-bundle Text payloads now use base64 with 76-character lines to avoid quadratic insertion of megabyte-long Blender Text lines. embedded.decode accepts legacy single-line payloads or CR/LF-wrapped payloads with otherwise strict base64 validation. The ZIP format and raw resources are unchanged. All bundle readers/writers use this helper. Action metadata is pretty-printed JSON rather than one long line; its schema is unchanged.


## R10 archive evidence and upgrade lifecycle

The actual uploaded textures.mw4 has 13,223 declared members. Uller image names are textures/@aulr0.tga, textures/@pilot.tga, textures/@team.tga, textures/runninglight.tga, textures/cage1.tga, textures/cdash1.tga, with matching {hint} members. Hints respectively: 0x20900, 0x20141, 0x20141, 0x20141, 0x900, 0x20900. Actual image bytes load as TGA in Blender. @pilot/@team are identical transparent decal placeholders, so content-addressed image reuse is expected. Their alpha has surface-transparency meaning, unlike the body detail image's camouflage mask.

Legacy Blender ZIP installs can reload __init__ while retaining dependency modules. This reproduced both the R9 missing-register_properties exception and R6 texture-path logic surviving an R8 update. R10 cleans prior RNA registrations and reloads only this add-on's modules in dependency order, then registers transactionally. Real archive and update-path test reports are in validation/.

## R15 native geometry writer

`erf_write.py` and `mesh_export.py` implement template-based export for supported existing mech parts. See [ERF-EXPORT.md](docs/ERF-EXPORT.md) for the source evidence, serialized fields, limits and tests. Earlier statements in this document that mesh export is absent describe earlier releases. Native `.mw4` archive writing and general `.ebf` authoring remain outside this implementation.
