"""Template-preserving ERF14/MLR18 mech-part writer.

The supplied Pascal TMW4LOD.Save/TMW4Mesh.Save confirm lengths, byte indices,
plane arrays and normals. CalcPlaneEQ uses dot(normal, vertex) = distance.
"""
import math
import struct
from . import erf
from .codec import FormatError


def floats(rows, width):
    if any(len(row) != width or not all(math.isfinite(x) for x in row) for row in rows):
        raise FormatError('Invalid/nonfinite ERF vertex attribute')
    try: return struct.pack('<I', len(rows))+b''.join(struct.pack('<'+'f'*width,*row) for row in rows)
    except (struct.error, OverflowError) as exc: raise FormatError('ERF float overflow') from exc


def planes(vertices, triangles):
    result=[]
    for tri in triangles:
        a,b,c=(vertices[i] for i in tri)
        u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
        n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        length=math.sqrt(sum(x*x for x in n))
        if length<=1e-12: raise FormatError('Degenerate triangle; remove zero-area faces before ERF export')
        n=[x/length for x in n];result.append((*n,sum(n[i]*a[i] for i in range(3))))
    return result


def primitive(mesh, template):
    verts=mesh['vertices'];triangles=mesh['triangles']
    if not 1<=len(verts)<=256: raise FormatError('ERF primitive must have 1..256 vertices')
    if any(len(t)!=3 or any(not isinstance(i,int) or not 0<=i<len(verts) for i in t) for t in triangles):
        raise FormatError('Invalid ERF triangle indices')
    if not triangles: raise FormatError('Empty geometry is not a replacement ERF primitive')
    uv=mesh.get('uv',[]);normals=mesh.get('normals',[]);colors=mesh.get('colors',[])
    if any(len(a) not in (0,len(verts)) for a in (uv,normals,colors)):
        raise FormatError('ERF vertex attribute count mismatch')
    if any(not isinstance(c,int) or not 0<=c<=0xffffffff for c in colors):raise FormatError('Invalid packed vertex color')
    # Exact original material state, texture spelling and trailing flags retained.
    return (struct.pack('<I',0x66)+floats(verts,3)+floats(uv,2)+template['material_raw']+
        struct.pack('<I',len(triangles)*3)+bytes(i for t in triangles for i in t)+
        floats(planes(verts,triangles),4)+struct.pack('<I',len(colors))+
        b''.join(struct.pack('<I',c) for c in colors)+floats(normals,3))


def replace_lod0(data, replacements):
    """Map original primitive index to one or more replacement primitives.

    Unchanged primitives and all other LOD records remain byte-identical.
    Empty replacement map is an exact byte pass-through.
    """
    source=erf.loads(data)
    if not replacements:return bytes(data)
    if source['flags']&0x20:
        raise FormatError('Edited ERF with oriented bounding box is not supported yet; sphere-bounded parts only')
    originals=source['lods'][0]['meshes']
    if any(not isinstance(i,int) or not 0<=i<len(originals) for i in replacements):raise FormatError('Unknown primitive index')
    raw=[];edited=[]
    for i,template in enumerate(originals):
        if i in replacements:
            if not replacements[i]:raise FormatError('Cannot delete an entire source primitive')
            for mesh in replacements[i]:raw.append(primitive(mesh,template));edited.append(mesh)
        else:raw.append(template['raw']);edited.append(template)
    if len(raw)>255:raise FormatError('LOD exceeds 255 mesh primitives after vertex splitting')
    shape=struct.pack('<IB',0x4b,len(raw))+b''.join(raw)
    lod=(struct.pack('<2f',*source['lods'][0]['distance']) if source['kind']==0x90 else b'')+struct.pack('<I',len(shape))+shape
    vertices=[v for mesh in edited for v in mesh['vertices']]
    vertices += [v for l in source['lods'][1:] for mesh in l['meshes'] for v in mesh['vertices']]
    if not vertices:raise FormatError('Cannot calculate empty ERF bounds')
    # Sphere is local to the ERF. Original element matrix remains unchanged.
    center=[(min(v[i] for v in vertices)+max(v[i] for v in vertices))/2 for i in range(3)]
    # Round center first and pad radius to remain conservative after float32 encoding.
    center=struct.unpack('<3f',struct.pack('<3f',*center))
    radius=max(math.sqrt(sum((v[i]-center[i])**2 for i in range(3))) for v in vertices)
    radius=radius*(1+1e-6)+1e-6
    header=bytearray(source['prefix']);struct.pack_into('<4f',header,source['bounds_offset'],*center,radius)
    result=bytes(header)+lod+b''.join(l['raw'] for l in source['lods'][1:])
    erf.loads(result)
    return result
