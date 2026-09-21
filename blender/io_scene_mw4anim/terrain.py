"""Read-only ERF14 world grids and MLR18 Terrain2 meshes (class 0x68).

Terrain vertices use native world coordinates; element bounds are not transforms.
See docs/MAP_IMPORT.md for source evidence and deliberately unsupported features.
"""
import hashlib
import math
import re
import struct
from pathlib import PurePosixPath
from . import archives, erf
from .codec import FormatError

IDENTITY = (1,0,0,0,0,1,0,0,0,0,1,0)


def unpack(r, fmt):
    return struct.unpack('<'+fmt, r.take(struct.calcsize('<'+fmt)))


def mlr(r):
    if r.take(4) != b'#RLM' or r.u32() != 18:
        raise FormatError('Expected terrain MLR version 18')


def state(r):
    fields = unpack(r, '6I')
    texture = ''
    if fields[0] & 0x3fff:
        size = r.u32()
        if size > 4096: raise FormatError('Excessive terrain texture name')
        raw = r.take(size+1)
        if raw[-1] != 0: raise FormatError('Unterminated terrain texture name')
        texture = raw[:-1].decode('cp1252')
        r.take(4)
    return texture


def grid(data):
    r = erf.Reader(data)
    if unpack(r, '4sIII') != (b'#FRE',14,0x8c,5):
        raise FormatError('Unsupported map grid: expected ERF14 class 0x8c, flags 5')
    r.take(16)
    reserved, nz, nx = unpack(r, 'HBB')
    sz, sx, oz, ox = unpack(r, '4f')
    if reserved or not nx or not nz or nx*nz > 4096 or r.p != len(data):
        raise FormatError('Invalid map grid dimensions or trailing data')
    if not all(math.isfinite(v) for v in (sz,sx,oz,ox)) or min(sz,sx) <= 0:
        raise FormatError('Invalid map grid extents')
    return dict(columns=nx, rows=nz, cell_size=[sx,sz], origin=[ox,oz])


def primitive(r):
    vertices = r.array(3)
    stored_uv = r.array(2)
    mode = r.take(1)[0]
    texture = state(r)
    count = r.u32()
    indices = list(r.take(count))
    if count % 3 or any(i >= len(vertices) for i in indices):
        raise FormatError('Invalid terrain triangle indices')
    planes = r.array(4)
    if len(planes) != count//3 or len(stored_uv) not in (0,len(vertices)):
        raise FormatError('Terrain attribute count mismatch')
    detail = state(r)
    detail_params = unpack(r, '6f')
    cell = unpack(r, '4B')
    bounds = [unpack(r, '4f') for _ in range(8)]
    reserved, available = unpack(r, 'IB')
    if any(not math.isfinite(v) for row in bounds for v in row):
        raise FormatError('Non-finite terrain texture bounds')
    match = re.search(r'_(\d)_[0-9a-fA-F]{4}$', texture)
    if not match or int(match[1]) >= 8:
        raise FormatError('Unsupported terrain texture level name: '+texture)
    level = int(match[1])
    x0,z0,x1,z1 = bounds[level]
    if x1 <= x0 or z1 <= z0: raise FormatError('Invalid terrain UV rectangle')
    # 00448b90: native U=(maxX-X)/width, V=(maxZ-Z)/depth.
    uv = [((x1-x)/(x1-x0),(z1-z)/(z1-z0)) for x,y,z in vertices]
    return dict(vertices=vertices,uv=uv,texture=texture,
                triangles=[indices[i:i+3] for i in range(0,count,3)],
                detail=detail,detail_params=detail_params,cell=cell,
                texture_level=level,available=available)


def zone(data):
    r = erf.Reader(data)
    if unpack(r, '4sI') != (b'#FRE',14): raise FormatError('Expected terrain ERF14')
    meshes, skipped = [], []
    def element(transforms=(), depth=0):
        if depth > 32: raise FormatError('Excessive terrain element nesting')
        offset = r.p
        kind, flags = unpack(r, 'II')
        if kind not in (0x83,0x84) or flags & ~0x4e7:
            raise FormatError(f'Unsupported terrain element {kind:#x}, flags {flags:#x} at {offset:#x}')
        if flags & 0x400:
            mlr(r); state(r)
        matrix = IDENTITY if flags & 1 else unpack(r, '12f')
        if not all(math.isfinite(v) for v in matrix): raise FormatError('Non-finite terrain transform')
        transforms = transforms + (matrix,)
        r.take(64 if flags & 0x20 else 16)
        if kind == 0x84:
            count, = unpack(r, 'H')
            for _ in range(count): element(transforms, depth+1)
            return
        mlr(r)
        size = r.u32()
        if size < 5: raise FormatError(f'Invalid terrain shape length {size} at {r.p-4:#x}')
        # Every shape has a byte extent, regardless of its runtime class.
        # Isolate that extent so malformed arrays cannot consume the next element.
        shape_offset = r.p
        shape = erf.Reader(r.take(size))
        shape_kind = shape.u32()
        if shape_kind != 0x4b:
            skipped.append(dict(offset=offset,shape_offset=shape_offset,
                shape_class=hex(shape_kind),bytes=size,
                class_name='MLRCulturShape' if shape_kind == 0x74 else 'Unknown shape',
                reason='Non-terrain shape omitted; original bytes retained in the resource bundle'))
            return
        count = shape.take(1)[0]
        shapes = []
        for index in range(count):
            primitive_kind = shape.u32()
            if primitive_kind != 0x68:
                skipped.append(dict(offset=offset,shape_offset=shape_offset,
                    primitive=hex(primitive_kind),primitive_index=index,
                    omitted_primitives=count-index,
                    class_name='MLR_Water' if primitive_kind == 0x67 else 'Unknown primitive',
                    reason='Unsupported primitive and remaining shape payload omitted'))
                meshes.extend(shapes)
                return
            mesh = primitive(shape); mesh['transforms'] = transforms; shapes.append(mesh)
        if shape.p != size: raise FormatError('Terrain shape length mismatch')
        meshes.extend(shapes)
    cells = 0
    while r.p < len(data):
        element(); cells += 1
        if cells > 64: raise FormatError('More than 64 cells in terrain zone')
    if cells != 64: raise FormatError(f'Expected 64 terrain cells, found {cells}')
    return dict(meshes=meshes,skipped=skipped,cells=cells)


def collect(catalog, root):
    name = archives.normalized(root['name'])
    rows = [r for r in catalog.rows if r['archive'] == root['archive']]
    def named(path):
        found = catalog.unique([r for r in rows if archives.normalized(r['name']) == path])
        if found is None: raise FormatError('Missing map resource: '+path)
        return found
    files = {}
    report = dict(schema=1,asset_mode='map_terrain',model=PurePosixPath(name).stem,
        source=catalog.describe(root),resources=[],errors=[],warnings=list(catalog.warnings),
        geometry_files=[],animation_files=[],unresolved_shapes=0,shape_references=[])
    def add(row):
        path = archives.normalized(row['name']); archives.helm.safe_parts(path)
        data, method = catalog.read(row)
        if path not in files:
            files[path] = data
            report['resources'].append(dict(catalog.describe(row),**method,
                sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)))
        return data
    info = grid(add(root))
    handles = add(named(name+'{zones}'))
    total = info['columns']*info['rows']
    if len(handles) != total*12: raise FormatError('Map zone handle count does not match grid')
    refs = list(struct.iter_unpack('<HH',handles))
    prefix = name.rsplit('/',1)[0]+'/'
    for i in range(total):
        # Three handles per zone: ERF geometry, BSP collision, material table.
        db,rid = refs[i*3]
        candidates = [r for r in rows if r['id'] == rid
            and archives.normalized(r['name']).startswith(prefix)
            and archives.normalized(r['name']).endswith('.erf') and r != root]
        row = catalog.unique(candidates)
        if row is None: raise FormatError(f'Missing terrain zone {i}: database {db}, resource {rid}')
        add(row); report['geometry_files'].append(archives.normalized(row['name']))
    if len(set(report['geometry_files'])) != total: raise FormatError('Duplicate terrain zone handles')
    report['terrain_grid'] = info
    report['scope'] = 'Terrain geometry and baked base textures only; no mission placement, vegetation, water effects or native map export.'
    report['warnings'].append(report['scope'])
    return files, report


def decode_files(files, report):
    grid(files[archives.normalized(report['source']['name'])])
    decoded = []
    for name in report['geometry_files']:
        try: decoded.append((name,zone(files[name])))
        except (ValueError, KeyError) as exc:
            raise FormatError(f'{name}: {exc}') from exc
    if not decoded or not any(z['meshes'] for n,z in decoded): raise FormatError('No supported terrain meshes')
    return decoded


def build(files, report, context, decoded=None):
    import bpy
    from mathutils import Matrix, Vector
    from . import rig
    decoded = decode_files(files,report) if decoded is None else decoded
    root = bpy.data.objects.new(report['model']+' · MW4 Terrain',None)
    context.collection.objects.link(root)
    root['mw4_map'] = True
    root.rotation_euler.x = math.pi/2
    materials = {}; triangles = 0; skipped = []
    for name, data in decoded:
        vertices, uv, faces, slots = [], [], [], []
        refs = []
        for part in data['meshes']:
            transform = Matrix.Identity(4)
            for matrix in part['transforms']: transform = transform @ rig.affine(matrix)
            start = len(vertices)
            vertices.extend(tuple(transform @ Vector(v)) for v in part['vertices'])
            uv.extend(part['uv'])
            faces.extend(tuple(start+i for i in f) for f in part['triangles'])
            ref = part['texture']
            if ref not in refs: refs.append(ref)
            slots.extend([refs.index(ref)]*len(part['triangles']))
        skipped.extend(dict(source=name,**item) for item in data['skipped'])
        if not faces: continue
        mesh = bpy.data.meshes.new(PurePosixPath(name).stem+' terrain')
        mesh.from_pydata(vertices,[],faces); mesh.update()
        layer = mesh.uv_layers.new(name='MW4 Terrain UV')
        for loop in mesh.loops:
            u,v = uv[loop.vertex_index]; layer.data[loop.index].uv = (u,1-v)
        for ref in refs:
            if ref not in materials:
                mat = bpy.data.materials.new(PurePosixPath(ref.replace('\\','/')).name)
                mat.use_nodes = True; mat['mw4_texture_reference'] = ref
                materials[ref] = mat
            mesh.materials.append(materials[ref])
        for face,index in zip(mesh.polygons,slots): face.material_index = index
        obj = bpy.data.objects.new(mesh.name,mesh); context.collection.objects.link(obj)
        obj.parent = root; obj['mw4_terrain_source'] = name
        triangles += len(faces)
    for obj in context.selected_objects: obj.select_set(False)
    root.select_set(True)
    for child in root.children: child.select_set(True)
    context.view_layer.objects.active = root
    root['mw4_mesh_count'] = len(root.children)
    report['mesh_import'] = dict(total_objects=len(root.children),triangles=triangles,errors=[],skipped=skipped)
    report['terrain_import'] = dict(zones=len(decoded),cells=sum(z['cells'] for n,z in decoded),
        triangles=triangles,skipped_shapes=skipped)
    counts = {}
    for item in skipped:
        label = item['class_name']
        counts[label] = counts.get(label,0)+1
    report['terrain_import']['omission_counts'] = counts
    summary = ', '.join(f'{count} {name}' for name,count in sorted(counts.items()))
    root['mw4_terrain_omissions'] = summary
    if skipped: report['warnings'].append('Omitted non-terrain records: '+summary+'; see terrain_import.skipped_shapes')
    report['geometry_imported'] = True
    # Maps exceed Blender's default viewport clipping distance.
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D': area.spaces.active.clip_end = max(area.spaces.active.clip_end,100000)
    return root
