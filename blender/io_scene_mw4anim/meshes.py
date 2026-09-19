"""Rigid-part binding from contents model handles -> .data -> .video -> ERF."""
import base64
import io
import json
from pathlib import Path
import struct
import zipfile
import bpy
from mathutils import Matrix,Vector
from . import archives,codec,erf,hierarchy,rig,embedded


def read_bundle(source):
    with zipfile.ZipFile(source) as z:
        total=sum(i.file_size for i in z.infolist())
        if total>archives.MAX_TOTAL:raise codec.FormatError('Resource bundle exceeds 512 MiB')
        files={}
        for item in z.infolist():
            if item.is_dir():continue
            if item.file_size>archives.helm.DEFAULT_LIMIT:raise codec.FormatError('Bundle member exceeds 64 MiB')
            name=archives.normalized(item.filename)
            archives.helm.safe_parts(name)
            if name in files:raise codec.FormatError('Duplicate bundle member: '+name)
            files[name]=z.read(item)
    raw=files.pop('_mw4_resource_report.json',None)
    if raw is None:raise codec.FormatError('Select an exported MW4 resource bundle ZIP')
    return files,json.loads(raw)


def plans(files,report,info,include_cockpit=False):
    rows=report['resources']
    def resource(rid,suffix):
        names={archives.normalized(r['name']) for r in rows if r['id']==rid and archives.normalized(r['name']).endswith(suffix)}
        if len(names)!=1:raise codec.FormatError(f'Expected one {suffix} resource with ID {rid}; found {len(names)}')
        name=next(iter(names))
        if name not in files:raise codec.FormatError('Missing resource '+name)
        return name,files[name]
    node_by_name={n['name']:n for n in info['nodes']};result=[];errors=[]
    base=archives.normalized(report['source']['name'])
    for name,data in files.items():
        match=hierarchy.PATTERN.fullmatch(name)
        if not match or match.group(1)!=base:continue
        for node in hierarchy.read_records(data,match.group(2),name):
            bone=node['name']
            if bone not in node_by_name:raise codec.FormatError('Bundle hierarchy differs from selected armature')
            if any(abs(a-b)>1e-5 for a,b in zip(node['matrix'],node_by_name[bone]['matrix'])) or node['parent']!=node_by_name[bone]['parent']:
                raise codec.FormatError('Bundle rest transforms differ from selected armature')
            p=node['record_offset'];db,rid=struct.unpack_from('<HH',data,p+84)
            # Dummy shared models are outside the model subtree and have no supplied geometry.
            if not any(r['id']==rid and archives.normalized(r['name']).endswith('.data') for r in rows):continue
            if bone=='joint_cage' and not include_cockpit:continue
            try:
                data_name,model=resource(rid,'.data')
                if len(model)!=12:raise codec.FormatError('Unsupported model link layout: '+data_name)
                element_name=data_name+'{element}'
                element=files.get(element_name)
                if element is not None:
                    if len(element)<52:raise codec.FormatError('Truncated model element')
                    em=struct.unpack_from('<12f',element,4)
                    identity=(1,0,0,0,0,1,0,0,0,0,1,0)
                    if any(abs(a-b)>1e-5 for a,b in zip(em,identity)):
                        raise codec.FormatError('Nonidentity model-element transform is not supported yet')
                vdb,vid=struct.unpack_from('<HH',model,4)
                video_name,video=resource(vid,'.video');p=4;seen=set();node_parts=[]
                if len(video)<4:raise codec.FormatError('Truncated video')
                for _ in range(struct.unpack_from('<I',video)[0]):
                    if p+8>len(video):raise codec.FormatError('Truncated component')
                    size,kind=struct.unpack_from('<II',video,p)
                    if size<8 or p+size>len(video):raise codec.FormatError('Invalid component length')
                    if kind==0x220:
                        if size<64:raise codec.FormatError('Truncated group component')
                        gm=struct.unpack_from('<12f',video,p+16)
                        identity=(1,0,0,0,0,1,0,0,0,0,1,0)
                        if any(abs(a-b)>1e-5 for a,b in zip(gm,identity)):
                            raise codec.FormatError('Nonidentity video-group transform is not supported yet')
                    if kind==0x21e:
                        if size<69:raise codec.FormatError('Truncated shape component')
                        edb,eid=struct.unpack_from('<HH',video,p+9)
                        ename,edata=resource(eid,'.erf')
                        transform=tuple(struct.unpack_from('<12f',video,p+21))
                        if '_dam.' not in ename and (ename,transform) not in seen:
                            decoded=erf.loads(edata)
                            node_parts.append(dict(bone=bone,source=ename,component_matrix=transform,decoded=decoded))
                            seen.add((ename,transform))
                    p+=size
                result.extend(node_parts)
            except (ValueError,struct.error) as exc:errors.append({'bone':bone,'error':str(exc)})
    return result,errors


def attach(files,report,obj,context,include_cockpit=False):
    if obj.type!='ARMATURE' or 'mw4_hierarchy' not in obj:raise codec.FormatError('Select an imported MW4 armature')
    info=json.loads(obj['mw4_hierarchy'])
    items,errors=plans(files,report,info,include_cockpit)
    globals_={}
    for node in info['nodes']:
        local=rig.affine(node['matrix'])
        globals_[node['name']]=globals_[node['parent']]@local if node['parent'] else local
    existing={o.get('mw4_mesh_binding') for o in obj.children if 'mw4_mesh_binding' in o}
    created=[];skipped=0
    for part in items:
        transform=globals_[part['bone']]@rig.affine(part['component_matrix'])@rig.affine(part['decoded']['matrix'])
        for i,m in enumerate(part['decoded']['lods'][0]['meshes']):
            key=part['bone']+'|'+part['source']+'|'+str(i)
            if key in existing:skipped+=1;continue
            vertices=[transform@Vector(v) for v in m['vertices']]
            mesh=bpy.data.meshes.new(Path(part['source']).stem+f' · {i}')
            mesh.from_pydata(vertices,[],m['triangles']);mesh.update()
            if m['uv']:
                uv=mesh.uv_layers.new(name='MW4 UV')
                for loop in mesh.loops:
                    u,v=m['uv'][loop.vertex_index];uv.data[loop.index].uv=(u,1-v)
            if m['normals']:
                normal_matrix=transform.to_3x3().inverted().transposed()
                normals=[(normal_matrix@Vector(n)).normalized() for n in m['normals']]
                mesh.normals_split_custom_set_from_vertices(normals)
                for polygon in mesh.polygons:polygon.use_smooth=True
            texture=m['texture'] or 'Untextured'
            mat=bpy.data.materials.get('MW4 · '+texture)
            if mat is None:
                mat=bpy.data.materials.new('MW4 · '+texture)
                color=(.28,.32,.3,1)
                if texture=='RunningLight':color=(.9,.32,.04,1)
                mat.diffuse_color=color;mat.use_nodes=True
                bsdf=mat.node_tree.nodes.get('Principled BSDF')
                bsdf.inputs['Base Color'].default_value=color
                bsdf.inputs['Roughness'].default_value=.65
                mat['mw4_texture_reference']=texture
                mat['mw4_texture_image_missing']=True
            mesh.materials.append(mat)
            child=bpy.data.objects.new(mesh.name,mesh);context.collection.objects.link(child)
            child.parent=obj;child.matrix_parent_inverse=Matrix.Identity(4);child.matrix_basis=Matrix.Identity(4)
            group=child.vertex_groups.new(name=part['bone']);group.add(list(range(len(vertices))),1,'REPLACE')
            modifier=child.modifiers.new('MW4 rigid joint','ARMATURE');modifier.object=obj
            child['mw4_mesh_binding']=key;child['mw4_erf_source']=part['source'];child['mw4_bone']=part['bone']
            child['mw4_lod']=0;child['mw4_lod_count']=len(part['decoded']['lods'])
            created.append(child);existing.add(key)
    obj['mw4_mesh_count']=sum(o.type=='MESH' and 'mw4_mesh_binding' in o for o in obj.children)
    obj['mw4_rig_note']='Recovered hierarchy with rigid ERF parts; highest-detail intact geometry.'
    report['geometry_imported']=bool(obj['mw4_mesh_count'])
    report['mesh_import']={'created_objects':len(created),'existing_objects_skipped':skipped,
        'total_objects':obj['mw4_mesh_count'],'errors':errors,'lod':0,'damage_variants':False,
        'textures':'UVs and names preserved; neutral preview materials, image files unavailable'}
    return report['mesh_import']


class MW4ANIM_OT_attach_meshes(bpy.types.Operator):
    bl_idname='import_scene.mw4_attach_meshes'
    bl_label='Add Meshes from Collected Resources'
    bl_options={'REGISTER','UNDO'}
    include_cockpit:bpy.props.BoolProperty(name='Include cockpit cage',default=False)
    @classmethod
    def poll(cls,context):
        return context.object is not None and context.object.type=='ARMATURE' and 'mw4_resource_bundle' in context.object
    def execute(self,context):
        obj=context.object
        try:
            text=bpy.data.texts.get(obj['mw4_resource_bundle'])
            if text is None:raise codec.FormatError('Missing embedded resource bundle')
            files,report=read_bundle(io.BytesIO(embedded.decode(text.as_string())))
            result=attach(files,report,obj,context,self.include_cockpit)
            from . import textures
            textures.apply(files,report,obj)
            rpt=bpy.data.texts.get(obj.get('mw4_resource_report',''))
            if rpt:rpt.clear();rpt.write(json.dumps(report,indent=2))
            packed=io.BytesIO();archives.write_bundle(packed,files,report)
            text.from_string(embedded.encode(packed.getvalue()))
        except (ValueError,OSError,KeyError,struct.error,zipfile.BadZipFile) as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        self.report({'WARNING'} if result['errors'] else {'INFO'},
            f"{result['created_objects']} mesh objects added; {result['existing_objects_skipped']} already present; {len(result['errors'])} errors")
        return {'FINISHED'}


class MW4ANIM_OT_bundle_import(bpy.types.Operator):
    bl_idname='import_scene.mw4_resource_bundle'
    bl_label='Import MW4 Resource Bundle'
    bl_options={'REGISTER','UNDO'}
    filepath:bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob:bpy.props.StringProperty(default='*.zip',options={'HIDDEN'})
    def invoke(self,context,event):context.window_manager.fileselect_add(self);return {'RUNNING_MODAL'}
    def execute(self,context):
        from . import game_import, textures
        try:
            files,report=read_bundle(self.filepath)
            prefs = game_import.preferences(context)
            directory = prefs.game_directory if prefs else ''
            if directory:
                try:
                    catalog = archives.Catalog(bpy.path.abspath(directory),
                        bpy.path.abspath(prefs.key_source) if prefs.key_source else '')
                    textures.collect(catalog, files, report)
                except (OSError, ValueError, RuntimeError) as exc:
                    report.setdefault('warnings', []).append('Texture lookup: ' + str(exc))
            obj,report=game_import.import_resource_files(files,report,context, game_directory=directory)
        except (ValueError,OSError,KeyError,zipfile.BadZipFile) as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        result=report.get('mesh_import',{})
        tx = report.get('texture_import', {})
        problem = report['errors'] or tx.get('missing') or tx.get('errors') or report.get('warnings')
        self.report({'WARNING'} if problem else {'INFO'},
            f"{report['imported_actions']} Actions; {result.get('total_objects',0)} mesh objects; "
            f"{len(tx.get('images', []))} textures; {len(tx.get('missing', []))} missing textures; {len(report['errors'])} errors")
        return {'FINISHED'}

CLASSES=(MW4ANIM_OT_attach_meshes,MW4ANIM_OT_bundle_import)
