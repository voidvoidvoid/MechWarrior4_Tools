# R6 multi-mech review

The supplied `mechs core.zip` contains 501 hierarchy/model-link/video/other records. `mechs props.zip` contains 460 animation clips and four animscripts. Neither contains ERF polygon geometry.

## Findings

| Mech | Recovered bones | Supplied clips | Result |
|---|---:|---:|---|
| Crab | 36 | 153 | All supplied clips bind and export unchanged |
| Daishi | 40 | 146 | All supplied clips bind; rotated foot-site rest transforms preserved |
| Uller | 38 | 7 | All supplied clips bind; script's shared Cougar clips absent from uploads |
| Uziel | 40 | 154 | All supplied clips bind; distinct leg/toe and special-joint hierarchy preserved |

The Uller script declares Cougar/cgr for its shared animation paths. All 153 unique expanded animation paths in that script point to Cougar. The Uller folder itself contains fall/get-up clips, so collecting only that folder does not provide its normal movement animations. R5 could then leave the final get-up clip active. R6 collects script-referenced animation paths across archives and deliberately chooses walk/stand, with a rest-pose fallback.

This is a demonstrated import defect and a plausible cause of the reported odd initial pose. It does not establish that every visible Uller mesh issue is fixed.

## Rig checks

The existing importer constructs each hierarchy from its own parent-local matrices. The four samples have different joint counts and leg/toe structures. Daishi, Uller, and Uziel have rotated foot-site rest transforms that the Bushwacker sample did not exercise. No hierarchy matrix in these samples required relaxing the rigid-transform validation. All sampled model-element and video-group transforms were identity, so those samples do not establish support for arbitrary transforms there.

On both Blender 5.1.0 and 5.2.0 LTS:

- Imported and exported all 460 clips byte-identically.
- Checked 53,322 joint pose matrices, covering every clip at its start, an interior time, and end.
- Compared evaluated Blender joint matrices against an independent composition of the raw parent-local transforms and normalized linear quaternion samples.
- Maximum matrix-component error: approximately 0.0000052.
- No unbound animation channel names in these four supplied sample sets.
- Confirmed the seven-clip Uller import leaves no active fall/get-up pose and preserves all seven Actions.

Separate synthetic archive checks cover shared clips across archives, optional content/ prefixes, case normalization, missing and conflicting resources, refusal to choose unrelated same-basename files, macro diagnostics, and preview selection.

These checks validate the supported animation transform representation. They do not prove exact game interpolation, root locomotion integration, procedural foot placement, aiming, or animation-state blending. Types 0/4 remain preserved motion data on joint_vel rather than integrated world movement, as documented in earlier releases.

## Remaining geometry verification

The new ZIPs provide hierarchy/model/video links but no ERF vertex data or original archive index metadata. They therefore cannot establish correct visible polygon alignment or complete archive-ID resolution for these mechs. The actual shared Cougar clip bytes also remain absent.

For the next Uller check, import it from the game directory using R6, then select **Save resource bundle (.zip)** and supply that bundle. It should contain Uller hierarchy/model records, resolved ERFs, and the referenced Cougar clips when present in the installation. The report identifies any unresolved resources. A screenshot or .blend of a remaining incorrect pose would additionally identify the affected Action/frame.

No sample assets are included in this distribution; test programs take external file paths. Historical Bushwacker tests remain labeled with their original scope.
