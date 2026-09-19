"""Blender UI for directory discovery, model selection and decoded resource bundles."""
import base64
import io
import json
from pathlib import Path
import tempfile
import zipfile

import bpy
from bpy_extras.io_utils import ExportHelper
from . import archives, codec, hierarchy, rig, meshes, textures, animscript, embedded, animation_ui

_catalog = None
_model_rows = []
_model_items = []


def model_items(self, context):
    return _model_items


def preferences(context):
    addon = context.preferences.addons.get(__package__)
    return addon.preferences if addon else None


class MW4ANIM_preferences(bpy.types.AddonPreferences):
    bl_idname = __package__
    game_directory: bpy.props.StringProperty(name='MW4 installation', subtype='DIR_PATH')
    key_source: bpy.props.StringProperty(name='Key source override', subtype='FILE_PATH',
        description='Optional verified image.bin or unpacked analysis PE; leave empty for the bundled verified profile')

    def draw(self, context):
        self.layout.prop(self, 'game_directory')
        self.layout.prop(self, 'key_source')
        self.layout.label(text='Default: verified Mercenaries decryption profile. Game files are read-only.')


class MW4ANIM_OT_game_directory(bpy.types.Operator):
    bl_idname = 'import_scene.mw4_game_directory'
    bl_label = 'Import from MW4 Installation'
    directory: bpy.props.StringProperty(name='MW4 installation directory', subtype='DIR_PATH')
    filter_folder: bpy.props.BoolProperty(default=True, options={'HIDDEN'})

    def invoke(self, context, event):
        prefs = preferences(context)
        if prefs and prefs.game_directory: self.directory = prefs.game_directory
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        global _catalog, _model_rows, _model_items
        _catalog = None; _model_rows = []; _model_items = []
        prefs = preferences(context)
        wm = context.window_manager
        wm.progress_begin(0, 100)
        try:
            catalog = archives.Catalog(bpy.path.abspath(self.directory),
                bpy.path.abspath(prefs.key_source) if prefs and prefs.key_source else '',
                lambda i, n, path: wm.progress_update(100*i/max(1,n)))
            rows = sorted(catalog.models(), key=lambda r:(r['name'].casefold(),r['archive']))
            if not rows: raise archives.Error('No mech .contents resources found in readable archives')
            _catalog = catalog; _model_rows = rows
            _model_items = [(str(i), r['name'].replace('\\','/') + ' — ' +
                catalog.archives[r['archive']]['relative'], 'Import this hierarchy and collect its resources')
                for i, r in enumerate(rows)]
            if prefs: prefs.game_directory = str(catalog.root)
            selected = '0'
            bpy.ops.import_scene.mw4_game_model('INVOKE_DEFAULT', model=selected, import_animations=True)
        except (OSError, ValueError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
        finally:
            wm.progress_end()
        return {'FINISHED'}


def import_model(catalog, row, context, import_animations=True, fps=30):
    files, report = catalog.collect(row)
    textures.collect(catalog, files, report)
    return import_resource_files(files, report, context, import_animations, fps, str(catalog.root))


def import_resource_files(files, report, context, import_animations=True, fps=30, game_directory=''):
    # Keep a portable bundle even if unsupported rig/clip formats are encountered.
    # It preserves original resources for subsequent mesh/texture attachment.
    root_name = archives.normalized(report['source']['name'])
    errors = report['errors']
    obj = None
    imported = 0
    imported_actions = []
    animation_errors = []
    context.window_manager.progress_begin(0, max(1, len(report['animation_files'])))
    try:
        with tempfile.TemporaryDirectory(prefix='mw4_blender_') as tmp:
            path = Path(tmp)
            hp = path / 'hierarchy.zip'
            with zipfile.ZipFile(hp, 'w') as z:
                for name, data in files.items():
                    match = hierarchy.PATTERN.fullmatch(name)
                    if match and match.group(1) == root_name: z.writestr(name, data)
            try:
                # Validate before creating Blender data.
                hierarchy.load_hierarchy(hp)
                obj = rig.build_armature(hp, context)
                obj['mw4_game_directory'] = game_directory
                obj['mw4_archive_source'] = json.dumps(report['source'])
            except (ValueError, OSError, RuntimeError) as exc:
                errors.append({'name': root_name, 'error': 'Armature import: ' + str(exc)})
            if obj and import_animations:
                # Valid rigs may have no collected/decodable clips. Blender creates
                # AnimData lazily; do not depend on a successful clip import.
                obj.animation_data_create()
                for i, name in enumerate(report['animation_files']):
                    context.window_manager.progress_update(i)
                    try:
                        codec.loads(files[name])
                        ap = path / 'clip.mw4anim'; ap.write_bytes(files[name])
                        action = rig.import_action(ap, context, obj, fps)
                        action['mw4_archive_member'] = name
                        imported_actions.append(action)
                        imported += 1
                    except (ValueError, OSError, RuntimeError, KeyError) as exc:
                        entry = {'name': name, 'error': 'Animation import: ' + str(exc)}
                        errors.append(entry); animation_errors.append(entry)
                preview = animscript.choose_action(imported_actions, files)
                if preview is not None:
                    obj.animation_data.action = preview
                    context.scene.frame_end = max(1, round(1+preview['mw4_duration']*fps))
                    report['preview_action'] = preview.get('mw4_archive_member', preview.name)
                else:
                    obj.animation_data.action = None
                    for pb in obj.pose.bones:
                        pb.location = (0,0,0); pb.rotation_quaternion = (1,0,0,0); pb.scale = (1,1,1)
                    report['preview_action'] = None
                    report['warnings'].append(
                        'No walk/stand preview available; rig left in rest pose. Imported Actions remain available.'
                        if imported_actions else
                        'No usable animation Actions were imported; rig left in rest pose. '
                        'Copy diagnostics for missing resources, decode failures, or unsupported clips.')
                if hasattr(obj, 'mw4_preview_action'):
                    animation_ui.sync_selection(obj, obj.animation_data.action)
                context.scene.frame_set(1)

    finally:
        context.window_manager.progress_end()
    if obj:
        result = meshes.attach(files, report, obj, context)
        errors.extend({'name': e.get('bone','mesh'), 'error': e['error']} for e in result['errors'])
        tx = textures.apply(files, report, obj)
        if tx['images']: textures.show_textures(context)
    report['animation_import'] = {'enabled': bool(import_animations),
        'discovered': len(report['animation_files']), 'imported': imported, 'errors': animation_errors}
    if obj:
        obj['mw4_animation_discovered'] = len(report['animation_files'])
        obj['mw4_animation_import_enabled'] = bool(import_animations)
        obj['mw4_animation_import_errors'] = len(animation_errors)
    if import_animations and not imported:
        report['warnings'].append('No animation Actions imported; see animation collection/import diagnostics')
    report['imported_actions'] = imported
    report['imported_bones'] = len(obj.data.bones) if obj else 0
    report['complete'] = not errors and not report['unresolved_shapes']
    report_text = bpy.data.texts.new(report['model'] + ' · MW4 resource report')
    report_text.write(json.dumps(report, indent=2)); report_text.use_fake_user=True
    bundle = io.BytesIO(); archives.write_bundle(bundle, files, report)
    payload = bpy.data.texts.new(report['model'] + ' · MW4 resource bundle')
    payload.from_string(embedded.encode(bundle.getvalue()));payload.use_fake_user=True
    for owner in [context.scene] + ([obj] if obj else []):
        owner['mw4_resource_bundle'] = payload.name
        owner['mw4_resource_report'] = report_text.name
    if obj: obj['mw4_geometry_count'] = len(report['geometry_files'])
    return obj, report


class MW4ANIM_OT_game_model(bpy.types.Operator):
    bl_idname = 'import_scene.mw4_game_model'
    bl_label = 'Import MW4 Model Resources'
    bl_options = {'REGISTER', 'UNDO'}
    model: bpy.props.EnumProperty(name='Model / source archive', items=model_items)
    import_animations: bpy.props.BoolProperty(name='Import animation Actions', default=True)
    fps: bpy.props.FloatProperty(name='Timeline FPS', default=30, min=1, max=240)

    def invoke(self, context, event):
        if _catalog is None:
            self.report({'ERROR'}, 'Select the game directory first');return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=650)

    def draw(self, context):
        self.layout.prop(self, 'model')
        self.layout.prop(self, 'import_animations')
        self.layout.prop(self, 'fps')
        self.layout.label(text='Loads the armature, animation clips, and supported ERF meshes.')
        self.layout.label(text='Highest-detail intact parts; texture images loaded and packed automatically.')
        if _catalog and _catalog.warnings:
            self.layout.label(text=f'{len(_catalog.warnings)} unreadable archives; details will be in the report.', icon='ERROR')

    def execute(self, context):
        if _catalog is None or not self.model:
            self.report({'ERROR'}, 'Scan the game directory first');return {'CANCELLED'}
        try:
            obj, report = import_model(_catalog, _model_rows[int(self.model)], context,
                                      self.import_animations, self.fps)
        except (OSError, ValueError, RuntimeError, IndexError) as exc:
            self.report({'ERROR'}, str(exc));return {'CANCELLED'}
        message = (f"{report['imported_bones']} bones, {report['imported_actions']} Actions; "
                   f"{report.get('mesh_import',{}).get('total_objects',0)} mesh objects. "
                   f"{report['unresolved_shapes']} unresolved shape references, {len(report['errors'])} errors.")
        tx = report.get('texture_import', {})
        message += f" {len(tx.get('images',[]))} textures; {len(tx.get('missing',[]))} unresolved materials."
        deps = report.get('animation_dependencies', {})
        if deps.get('missing'):
            message += f" {len(deps['missing'])} referenced animation files missing."
        texture_problem = deps.get('missing') or deps.get('errors') or tx.get('missing') or tx.get('errors') or report.get('texture_resources',{}).get('errors')
        self.report({'INFO'} if report['complete'] and not texture_problem else {'WARNING'}, message)
        return {'FINISHED'}


class MW4ANIM_OT_resource_bundle(bpy.types.Operator, ExportHelper):
    bl_idname = 'export_scene.mw4_resource_bundle'
    bl_label = 'Save MW4 Resource Bundle'
    filename_ext = '.zip'
    filter_glob: bpy.props.StringProperty(default='*.zip', options={'HIDDEN'})

    def execute(self, context):
        obj = context.object
        owner = obj if obj and 'mw4_resource_bundle' in obj else context.scene
        text = bpy.data.texts.get(owner.get('mw4_resource_bundle',''))
        if not text:
            self.report({'ERROR'}, 'Import from the game directory first');return {'CANCELLED'}
        try:
            Path(self.filepath).write_bytes(embedded.decode(text.as_string()))
        except (ValueError, OSError) as exc:
            self.report({'ERROR'}, str(exc));return {'CANCELLED'}
        self.report({'INFO'}, 'Saved decoded resources and resolution report')
        return {'FINISHED'}


CLASSES = (MW4ANIM_preferences, MW4ANIM_OT_game_directory, MW4ANIM_OT_game_model,
           MW4ANIM_OT_resource_bundle)
