"""Export original mech ERF resources with edited base mesh geometry.

Export the datablock in rest coordinates, never evaluated animation/Armature
results. Keep archive packaging separate from this native geometry writer.
"""
import hashlib
import io
import json
import math
from pathlib import Path
import tempfile
import os
import zipfile
import bpy
from bpy_extras.io_utils import ExportHelper
from mathutils import Matrix, Vector
from . import archives, embedded, erf, erf_write, meshes, rig
from .codec import FormatError


def geometry_fingerprint(obj):
    mesh=obj.data
    uv=mesh.uv_layers.active
    record={'vertices':[list(v.co) for v in mesh.vertices],
        'faces':[(list(p.vertices),p.material_index,p.use_smooth) for p in mesh.polygons],
        'uv':[list(l.uv) for l in uv.data] if uv else [],
        'normals':[list(n.vector) for n in mesh.corner_normals],
        'matrix':[list(row) for row in (obj.matrix_parent_inverse@obj.matrix_basis)],
        'materials':[s.material.get('mw4_texture_reference','') if s.material else '' for s in obj.material_slots]}
    return hashlib.sha256(json.dumps(record,sort_keys=True).encode()).hexdigest()


def check_object(obj, root, template):
    if obj.parent!=root:raise FormatError('Export requires mesh parts parented directly to the imported rig: '+obj.name)
    for mod in obj.modifiers:
        if not (mod.show_viewport or mod.show_render):continue
        if mod.type!='ARMATURE' or mod.object!=root:
            raise FormatError('Apply non-armature modifiers before ERF export: '+obj.name)
    if obj.constraints:raise FormatError('Mesh constraints must be removed before ERF export: '+obj.name)
    if obj.data.shape_keys:raise FormatError('Shape keys are not supported by static ERF export: '+obj.name)
    bone=obj.get('mw4_bone')
    for vertex in obj.data.vertices:
        groups=[(obj.vertex_groups[g.group].name,g.weight) for g in vertex.groups if g.weight>1e-6]
        if len(groups)!=1 or groups[0][0]!=bone or abs(groups[0][1]-1)>1e-5:
            raise FormatError('Every vertex must retain weight 1 on its original rigid bone: '+obj.name)
    if len(obj.material_slots)!=1 or not obj.material_slots[0].material:
        raise FormatError('Retain one original material per imported ERF mesh part: '+obj.name)
    reference=obj.material_slots[0].material.get('mw4_texture_reference','')
    if reference!=(template['texture'] or 'Untextured'):
        raise FormatError('Changing texture references/material states is not supported by this export: '+obj.name)
    if any(p.material_index!=0 for p in obj.data.polygons):raise FormatError('Unsupported material assignment: '+obj.name)


def legacy_unchanged(obj, template, transform):
    """Check older imports against original geometry, allowing matrix float noise."""
    mesh=obj.data
    if len(mesh.vertices)!=len(template['vertices']):return False
    if [tuple(p.vertices) for p in mesh.polygons]!=[tuple(t) for t in template['triangles']]:return False
    if any(abs((obj.matrix_parent_inverse@obj.matrix_basis)[i][j]-(1 if i==j else 0))>1e-7 for i in range(4) for j in range(4)):return False
    for v,original in zip(mesh.vertices,template['vertices']):
        if (v.co-transform@Vector(original)).length>1e-5:return False
    uv=mesh.uv_layers.active
    if bool(uv)!=bool(template['uv']):return False
    for loop in mesh.loops:
        i=loop.vertex_index
        if uv:
            u,v=template['uv'][i]
            if abs(uv.data[loop.index].uv.x-u)>1e-6 or abs(uv.data[loop.index].uv.y-(1-v))>1e-6:return False
    # Blender encodes custom normals relative to its smoothing topology. Rebuild
    # the original import sequence instead of comparing against raw ERF normals.
    baseline=bpy.data.meshes.new('MW4 export comparison')
    try:
        baseline.from_pydata([transform@Vector(v) for v in template['vertices']],[],template['triangles'])
        baseline.update()
        if template['normals']:
            normal_matrix=transform.to_3x3().inverted().transposed()
            baseline.normals_split_custom_set_from_vertices([(normal_matrix@Vector(n)).normalized() for n in template['normals']])
            for polygon in baseline.polygons:polygon.use_smooth=True
        if any(a.use_smooth!=b.use_smooth for a,b in zip(mesh.polygons,baseline.polygons)):return False
        if any((a.vector-b.vector).length>1e-4 for a,b in zip(mesh.corner_normals,baseline.corner_normals)):return False
    finally:
        bpy.data.meshes.remove(baseline)
    return True


def extract_primitives(obj, template, transform):
    mesh=obj.data
    # Object placement in rig-local coordinates is baked; the rig's world
    # placement and animation pose are intentionally excluded.
    local=transform.inverted()@(obj.matrix_parent_inverse@obj.matrix_basis)
    if not all(math.isfinite(v) for row in local for v in row):raise FormatError('Nonfinite object transform')
    if local.to_3x3().determinant()<=1e-12:raise FormatError('Apply/remove mirrored or singular mesh transforms before export')
    nm=local.to_3x3().inverted().transposed()
    uv=mesh.uv_layers.active
    if template['uv'] and uv is None:raise FormatError('The original textured mesh requires a UV map: '+obj.name)
    colors=template['colors']
    if colors and len(set(colors))>1:
        raise FormatError('Editing nonuniform packed vertex colors is not supported yet: '+obj.name)
    mesh.calc_loop_triangles()
    if not mesh.loop_triangles:raise FormatError('Cannot export an empty part: '+obj.name)
    chunks=[];chunk=None;keys={}
    def fresh():return {'vertices':[],'uv':[],'normals':[],'colors':[],'triangles':[]}
    for tri in mesh.loop_triangles:
        corners=[]
        for li in tri.loops:
            loop=mesh.loops[li];v=local@mesh.vertices[loop.vertex_index].co
            normal=(nm@mesh.corner_normals[li].vector).normalized()
            tex=(uv.data[li].uv.x,1-uv.data[li].uv.y) if uv else None
            corners.append((tuple(v),tex,tuple(normal)))
        if chunk is None or len(keys)+len(set(corners)-set(keys))>256:
            chunk=fresh();chunks.append(chunk);keys={}
        indices=[]
        for key in corners:
            if key not in keys:
                keys[key]=len(keys);chunk['vertices'].append(key[0]);chunk['normals'].append(key[2])
                if uv:chunk['uv'].append(key[1])
                if colors:chunk['colors'].append(colors[0])
            indices.append(keys[key])
        chunk['triangles'].append(indices)
    return chunks


def collect_exports(root, only_source=None):
    if root is None or root.type!='ARMATURE' or 'mw4_hierarchy' not in root:
        raise FormatError('Select a mesh belonging to an imported MW4 rig')
    if bpy.context.mode!='OBJECT':raise FormatError('Switch to Object Mode before ERF export')
    text=bpy.data.texts.get(root.get('mw4_resource_bundle',''))
    if text is None:raise FormatError('ERF export requires the original embedded resource bundle')
    files,report=meshes.read_bundle(io.BytesIO(embedded.decode(text.as_string())))
    info=json.loads(root['mw4_hierarchy']);globals_={}
    for node in info['nodes']:
        world=(globals_[node['parent']]@rig.affine(node['matrix'])) if node['parent'] else rig.affine(node['matrix'])
        globals_[node['name']]=world
        from mathutils import Quaternion
        expected=world@Quaternion(node['bone_correction']).to_matrix().to_4x4()
        bone=root.data.bones.get(node['name'])
        if bone is None or any(abs(bone.matrix_local[i][j]-expected[i][j])>1e-4 for i in range(4) for j in range(4)):
            raise FormatError('Rest skeleton changed; ERF replacement export requires the original rig')
    plans,plan_errors=meshes.plans(files,report,info,include_cockpit=True)
    transforms={}
    for part in plans:
        for i,m in enumerate(part['decoded']['lods'][0]['meshes']):
            key=part['bone']+'|'+part['source']+'|'+str(i)
            transform=globals_[part['bone']]@rig.affine(part['component_matrix'])@rig.affine(part['decoded']['matrix'])
            if key in transforms and transforms[key][0]!=transform:
                raise FormatError('One source mesh has multiple component transforms; cannot map edits safely')
            transforms[key]=(transform,m)
    if any(o.type=='MESH' and 'mw4_mesh_binding' not in o for o in root.children_recursive):
        raise FormatError('New mesh objects have no ERF resource mapping; edit the existing imported parts')
    objects=[o for o in root.children_recursive if o.type=='MESH' and 'mw4_mesh_binding' in o]
    if only_source:objects=[o for o in objects if o.get('mw4_erf_source')==only_source]
    if not objects:raise FormatError('Select an imported mech with ERF meshes')
    seen=set();candidates={};changed_sources=set()
    for obj in objects:
        key=obj['mw4_mesh_binding']
        if key in seen:raise FormatError('Duplicated source mesh binding: '+obj.name)
        seen.add(key)
        if key not in transforms:raise FormatError('Cannot reconstruct source geometry mapping for '+obj.name)
        source=obj['mw4_erf_source'];index=int(key.rsplit('|',1)[1]);transform,template=transforms[key]
        check_object(obj,root,template)
        original_hash=obj.get('mw4_geometry_fingerprint')
        unchanged=(original_hash==geometry_fingerprint(obj)) if original_hash else legacy_unchanged(obj,template,transform)
        chunks=None if unchanged else extract_primitives(obj,template,transform)
        raw=template['raw'] if unchanged else b''.join(erf_write.primitive(m,template) for m in chunks)
        # Shared resources cannot represent different edits in different instances.
        ident=(source,index)
        if ident in candidates and candidates[ident][0]!=raw:raise FormatError('Conflicting edits to shared ERF resource: '+source)
        candidates[ident]=(raw,chunks)
        if not unchanged:changed_sources.add(source)
    output={};manifest={'schema':1,'format':'MW4 ERF replacement resources','resources':[],
        'notes':['Not a .mw4 archive. Replace matching original resource members using a compatible resource packer.',
                 'Only LOD0 edits are written. Other LODs, damage variants and unimported shapes retain original bytes.',
                 'Animations, textures, collision resources and hierarchy are not updated.'],
        'source_mesh_errors':plan_errors,
        'unrepresented_bindings_preserved_in_original_resources':sorted(set(transforms)-seen)}
    sources=sorted({o['mw4_erf_source'] for o in objects})
    for source in sources:
        replacements={i:chunks for (name,i),(_,chunks) in candidates.items() if name==source and chunks is not None}
        data=erf_write.replace_lod0(files[source],replacements)
        output[source]=data
        manifest['resources'].append({'path':source,'changed':source in changed_sources,'bytes':len(data),
            'source_sha256':hashlib.sha256(files[source]).hexdigest(),'export_sha256':hashlib.sha256(data).hexdigest(),
            'changed_primitive_indices':sorted(replacements)})
    return output,manifest


def atomic_write(path,data):
    path=Path(path)
    if not path.parent.is_dir():raise FormatError('Output directory does not exist')
    fd,temp=tempfile.mkstemp(prefix='.mw4-export-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


class MW4ANIM_OT_export_erfs(bpy.types.Operator,ExportHelper):
    bl_idname='export_scene.mw4_erf_package'
    bl_label='Export Asset ERF Replacements'
    filename_ext='.zip'
    filter_glob:bpy.props.StringProperty(default='*.zip',options={'HIDDEN'})
    @classmethod
    def poll(cls,context):
        from . import clip_root
        obj=clip_root(context.object)
        return obj is not None and 'mw4_hierarchy' in obj
    def execute(self,context):
        from . import clip_root
        try:
            files,manifest=collect_exports(clip_root(context.object))
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
                for name,data in sorted(files.items()):z.writestr('/'.join(archives.helm.safe_parts(name)),data)
                z.writestr('_mw4_erf_export.json',json.dumps(manifest,indent=2))
            atomic_write(self.filepath,stream.getvalue())
        except (ValueError,OSError,RuntimeError,KeyError,zipfile.BadZipFile) as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        self.report({'INFO'},f'{len(files)} native ERF resources exported; lower LODs retained. Archive installation is separate.')
        return {'FINISHED'}


class MW4ANIM_OT_export_erf(bpy.types.Operator,ExportHelper):
    bl_idname='export_scene.mw4_erf'
    bl_label='Export Selected Part ERF'
    filename_ext='.erf'
    filter_glob:bpy.props.StringProperty(default='*.erf',options={'HIDDEN'})
    @classmethod
    def poll(cls,context):return context.object is not None and bool(context.object.get('mw4_erf_source'))
    def invoke(self,context,event):
        self.filepath=Path(context.object['mw4_erf_source']).name
        return super().invoke(context,event)
    def execute(self,context):
        from . import clip_root
        try:
            source=context.object['mw4_erf_source'];files,_=collect_exports(clip_root(context.object),source)
            atomic_write(self.filepath,files[source])
        except (ValueError,OSError,RuntimeError,KeyError,zipfile.BadZipFile) as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        self.report({'INFO'},'Native ERF written for resource: '+source)
        return {'FINISHED'}


CLASSES=(MW4ANIM_OT_export_erfs,MW4ANIM_OT_export_erf)
