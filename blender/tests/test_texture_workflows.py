"""External Uller bundle + real textures.mw4; no game assets distributed.
Usage: bpy-python test_texture_workflows.py bundle.zip textures.mw4 output.json
"""
import sys,json,tempfile,struct,os
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
import io_scene_mw4anim as addon
from io_scene_mw4anim import meshes,archives,textures,game_import
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
 # Exercise real UI draw calls without depending on a window screenshot.
 class Layout:
  def __init__(self):self.labels=[];self.ops=[]
  def box(self):return self
  def row(self,**kw):return self
  def label(self,**kw):self.labels.append(kw.get('text',''))
  def operator(self,id,**kw):self.ops.append(id);return SimpleNamespace()
  def prop(self,*a,**kw):pass
 layout=Layout();addon.MW4ANIM_PT_tools.draw(SimpleNamespace(layout=layout),SimpleNamespace(scene=bpy.context.scene,object=None,active_object=None))
 assert textures.MW4ANIM_OT_textures.bl_idname in layout.ops
 assert addon.MW4ANIM_PT_tools.bl_category=='MW4'
 # Reproduce previously hidden reload control: rig with meshes but no bundle.
 del obj['mw4_resource_bundle'];bpy.context.view_layer.objects.active=obj.children[0]
 assert textures.MW4ANIM_OT_textures.poll(bpy.context)
 assert bpy.ops.import_scene.mw4_textures(directory=str(root))=={'FINISHED'}
 assert obj['mw4_texture_count']==4
 layout=Layout();addon.MW4ANIM_PT_tools.draw(SimpleNamespace(layout=layout),bpy.context)
 assert textures.MW4ANIM_OT_textures.bl_idname in layout.ops
 # Old texture-free resource bundle automatically uses saved installation.
 original=game_import.preferences
 game_import.preferences=lambda context:SimpleNamespace(game_directory=str(root),key_source='')
 try:assert bpy.ops.import_scene.mw4_resource_bundle(filepath=str(bundle.resolve()))=={'FINISHED'}
 finally:game_import.preferences=original
 other=bpy.context.object
 assert other!=obj and other['mw4_texture_count']==4
 result={'blender':bpy.app.version_string,'tab':'MW4','directory_import_real_textures':True,
 'legacy_bundle_saved_directory_auto_load':True,'reload_without_embedded_bundle_from_child_selection':True,
 'texture_controls_visible_without_selection_or_bundle':True,'automatic_material_preview':True,
 'texture_resources_per_mech':4,'source':'Real Uller records repacked into test VBDs; unmodified supplied textures.mw4'}
 out.write_text(json.dumps(result,indent=2));print(json.dumps(result))
addon.unregister()
