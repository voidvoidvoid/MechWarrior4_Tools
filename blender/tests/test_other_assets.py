"""Synthetic non-mech discovery, import and native export regressions.
These fixtures exercise supported layouts; they are not real vehicle/building samples.
"""
import sys,struct,tempfile,json,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
import io_scene_mw4anim as addon
from io_scene_mw4anim import archives,assets,game_import,mesh_export,erf,animscript
addon.register()
refs=animscript.model_script_references({'aircraft/test/test.data{GameModel}':b'content/aircraft/donor/donor.animscript\0'})
assert refs[0]['path']=='content/aircraft/donor/donor.animscript'
identity=(1,0,0,0,0,1,0,0,0,0,1,0)
primitive=struct.pack('<II9fI',0x66,3,0,0,0,1,0,0,0,1,0,0)+b'\0'+bytes(24)+struct.pack('<I',3)+bytes([0,1,2])+struct.pack('<I4fII',1,0,0,1,0,0,0)
shape=struct.pack('<IB',0x4b,1)+primitive
raw=struct.pack('<4sIII',b'#FRE',14,0x83,1)+struct.pack('<4f',0,0,0,2)+struct.pack('<4sII',b'#RLM',18,len(shape))+shape

def vbd(path,entries):
 records=[];payload=bytearray()
 for rid,name,data in entries:
  nb=name.encode();records.append(struct.pack('<QIIIHB',0,len(data),len(data),len(payload),rid,len(nb))+nb);payload+=data
 index=b''.join(records);path.write_bytes(struct.pack('<4sIIIHH',b'#VBD',4,0,20+len(index),len(entries),len(entries))+index+payload)

with tempfile.TemporaryDirectory() as td:
 folder=Path(td)
 entries=[]
 for category,bone in [('buildings','Building'),('vehicles','Turret'),('aircraft','Rotor')]:
  prefix=category+'/fixture_'+category+'/';base=prefix+'fixture.contents'
  record=bytearray(280);struct.pack_into('<I',record,0,280);struct.pack_into('<12f',record,28,*identity);struct.pack_into('<HH',record,84,1,10)
  record[152:152+len(bone)]=bone.encode()
  component=bytearray(69);struct.pack_into('<II',component,0,69,0x21e);struct.pack_into('<HH',component,9,0,30);struct.pack_into('<12f',component,21,*identity)
  entries.extend([(1,base,b'\0\0'+record),(10,prefix+'body.data',struct.pack('<6H',1,11,1,20,65535,0)),(20,prefix+'body.video',struct.pack('<I',1)+component),(30,prefix+'body.erf',raw)])
 vbd(folder/'props.mw4',entries)
 cat=archives.Catalog(folder);models=cat.models()
 assert len(models)==6
 for row in models:
  obj,report=game_import.import_model(cat,row,bpy.context,False)
  assert obj and obj['mw4_mesh_count']==1,report
  output,_=mesh_export.collect_exports(obj)
  assert list(output.values())==[raw]
  child=obj.children[0];child.data.vertices[1].co.x=2;child.data.update()
  edited,_=mesh_export.collect_exports(obj)
  decoded=erf.loads(next(iter(edited.values())))
  assert max(v[0] for v in decoded['lods'][0]['meshes'][0]['vertices'])==2
  if report.get('asset_mode')=='standalone_erf':
   assert len(obj.data.bones)==1 and 'asset_root' in obj.data.bones
   assert not report['animation_import']['enabled']
 # Direct extracted ERF path, with bundle persistence and export operators.
 source=folder/'fixture.erf';source.write_bytes(raw)
 assert bpy.ops.import_scene.mw4_erf(filepath=str(source))=={'FINISHED'}
 obj=bpy.context.object
 assert mesh_export.collect_exports(obj)[0]=={'fixture.erf':raw}
 destination=folder/'output.zip'
 assert bpy.ops.export_scene.mw4_erf_package(filepath=str(destination))=={'FINISHED'}
 with zipfile.ZipFile(destination) as z:assert z.read('fixture.erf')==raw
 save=folder/'asset.blend';bpy.ops.wm.save_as_mainfile(filepath=str(save));name=obj.name
 bpy.ops.wm.open_mainfile(filepath=str(save))
 assert mesh_export.collect_exports(bpy.data.objects[name])[0]=={'fixture.erf':raw}
 before=len(bpy.data.objects)
 bad=bytearray(raw);struct.pack_into('<I',bad,8,0xdead)
 source.write_bytes(bad)
 try:result=bpy.ops.import_scene.mw4_erf(filepath=str(source))
 except RuntimeError:result={'CANCELLED'}
 assert result=={'CANCELLED'} and len(bpy.data.objects)==before
result={'blender':bpy.app.version_string,'synthetic_nonmech_hierarchies':3,'synthetic_standalone_erfs':3,'edited_geometry_roundtrip':True,'direct_import_and_zip_export':True,'save_reopen':True,'unsupported_class_rejected_before_creation':True,'real_nonmech_assets_tested':False}
print(json.dumps(result))
if len(sys.argv)>1:Path(sys.argv[-1]).write_text(json.dumps(result,indent=2)+'\n')
addon.unregister()
