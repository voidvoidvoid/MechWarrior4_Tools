"""Armature binding using recovered parent-local matrices and bone-axis correction."""
import base64
import hashlib
import json
import math
import uuid
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector
from . import codec, hierarchy

def affine(values):
    return Matrix((values[0:4],values[4:8],values[8:12],(0,0,0,1)))

def curve_fingerprint(curves):
    rows = []
    for fc in sorted(curves,key=lambda fc:(fc.data_path,fc.array_index)):
        rows.append([fc.data_path,fc.array_index,fc.mute,fc.extrapolation,
            [(tuple(k.co),k.interpolation,tuple(k.handle_left),tuple(k.handle_right),
              k.handle_left_type,k.handle_right_type,k.easing,k.back,k.amplitude,k.period)
             for k in fc.keyframe_points], [m.type for m in fc.modifiers]])
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()

def build_armature(filepath,context):
    return build_from_info(hierarchy.load_hierarchy(filepath), context)

def build_from_info(info, context):
    data = bpy.data.armatures.new(info['name']+' · MW4 Skeleton')
    obj = bpy.data.objects.new(info['name']+' · MW4 Rig',data)
    context.collection.objects.link(obj)
    if context.object and context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for selected in context.selected_objects:
        selected.select_set(False)
    obj.select_set(True);context.view_layer.objects.active=obj
    obj['mw4_rig_id'] = uuid.uuid4().hex
    obj.show_in_front = True
    obj.rotation_euler.x = math.pi/2  # Native Y-up to Blender Z-up, outside rig data.
    data.display_type = 'STICK'
    bpy.ops.object.mode_set(mode='EDIT')
    globals_ = {}
    for node in info['nodes']:
        local = affine(node['matrix'])
        world = globals_[node['parent']] @ local if node['parent'] else local
        globals_[node['name']] = world
        bone = data.edit_bones.new(node['name'])
        if node['parent']:
            bone.parent = data.edit_bones[node['parent']]
        bone.head = world.translation
        children = [n for n in info['nodes'] if n['parent'] == node['name']]
        directions = [affine(n['matrix']).translation for n in children]
        nonzero = [v for v in directions if v.length > 0.02]
        # Bone tails are display axes, not additional recovered pivots.
        direction = max(nonzero,key=lambda v:v.length) if nonzero else Vector((0,0.22,0))
        bone.tail = bone.head + world.to_3x3() @ direction
        bone.use_connect = False
    bpy.ops.object.mode_set(mode='OBJECT')
    for node in info['nodes']:
        correction = globals_[node['name']].inverted() @ data.bones[node['name']].matrix_local
        node['bone_correction'] = list(correction.to_quaternion())
        obj.pose.bones[node['name']].rotation_mode = 'QUATERNION'
    obj['mw4_hierarchy'] = json.dumps(info,separators=(',',':'))
    obj['mw4_rig_note'] = 'Recovered joint pivots/hierarchy. Bone tails are display choices; meshes absent.'
    return obj

def _node_transforms(node):
    rest = affine(node['matrix'])
    return rest.translation,rest.to_quaternion(),Quaternion(node['bone_correction'])

def import_action(filepath,context,obj,fps=30.0):
    from . import curves_for
    info = json.loads(obj['mw4_hierarchy'])
    nodes = {n['name']:n for n in info['nodes']}
    clip = codec.loads(Path(filepath).read_bytes())
    if context.object and context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    obj.animation_data_create()
    if obj.animation_data.action:
        obj.animation_data.action.use_fake_user = True
    obj.animation_data.action = None
    # Clear pose residue from the previously active action, including unkeyed bones.
    for pb in obj.pose.bones:
        pb.location = (0,0,0);pb.rotation_mode='QUATERNION'
        pb.rotation_quaternion=(1,0,0,0);pb.scale=(1,1,1)
    meta = {'schema':2,'mode':'armature','source':base64.b64encode(clip.original).decode(),
            'fps':fps,'nodes':nodes,'bindings':[],'unbound_names':[],
            'hierarchy_fingerprint':rig_fingerprint(obj)}
    for i,tr in enumerate(clip.tracks):
        name = clip.channels[tr.channel].name
        bound = name in nodes and tr.kind in (1,2)
        if name not in nodes:
            meta['unbound_names'].append(name)
        if bound:
            pb = obj.pose.bones[name]
            path = pb.path_from_id('location' if tr.kind==1 else 'rotation_quaternion')
            t0,q0,qc = _node_transforms(nodes[name])
            width = 3 if tr.kind==1 else 4
        else:
            prop = f'mw4_track_{i}'
            path = f'["{prop}"]'
            width = 4 if tr.kind==3 else tr.stride//4
        binding = {'path':path,'width':width,'bound':bound,'node':name,'track':i}
        for t,row in zip(tr.times,tr.values):
            if bound:
                if tr.kind==1:
                    values = (q0 @ qc).inverted() @ (Vector(row)-t0)
                    pb.location = values
                else:
                    q = Quaternion((row[3],row[0],row[1],row[2]))
                    pb.rotation_quaternion = qc.inverted() @ q0.inverted() @ q @ qc
            else:
                values = [(row[0]>>(8*j))&255 for j in range(4)] if tr.kind==3 else row
                obj[prop] = list(values)
            obj.keyframe_insert(data_path=path,frame=1+(t-clip.start)*fps,group=name)
        meta['bindings'].append(binding)
    for binding,tr in zip(meta['bindings'],clip.tracks):
        fcs = [fc for fc in curves_for(obj) if fc.data_path==binding['path']]
        for fc in fcs:
            for k in fc.keyframe_points:
                k.interpolation = 'CONSTANT' if tr.kind==3 or (
                    tr.kind==0 and fc.array_index>=3) or (
                    tr.kind==4 and fc.array_index>=4) else 'LINEAR'
            fc.update()
        binding['fingerprint'] = curve_fingerprint(fcs)
    # Key defaults for missing transform tracks so switching Actions cannot
    # leave a joint in a pose left behind by the previously selected clip.
    existing = {b['path'] for b in meta['bindings']}
    meta['defaults'] = []
    for pb in obj.pose.bones:
        for prop,width in (('location',3),('rotation_quaternion',4)):
            path = pb.path_from_id(prop)
            if path in existing:continue
            obj.keyframe_insert(data_path=path,frame=1,group=pb.name+' · defaults')
            fcs = [fc for fc in curves_for(obj) if fc.data_path==path]
            for fc in fcs:
                for key in fc.keyframe_points:key.interpolation='CONSTANT'
                fc.update()
            meta['defaults'].append({'path':path,'width':width,'fingerprint':curve_fingerprint(fcs)})
    action = obj.animation_data.action
    action.name = clip.name
    action.use_fake_user = True
    if 'mw4_rig_id' in obj: action['mw4_rig_id'] = obj['mw4_rig_id']
    action['mw4_duration'] = clip.end-clip.start
    action['mw4_fps'] = fps
    text = bpy.data.texts.new(clip.name+' · MW4 rig source')
    text.from_string(json.dumps(meta,indent=2));text.use_fake_user=True
    action['mw4_rig_metadata'] = text.name
    if hasattr(obj, 'mw4_preview_action'):
        from . import animation_ui
        animation_ui.sync_selection(obj, action)
    obj['mw4_unbound_channels'] = ', '.join(sorted(set(meta['unbound_names'])))
    obj['mw4_source_clip'] = str(filepath)
    context.scene.render.fps = max(1,round(fps))
    context.scene.render.fps_base = context.scene.render.fps/fps
    context.scene.frame_start = 1
    context.scene.frame_end = max(1,math.ceil(1+(clip.end-clip.start)*fps))
    context.scene.frame_set(1)
    for selected in context.selected_objects:selected.select_set(False)
    obj.select_set(True);context.view_layer.objects.active=obj
    return action

def rig_fingerprint(obj):
    bones = [[b.name,b.parent.name if b.parent else None,
              [list(row) for row in b.matrix_local]] for b in obj.data.bones]
    return hashlib.sha256(json.dumps(bones).encode()).hexdigest()

def export_action(obj,bake=False):
    from . import curves_for,_unique_frames
    ad = obj.animation_data
    if not ad or not ad.action or 'mw4_rig_metadata' not in ad.action:
        raise codec.FormatError('Select an imported MW4 Action on the rig')
    action = ad.action
    text = bpy.data.texts.get(action['mw4_rig_metadata'])
    if text is None:raise codec.FormatError('Missing Action source metadata')
    meta = json.loads(text.as_string())
    if rig_fingerprint(obj)!=meta['hierarchy_fingerprint']:
        raise codec.FormatError('Rest bones/hierarchy changed; export supports animation edits only')
    if obj.constraints or ad.drivers or any(pb.constraints for pb in obj.pose.bones):
        raise codec.FormatError('Constraints/drivers are not exported; bake to the imported Action and remove them first')
    if any(not strip.mute for track in ad.nla_tracks for strip in track.strips):
        raise codec.FormatError('NLA is not exported; select and edit an imported Action directly')
    if any(pb.rotation_mode!='QUATERNION' for pb in obj.pose.bones):
        raise codec.FormatError('Keep pose bones in Quaternion rotation mode')
    clip = codec.loads(base64.b64decode(meta['source'],validate=True))
    fcs = curves_for(obj)
    expected = {(b['path'],i) for b in meta['bindings']+meta.get('defaults',[]) for i in range(b['width'])}
    found = {(fc.data_path,fc.array_index) for fc in fcs}
    if expected!=found or len(fcs)!=len(found):
        raise codec.FormatError('Action channels differ from the imported template (missing, extra, or duplicate curves)')
    for default in meta.get('defaults',[]):
        curves = [fc for fc in fcs if fc.data_path==default['path']]
        if curve_fingerprint(curves)!=default['fingerprint']:
            raise codec.FormatError('Edited a default-only bone channel with no source track: '+default['path'])
    duration = float(action['mw4_duration']);fps = meta['fps']
    if not math.isfinite(duration) or duration<0:raise codec.FormatError('Invalid clip duration')
    replacements = {}
    for binding,tr in zip(meta['bindings'],clip.tracks):
        selected = sorted((fc for fc in fcs if fc.data_path==binding['path']),key=lambda fc:fc.array_index)
        if any(fc.mute or fc.modifiers or not fc.keyframe_points for fc in selected):
            raise codec.FormatError('Muted, modified, or empty curves cannot be exported')
        if curve_fingerprint(selected)==binding['fingerprint']:continue
        for fc in selected:
            constant = tr.kind==3 or (tr.kind==0 and fc.array_index>=3) or (tr.kind==4 and fc.array_index>=4)
            interp = 'CONSTANT' if constant else 'LINEAR'
            if not bake and any(k.interpolation!=interp for k in fc.keyframe_points):
                raise codec.FormatError('Keep imported interpolation or enable Bake edited tracks')
        frames = _unique_frames(k.co.x for fc in selected for k in fc.keyframe_points)
        if bake:
            last=1+duration*fps
            frames = _unique_frames(frames+[1.0,last]+list(range(1,math.floor(last)+1)))
        if len(frames)>255:raise codec.FormatError('Edited track exceeds 255 keys')
        times,rows = [],[]
        if binding['bound']:
            t0,q0,qc = _node_transforms(meta['nodes'][binding['node']])
        for frame in frames:
            t = clip.start+(frame-1)/fps
            for old in tr.times:
                if abs(frame-(1+(old-clip.start)*fps))<1e-5:t=old;break
            values = [fc.evaluate(frame) for fc in selected]
            if not all(math.isfinite(v) for v in values):raise codec.FormatError('Non-finite curve value')
            if binding['bound']:
                if tr.kind==1:values=list(t0+(q0 @ qc) @ Vector(values))
                else:
                    q = q0 @ qc @ Quaternion(values) @ qc.inverted()
                    values = [q.x,q.y,q.z,q.w]
            elif tr.kind==3:
                if any(abs(v-round(v))>1e-4 or not 0<=v<=255 for v in values):
                    raise codec.FormatError('Variant bytes must be integers from 0 through 255')
                values = [sum(round(v)<<(8*j) for j,v in enumerate(values))]
            if tr.kind in (2,4) and sum(v*v for v in values[:4])<1e-12:
                raise codec.FormatError('Zero-length quaternion')
            times.append(t);rows.append(values)
        replacements[binding['track']] = times,rows
    return codec.dumps(clip,replacements,end=clip.start+duration)


class MW4ANIM_OT_hierarchy(bpy.types.Operator):
    bl_idname='import_scene.mw4_hierarchy'
    bl_label='Import MW4 Armature'
    bl_options={'REGISTER','UNDO'}
    filepath:bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob:bpy.props.StringProperty(default='*.zip;*.contents',options={'HIDDEN'})
    def invoke(self,context,event):
        context.window_manager.fileselect_add(self);return {'RUNNING_MODAL'}
    def execute(self,context):
        try:
            obj=build_armature(self.filepath,context)
        except (OSError,ValueError,RuntimeError) as e:
            self.report({'ERROR'},str(e));return {'CANCELLED'}
        self.report({'INFO'},f'Imported {len(obj.data.bones)} joints; polygon meshes are not in these assets')
        return {'FINISHED'}


class MW4ANIM_OT_rig_clip(bpy.types.Operator):
    bl_idname='import_scene.mw4_rig_clip'
    bl_label='Import MW4 Animation onto Rig'
    bl_options={'REGISTER','UNDO'}
    filepath:bpy.props.StringProperty(subtype='FILE_PATH')
    directory:bpy.props.StringProperty(subtype='DIR_PATH')
    files:bpy.props.CollectionProperty(type=bpy.types.OperatorFileListElement)
    filter_glob:bpy.props.StringProperty(default='*.mw4anim',options={'HIDDEN'})
    fps:bpy.props.FloatProperty(name='Timeline FPS',default=30,min=1,max=240)
    @classmethod
    def poll(cls,context):return context.object is not None and 'mw4_hierarchy' in context.object
    def invoke(self,context,event):
        context.window_manager.fileselect_add(self);return {'RUNNING_MODAL'}
    def execute(self,context):
        obj=context.object
        paths=[Path(self.directory)/f.name for f in self.files] or [Path(self.filepath)]
        try:
            for p in paths:codec.loads(p.read_bytes())
            for p in paths:import_action(p,context,obj,self.fps)
        except (OSError,ValueError,RuntimeError) as e:
            self.report({'ERROR'},str(e));return {'CANCELLED'}
        self.report({'INFO'},f'Imported {len(paths)} Action(s); unbound tracks retained: '+obj['mw4_unbound_channels'])
        return {'FINISHED'}


CLASSES=(MW4ANIM_OT_hierarchy,MW4ANIM_OT_rig_clip)
