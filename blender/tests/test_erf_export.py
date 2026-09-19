"""External Uller bundle regression. No game assets included.
Usage: blender --background --python tests/test_erf_export.py -- bundle.zip report.json
"""
import sys,json,tempfile,zipfile,struct,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
from mathutils import Vector
import io_scene_mw4anim as addon
from io_scene_mw4anim import meshes,game_import,mesh_export,erf,erf_write,rig
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
source,report_path=map(Path,args);addon.register()
files,report=meshes.read_bundle(source)
obj,rpt=game_import.import_resource_files(files,report,bpy.context,import_animations=False)
output,manifest=mesh_export.collect_exports(obj)
assert len(output)==19 and all(data==files[n] for n,data in output.items())
# Older imported projects have no geometry fingerprint.
fingerprints={o.name:o['mw4_geometry_fingerprint'] for o in obj.children if o.type=='MESH'}
for name in fingerprints:del bpy.data.objects[name]['mw4_geometry_fingerprint']
assert mesh_export.collect_exports(obj)[0]==output
for name,value in fingerprints.items():bpy.data.objects[name]['mw4_geometry_fingerprint']=value
# Original rig world orientation/placement and current pose must not bake into ERFs.
obj.location=(12,-3,9);obj.pose.bones['joint_hip'].rotation_quaternion=(0.9,0,0,0.43589)
assert mesh_export.collect_exports(obj)[0]==output
obj.pose.bones['joint_hip'].rotation_quaternion=(1,0,0,0)
child=next(o for o in obj.children if o.type=='MESH' and o['mw4_erf_source'].endswith('ulr_torso.erf'))
source_name=child['mw4_erf_source'];original=erf.loads(files[source_name]);index=int(child['mw4_mesh_binding'].rsplit('|',1)[1])
# Vertex and UV edit; original state blobs and lower LOD bytes must survive.
child.data.vertices[0].co.x+=0.25
child.data.uv_layers.active.data[0].uv.x+=0.125
child.data.update()
edited,manifest=mesh_export.collect_exports(obj)
assert [n for n in output if edited[n]!=output[n]]==[source_name]
decoded=erf.loads(edited[source_name])
assert [l['raw'] for l in decoded['lods'][1:]]==[l['raw'] for l in original['lods'][1:]]
assert all(m['material_raw']==original['lods'][0]['meshes'][index]['material_raw'] for m in decoded['lods'][0]['meshes'][index:index+1])
# Independently check positive plane-distance convention from Pascal CalcPlaneEQ.
for l in decoded['lods']:
 for m in l['meshes']:
  assert len(m['vertices'])<=256
cx,cy,cz,radius=struct.unpack_from('<4f',edited[source_name],decoded['bounds_offset'])
assert all((Vector(v)-Vector((cx,cy,cz))).length<=radius+1e-5 for l in decoded['lods'] for m in l['meshes'] for v in m['vertices'])
# Plane convention independently checked against each exported triangle.
for m in decoded['lods'][0]['meshes']:
 for triangle,plane in zip(m['triangles'],m['planes']):
  assert abs(sum(plane[i]*m['vertices'][triangle[0]][i] for i in range(3))-plane[3])<1e-5
# Retopology beyond a byte-indexed primitive: split 300 distinct vertices.
verts=[];faces=[]
for i in range(100):
 verts.extend([(i*0.01,0,0),(i*0.01,0.005,0),(i*0.01,0,0.005)]);faces.append((3*i,3*i+1,3*i+2))
mesh=bpy.data.meshes.new('export retopology fixture');mesh.from_pydata(verts,[],faces);mesh.update();mesh.uv_layers.new(name='MW4 UV')
mesh.materials.append(child.material_slots[0].material);child.data=mesh
child.vertex_groups.new(name=child['mw4_bone']).add(list(range(300)),1,'REPLACE')
retopo,_=mesh_export.collect_exports(obj);retopo_decoded=erf.loads(retopo[source_name])
assert len(retopo_decoded['lods'][0]['meshes'])==len(original['lods'][0]['meshes'])+1
assert all(len(m['vertices'])<=256 for m in retopo_decoded['lods'][0]['meshes'])
# Unsupported shapes are copied if unchanged, but edits cannot retain stale OBB bounds.
obb=next(o for o in obj.children if o.type=='MESH' and erf.loads(files[o['mw4_erf_source']])['flags']&32)
coord=obb.data.vertices[0].co.copy();obb.data.vertices[0].co.x+=0.1
try:mesh_export.collect_exports(obj);raise AssertionError('OBB edit accepted')
except ValueError as exc:assert 'oriented bounding box' in str(exc)
obb.data.vertices[0].co=coord
# Pose and native animation export still operate after mesh export.
with tempfile.TemporaryDirectory() as td:
 td=Path(td)
 clip_name=next(n for n in files if n.endswith('_walk.mw4anim'))
 clip=td/'walk.mw4anim';clip.write_bytes(files[clip_name]);rig.import_action(clip,bpy.context,obj)
 assert rig.export_action(obj)==files[clip_name]
 bpy.context.view_layer.objects.active=obj
 package=td/'replacement.zip'
 assert bpy.ops.export_scene.mw4_erf_package(filepath=str(package))=={'FINISHED'}
 with zipfile.ZipFile(package) as z:
  assert z.read(source_name)==retopo[source_name]
  assert '_mw4_erf_export.json' in z.namelist()
 bpy.context.view_layer.objects.active=child
 part=td/'part.erf';assert bpy.ops.export_scene.mw4_erf(filepath=str(part))=={'FINISHED'}
 assert part.read_bytes()==retopo[source_name]
 # A failed export must leave an existing destination untouched.
 part.write_bytes(b'keep me');child.modifiers.new('unsupported','SUBSURF')
 try:result=bpy.ops.export_scene.mw4_erf(filepath=str(part))
 except RuntimeError:result={'CANCELLED'}
 assert result=={'CANCELLED'} and part.read_bytes()==b'keep me'
 child.modifiers.remove(child.modifiers[-1])
 root_name=obj.name
 blend=td/'roundtrip.blend';bpy.ops.wm.save_as_mainfile(filepath=str(blend))
 bpy.ops.wm.open_mainfile(filepath=str(blend));obj=bpy.data.objects[root_name]
 assert mesh_export.collect_exports(obj)[0]==retopo
result={'blender':bpy.app.version_string,'unchanged_erfs_byte_identical':19,
 'legacy_import_noop_byte_identical':True,'pose_and_world_placement_excluded':True,'edited_resource_isolation':True,
 'lower_lod_bytes_preserved':True,'bounds_enclose_all_lods':True,
 'uv_edit_and_300_vertex_retopology_split':True,'obb_edit_rejected':True,
 'single_erf_and_package_operators':True,'failed_export_preserves_destination':True,
 'native_animation_export_still_byte_identical':True,'save_reopen_geometry_stable':True,'live_game_test':False}
report_path.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
addon.unregister()
