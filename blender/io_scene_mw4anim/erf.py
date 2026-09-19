"""Strict ERF14 / MLR18 reader for recovered MW4 triangle-mesh classes."""
import math
import struct
from .codec import FormatError


class Reader:
    def __init__(self,data):self.data=data;self.p=0
    def take(self,n):
        if n<0 or self.p+n>len(self.data):raise FormatError(f'Truncated ERF at {self.p:#x}, need {n} bytes')
        b=self.data[self.p:self.p+n];self.p+=n;return b
    def u32(self):return struct.unpack('<I',self.take(4))[0]
    def f32(self):return struct.unpack('<f',self.take(4))[0]
    def array(self,width):
        n=self.u32()
        if n>1000000:raise FormatError('Excessive ERF array count')
        values=list(struct.iter_unpack('<'+'f'*width,self.take(n*width*4)))
        if any(not math.isfinite(v) for row in values for v in row):raise FormatError('Non-finite ERF array')
        return values


def primitive(r):
    start=r.p
    kind=r.u32()
    if kind != 0x66:raise FormatError(f'Unsupported MLR primitive {kind:#x} at {r.p-4:#x}')
    vertices=r.array(3);uv=r.array(2);material_start=r.p;mode=r.take(1)[0]
    state=struct.unpack('<6I',r.take(24));texture=''
    if state[0]&0x3fff:
        n=r.u32()
        if n>4096:raise FormatError('Excessive texture name')
        raw=r.take(n+1)
        if raw[-1]!=0:raise FormatError('Unterminated texture name')
        texture=raw[:-1].decode('cp1252');r.take(4)
    material_raw=r.data[material_start:r.p]
    count=r.u32();indices=list(r.take(count))
    if count%3 or any(i>=len(vertices) for i in indices):raise FormatError('Invalid triangle indices')
    planes=r.array(4)
    if len(planes)!=count//3:raise FormatError('Triangle/plane count mismatch')
    colors=[];normals=[]
    if kind in (0x65,0x66):
        n=r.u32();colors=[x[0] for x in struct.iter_unpack('<I',r.take(n*4))]
    if kind==0x66:normals=r.array(3)
    if len(uv) not in (0,len(vertices)) or len(normals) not in (0,len(vertices)) or len(colors) not in (0,len(vertices)):
        raise FormatError('Vertex attribute count mismatch')
    return dict(kind=kind,vertices=vertices,uv=uv,triangles=[indices[i:i+3] for i in range(0,count,3)],
                normals=normals,colors=colors,texture=texture,mode=mode,planes=planes,
                material_raw=material_raw,raw=r.data[start:r.p])


def shape(r,size):
    end=r.p+size
    if end>len(r.data):raise FormatError('Shape extent exceeds ERF')
    if r.u32()!=0x4b:raise FormatError('Unsupported MLR shape class')
    count=r.take(1)[0]
    meshes=[primitive(r) for _ in range(count)]
    if r.p!=end:raise FormatError(f'Shape extent mismatch: {r.p:#x} != {end:#x}')
    return meshes


def loads(data):
    r=Reader(data)
    if r.take(4)!=b'#FRE' or r.u32()!=14:raise FormatError('Expected ERF version 14')
    kind=r.u32();flags=r.u32()
    if kind not in (0x90,0x83):raise FormatError(f'Unsupported ERF element {kind:#x}')
    if flags&0x400:raise FormatError('Animated ERF element transforms unsupported')
    matrix=(1,0,0,0,0,1,0,0,0,0,1,0)
    if not flags&1:matrix=struct.unpack('<12f',r.take(48))
    if not all(math.isfinite(v) for v in matrix):raise FormatError('Non-finite ERF transform')
    bounds_offset=r.p
    r.take(64 if flags&0x20 else 16)  # Oriented box + extents/radius, or sphere.
    count=struct.unpack('<H',r.take(2))[0] if kind==0x90 else 1
    if not 1<=count<=256:raise FormatError('Invalid LOD count')
    if r.take(4)!=b'#RLM' or r.u32()!=18:raise FormatError('Expected MLR version 18')
    prefix=data[:r.p]
    lods=[]
    for _ in range(count):
        lod_start=r.p
        distance=struct.unpack('<2f',r.take(8)) if kind==0x90 else (0,0)
        size=r.u32();meshes=shape(r,size)
        lods.append(dict(distance=distance,meshes=meshes,raw=data[lod_start:r.p]))
    if r.p!=len(data):raise FormatError(f'Unconsumed ERF bytes at {r.p:#x} of {len(data):#x}')
    return dict(kind=kind,matrix=matrix,lods=lods,flags=flags,
                bounds_offset=bounds_offset,prefix=prefix,original=bytes(data))
