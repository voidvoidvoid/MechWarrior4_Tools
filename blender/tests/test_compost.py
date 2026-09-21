"""Synthetic composition checks; optional full real-map Blender import.
Usage with bpy Python: test_compost.py [archive_directory map_name result.json]
Private game resources are never distributed with this test.
"""
import sys,struct,tempfile,json,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import bpy
import io_scene_mw4anim as addon
from io_scene_mw4anim import compost,archives,game_import,textures,meshes,embedded
addon.register()

def image(kind,w,h,value):
    dtype='<u2' if kind in (1,2) else 'u1'
    data=b''.join(np.full(((h>>level)+2,(w>>level)+2),value,dtype=dtype).tobytes()
                  for level in range(3 if kind in (1,2,5) else 1))
    return compost.read_bid(data,dict(name='synthetic',kind=kind,width=w,height=h)),data
red,raw=image(1,4,4,31<<10);blue,_=image(1,4,4,31)
mask,_=image(5,4,4,128);alpha,_=image(2,4,4,0xf008)
assert tuple(red['pixels'][1,1])==(248,0,0)
assert tuple(alpha['pixels'][1,1])==(240,0,0,128)
try:compost.read_bid(raw[:-1],dict(name='bad',kind=1,width=4,height=4))
except ValueError:pass
else:raise AssertionError('Truncated BID accepted')

def feature(mode,ref,mask='',flags=0,size=(4,4)):
    return dict(mode=mode,refs=[ref,mask,'',''],flags=mode|flags,size=size,scales=(0,0))
def instance(f,x=0,y=0):return dict(feature=f,x=x,y=y,offset=(0,0))
f=dict(width=4,height=4,instances=[instance(feature(0x40,'blue')),instance(feature(0x280,'red','mask'))])
out=compost.compose(f,dict(red=red,blue=blue,mask=mask),(0,0,4,4))
assert tuple(out[0,0])==(124,0,123)
assert np.array_equal(out[1:3,1:3],compost.compose(f,dict(red=red,blue=blue,mask=mask),(1,1,2,2)))
f['instances'][1]=instance(feature(0x180,'alpha'))
assert tuple(compost.compose(f,dict(blue=blue,alpha=alpha),(0,0,4,4))[0,0])==(120,0,108)
# Mirror bits and padded scaled sampling are independent of source color tiling.
red['pixels'][1,1]=(8,16,24)
assert tuple(compost.sample_color(red,np.array([3]),np.array([0]),1)[0,0])==(8,16,24)
assert compost.sample_mask(mask,np.array([0,7]),np.array([0,7]),(1,1),0).shape==(2,2,1)
with tempfile.TemporaryDirectory() as td:
    p=Path(td)/'test.png';p.write_bytes(compost.png(out))
    img=bpy.data.images.load(str(p));assert tuple(img.size)==(4,4)
    px=np.empty(4*4*4,dtype=np.float32);img.pixels.foreach_get(px)
    assert np.max(np.abs(px.reshape(4,4,4)[::-1,:,:3]*255-out))<1
    bpy.data.images.remove(img)
# Missing composition resources must retain the existing far mapping and report why.
from types import SimpleNamespace
fake=SimpleNamespace(rows=[],unique=lambda rows,preferred:None)
report=dict(source={'name':'maps/test/test.erf'},resources=[],warnings=[],texture_resources={'mapping':{'base':'far.tga'}})
failed=compost.prepare(fake,{},report,[],None)
assert failed['status']=='fallback' and failed['errors'] and report['texture_resources']['mapping']=={'base':'far.tga'}
result=dict(blender=bpy.app.version_string,bid_formats_and_extents=True,blend_formulas=True,
    mirrors_and_scaled_masks=True,cropped_composition=True,explicit_far_fallback=True,png_decodes_correctly=True)
if len(sys.argv)>1:
    c=archives.Catalog(sys.argv[1]);model=sys.argv[2]
    row=next(r for r in c.models() if r.get('map_root') and r['name'].lower().replace('\\','/').endswith('/'+model+'.erf'))
    if model.startswith('urban'):
        root,report=game_import.import_model(c,row,bpy.context,full_terrain_textures=False)
        assert root['mw4_terrain_texture_status'].startswith('Baked far')
        before={o.name:len(o.data.vertices) for o in root.children}
        assert bpy.ops.import_scene.mw4_textures(directory=str(Path(sys.argv[1]).resolve()))=={'FINISHED'}
        report=json.loads(bpy.data.texts[root['mw4_resource_report']].as_string())
        assert before=={o.name:len(o.data.vertices) for o in root.children}
        result['reload_upgrades_existing_map']=True
    else:
        root,report=game_import.import_model(c,row,bpy.context)
    comp=report['terrain_composition'];tx=report['texture_import']
    assert comp['status']=='full' and not comp['errors'],comp
    assert not tx['missing'] and not tx['errors']
    assert all(i['width']==2048 and i['height']==2048 for i in comp['images'])
    assert len(comp['images'])==len(root.children)
    for obj in root.children:
        for mat in obj.data.materials:
            img=next(n.image for n in mat.node_tree.nodes if n.type=='TEX_IMAGE')
            assert img.packed_file and tuple(img.size)==(2048,2048)
    payload=bpy.data.texts[root['mw4_resource_bundle']]
    files,rpt=meshes.read_bundle(io.BytesIO(embedded.decode(payload.as_string())))
    assert rpt['terrain_composition']==comp
    assert all(i['path'] in files for i in comp['images'])
    # Reload the portable bundle independently of the MW4 installation.
    other,rr=game_import.import_resource_files(files,rpt,bpy.context)
    assert len(rr['texture_import']['images'])==len(comp['images'])
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'terrain.blend';name=root.name
        bpy.ops.wm.save_as_mainfile(filepath=str(path));bpy.ops.wm.open_mainfile(filepath=str(path))
        assert bpy.data.objects[name]['mw4_terrain_texture_status'].startswith('Full terrain textures')
        assert all(i.packed_file for i in bpy.data.images if i.get('mw4_sha256'))
    result.update(map=model,zones=len(comp['images']),source_bid_images=len(comp['source_images']),
        placements=comp['placements'],image_dimensions=[2048,2048],fgd_dimensions=comp['fgd_size'],
        generated_bytes=comp['generated_bytes'],packed_materials=True,bundle_and_blend_reopen=True)
print(json.dumps(result),flush=True)
if len(sys.argv)>3:Path(sys.argv[3]).write_text(json.dumps(result,indent=2)+'\n')
addon.unregister()
