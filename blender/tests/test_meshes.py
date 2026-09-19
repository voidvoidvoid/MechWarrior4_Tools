"""Validate actual ERF decoding, rigid binding, R3 upgrade and animation preservation.
Usage: bpy-python test_meshes.py resource-bundle.zip output-directory
"""
import bisect,json,sys,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
from mathutils import Vector,Quaternion
import io_scene_mw4anim as addon
from io_scene_mw4anim import meshes,erf,rig,game_import,codec
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
source,out=map(Path,args);out.mkdir(parents=True,exist_ok=True)
files,report=meshes.read_bundle(source)
parsed=[erf.loads(data) for name,data in files.items() if name.endswith('.erf')]
assert len(parsed)==38
result={'blender':bpy.app.version_string,'real_erf_files':len(parsed),'lods':sum(len(x['lods']) for x in parsed),
        'byte_identical_actions':0,'vertex_pose_checks':0,'max_vertex_error':0.0,'tests':[]}
# Reject malformed versions, counts and truncated payloads.
sample=files['mechs/bushwacker/bw_hip.erf']
for broken in (sample[:-1],sample+b'\0',b'BAD!'+sample[4:],sample[:8]+b'\xff'*4+sample[12:]):
 try:erf.loads(broken)
 except codec.FormatError:pass
 else:raise AssertionError('Malformed ERF accepted')
result['tests'].append('strict version, bounds and end-of-file validation')
bpy.ops.wm.read_factory_settings(use_empty=True);addon.register()
# Exercise the public resource-bundle operator, including automatic mesh attachment.
assert bpy.ops.import_scene.mw4_resource_bundle(filepath=str(source.resolve()))=={'FINISHED'}
obj=bpy.context.object
assert obj['mw4_mesh_count']==26
info=json.loads(obj['mw4_hierarchy']);parts,errors=meshes.plans(files,report,info)
assert not errors
result.update(bones=len(obj.data.bones),mesh_objects=len(obj.children),
              vertices=sum(len(o.data.vertices) for o in obj.children),triangles=sum(len(o.data.polygons) for o in obj.children))
for action in list(bpy.data.actions):
 if 'mw4_archive_member' not in action:continue
 obj.animation_data.action=action
 assert rig.export_action(obj)==files[action['mw4_archive_member']],action.name
 result['byte_identical_actions']+=1
assert result['byte_identical_actions']==154
walk=next(a for a in bpy.data.actions if a.get('mw4_archive_member','').endswith('/bw_walk.mw4anim'))
obj.animation_data.action=walk
clip=codec.loads(files[walk['mw4_archive_member']])

def sample_track(tr,t):
 j=max(0,min(bisect.bisect_right(tr.times,t)-1,len(tr.times)-1))
 if j+1==len(tr.times):return tr.values[j]
 f=max(0,min(1,(t-tr.times[j])/(tr.times[j+1]-tr.times[j])))
 return [a+(b-a)*f for a,b in zip(tr.values[j],tr.values[j+1])]

for frame in (1,9,17,25):
 bpy.context.scene.frame_set(frame);bpy.context.view_layer.update()
 local={n['name']:rig.affine(n['matrix']) for n in info['nodes']}
 for tr in clip.tracks:
  name=clip.channels[tr.channel].name
  if name not in local or tr.kind not in (1,2):continue
  row=sample_track(tr,clip.start+(frame-1)/30)
  if tr.kind==1:local[name].translation=Vector(row)
  else:
   q=Quaternion((row[3],row[0],row[1],row[2]));q.normalize()
   t=local[name].translation.copy();local[name]=q.to_matrix().to_4x4();local[name].translation=t
 world={}
 for n in info['nodes']:world[n['name']]=world[n['parent']]@local[n['name']] if n['parent'] else local[n['name']]
 dg=bpy.context.evaluated_depsgraph_get()
 for part in parts:
  expected_matrix=obj.matrix_world@world[part['bone']]@rig.affine(part['component_matrix'])@rig.affine(part['decoded']['matrix'])
  for i,m in enumerate(part['decoded']['lods'][0]['meshes']):
   key=part['bone']+'|'+part['source']+'|'+str(i)
   child=next(o for o in obj.children if o.get('mw4_mesh_binding')==key)
   evaluated=child.evaluated_get(dg)
   assert len(evaluated.data.vertices)==len(m['vertices'])
   for a,b in zip(m['vertices'],evaluated.data.vertices):
    error=(expected_matrix@Vector(a)-evaluated.matrix_world@b.co).length
    result['max_vertex_error']=max(result['max_vertex_error'],error);result['vertex_pose_checks']+=1
    assert error<2e-4,(frame,child.name,error)
result['tests'].append('evaluated vertices match independent native-transform reconstruction at four walk poses')
# Upgrade a skeleton-only project with the existing R3 embedded-bundle workflow.
for child in list(obj.children):bpy.data.objects.remove(child,do_unlink=True)
obj.pop('mw4_mesh_count',None)
assert bpy.ops.import_scene.mw4_attach_meshes()=={'FINISHED'}
assert len(obj.children)==26
assert bpy.ops.import_scene.mw4_attach_meshes()=={'FINISHED'}
assert len(obj.children)==26
result['tests'].append('R3 embedded-bundle upgrade and duplicate prevention')
bpy.context.scene.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=str((out/'Mesh-Test.blend').resolve()),compress=True)
bpy.ops.wm.open_mainfile(filepath=str((out/'Mesh-Test.blend').resolve()))
obj=next(o for o in bpy.data.objects if o.type=='ARMATURE')
# The old Action Python pointer is invalid after open_mainfile; get the live data.
assert rig.export_action(obj)==files['mechs/bushwacker/animation/bw_walk.mw4anim']
result['tests'].append('mesh/modifier/Action save and reopen')
(out/'mesh-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2));addon.unregister()
