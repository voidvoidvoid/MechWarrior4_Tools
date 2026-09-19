"""Asset-free regression for the MekTek-reported no-AnimData crash.
Run: blender --background --python tests/test_empty_animation_import.py
"""
import sys, struct, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
import io_scene_mw4anim as addon
from io_scene_mw4anim import game_import, meshes, embedded
import io
addon.register()
record=bytearray(280)
struct.pack_into('<I',record,0,280)
struct.pack_into('<12f',record,28,1,0,0,0,0,1,0,0,0,0,1,0)
record[152:163]=b'joint_root\0'
name='mechs/test/test.contents'
for case in ('none','invalid','missing','upstream_decode_error'):
 files={name:b'\0\0'+record}
 clips=[]
 errors=[]
 if case in ('invalid','missing'):
  clips=['mechs/test/animation/test_walk.mw4anim']
  if case=='invalid':files[clips[0]]=b'not a native animation'
 if case=='upstream_decode_error':
  errors=[{'name':'mechs/test/animation/test_walk.mw4anim','error':'CRC32 mismatch: injected upstream failure'}]
 report={'source':{'name':name},'model':'test','resources':[], 'errors':errors,
  'warnings':[], 'animation_files':clips,'geometry_files':[],'unresolved_shapes':0}
 obj,result=game_import.import_resource_files(files,report,bpy.context)
 assert obj and obj.animation_data is not None and obj.animation_data.action is None
 assert result['imported_actions']==0 and result['preview_action'] is None
 assert result['animation_import']['discovered']==len(clips)
 assert len(result['animation_import']['errors'])==int(case in ('invalid','missing'))
 assert 'mw4_resource_report' in obj and 'mw4_resource_bundle' in obj
 _,saved=meshes.read_bundle(io.BytesIO(embedded.decode(bpy.data.texts[obj['mw4_resource_bundle']].as_string())))
 assert saved['errors']==result['errors']
 if case=='upstream_decode_error':assert 'CRC32 mismatch' in saved['errors'][0]['error']
 assert not any('Imported Actions remain available' in w for w in result['warnings'])
 print(case, 'PASS')
addon.unregister()
print('Blender',bpy.app.version_string,': all no-animation import regressions passed')
