"""Synthetic parser/lookup tests and optional privately supplied map archive tests.
Run with Blender's Python + bpy: test_terrain.py [archive_directory] [report.json].
No game data is embedded in this test or its numeric output.
"""
import io
import json
import math
import struct
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
import io_scene_mw4anim as addon
from io_scene_mw4anim import terrain,archives,game_import,textures,meshes,embedded,resource_browser
addon.register()

def packed(fmt,*values):return struct.pack('<'+fmt,*values)
def state(name=''):
    b=name.encode()
    return packed('6I',int(bool(b)),0,0,0,0,0)+(packed('I',len(b))+b+b'\0'+bytes(4) if b else b'')
def cell(kind=0x68,shape_kind=0x4b):
    body=packed('I',kind)+packed('I9fI',3,0,2,0,10,2,0,0,2,10,0)
    body+=b'\1'+state('maps/test/test_0_0000')+packed('I',3)+bytes([0,2,1])+packed('I4f',1,0,1,0,2)
    body+=state()+bytes(24)+bytes([0,0,3,3])+packed('32f',*([0,0,10,10]*8))+packed('IB',0,3)
    shape=packed('IB',shape_kind,1)+body
    child=packed('II',0x83,1)+bytes(16)+packed('4sII',b'#RLM',18,len(shape))+shape
    return packed('II',0x84,1)+bytes(16)+packed('H',1)+child
raw=packed('4sI',b'#FRE',14)+cell()*64
decoded=terrain.zone(raw)
assert len(decoded['meshes'])==64 and not decoded['skipped']
assert decoded['meshes'][0]['uv']==[(1,1),(0,1),(1,0)]
assert len(terrain.zone(packed('4sI',b'#FRE',14)+cell(0x67)*64)['skipped'])==64
# Non-mesh shapes may occur between terrain cells, with terrain still following.
for index in (0,31,63):
    mixed=raw[:8]+b''.join(cell(shape_kind=0x74) if i==index else cell() for i in range(64))
    parsed=terrain.zone(mixed)
    assert len(parsed['meshes'])==63 and len(parsed['skipped'])==1
    assert parsed['skipped'][0]['class_name']=='MLRCulturShape'
malformed=[]
for delta in (-1,1):
    bad=bytearray(raw);size=struct.unpack_from('<I',bad,66)[0]
    struct.pack_into('<I',bad,66,size+delta);malformed.append(bytes(bad))
for size in (0,4,len(raw)*2):
    bad=bytearray(raw[:8]+cell(shape_kind=0x74)+cell()*63)
    struct.pack_into('<I',bad,66,size);malformed.append(bytes(bad))
for bad in (raw[:-1],raw+b'X',raw[:8]+cell()*63,*malformed):
    try:terrain.zone(bad)
    except ValueError:pass
    else:raise AssertionError('Malformed zone accepted')
# Local archive preference is explicit; default ambiguous lookup stays strict.
class Fake:
    rows=[dict(name='textures/map.tga',archive=i) for i in (0,1)]
    unique=archives.Catalog.unique
    archives=[]
    def read(self,row):return bytes([row['archive']]),{}
    def describe(self,row):return row
cat=Fake()
assert textures.collect(cat,{},dict(resources=[]),refs=['map'])['errors']
f={};r=dict(resources=[])
assert not textures.collect(cat,f,r,refs=['map'],preferred_archive=1)['errors']
assert f['textures/map.tga']==b'\1'
result=dict(blender=bpy.app.version_string,synthetic_uv_and_structure=True,nonterrain_shapes_preserve_surrounding_terrain=True,
    malformed_shape_extents_rejected=True,
    truncated_and_trailing_data_rejected=True,explicit_archive_texture_preference=True,maps=[])
if len(sys.argv)>1:
    cat=archives.Catalog(sys.argv[1]);rows=cat.models()
    selected=[r for r in rows if r.get('map_root')]
    assert selected
    assert len(resource_browser.filter_rows(rows,'MAP'))==len(selected)
    for row in selected:
        root,report=game_import.import_model(cat,row,bpy.context)
        tx=report['texture_import']
        grid=report['terrain_grid'];expected_zones=grid['columns']*grid['rows']
        assert len(root.children)==expected_zones and len(tx['images'])==expected_zones and not tx['missing'] and not tx['errors']
        assert not report['texture_resources']['errors']
        assert textures.texture_root(root.children[0])==root and addon.clip_root(root) is None
        coordinates=[]
        bpy.context.view_layer.update()
        for child in root.children:
            assert len(child.data.uv_layers.active.data)==len(child.data.loops)
            assert all(math.isfinite(v) for uv in child.data.uv_layers.active.data for v in uv.uv)
            coordinates.extend(tuple(root.matrix_world@v.co) for v in child.data.vertices)
            for material in child.data.materials:
                assert any(n.type=='TEX_IMAGE' and n.image.packed_file for n in material.node_tree.nodes)
        bounds=[[min(v[i] for v in coordinates),max(v[i] for v in coordinates)] for i in range(3)]
        assert all(abs((bounds[i][1]-bounds[i][0])-grid['cell_size'][i]*[grid['columns'],grid['rows']][i])<0.01 for i in (0,1)),bounds
        entry=dict(map=report['model'],zones=len(root.children),triangles=report['terrain_import']['triangles'],
            packed_textures=len(tx['images']),omission_counts=report['terrain_import']['omission_counts'],skipped_shapes=len(report['terrain_import']['skipped_shapes']),bounds=bounds)
        expected={'alpine01':(9,40374,454,36),'urban01':(16,14918,0,10),
                  'urban02':(16,14918,0,10),'urban05':(16,14918,0,10)}
        if report['model'] in expected:
            zones,triangles,culture,water=expected[report['model']]
            assert (entry['zones'],entry['triangles'])==(zones,triangles),entry
            assert entry['omission_counts'].get('MLRCulturShape',0)==culture,entry
            assert entry['omission_counts'].get('MLR_Water',0)==water,entry
        result['maps'].append(entry)
        if len(result['maps'])==1:
            payload=bpy.data.texts[root['mw4_resource_bundle']]
            files,rpt=meshes.read_bundle(io.BytesIO(embedded.decode(payload.as_string())))
            other,rr=game_import.import_resource_files(files,rpt,bpy.context)
            assert rr['terrain_import']==report['terrain_import'] and len(rr['texture_import']['images'])==expected_zones
            with tempfile.TemporaryDirectory() as td:
                name=root.name;path=Path(td)/'terrain.blend'
                bpy.ops.wm.save_as_mainfile(filepath=str(path))
                bpy.ops.wm.open_mainfile(filepath=str(path))
                assert textures.texture_root(bpy.data.objects[name].children[0]).name==name
                assert all(i.packed_file for i in bpy.data.images if i.get('mw4_sha256'))
            result['bundle_reimport_and_blend_reopen']=True
        print(json.dumps(entry),flush=True)
print(json.dumps(result),flush=True)
if len(sys.argv)>2:Path(sys.argv[2]).write_text(json.dumps(result,indent=2)+'\n')
addon.unregister()
