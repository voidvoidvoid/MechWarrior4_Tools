"""Synthetic VBD containers with real supplied Bushwacker records and clips.
Run with bpy Python: test_archives.py animations.zip hierarchy.zip results-dir
The fixture encoder is test-only and independent of the production decoder.
"""
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import zipfile
import zlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
import io_scene_mw4anim as addon
from io_scene_mw4anim import archives, helm, game_import
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
anims, assets, out=map(Path,args);out.mkdir(parents=True,exist_ok=True)


def compress(data):
    table={bytes([i]):i for i in range(256)};next_code=258
    codes=[256];word=b''
    for byte in data:
        pair=word+bytes([byte])
        if pair in table:word=pair;continue
        codes.append(table[word]);table[pair]=next_code;next_code+=1;word=bytes([byte])
        if next_code==500:
            codes.append(table[word]);word=b'';codes.append(256)
            table={bytes([i]):i for i in range(256)};next_code=258
    if word:codes.append(table[word])
    codes.append(257)
    bits=0;acc=0;result=bytearray()
    for code in codes:
        acc |= code<<bits;bits+=9
        while bits>=8:result.append(acc&255);acc>>=8;bits-=8
    if bits:result.append(acc&255)
    return bytes(result)


def wrapped(data,tag,keys):
    compressed=compress(data)
    assert helm.lzw_decode(compressed,len(data))==data
    padded=compressed+b'\0'*((-len(compressed))%8)
    p,s=helm.expand_key(keys.tables,keys.keys[tag]);enc=bytearray()
    for i in range(0,len(padded),8):
        enc.extend(struct.pack('<II',*helm.transform(p,s,*struct.unpack_from('<II',padded,i))))
    blob=tag.encode()+struct.pack('<III',len(enc),len(compressed),zlib.crc32(data)&0xffffffff)+enc
    assert len(blob)<len(data)
    return blob


def vbd(path,rows):
    records=[];payload=bytearray()
    for rid,name,plain,stored in rows:
        nb=name.encode('cp1252')
        records.append(struct.pack('<QIIIHB',0,len(plain),len(stored),len(payload),rid,len(nb))+nb)
        payload.extend(stored)
    index=b''.join(records)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(struct.pack('<4sIIIHH',b'#VBD',4,0,20+len(index),len(rows),max(r[0] for r in rows))+index+payload)


with tempfile.TemporaryDirectory() as td:
    root=Path(td);keys=archives.bundled_keys();rows=[];nextid=1000
    az=zipfile.ZipFile(anims);hz=zipfile.ZipFile(assets)
    original=az.read('bushwacker/animation/bw_walk.mw4anim')
    for n in hz.namelist():
        if n.endswith('/'):continue
        data=hz.read(n);rows.append((nextid,'mechs/'+n,data,data));nextid+=1
    for n in az.namelist():
        if not n.endswith('.mw4anim'):continue
        data=az.read(n)
        blob=wrapped(data,'mektek' if nextid%2 else 'secure',keys)
        rows.append((nextid,'mechs/'+n,data,blob));nextid+=1
    vbd(root/'Resource'/'core.mw4',rows)
    # Stand-in geometry bytes exercise retrieval only, never claimed as mesh decoding.
    geom=b'#FRE'+struct.pack('<I',14)+b'fixture geometry\0'*120
    vbd(root/'Resource'/'textures.mw4',[(i,f'mechs/bushwacker/geometry/part_{i}.erf',geom,wrapped(geom,'secure',keys)) for i in range(137,175)])
    catalog=archives.Catalog(root)
    assert len(catalog.models())==1
    model=catalog.models()[0]
    files,report=catalog.collect(model)
    assert len(report['geometry_files'])==38 and report['unresolved_shapes']==0
    assert files['mechs/bushwacker/animation/bw_walk.mw4anim']==original
    assert {r['method'] for r in report['resources']}=={'raw','mektek','secure'}
    # Wrong resource IDs in unrelated models must not bind.
    vbd(root/'Resource'/'unrelated.mw4',[(147,'mechs/other/part.erf',b'other',b'other')])
    cat2=archives.Catalog(root);assert cat2.collect(cat2.models()[0])[1]['unresolved_shapes']==0
    # Same model/id with conflicting geometry must remain unresolved.
    vbd(root/'Resource'/'conflict.mw4',[(147,'mechs/bushwacker/alternative.erf',b'different',b'different')])
    cat3=archives.Catalog(root);assert cat3.collect(cat3.models()[0])[1]['unresolved_shapes']>0
    (root/'Resource'/'conflict.mw4').unlink()
    # CRC corruption and truncated indexes must fail.
    encrypted=bytearray(wrapped(geom,'secure',keys));encrypted[14]^=1
    try:helm.decode_member(bytes(encrypted),{'decoded_size':len(geom)},keys,helm.DEFAULT_LIMIT)
    except helm.ExtractError:pass
    else:raise AssertionError('Bad CRC accepted')
    (root/'Resource'/'bad.mw4').write_bytes(b'#VBD')
    cat4=archives.Catalog(root);assert cat4.warnings
    # Legacy plain LZW extraction.
    packed=compress(geom);assert helm.decode_member(packed,{'decoded_size':len(geom)},None,helm.DEFAULT_LIMIT)[0]==geom
    bpy.ops.wm.read_factory_settings(use_empty=True);addon.register()
    obj,report=game_import.import_model(catalog,model,bpy.context)
    assert len(obj.data.bones)==41 and report['imported_actions']==154
    assert addon.rig.export_action(obj)==original
    bundle=out/'Bushwacker-Resource-Fixture.zip'
    assert bpy.ops.export_scene.mw4_resource_bundle(filepath=str(bundle.resolve()))=={'FINISHED'}
    with zipfile.ZipFile(bundle) as z:
        assert z.read('mechs/bushwacker/animation/bw_walk.mw4anim')==original
        assert len(json.loads(z.read('_mw4_resource_report.json'))['geometry_files'])==38
    blend=out/'Archive-Import-Fixture.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend.resolve()),compress=True)
    bpy.ops.wm.open_mainfile(filepath=str(blend.resolve()))
    assert bpy.ops.export_scene.mw4_resource_bundle(filepath=str(bundle.resolve()))=={'FINISHED'}
    # No source archives or persistent extracted files were written by importer.
    assert not list(root.rglob('*.mw4anim'))
    result={'blender':bpy.app.version_string,'fixture':'Synthetic VBD containers; supplied real hierarchy/154 clips; stand-in ERF payloads',
      'bones':41,'actions':154,'collected_geometry_resources':38,'walk_byte_identical':True,
      'tests':['raw/LZW/mektek/secure decoding','CRC corruption rejected','unreadable archive reported',
        'unrelated resource-ID collision ignored','ambiguous geometry reference reported',
        'resource bundle export and blend save/reopen','addon operator registration','read-only source tree'],
      'real_game_installation_tested':False,'ERF_mesh_decoding_tested':False}
    (out/'archive-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    addon.unregister()
