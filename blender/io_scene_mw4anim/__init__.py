"""Blender integration for the verified MW4ANIM 2.1 track layout."""
bl_info = {
    'name': 'MechWarrior 4 Animation Tools',
    'author': 'MW4 Mercenaries Decompilation Project',
    'version': (0, 12, 0),
    'blender': (5, 1, 0),
    'location': 'File > Import/Export; 3D View > Sidebar > MW4',
    'description': 'Import MW4 skeletons and edit/export native MW4ANIM 2.1 Actions',
    'category': 'Import-Export',
}

import base64
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import uuid

import bpy
from bpy.props import StringProperty, CollectionProperty, BoolProperty, FloatProperty
from bpy_extras.io_utils import ImportHelper, ExportHelper
# Blender legacy ZIP upgrades may reload only this package, retaining old
# submodules in sys.modules. Clean up the previous RNA classes before reloading
# dependencies; otherwise the root and submodule APIs can come from different releases.
import importlib
import sys
if 'CLASSES' in globals():
    for menu, callback_name in ((bpy.types.TOPBAR_MT_file_import, 'menu_import'),
                                (bpy.types.TOPBAR_MT_file_export, 'menu_export')):
        callback = globals().get(callback_name)
        if callback:
            try: menu.remove(callback)
            except (ValueError, RuntimeError): pass
    if hasattr(bpy.types.Object, 'mw4_preview_action'):
        del bpy.types.Object.mw4_preview_action
    for old_class in reversed(CLASSES):
        if getattr(old_class, 'is_registered', False):
            bpy.utils.unregister_class(old_class)

for module_name in ('codec', 'helm', 'archives', 'embedded', 'hierarchy', 'erf',
                    'rig', 'animscript', 'meshes', 'textures', 'animation_ui', 'game_import'):
    module = sys.modules.get(__name__ + '.' + module_name)
    if module is not None: importlib.reload(module)
from . import codec, rig, game_import, meshes, textures, animation_ui


def curves_for(obj):
    """Handle Blender legacy Actions and 4.4+ slotted Actions."""
    ad = obj.animation_data
    if not ad or not ad.action:
        return []
    action = ad.action
    slot = getattr(ad, 'action_slot', None)
    if slot is not None and getattr(action, 'is_action_layered', False):
        result = []
        for layer in action.layers:
            for strip in layer.strips:
                if hasattr(strip, 'channelbag'):
                    bag = strip.channelbag(slot)
                    if bag:
                        result.extend(bag.fcurves)
        return result
    return list(action.fcurves)


def bindings(kind):
    # Each entry describes an RNA path and its indices in the on-disk value row.
    if kind == 0:
        return [('location', (0,1,2)), ('["linear_motion"]', (3,4,5))]
    if kind == 1:
        return [('location', (0,1,2))]
    if kind == 2:
        return [('rotation_quaternion', (3,0,1,2))]
    if kind == 3:
        # Four bytes avoid loss of 32-bit flags through Blender float F-curves.
        return [('["variant_bytes"]', (0,1,2,3))]
    return [('rotation_quaternion', (3,0,1,2)), ('["angular_motion"]', (4,5,6))]


def fingerprint(obj):
    result = []
    for fc in sorted(curves_for(obj), key=lambda x:(x.data_path,x.array_index)):
        result.append([fc.data_path,fc.array_index,fc.extrapolation,fc.mute,
                       [(tuple(k.co),k.interpolation,tuple(k.handle_left),
                         tuple(k.handle_right),k.handle_left_type,k.handle_right_type,
                         k.easing,k.back,k.amplitude,k.period) for k in fc.keyframe_points],
                       [m.type for m in fc.modifiers]])
    return hashlib.sha256(json.dumps(result).encode()).hexdigest()


def _set_value(obj, path, value):
    if path.startswith('["'):
        obj[path[2:-2]] = list(value)
    else:
        setattr(obj,path,value)


def import_clip(filepath, context, fps=30.0):
    clip = codec.loads(Path(filepath).read_bytes())
    ident = uuid.uuid4().hex
    collection = bpy.data.collections.new('MW4 · '+clip.name)
    context.scene.collection.children.link(collection)
    root = bpy.data.objects.new(clip.name+' · MW4 Channels',None)
    collection.objects.link(root)
    root.empty_display_type = 'PLAIN_AXES'
    root['mw4_clip_id'] = ident
    root['mw4_duration'] = clip.end-clip.start
    root['mw4_fps'] = float(fps)
    root['mw4_source'] = str(filepath)
    root['mw4_note'] = 'Native channel study, not a reconstructed skeleton. Insert keys to export edits.'
    meta = {'schema':1, 'source':base64.b64encode(clip.original).decode(),
            'fps':float(fps), 'clip_id':ident, 'fingerprints':{}}
    anchors = []
    for i,ch in enumerate(clip.channels):
        anchor = bpy.data.objects.new(ch.name+' · layout',None)
        collection.objects.link(anchor)
        anchor.parent = root
        anchor.location = ((i%5)*4,0,-(i//5)*4)
        anchor.empty_display_type = 'PLAIN_AXES'
        anchor.empty_display_size = 0.12
        anchor.show_name = True
        anchors.append(anchor)
    for i,tr in enumerate(clip.tracks):
        name = clip.channels[tr.channel].name+' · '+codec.KINDS[tr.kind]
        obj = bpy.data.objects.new(name,None)
        collection.objects.link(obj)
        obj.parent = anchors[tr.channel]
        obj.rotation_mode = 'QUATERNION'
        obj.empty_display_type = 'ARROWS'
        obj.empty_display_size = 0.8
        obj['mw4_clip_id'] = ident
        obj['mw4_track_index'] = i
        obj['mw4_joint'] = clip.channels[tr.channel].name
        obj['mw4_track_type'] = codec.KINDS[tr.kind]
        for time,row in zip(tr.times,tr.values):
            if tr.kind == 3:
                row = tuple((row[0] >> (8*j)) & 255 for j in range(4))
            frame = 1+(time-clip.start)*fps
            for path,indices in bindings(tr.kind):
                _set_value(obj,path,tuple(row[j] for j in indices))
                obj.keyframe_insert(data_path=path,frame=frame,group=codec.KINDS[tr.kind])
        for fc in curves_for(obj):
            for k in fc.keyframe_points:
                k.interpolation = 'CONSTANT' if tr.kind == 3 or fc.data_path in (
                    '["linear_motion"]','["angular_motion"]') else 'LINEAR'
            fc.update()
        meta['fingerprints'][str(i)] = fingerprint(obj)
    text = bpy.data.texts.new(clip.name+' · MW4 source metadata')
    text.from_string(json.dumps(meta,indent=2))
    text.use_fake_user = True
    root['mw4_metadata'] = text.name
    # Display native Y-up channels through a common rigid layout rotation.
    # This does not change the file's local-space transforms on export.
    root.rotation_euler[0] = math.pi/2
    context.scene.render.fps = max(1,round(fps))
    context.scene.render.fps_base = context.scene.render.fps/fps
    context.scene.frame_start = 1
    context.scene.frame_end = max(1,math.ceil(1+(clip.end-clip.start)*fps))
    context.scene.frame_set(1)
    for ob in context.selected_objects:
        ob.select_set(False)
    root.select_set(True)
    context.view_layer.objects.active = root
    return root


def clip_root(obj):
    while obj:
        if 'mw4_metadata' in obj or 'mw4_hierarchy' in obj:
            return obj
        obj = obj.parent
    return None


def _unique_frames(frames):
    result = []
    for f in sorted(frames):
        if not result or abs(f-result[-1]) > 1e-5:
            result.append(f)
    return result


def export_bytes(root, bake=False):
    if 'mw4_hierarchy' in root:
        return rig.export_action(root,bake)
    text = bpy.data.texts.get(root.get('mw4_metadata',''))
    if text is None:
        raise codec.FormatError('Missing source metadata Text datablock')
    meta = json.loads(text.as_string())
    clip = codec.loads(base64.b64decode(meta['source'],validate=True))
    fps = meta['fps']
    duration = float(root.get('mw4_duration',clip.end-clip.start))
    if not math.isfinite(duration) or duration < 0:
        raise codec.FormatError('Invalid clip duration')
    by_index = {}
    for obj in root.children_recursive:
        if obj.get('mw4_clip_id') == meta['clip_id'] and 'mw4_track_index' in obj:
            index = obj['mw4_track_index']
            if index in by_index:
                raise codec.FormatError(f'Duplicate track object {index}')
            by_index[index] = obj
    if set(by_index) != set(range(len(clip.tracks))):
        raise codec.FormatError('Track objects were removed or their indices changed')
    replacements = {}
    for i,tr in enumerate(clip.tracks):
        obj = by_index[i]
        ad = obj.animation_data
        if obj.constraints or (ad and ad.drivers):
            raise codec.FormatError('Constraints/drivers are not exported; edit the imported keyframes directly')
        if ad and any(not strip.mute for track in ad.nla_tracks for strip in track.strips):
            raise codec.FormatError('NLA blending is not exported; edit the imported Action directly')
        if tr.kind in (2,4) and obj.rotation_mode != 'QUATERNION':
            raise codec.FormatError('Keep imported rotation tracks in Quaternion mode')
        if fingerprint(obj) == meta['fingerprints'][str(i)]:
            continue
        curves = curves_for(obj)
        fcmap = {(fc.data_path,fc.array_index):fc for fc in curves}
        expected = {(path,j) for path,indices in bindings(tr.kind) for j in range(len(indices))}
        if set(fcmap) != expected or len(fcmap) != len(curves):
            raise codec.FormatError(f'Track {i}: expected original channel curves; Euler/scale/extra layers unsupported')
        for fc in curves:
            if fc.mute or fc.modifiers or not fc.keyframe_points:
                raise codec.FormatError(f'Track {i}: muted, modified, or empty curves cannot be exported')
            allowed = {'CONSTANT'} if tr.kind == 3 or fc.data_path in (
                '["linear_motion"]','["angular_motion"]') else {'LINEAR'}
            if not bake and any(k.interpolation not in allowed for k in fc.keyframe_points):
                raise codec.FormatError(f'Track {i}: use the original interpolation or enable Bake edited tracks')
        frames = _unique_frames(k.co.x for fc in curves for k in fc.keyframe_points)
        if bake:
            last = 1+duration*fps
            frames = _unique_frames(frames+[1.0,last]+list(range(1,math.floor(last)+1)))
        if len(frames) > 255:
            raise codec.FormatError(f'Track {i}: {len(frames)} keys exceed the engine limit of 255')
        times, rows = [], []
        for frame in frames:
            time = clip.start+(frame-1)/fps
            # Recover original float32 times where Blender frame storage rounded them.
            for old in tr.times:
                if abs(frame-(1+(old-clip.start)*fps)) < 1e-5:
                    time = old
                    break
            if time < clip.start-1e-5 or time > clip.start+duration+1e-5:
                raise codec.FormatError(f'Track {i}: key outside clip duration; change Duration in the MW4 panel')
            row = [0.0] * (4 if tr.kind == 3 else tr.stride//4)
            for path,indices in bindings(tr.kind):
                for j,index in enumerate(indices):
                    row[index] = fcmap[path,j].evaluate(frame)
            if tr.kind == 3:
                if any(abs(v-round(v)) > 1e-4 or not 0 <= v <= 255 for v in row):
                    raise codec.FormatError('Variant bytes must be integers between 0 and 255')
                row = [sum(round(v) << (8*j) for j,v in enumerate(row))]
            if tr.kind in (2,4) and sum(v*v for v in row[:4]) < 1e-12:
                raise codec.FormatError(f'Track {i}: zero-length quaternion')
            times.append(time)
            rows.append(row)
        replacements[i] = (times,rows)
    return codec.dumps(clip,replacements,end=clip.start+duration)


class MW4ANIM_OT_import(bpy.types.Operator, ImportHelper):
    bl_idname = 'import_scene.mw4anim'
    bl_label = 'Import MW4 Animation Channels'
    bl_options = {'REGISTER','UNDO'}
    filename_ext = '.mw4anim'
    filter_glob: StringProperty(default='*.mw4anim',options={'HIDDEN'})
    files: CollectionProperty(type=bpy.types.OperatorFileListElement)
    directory: StringProperty(subtype='DIR_PATH')
    fps: FloatProperty(name='Timeline FPS',default=30,min=1,max=240)

    def execute(self,context):
        paths = [os.path.join(self.directory,f.name) for f in self.files] or [self.filepath]
        try:
            # Fail before creating objects if any selected file is invalid.
            for p in paths:
                codec.loads(Path(p).read_bytes())
            for p in paths:
                import_clip(p,context,self.fps)
        except (OSError,ValueError,RuntimeError) as e:
            self.report({'ERROR'},str(e))
            return {'CANCELLED'}
        self.report({'INFO'},f'Imported {len(paths)} clip(s) as native channels; skeleton/model not included')
        return {'FINISHED'}


class MW4ANIM_OT_export(bpy.types.Operator, ExportHelper):
    bl_idname = 'export_scene.mw4anim'
    bl_label = 'Export MW4 Animation'
    filename_ext = '.mw4anim'
    filter_glob: StringProperty(default='*.mw4anim',options={'HIDDEN'})
    bake: BoolProperty(name='Bake edited tracks',default=False,
        description='Sample edited curves each source-timeline frame; maximum 255 keys per track')

    @classmethod
    def poll(cls,context):
        return clip_root(context.active_object) is not None

    def invoke(self, context, event):
        root = clip_root(context.active_object)
        action = root.animation_data.action if root and root.animation_data else None
        name = action.get('mw4_archive_member', action.name) if action else 'animation'
        name = Path(name.replace('\\', '/')).name
        name = ''.join(c if c not in '<>:"/\\|?*' else '_' for c in name)
        self.filepath = name if name.lower().endswith('.mw4anim') else name+'.mw4anim'
        return ExportHelper.invoke(self, context, event)

    def execute(self,context):
        tmp = None
        try:
            data = export_bytes(clip_root(context.active_object),self.bake)
            dest = Path(self.filepath)
            with tempfile.NamedTemporaryFile(dir=dest.parent,prefix='.mw4-',delete=False) as f:
                tmp = f.name
                f.write(data)
            os.replace(tmp,dest)
        except (OSError,ValueError,RuntimeError,KeyError) as e:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)
            self.report({'ERROR'},str(e))
            return {'CANCELLED'}
        self.report({'INFO'},'Exported MW4ANIM 2.1; verify edited clips in-game')
        return {'FINISHED'}


class MW4ANIM_PT_tools(bpy.types.Panel):
    bl_label = 'MW4 Animation Tools'
    bl_idname = 'MW4ANIM_PT_tools'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'MW4'

    def draw(self,context):
        layout = self.layout
        layout.operator(game_import.MW4ANIM_OT_game_directory.bl_idname,text='Import from MW4 installation',icon='FILE_FOLDER')
        if 'mw4_resource_bundle' in context.scene or (context.object and 'mw4_resource_bundle' in context.object):
            layout.operator(game_import.MW4ANIM_OT_resource_bundle.bl_idname,text='Save resource bundle (.zip)')
        layout.operator(meshes.MW4ANIM_OT_bundle_import.bl_idname,text='Import resource bundle (.zip)')
        layout.operator(rig.MW4ANIM_OT_hierarchy.bl_idname,text='Import armature (.zip / .contents)')
        layout.operator(rig.MW4ANIM_OT_rig_clip.bl_idname,text='Import animation onto rig')
        layout.operator(MW4ANIM_OT_import.bl_idname,text='Import raw channels (diagnostic)')
        root = clip_root(context.active_object)
        box = layout.box()
        box.label(text='Textures · R12')
        box.operator(textures.MW4ANIM_OT_textures.bl_idname, text='Load / Reload Textures from MW4')
        box.operator(textures.MW4ANIM_OT_material_preview.bl_idname)
        if root:
            box.label(text=root.get('mw4_texture_status', 'Textures have not been loaded for this mech'))
            if not textures.material_references(root):
                box.label(text='This rig has no mesh texture references', icon='INFO')
        else:
            box.label(text='Select an imported mech armature or mesh', icon='INFO')
        if root and 'mw4_hierarchy' in root:
            layout.label(text=f"{len(root.data.bones)} joints · {root.get('mw4_mesh_count',0)} mesh objects")
            if 'mw4_resource_bundle' in root:
                layout.operator(meshes.MW4ANIM_OT_attach_meshes.bl_idname,text='Add meshes from collected resources')
            if 'mw4_geometry_count' in root:
                layout.label(text=f"{root['mw4_geometry_count']} ERF resources collected")
            box = layout.box()
            box.label(text='Animations · R12')
            available = len(animation_ui.actions_for(root))
            box.label(text=f'{available} compatible animations available')
            if 'mw4_animation_discovered' in root:
                box.label(text=f"{root['mw4_animation_discovered']} source clips; {root.get('mw4_animation_import_errors', 0)} import errors")
            if root.get('mw4_animation_import_enabled') == False:
                box.label(text='Animation import was disabled', icon='ERROR')
            if not available:
                box.label(text='No compatible Actions; load clips below', icon='ERROR')
            box.operator(animation_ui.MW4ANIM_OT_load_animations.bl_idname, text='Load missing animations from bundle').from_installation = False
            box.operator(animation_ui.MW4ANIM_OT_load_animations.bl_idname, text='Load missing animations from MW4').from_installation = True
            if root.get('mw4_animation_load_status'):
                box.label(text=root['mw4_animation_load_status'])
            box.operator(animation_ui.MW4ANIM_OT_copy_diagnostics.bl_idname, text='Copy diagnostics', icon='COPYDOWN')
            box.prop(root, 'mw4_preview_action', text='Animation')
            if root.get('mw4_animation_status'):
                box.label(text=root['mw4_animation_status'], icon='ERROR')
            row = box.row(align=True)
            row.operator(animation_ui.MW4ANIM_OT_step_animation.bl_idname, text='Previous', icon='TRIA_LEFT').direction = -1
            row.operator(animation_ui.MW4ANIM_OT_step_animation.bl_idname, text='Next', icon='TRIA_RIGHT').direction = 1
            box.operator('screen.animation_play', text='Play / Pause', icon='PLAY')
            box.operator(animation_ui.MW4ANIM_OT_rest_pose.bl_idname, text='Show rest pose')
            ad=root.animation_data
            if not ad or not ad.action:
                box.label(text='Rest pose · no active animation')
            if ad and ad.action and 'mw4_rig_metadata' in ad.action:
                layout.label(text='Active Action: '+ad.action.name)
                layout.prop(ad.action,'["mw4_duration"]',text='Duration (seconds)')
                layout.operator(MW4ANIM_OT_export.bl_idname,text='Export native animation (.mw4anim)')
                txt=bpy.data.texts.get(ad.action['mw4_rig_metadata'])
                if txt:
                    missing=json.loads(txt.as_string()).get('unbound_names',[])
                    if missing:layout.label(text='Unbound: '+', '.join(sorted(set(missing))))
            layout.label(text='Edit bones in Pose Mode; insert keys.')
            return
        layout.label(text='Channel editor · no model rig')
        if root:
            layout.prop(root,'["mw4_duration"]',text='Duration (seconds)')
            layout.label(text=f'Source timeline: {root["mw4_fps"]:g} FPS')
            layout.operator(MW4ANIM_OT_export.bl_idname,text='Export selected clip')
            obj = context.active_object
            if 'mw4_track_index' in obj:
                layout.label(text=obj['mw4_joint'])
                layout.label(text=obj['mw4_track_type'])
                for prop in ('linear_motion','angular_motion','variant_bytes'):
                    if prop in obj:
                        layout.prop(obj,f'["{prop}"]',text=prop.replace('_',' ').title())
                layout.label(text='Insert keyframes to retain edits.')


def menu_import(self,context):
    self.layout.operator(meshes.MW4ANIM_OT_bundle_import.bl_idname,text='MechWarrior 4 Resource Bundle (.zip)')
    self.layout.operator(game_import.MW4ANIM_OT_game_directory.bl_idname,text='MechWarrior 4 from Installation')
    self.layout.operator(rig.MW4ANIM_OT_hierarchy.bl_idname,text='MechWarrior 4 Armature (.zip / .contents)')
    self.layout.operator(rig.MW4ANIM_OT_rig_clip.bl_idname,text='MechWarrior 4 Animation onto Rig (.mw4anim)')
    self.layout.operator(MW4ANIM_OT_import.bl_idname,text='MechWarrior 4 Raw Channels (.mw4anim)')

def menu_export(self,context):
    self.layout.operator(MW4ANIM_OT_export.bl_idname,text='MechWarrior 4 Animation (.mw4anim)')

CLASSES = animation_ui.CLASSES + textures.CLASSES + meshes.CLASSES + game_import.CLASSES + rig.CLASSES + (MW4ANIM_OT_import,MW4ANIM_OT_export,MW4ANIM_PT_tools)

def register():
    registered = []
    try:
        animation_ui.register_properties()
        for cls in CLASSES:
            bpy.utils.register_class(cls); registered.append(cls)
        bpy.types.TOPBAR_MT_file_import.append(menu_import)
        bpy.types.TOPBAR_MT_file_export.append(menu_export)
    except Exception:
        for cls in reversed(registered): bpy.utils.unregister_class(cls)
        if hasattr(bpy.types.Object, 'mw4_preview_action'):
            animation_ui.unregister_properties()
        raise


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_export)
    bpy.types.TOPBAR_MT_file_import.remove(menu_import)
    if hasattr(bpy.types.Object, 'mw4_preview_action'):
        animation_ui.unregister_properties()
    for cls in reversed(CLASSES):
        if getattr(cls, 'is_registered', False): bpy.utils.unregister_class(cls)

if __name__ == '__main__':
    register()
