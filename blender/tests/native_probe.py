"""Read-only Unicorn probes of ORIGINAL instructions, not a Windows game launch.

Requires unicorn. Arguments: unpacked image.bin, sample ZIP, output JSON.
Image produced by the repository's SHA-guarded scripts/unpack.py.
No original game bytes are shipped with this add-on.
"""
import importlib.util
import json
from pathlib import Path
import struct
import sys
import zipfile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EIP, UC_X86_REG_ECX, UC_X86_REG_EAX

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('codec',root/'io_scene_mw4anim/codec.py')
codec = importlib.util.module_from_spec(spec);sys.modules[spec.name] = codec;spec.loader.exec_module(codec)
image = Path(sys.argv[1]).read_bytes()
u = Uc(UC_ARCH_X86,UC_MODE_32)
u.mem_map(0x400000,(len(image)+4095)&~4095);u.mem_write(0x400000,image)
u.mem_map(0x2000000,0x100000)
STOP, STACK = 0x2000000,0x20ff000
BUFFER, STREAM, DATA, ITER, INDEX, INSTANCE, MAPPING = (
    0x2010000,0x2020000,0x2021000,0x2022000,0x2023000,0x2024000,0x2025000)

def put(a,v):u.mem_write(a,struct.pack('<I',v))
def get(a):return struct.unpack('<I',u.mem_read(a,4))[0]
def call(addr,self,args=()):
    u.reg_write(UC_X86_REG_ESP,STACK)
    u.reg_write(UC_X86_REG_ECX,self)
    u.mem_write(STACK,struct.pack('<'+'I'*(1+len(args)),STOP,*args))
    u.emu_start(addr,STOP,count=1000000)
    assert u.reg_read(UC_X86_REG_EIP) == STOP,hex(addr)
    return u.reg_read(UC_X86_REG_EAX)

z = zipfile.ZipFile(sys.argv[2])
counts = {'original_files':0,'rebuilt_files':0,'edited_files':0,'key_pointer_checks':0}
for name in z.namelist():
    if not name.endswith('.mw4anim'):continue
    original = z.read(name)
    clip = codec.loads(original)
    changed = list(clip.tracks[0].values)
    row = list(changed[0]);row[0] += 0.125;changed[0] = row
    edited = codec.dumps(clip,{0:(clip.tracks[0].times,changed)})
    for label,b in [('original_files',original),('rebuilt_files',codec.dumps(clip,force_rebuild=True)),('edited_files',edited)]:
        u.mem_write(BUFFER,b)
        call(0x421fc0,STREAM,[BUFFER,len(b),0])
        call(0x6801c0,DATA)
        assert call(0x6802e0,DATA,[STREAM]) & 255 == 1
        offsets = struct.unpack_from('<5I',b,25)
        assert [get(DATA+i) for i in (12,20,28,36,44)] == [BUFFER+1+off for off in offsets]
        assert get(STREAM+0x14) == BUFFER+len(b)
        counts[label] += 1
    # Check the native binary-search iterator and both key/time pointer accessors.
    put(ITER+0x18,DATA);put(ITER+0x1c,INDEX);put(ITER+0x28,INSTANCE)
    put(INSTANCE+0x14,MAPPING)
    for i in range(len(clip.channels)):put(MAPPING+i*4,i)
    for sec in (0,(clip.end-clip.start)*0.37,clip.end-clip.start):
        call(0x6a79c0,ITER,[struct.unpack('<I',struct.pack('<f',sec))[0]])
        t = sec+clip.start
        for i,tr in enumerate(clip.tracks):
            idx = bytes(u.mem_read(INDEX+i,1))[0]
            if t <= clip.start:expected = 0
            elif t >= clip.end:expected = len(tr.times)-1
            else:expected = next((j for j,kt in enumerate(tr.times) if kt > t),255)
            assert idx == expected,(name,i,t,idx,expected)
            desc = get(DATA+44)+16*i
            stride,voff,toff = struct.unpack('<III',u.mem_read(desc,12))
            nxt = 0 if idx == 255 else get(DATA+28)+voff+idx*stride
            prev_idx = len(tr.times)-1 if idx == 255 else idx-1
            prev = 0 if idx == 0 else get(DATA+28)+voff+prev_idx*stride
            assert call(0x6a76c0,ITER,[i]) == nxt
            assert call(0x6a7700,ITER,[i]) == prev
            assert call(0x6a77d0,ITER,[i]) == (0 if idx == 255 else get(DATA+36)+toff+idx*4)
            assert call(0x6a7810,ITER,[i]) == (0 if idx == 0 else get(DATA+36)+toff+prev_idx*4)
            counts['key_pointer_checks'] += 4

result = {'passed':True,'counts':counts,
          'original_addresses':['00421fc0','006801c0','006802e0','006a79c0',
                                '006a76c0','006a7700','006a77d0','006a7810'],
          'scope':'Original loader, time seek and key/time addresses under synthetic memory; no renderer, resource archive or live gameplay.',
          'edited_case':'First scalar of first track +0.125 in each file; all other data retained.'}
Path(sys.argv[3]).write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
