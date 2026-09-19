"""Legacy/wrapped bundle compatibility, large payload timing, save/reopen."""
import base64,json,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
from io_scene_mw4anim import embedded
raw=bytes(range(256))*24000
assert embedded.decode(base64.b64encode(raw).decode())==raw
wrapped=embedded.encode(raw)
assert max(map(len,wrapped.splitlines()))==76
assert embedded.decode(wrapped.replace('\n','\r\n'))==raw
try:embedded.decode(wrapped+'!')
except ValueError:pass
else:raise AssertionError('Invalid base64 accepted')
text=bpy.data.texts.new('large test bundle');text.use_fake_user=True
start=time.perf_counter();text.from_string(wrapped);elapsed=time.perf_counter()-start
assert embedded.decode(text.as_string())==raw
with tempfile.TemporaryDirectory() as td:
 path=Path(td)/'packed.blend';name=text.name
 bpy.ops.wm.save_as_mainfile(filepath=str(path));bpy.ops.wm.open_mainfile(filepath=str(path))
 assert embedded.decode(bpy.data.texts[name].as_string())==raw
result={'blender':bpy.app.version_string,'binary_bytes':len(raw),'encoded_bytes':len(wrapped),'text_write_seconds':elapsed,'legacy_and_wrapped_roundtrip':True,'save_reopen':True,'invalid_characters_rejected':True}
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
if args:Path(args[0]).write_text(json.dumps(result,indent=2))
print(json.dumps(result))
