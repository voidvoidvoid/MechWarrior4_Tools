"""Synthetic dependency/mesh regressions; optional external Solitaire core ZIP."""
import sys,struct,tempfile,zipfile,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
from io_scene_mw4anim import archives,animscript,hierarchy,meshes,rig

def vbd(path,entries):
 records=[];payload=bytearray()
 for rid,(name,data) in enumerate(entries,1):
  nb=name.encode();records.append(struct.pack('<QIIIHB',0,len(data),len(data),len(payload),rid,len(nb))+nb);payload+=data
 index=b''.join(records);path.write_bytes(struct.pack('<4sIIIHH',b'#VBD',4,0,20+len(index),len(entries),len(entries))+index+payload)

field=b'\0'*136+b'content\\mechs\\donor\\donor.animscript\0'
with tempfile.TemporaryDirectory() as td:
 root=Path(td)
 vbd(root/'core.mw4',[('mechs/recipient/recipient.contents',b'\0\0'),('mechs/recipient/recipient.data{GameModel}',field)])
 cat=archives.Catalog(root);_,report=cat.collect(cat.models()[0])
 assert report['animation_dependencies']['missing']==['content/mechs/donor/donor.animscript']
 script=b'!Walk=content\\mechs\\donor\\animation\\donor_walk\n'
 vbd(root/'props.mw4',[('mechs/donor/donor.animscript',script),('mechs/donor/animation/donor_walk.mw4anim',b'clip fixture')])
 cat=archives.Catalog(root);files,report=cat.collect(cat.models()[0])
 assert report['animation_files']==['mechs/donor/animation/donor_walk.mw4anim']
 assert not report['animation_dependencies']['missing']
 assert report['animation_dependencies']['scripts_collected']==['mechs/donor/donor.animscript']
 vbd(root/'conflict.mw4',[('mechs/donor/donor.animscript',b'different')])
 cat=archives.Catalog(root);_,report=cat.collect(cat.models()[0]);assert report['animation_dependencies']['errors']
 # Geometry fixture: one valid intact shape, one missing secondary shape.
 record=bytearray(280);struct.pack_into('<I',record,0,280)
 identity=(1,0,0,0,0,1,0,0,0,0,1,0)
 struct.pack_into('<12f',record,28,*identity);struct.pack_into('<HH',record,84,1,10)
 record[152:168]=b'joint_torsoabove';record[168]=0
 base='mechs/recipient/recipient.contents'
 data_name='mechs/recipient/torso.data';video_name='mechs/recipient/torso.video';shape_name='mechs/recipient/torso.erf'
 def component(rid):
  b=bytearray(69);struct.pack_into('<II',b,0,69,0x21e);struct.pack_into('<HH',b,9,0,rid);struct.pack_into('<12f',b,21,*identity);return b
 primitive=struct.pack('<II9fI',0x66,3,0,0,0,1,0,0,0,1,0,0)+b'\0'+bytes(24)+struct.pack('<I',3)+bytes([0,1,2])+struct.pack('<I4fII',1,0,0,1,0,0,0)
 shape=struct.pack('<IB',0x4b,1)+primitive
 erf=struct.pack('<4sIII',b'#FRE',14,0x83,1)+bytes(16)+struct.pack('<4sII',b'#RLM',18,len(shape))+shape
 files={base:b'\0\0'+record,data_name:struct.pack('<6H',1,11,1,20,65535,0),video_name:struct.pack('<I',2)+component(30)+component(31),shape_name:erf}
 report={'source':{'name':base},'resources':[{'name':data_name,'id':10},{'name':video_name,'id':20},{'name':shape_name,'id':30}]}
 hp=root/'hierarchy.zip'
 with zipfile.ZipFile(hp,'w') as z:z.writestr(base,files[base])
 obj=rig.build_armature(hp,bpy.context)
 result=meshes.attach(files,report,obj,bpy.context)
 assert result['created_objects']==1 and result['errors'][0]['resource_id']==31,result
 assert len(obj.children[0].data.polygons)==1
 # Malformed secondary ERF also cannot erase the intact part.
 files['mechs/recipient/bad.erf']=b'bad';report['resources'].append({'name':'mechs/recipient/bad.erf','id':31})
 items,errors=meshes.plans(files,report,json.loads(obj['mw4_hierarchy']))
 assert len(items)==1 and len(errors)==1
 print('Synthetic shared-script and partial-mesh regressions PASS',bpy.app.version_string)
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
if args:
 with zipfile.ZipFile(args[0]) as z:files={n.lower():z.read(n) for n in z.namelist() if not n.endswith('/')}
 refs=animscript.model_script_references(files)
 assert len(refs)==1 and refs[0]['path']=='content/mechs/cougar/cougar.animscript',refs
 assert refs[0]['offset']==136
 assert not any(n.endswith(('.mw4anim','.animscript','.erf')) for n in files)
 info=hierarchy.load_hierarchy(args[0]);assert len(info['nodes'])==39
 print('External Solitaire: 39 hierarchy nodes; Cougar script field +0x88; no clips/scripts/ERFs supplied')
