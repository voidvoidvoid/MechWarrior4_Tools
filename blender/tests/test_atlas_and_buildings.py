"""External archive regression: Atlas stale size, buildings, and export integrity.
Usage: bpy-python test_atlas_and_buildings.py archive-directory report.json
Game assets remain external to the repository and installer.
"""
import sys,struct,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
import io_scene_mw4anim as addon
from io_scene_mw4anim import archives,game_import,erf,mesh_export,textures,resource_browser
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
addon.register();catalog=archives.Catalog(args[0]);models=catalog.models()
def find(name):return next(r for r in models if archives.normalized(r['name'])==name)
source=find('mechs/atlas/atl_torso.erf');raw=catalog.read(source)[0];decoded=erf.loads(raw)
assert len(decoded['lods'])==1 and len(decoded['lods'][0]['meshes'])==3
assert decoded['warnings'][0]['actual_size']-decoded['warnings'][0]['declared_size']==2
# Accept metadata inconsistency only at EOF, never truncation or trailing data.
for bad in (raw[:-1],raw+b'\0'):
 try:erf.loads(bad);raise AssertionError('Corrupted shape accepted')
 except ValueError:pass
# A stale boundary before another LOD is deliberately unsupported.
bad=bytearray(decoded['prefix']);struct.pack_into('<H',bad,32,2)
bad+=decoded['lods'][0]['raw']*2
try:erf.loads(bad);raise AssertionError('Nonterminal mismatch accepted')
except ValueError:pass
obj,r=game_import.import_model(catalog,find('mechs/atlas/atlas.contents'),bpy.context,False)
torso=[o for o in obj.children if o.get('mw4_erf_source')=='mechs/atlas/atl_torso.erf']
assert len(torso)==3 and not r['mesh_import']['errors']
assert any(o.material_slots[0].material.get('mw4_texture_reference')=='atlface1' for o in torso)
assert not r['texture_import']['missing'] and not r['texture_import']['errors']
output,_=mesh_export.collect_exports(obj)
assert output['mechs/atlas/atl_torso.erf']==raw
assert all(data==catalog.read(find(name))[0] for name,data in output.items())
# Editing corrects the size field; no-op export preserves the original bytes.
torso[0].data.vertices[0].co.x+=0.01;torso[0].data.update()
edited,_=mesh_export.collect_exports(obj)
assert not erf.loads(edited['mechs/atlas/atl_torso.erf'])['warnings']
result={'blender':bpy.app.version_string,'atlas_mesh_objects':obj['mw4_mesh_count'],
 'atlas_torso_sections':len(torso),'atlas_textures':obj['mw4_texture_count'],
 'atlas_unchanged_erfs_byte_identical':len(output),'edited_size_corrected':True,
 'truncated_trailing_and_nonterminal_mismatches_rejected':True,'buildings':{}}
for name in ['buildings/satelite_control/satelite_control.contents']:
 ob,r=game_import.import_model(catalog,find(name),bpy.context,False)
 assert ob['mw4_mesh_count']==3 and ob['mw4_texture_count']==1
 assert r['texture_import']['images']==['textures/bisat1.tga']
 result['buildings'][name]={'meshes':ob['mw4_mesh_count'],'textures':r['texture_import']['images']}
indices=resource_browser.filter_rows(models,'CONTENTS','buildings','buildings/vehicle_hangar2')
assert not indices
indices=resource_browser.filter_rows(models,'ERF','buildings','buildings/vehicle_hangar2')
assert len(indices)==2
for i in indices:
 ob,r=game_import.import_model(catalog,models[i],bpy.context,False)
 assert ob['mw4_mesh_count']>0 and ob['mw4_texture_count']>0
 assert not r['texture_import']['missing'] and not r['texture_import']['errors']
 result['buildings'][archives.normalized(models[i]['name'])]={'meshes':ob['mw4_mesh_count'],'textures':r['texture_import']['images']}
assert 'bisat1' in textures.problem_summary({'texture_import':{'missing':['bisat1']},'texture_resources':{'missing':[{'reference':'bisat1','searched':['textures/bisat1.tga']} ]}})
Path(args[1]).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
addon.unregister()
