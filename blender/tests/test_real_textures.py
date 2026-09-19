"""Real archive regression; external game assets are never bundled with the tool.
Usage: bpy-python test_real_textures.py bundle.zip archive-directory output.json
"""
import sys,json,time,tempfile,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
import io_scene_mw4anim as addon
from io_scene_mw4anim import archives,textures,meshes,game_import,rig,animation_ui
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
bundle,folder,out=map(Path,args[:3]);addon.register()
files,report=meshes.read_bundle(bundle);catalog=archives.Catalog(folder)
start=time.perf_counter();lookup=textures.collect(catalog,files,report)
assert not lookup['missing'] and not lookup['errors'],lookup
for path in lookup['mapping'].values():assert files[path] and path.startswith('textures/')
obj,report=game_import.import_resource_files(files,report,bpy.context)
assert not report['texture_import']['missing'] and not report['texture_import']['errors'],report['texture_import']
assert obj['mw4_mesh_count']==25 and obj['mw4_texture_count']==4
images=[i for i in bpy.data.images if i.get('mw4_sha256')]
assert len(images)==len({hashlib.sha256(files[p]).hexdigest() for p in report['texture_import']['images']})
assert all(i.packed_file for i in images)
for mat in bpy.data.materials:
 if not mat.get('mw4_texture_archive_member'):continue
 shader=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
 if mat.get('mw4_texture_reference') in ('@pilot','@team'):assert shader.inputs['Alpha'].is_linked
 if mat.get('mw4_texture_reference')=='@aulr0':assert not shader.inputs['Alpha'].is_linked
active=obj.animation_data.action;original=files[active['mw4_archive_member']]
assert rig.export_action(obj)==original
# Drive the actual persistent dropdown callback using all imported clips.
for action in animation_ui.actions_for(obj):
 obj.mw4_preview_action=action
 assert obj.animation_data.action==action and not obj.get('mw4_animation_status')
 assert rig.export_action(obj)==files[action['mw4_archive_member']]
obj.mw4_preview_action=active
with tempfile.TemporaryDirectory() as td:
 path=Path(td)/'real-textures.blend';name=obj.name
 bpy.ops.wm.save_as_mainfile(filepath=str(path));bpy.ops.wm.open_mainfile(filepath=str(path))
 obj=bpy.data.objects[name];bpy.context.view_layer.objects.active=obj
 assert rig.export_action(obj)==original
 assert all(i.packed_file for i in bpy.data.images if i.get('mw4_sha256'))
 dest=Path(td)/'export.zip';assert bpy.ops.export_scene.mw4_resource_bundle(filepath=str(dest))=={'FINISHED'}
 actual,rpt=meshes.read_bundle(dest)
 assert all(actual[p]==files[p] for p in lookup['mapping'].values())
result={'blender':bpy.app.version_string,'real_archive':True,'indexed_members':len(catalog.rows),
 'resolved_textures':lookup['mapping'],'errors':report['texture_import']['errors'],
 'mesh_objects':obj['mw4_mesh_count'],'visible_materials':report['texture_import']['materials'],
 'images':[{'name':i.get('mw4_archive_member'),'size':list(i.size),'packed':bool(i.packed_file),
 'sha256':i.get('mw4_sha256')} for i in bpy.data.images if i.get('mw4_sha256')],
 'actions_switched_and_exported':len(animation_ui.actions_for(obj)),
 'elapsed_seconds':time.perf_counter()-start,'save_reopen_and_bundle_image_bytes_verified':True}
out.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
# Optional local inspection project, excluded from the public distribution.
if len(args)>3:bpy.ops.wm.save_as_mainfile(filepath=str(Path(args[3]).resolve()))
addon.unregister()
