"""External resource bundle -> picker, Action isolation, native export regression.
Usage: bpy-python test_animation_ui.py bundle.zip results.json
"""
import json,sys,tempfile,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
from mathutils import Quaternion
import io_scene_mw4anim as addon
from io_scene_mw4anim import animation_ui as ui,rig,codec,hierarchy,meshes
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
source,out=map(Path,args)
addon.register()
files,report=meshes.read_bundle(source)
with tempfile.TemporaryDirectory() as td:
    folder=Path(td);hp=folder/'hierarchy.zip'
    with zipfile.ZipFile(hp,'w') as z:
        for name,data in files.items():
            if hierarchy.PATTERN.fullmatch(name):z.writestr(name,data)
    obj=rig.build_armature(hp,bpy.context)
    names=[next(n for n in files if n.endswith(suffix)) for suffix in ('_walk.mw4anim','_standpose.mw4anim','_getup.mw4anim')]
    actions=[]
    for name in names:
        path=folder/'clip.mw4anim';path.write_bytes(files[name])
        a=rig.import_action(path,bpy.context,obj);a['mw4_archive_member']=name;actions.append(a)
    other=rig.build_armature(hp,bpy.context)
    foreign=rig.import_action(path,bpy.context,other)
    bpy.context.view_layer.objects.active=obj
    assert set(ui.actions_for(obj))==set(actions) and foreign not in ui.actions_for(obj)
    # Selecting a child mesh still resolves the correct rig.
    mesh=bpy.data.objects.new('selected child',bpy.data.meshes.new('dummy'));bpy.context.collection.objects.link(mesh);mesh.parent=obj
    bpy.context.view_layer.objects.active=mesh
    for action,name in zip(actions,names):
        obj.data.pose_position='REST'
        obj.mw4_preview_action=action
        assert not obj.get('mw4_animation_status')
        assert obj.data.pose_position=='POSE'
        assert obj.mw4_preview_action==action
        assert obj.animation_data.action==action and obj.animation_data.action_slot is not None
        assert bpy.context.scene.frame_current==1
        assert bpy.context.scene.frame_end>=1+action['mw4_duration']*action['mw4_fps']-1e-5
        dest=folder/Path(name).name
        assert bpy.ops.export_scene.mw4anim(filepath=str(dest))=={'FINISHED'}
        assert dest.read_bytes()==files[name]
    obj.mw4_preview_action=foreign
    assert obj.get('mw4_animation_status') and obj.mw4_preview_action!=foreign
    ui.activate(obj,actions[0],bpy.context)
    pb=obj.pose.bones['joint_ldleg']
    pb.rotation_quaternion=Quaternion((1,0,0),.15)@pb.rotation_quaternion
    pb.keyframe_insert(data_path='rotation_quaternion',frame=1)
    for fc in addon.curves_for(obj):
        if fc.data_path==pb.path_from_id('rotation_quaternion'):
            for k in fc.keyframe_points:k.interpolation='LINEAR'
            fc.update()
    edited=rig.export_action(obj)
    assert edited!=files[names[0]]
    original=codec.loads(files[names[0]]);parsed=codec.loads(edited)
    changed=[i for i,(a,b) in enumerate(zip(original.tracks,parsed.tracks)) if a!=b]
    assert len(changed)==1 and original.channels[original.tracks[changed[0]].channel].name=='joint_ldleg'
    assert bpy.ops.mw4.step_animation(direction=1)=={'FINISHED'}
    assert bpy.ops.mw4.step_animation(direction=-1)=={'FINISHED'}
    assert obj.animation_data.action==actions[0] and rig.export_action(obj)==edited
    bpy.context.scene.frame_set(1);bpy.context.view_layer.update()
    before={pb.name:pb.matrix.copy() for pb in obj.pose.bones}
    dest=folder/'edited.mw4anim'
    assert bpy.ops.export_scene.mw4anim(filepath=str(dest))=={'FINISHED'}
    rig.import_action(dest,bpy.context,obj)
    bpy.context.view_layer.update()
    error=max(abs(pb.matrix[i][j]-before[pb.name][i][j]) for pb in obj.pose.bones for i in range(4) for j in range(4))
    assert error<2e-4,error
    assert bpy.ops.mw4.rest_pose()=={'FINISHED'} and obj.animation_data.action is None
    assert all(pb.matrix_basis.is_identity for pb in obj.pose.bones)
    ui.activate(obj,actions[0],bpy.context)
    # Old R3-R7 projects have no ownership tags. Match their rest fingerprint.
    obj.pop('mw4_rig_id');[a.pop('mw4_rig_id',None) for a in actions]
    assert all(a in ui.actions_for(obj) for a in actions) and foreign not in ui.actions_for(obj)
    blend=folder/'switching.blend';objname=obj.name;actionname=actions[0].name
    bpy.ops.wm.save_as_mainfile(filepath=str(blend));bpy.ops.wm.open_mainfile(filepath=str(blend))
    obj=bpy.data.objects[objname];bpy.context.view_layer.objects.active=obj
    assert bpy.ops.mw4.choose_animation(animation=actionname)=={'FINISHED'}
    assert rig.export_action(obj)==edited
    assert bpy.ops.mw4.copy_diagnostics()=={'FINISHED'}
    diagnostics=json.loads(bpy.data.texts[obj['mw4_diagnostics']].as_string())
    assert diagnostics['active_action']==actionname and diagnostics['compatible_actions']>=3
result={'blender':bpy.app.version_string,'native_format':'MW4ANIM 2.1','source_clips':3,
    'edited_track_count':1,'edited_reimport_matrix_error':error,
    'checks':['persistent Action-pointer dropdown update callback and validation','select rig through child mesh','per-rig Action ownership',
    'timeline, Pose Position, and Action slot update','previous/next preserve edits','rest pose preserves Actions',
    'native export operator byte-identical for originals','edited export/reimport reproduces pose',
    'legacy-project compatibility','save/reopen edited Action and selection'],
    'limit':'No live game test; no mesh/texture export or archive repacking'}
out.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2));addon.unregister()
