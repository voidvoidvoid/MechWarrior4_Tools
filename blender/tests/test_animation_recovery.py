"""External Uller bundle + real textures.mw4; no game assets distributed.
Usage: bpy-python test_animation_recovery.py bundle.zip textures.mw4 output.json
"""
import sys,json,tempfile,struct,os
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
import io_scene_mw4anim as addon
from io_scene_mw4anim import meshes,archives,textures,game_import,animation_ui,rig
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
bundle,archive,out=map(Path,args[:3]);addon.register()
files,report=meshes.read_bundle(bundle)
with tempfile.TemporaryDirectory() as td:
 root=Path(td);groups={}
 for row in report['resources']:
  name=archives.normalized(row['name'])
  if name in files:groups.setdefault(row['archive'],[]).append((row['id'],row['name'],files[name]))
 for name,entries in groups.items():
  path=root/name;path.parent.mkdir(parents=True,exist_ok=True);records=[];payload=bytearray()
  for rid,name,data in entries:
   nb=name.encode('cp1252');records.append(struct.pack('<QIIIHB',0,len(data),len(data),len(payload),rid,len(nb))+nb);payload+=data
  index=b''.join(records);path.write_bytes(struct.pack('<4sIIIHH',b'#VBD',4,0,20+len(index),len(entries),max(r[0] for r in entries))+index+payload)
 (root/'resources').mkdir(exist_ok=True)
 os.link(archive,root/'resources'/'textures.mw4')
 cat=archives.Catalog(root);row=next(r for r in cat.models() if r['name'].lower().endswith('uller.contents'))
 obj,result=game_import.import_model(cat,row,bpy.context,import_animations=False)
 assert obj['mw4_texture_count']==4 and not result['texture_import']['missing']
 assert all(a.spaces.active.shading.type=='MATERIAL' for s in bpy.data.screens for a in s.areas if a.type=='VIEW_3D')
 # Reproduce the zero-Action state with a fully textured mesh.
 assert len(animation_ui.actions_for(obj))==0
 assert obj['mw4_animation_import_enabled']==False
 bpy.context.view_layer.objects.active=obj
 assert bpy.ops.mw4.load_animations(from_installation=False)=={'FINISHED'}
 assert len(animation_ui.actions_for(obj))==160
 assert obj.animation_data.action is not None
 before={a.name:a.as_pointer() for a in animation_ui.actions_for(obj)}
 materials=[slot.material.as_pointer() for child in obj.children_recursive for slot in child.material_slots]
 for action in animation_ui.actions_for(obj):
  obj.mw4_preview_action=action
  assert obj.animation_data.action==action
  assert rig.export_action(obj)==files[action['mw4_archive_member']]
 # Recover a missing/deleted Action via installation while preserving other Actions/materials.
 victim=animation_ui.actions_for(obj)[0];victim_name=victim.name
 bpy.data.actions.remove(victim)
 assert bpy.ops.mw4.load_animations(from_installation=True,directory=str(root))=={'FINISHED'}
 assert len(animation_ui.actions_for(obj))==160
 assert all(a.as_pointer()==before[a.name] for a in animation_ui.actions_for(obj) if a.name!=victim_name)
 assert materials==[slot.material.as_pointer() for child in obj.children_recursive for slot in child.material_slots]
 assert bpy.ops.mw4.copy_diagnostics()=={'FINISHED'}
 diagnostics=json.loads(bpy.data.texts[obj['mw4_diagnostics']].as_string())
 assert diagnostics['animation_recovery']['imported']==1
 assert diagnostics['animation_recovery']['existing']==159
 assert diagnostics['compatible_actions']==160
 # Repeating recovery does not overwrite edits or duplicate Actions.
 assert bpy.ops.mw4.load_animations(from_installation=False)=={'FINISHED'}
 assert len(animation_ui.actions_for(obj))==160
 # Invalid clips produce a per-file error and retain the previous active clip.
 previous=obj.animation_data.action
 failure=animation_ui.recover_actions(obj,{'broken.mw4anim':b'broken'},bpy.context)
 assert len(failure['errors'])==1 and obj.animation_data.action==previous
 result={'blender':bpy.app.version_string,'zero_action_state_recovered_from_bundle':True,
 'missing_action_recovered_from_installation':True,'existing_actions_and_materials_preserved':True,
 'all_160_actions_switched_and_native_exports_verified':True,'recovery_repeat_no_duplicates':True,
 'invalid_clip_error_recorded_and_active_action_preserved':True,
 'diagnostics_include_collection_and_import_details':True}
 out.write_text(json.dumps(result,indent=2));print(json.dumps(result))
addon.unregister()
