"""Asset-free integration checks; run using Blender 5.1+ Python/bpy.
Usage: blender --background --python tests/test_textures.py -- results.json
"""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import zlib
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bpy
import io_scene_mw4anim as addon
from io_scene_mw4anim import archives, textures


def vbd(path, entries):
    records = []; payload = bytearray()
    for rid, (name, data) in enumerate(entries, 1):
        nb = name.encode('cp1252')
        records.append(struct.pack('<QIIIHB', 0, len(data), len(data), len(payload), rid, len(nb))+nb)
        payload.extend(data)
    index = b''.join(records); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack('<4sIIIHH', b'#VBD',4,0,20+len(index),len(entries),len(entries))+index+payload)


def tga():
    # Bottom-left red, bottom-right green, top-left blue, top-right white.
    return struct.pack('<BBBHHBHHHHBB',0,0,2,0,0,0,0,0,2,2,32,8)+bytes(
        [0,0,255,255, 0,255,0,255, 255,0,0,255, 255,255,255,255])


def png():
    def chunk(tag, data):
        return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(b'\0\xff\0\0\x80'))+chunk(b'IEND',b'')


def mesh(root, material):
    data = bpy.data.meshes.new('synthetic triangle')
    data.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
    uv = data.uv_layers.new()
    for loop, co in zip(uv.data, [(0,0),(1,0),(0,1)]): loop.uv = co
    ob = bpy.data.objects.new('synthetic',data); bpy.context.collection.objects.link(ob)
    ob.parent = root; ob['mw4_mesh_binding'] = 'fixture'; data.materials.append(material)
    return ob


addon.register()
with tempfile.TemporaryDirectory() as td:
    folder = Path(td); archive = folder/'Resources'/'textures.mw4'
    entries = [('Textures\\@fixture0.tga',tga()),
        ('content/textures/lamp.png',png()),
        ('content/textures/lamp.png{hint}',struct.pack('<I',0x20000)),
        ('content/textures/@fixture0.tga{hint}',struct.pack('<I',0x20000))]
    vbd(archive,entries); before = hashlib.sha256(archive.read_bytes()).hexdigest()
    catalog = archives.Catalog(folder); files = {}; report = {'resources':[]}
    got = textures.collect(catalog,files,report,refs=['@fixture0','lamp','absent'])
    assert got['mapping']['@fixture0']=='textures/@fixture0.tga'
    assert got['hint_mapping']['@fixture0']=='content/textures/@fixture0.tga{hint}'
    assert got['mapping']['lamp'].endswith('.png') and len(got['missing'])==1 and not got['errors']
    root=bpy.data.objects.new('fixture rig',bpy.data.armatures.new('fixture rig'))
    bpy.context.collection.objects.link(root)
    mat=bpy.data.materials.new('fixture'); mat.use_nodes=True; mat['mw4_texture_reference']='@fixture0'
    ob=mesh(root,mat)
    other=bpy.data.objects.new('other rig',None);bpy.context.collection.objects.link(other)
    untouched=mesh(other,mat)
    lampmat=bpy.data.materials.new('lamp');lampmat.use_nodes=True;lampmat['mw4_texture_reference']='lamp'
    lamp=mesh(root,lampmat)
    applied=textures.apply(files,report,root)
    assert applied['materials']==2 and not applied['missing'] and not applied['errors'], applied
    assert untouched.data.materials[0]==mat and ob.data.materials[0]!=mat
    shader=next(n for n in ob.data.materials[0].node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    assert not shader.inputs['Alpha'].is_linked # Detail mask must not make mech transparent.
    shader2=next(n for n in lamp.data.materials[0].node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    assert shader2.inputs['Alpha'].is_linked
    image=next(n.image for n in ob.data.materials[0].node_tree.nodes if n.type=='TEX_IMAGE')
    assert image.packed_file and list(image.size)==[2,2]
    assert tuple(image.pixels[:4])==(1,0,0,1), list(image.pixels[:4])
    count=len(bpy.data.images); textures.apply(files,report,root)
    assert len(bpy.data.images)==count
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==before
    blend=folder/'packed.blend';bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    archive.unlink();bpy.ops.wm.open_mainfile(filepath=str(blend))
    assert all(i.packed_file for i in bpy.data.images if i.get('mw4_sha256'))
    assert bpy.data.objects['fixture rig']['mw4_texture_count']==2
    # Explicit overrides and conflicting archive members remain deterministic.
    vbd(archive,entries);vbd(folder/'duplicate.mw4',[('content/textures/@fixture0.tga',tga()+b'conflict')])
    conflict=textures.collect(archives.Catalog(folder),{}, {'resources':[]}, refs=['@fixture0'])
    assert conflict['errors'] and not conflict['mapping']
    (folder/'duplicate.mw4').unlink()
    mapped=textures.collect(archives.Catalog(folder),{}, {'resources':[]}, refs=['@team'],overrides={'@team':'lamp'})
    assert mapped['mapping']['@team']=='content/textures/lamp.png'
addon.unregister()
result={'blender':bpy.app.version_string,'synthetic_only':True,'checks':[
    'Resources/textures.mw4 discovery; content prefix aliases, case/slash normalization, literal @ names',
    'PNG fallback, hint alpha, opaque skin detail masks',
    'packed TGA/PNG images and pixel orientation', 'material isolation across rigs',
    'image deduplication', 'save/reopen without source files', 'read-only archives',
    'missing resources, conflicting archives, explicit name overrides', 'addon registration/unregistration']}
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
if args:Path(args[0]).write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
