"""Run in a Python environment with bpy, or Blender --background --python.

python tests/test_blender.py /path/to/bushwacker.zip /path/to/test-output
"""
import json
from pathlib import Path
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
import io_scene_mw4anim as addon

args = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
archive, output = Path(args[0]),Path(args[1])
output.mkdir(parents=True,exist_ok=True)
z = zipfile.ZipFile(archive)
addon.register()
results = {'blender':bpy.app.version_string,'cases':[]}

def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)

def source(name):
    b = z.read('bushwacker/animation/'+name+'.mw4anim')
    p = output/(name+'.mw4anim');p.write_bytes(b)
    return p,b

for name in sorted(Path(n).stem for n in z.namelist() if n.endswith('.mw4anim')):
    clear()
    p,b = source(name)
    root = addon.import_clip(p,bpy.context)
    assert addon.export_bytes(root) == b,name
    results.setdefault('unchanged_clips',[]).append(name)

clear()
p,b = source('bw_walk')
assert bpy.ops.import_scene.mw4anim(filepath=str(p)) == {'FINISHED'}
root = bpy.context.active_object
dest = output/'walk-unchanged.mw4anim'
assert bpy.ops.export_scene.mw4anim(filepath=str(dest)) == {'FINISHED'}
assert dest.read_bytes() == b
results['cases'].append('registered import/export operators')

original = addon.codec.loads(b)
objs = {ob['mw4_track_index']:ob for ob in root.children_recursive if 'mw4_track_index' in ob}
obj = objs[2]
fc = next(fc for fc in addon.curves_for(obj) if fc.data_path == 'location' and fc.array_index == 1)
fc.keyframe_points[0].co.y += 0.25
fc.update()
edited = addon.export_bytes(root)
c = addon.codec.loads(edited)
assert abs(c.tracks[2].values[0][1]-original.tracks[2].values[0][1]-0.25) < 1e-6
for i,tr in enumerate(c.tracks):
    if i != 2:
        assert tr == original.tracks[i]
(output/'walk-edited.mw4anim').write_bytes(edited)
results['cases'].append('position edit preserves other tracks')

# A new fractional-frame key must survive rebuilding all following offsets.
frame = (fc.keyframe_points[0].co.x+fc.keyframe_points[1].co.x)/2
k = fc.keyframe_points.insert(frame,fc.evaluate(frame)+0.1)
k.interpolation = 'LINEAR';fc.update()
c = addon.codec.loads(addon.export_bytes(root))
assert len(c.tracks[2].times) == len(original.tracks[2].times)+1
results['cases'].append('insert fractional-frame key')

qobj = objs[4]
qfc = next(fc for fc in addon.curves_for(qobj) if fc.data_path == 'rotation_quaternion' and fc.array_index == 1)
qfc.keyframe_points[0].co.y += 0.01;qfc.update()
c = addon.codec.loads(addon.export_bytes(root))
assert abs(c.tracks[4].values[0][0]-original.tracks[4].values[0][0]-0.01)<1e-6
results['cases'].append('quaternion xyzw/wxyz mapping')

variant = next(i for i,tr in enumerate(original.tracks) if tr.kind == 3)
vfc = next(fc for fc in addon.curves_for(objs[variant]) if fc.array_index == 0)
vfc.keyframe_points[0].co.y = 1;vfc.update()
c = addon.codec.loads(addon.export_bytes(root))
assert c.tracks[variant].values[0][0] == original.tracks[variant].values[0][0] | 1
results['cases'].append('variant low bit exact through byte curves')

fc.keyframe_points[0].interpolation = 'BEZIER'
try:
    addon.export_bytes(root)
    raise AssertionError('Bezier edit was silently exported')
except addon.codec.FormatError:
    pass
c = addon.codec.loads(addon.export_bytes(root,bake=True))
assert len(c.tracks[2].times) > len(original.tracks[2].times)
results['cases'].append('Bezier rejection and explicit baking')

# Store original bytes and metadata inside .blend, then re-open in this process.
clear()
p,b = source('bw_walk')
root = addon.import_clip(p,bpy.context)
blend = output/'roundtrip.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(blend))
bpy.ops.wm.open_mainfile(filepath=str(blend))
root = next(ob for ob in bpy.data.objects if 'mw4_metadata' in ob)
assert addon.export_bytes(root) == b
results['cases'].append('save/reopen blend retains byte-exact source')

results['passed'] = len(results['cases'])+len(results['unchanged_clips'])
(output/'blender-results.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
addon.unregister()
