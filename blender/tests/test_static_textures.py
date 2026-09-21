"""Static texture path regressions and optional external archive validation."""
import sys,struct,tempfile,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
import io_scene_mw4anim as addon
from io_scene_mw4anim import textures,archives,assets,game_import
addon.register()
def vbd(path,entries):
 records=[];payload=bytearray()
 for rid,(name,data) in enumerate(entries,1):
  nb=name.encode();records.append(struct.pack('<QIIIHB',0,len(data),len(data),len(payload),rid,len(nb))+nb);payload+=data
 index=b''.join(records);path.write_bytes(struct.pack('<4sIIIHH',b'#VBD',4,0,20+len(index),len(entries),len(entries))+index+payload)
def geometry(ref):
 nb=ref.encode()
 primitive=struct.pack('<II9fI6f',0x66,3,0,0,0,1,0,0,0,1,0,3,0,0,1,0,0,1)
 primitive+=b'\0'+struct.pack('<6I',1,0,0,0,0,0)+struct.pack('<I',len(nb))+nb+b'\0'+bytes(4)
 primitive+=struct.pack('<I',3)+bytes([0,1,2])+struct.pack('<I4fII',1,0,0,1,0,0,0)
 shape=struct.pack('<IB',0x4b,1)+primitive
 return struct.pack('<4sIII',b'#FRE',14,0x83,1)+struct.pack('<4f',0,0,0,2)+struct.pack('<4sII',b'#RLM',18,len(shape))+shape
pixel=struct.pack('<BBBHHBHHHHBB',0,0,2,0,0,0,0,0,1,1,24,0)+bytes([0,128,255])
with tempfile.TemporaryDirectory() as td:
 folder=Path(td)
 vbd(folder/'props.mw4', [('missions/desert/tower.tga',pixel),('textures/industrial/metal.tga',pixel),
   ('textures/a/duplicate.tga',pixel),('textures/b/duplicate.tga',pixel),('textures/plain.tga',pixel)])
 cat=archives.Catalog(folder);files={};report={'resources':[]}
 got=textures.collect(cat,files,report,refs=['content\\missions\\desert\\tower.tga','metal','duplicate','plain','missing','wrong/metal'])
 assert got['mapping']['content\\missions\\desert\\tower.tga']=='missions/desert/tower.tga'
 assert got['mapping']['metal']=='textures/industrial/metal.tga'
 assert got['resolutions']['metal']['method']=='unique_basename'
 assert got['mapping']['plain']=='textures/plain.tga'
 assert [e['reference'] for e in got['errors']]==['duplicate']
 assert {e['reference'] for e in got['missing']}=={'missing','wrong/metal'}
 for ref in ['content/missions/desert/tower.tga','metal','plain']:
  f,r=assets.erf_bundle('test.erf',geometry(ref));textures.collect(cat,f,r)
  obj,r=game_import.import_resource_files(f,r,bpy.context,False)
  assert obj['mw4_texture_count']==1 and not r['texture_import']['errors'],r
  node=next(n for n in obj.children[0].data.materials[0].node_tree.nodes if n.type=='TEX_IMAGE')
  assert node.image.packed_file
assert textures.texture_paths('content/missions/tower.dds')[0]=='missions/tower.dds'
result={'blender':bpy.app.version_string,'qualified_paths':True,'unique_basename':True,'ambiguous_basename_rejected':True,'explicit_directories_preserved':True,'static_material_images_packed':True,'tower_erf_tested':False}
if len(sys.argv)>1:
 cat=archives.Catalog(sys.argv[1])
 f,r=assets.erf_bundle('test.erf',geometry('bdmct1'));textures.collect(cat,f,r)
 obj,r=game_import.import_resource_files(f,r,bpy.context,False)
 assert obj['mw4_texture_count']==1 and not r['texture_import']['errors'],r
 node=next(n for n in obj.children[0].data.materials[0].node_tree.nodes if n.type=='TEX_IMAGE')
 assert node.image.packed_file and tuple(node.image.size)==(256,256)
 row=next(r for r in cat.rows if archives.normalized(r['name'])=='vehicles/jump_cradle/jump_cradle.erf')
 vehicle,r=game_import.import_model(cat,row,bpy.context,False)
 assert vehicle['mw4_texture_count']==1 and not r['texture_import']['errors']
 result.update(real_bdmct1_decoded_and_assigned=True,real_jump_cradle_textured=True)
print(json.dumps(result))
if len(sys.argv)>2:Path(sys.argv[2]).write_text(json.dumps(result,indent=2)+'\n')
addon.unregister()
