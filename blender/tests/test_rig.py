"""python test_rig.py animations.zip assets.zip results-directory (requires bpy)."""
import json
import math
from pathlib import Path
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
from mathutils import Matrix,Quaternion,Vector
import io_scene_mw4anim as addon
from io_scene_mw4anim import rig,codec,hierarchy

args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
anims,assets,out=Path(args[0]),Path(args[1]),Path(args[2]);out.mkdir(parents=True,exist_ok=True)
z=zipfile.ZipFile(anims)
bpy.ops.wm.read_factory_settings(use_empty=True)
addon.register()
assert bpy.ops.import_scene.mw4_hierarchy(filepath=str(assets))=={'FINISHED'}
obj=bpy.context.object
info=json.loads(obj['mw4_hierarchy'])
assert len(obj.data.bones)==41
assert obj.data.bones['joint_luleg'].parent.name=='joint_root'
assert obj.data.bones['joint_ldleg'].parent.name=='joint_luleg'
assert obj.data.bones['site_lfoot'].parent.name=='joint_lbelowankle'
result={'blender':bpy.app.version_string,'bone_count':41,'byte_identical_clips':0,
        'first_frame_bone_matrix_checks':0,'tests':[]}

def import_name(name):
    b=z.read(name);p=out/'current.mw4anim';p.write_bytes(b)
    action=rig.import_action(p,bpy.context,obj)
    return b,codec.loads(b),action

for name in sorted(n for n in z.namelist() if n.endswith('.mw4anim')):
    b,c,act=import_name(name)
    assert rig.export_action(obj)==b,name
    result['byte_identical_clips']+=1
    # Independent reconstruction: parent-local source transforms -> global pivots,
    # compared to evaluated Blender pose matrices with bone-axis correction.
    local={n['name']:rig.affine(n['matrix']) for n in info['nodes']}
    for tr in c.tracks:
        nm=c.channels[tr.channel].name
        if nm not in local:continue
        if tr.kind==1:
            local[nm].translation=Vector(tr.values[0])
        elif tr.kind==2:
            x,y,zz,w=tr.values[0]
            q=Quaternion((w,x,y,zz));q.normalize()
            t=local[nm].translation.copy();local[nm]=q.to_matrix().to_4x4();local[nm].translation=t
    world={}
    bpy.context.scene.frame_set(1);bpy.context.view_layer.update()
    for n in info['nodes']:
        nm=n['name'];world[nm]=world[n['parent']]@local[nm] if n['parent'] else local[nm]
        expected=world[nm]@Quaternion(n['bone_correction']).to_matrix().to_4x4()
        actual=obj.pose.bones[nm].matrix
        err=max(abs(actual[i][j]-expected[i][j]) for i in range(4) for j in range(4))
        assert err<2e-4,(name,nm,err)
        result['first_frame_bone_matrix_checks']+=1

b,c,action=import_name('bushwacker/animation/bw_walk.mw4anim')
assert obj['mw4_unbound_channels']=='joint_missile'
pb=obj.pose.bones['joint_ldleg']
pb.rotation_quaternion=Quaternion((1,0,0),0.15)@pb.rotation_quaternion
pb.keyframe_insert(data_path='rotation_quaternion',frame=1,group=pb.name)
for fc in addon.curves_for(obj):
    if fc.data_path==pb.path_from_id('rotation_quaternion'):
        for k in fc.keyframe_points:k.interpolation='LINEAR'
        fc.update()
bpy.context.scene.frame_set(1);bpy.context.view_layer.update()
before={pb.name:pb.matrix.copy() for pb in obj.pose.bones}
edited=rig.export_action(obj)
parsed=codec.loads(edited)
changed=[i for i,(a,b) in enumerate(zip(c.tracks,parsed.tracks)) if a!=b]
assert len(changed)==1 and c.channels[c.tracks[changed[0]].channel].name=='joint_ldleg',changed
(out/'walk-edited-rig.mw4anim').write_bytes(edited)
rig.import_action(out/'walk-edited-rig.mw4anim',bpy.context,obj)
bpy.context.scene.frame_set(1);bpy.context.view_layer.update()
for pb in obj.pose.bones:
    err=max(abs(pb.matrix[i][j]-before[pb.name][i][j]) for i in range(4) for j in range(4))
    assert err<2e-4,(pb.name,err)
result['tests'].append('pose rotation edit exports one track; reimport reproduces world pose')

# Translation edit exercises rest translation and bone-axis conversion.
pb=obj.pose.bones['joint_root'];pb.location.x+=0.12
pb.keyframe_insert(data_path='location',frame=1,group=pb.name)
for fc in addon.curves_for(obj):
    if fc.data_path==pb.path_from_id('location'):
        for k in fc.keyframe_points:k.interpolation='LINEAR'
        fc.update()
edited2=rig.export_action(obj)
assert edited2!=edited
result['tests'].append('pose translation edit exports through inverse bind conversion')

# Keying a default-only channel must be rejected, not silently ignored.
pb=obj.pose.bones['joint_cage'];pb.location.x=0.1
pb.keyframe_insert(data_path='location',frame=1)
try:
    rig.export_action(obj);raise AssertionError('default-channel edit accepted')
except codec.FormatError as e:assert 'default-only' in str(e)
result['tests'].append('unsupported default-channel edit rejected')

# Select the saved original Action again; all missing source channels reset.
obj.animation_data.action=action
bpy.context.scene.frame_set(1);bpy.context.view_layer.update()
assert obj.pose.bones['joint_cage'].location.length<1e-6
result['tests'].append('switching Actions restores default-only channels')

# Preserve both skeleton and source metadata across a project reload.
b,c,action=import_name('bushwacker/animation/bw_walk.mw4anim')
obj.name='Bushwacker';bpy.context.scene.frame_set(1)
blend=out/'Bushwacker-Animation-R2.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(blend.resolve()))
bpy.ops.wm.open_mainfile(filepath=str(blend.resolve()))
obj=bpy.data.objects['Bushwacker']
assert rig.export_action(obj)==b
result['tests'].append('blend save/reopen preserves byte-exact rig export')
result['retained_actions']=len([a for a in bpy.data.actions if 'mw4_rig_metadata' in a])
(out/'rig-results.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
addon.unregister()
