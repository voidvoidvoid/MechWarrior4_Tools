"""Searchable per-mech animation selection with legacy project compatibility."""
import json
import math
import bpy
from . import rig

_items = []
_item_cache = {}  # Retain every returned enum string for the registration lifetime.
_syncing = False


def root(context):
    from . import clip_root
    obj = clip_root(context.object)
    return obj if obj is not None and 'mw4_hierarchy' in obj else None


def compatible(obj, action, fingerprint=None):
    if obj is None or action is None or 'mw4_hierarchy' not in obj: return False
    aid = action.get('mw4_rig_id')
    if aid and aid != obj.get('mw4_rig_id'): return False
    text = bpy.data.texts.get(action.get('mw4_rig_metadata', ''))
    if text is None: return False
    try:
        return json.loads(text.as_string()).get('hierarchy_fingerprint') == (fingerprint if fingerprint is not None else rig.rig_fingerprint(obj))
    except (ValueError, KeyError): return False


def actions_for(obj):
    if obj is None: return []
    fingerprint = rig.rig_fingerprint(obj)
    return sorted((a for a in bpy.data.actions if compatible(obj, a, fingerprint)), key=lambda a: a.name.casefold())


def sync_selection(obj, action):
    global _syncing
    _syncing = True
    try: obj.mw4_preview_action = action
    finally: _syncing = False


def selection_changed(obj, context):
    if _syncing: return
    previous = obj.animation_data.action if obj.animation_data else None
    try:
        activate(obj, obj.mw4_preview_action, context)
        obj['mw4_animation_status'] = ''
    except (ValueError, RuntimeError, KeyError) as exc:
        obj['mw4_animation_status'] = str(exc)
        sync_selection(obj, previous)


def register_properties():
    bpy.types.Object.mw4_preview_action = bpy.props.PointerProperty(
        name='Animation', description='Choose an imported clip to preview on this mech',
        type=bpy.types.Action, poll=lambda obj, action: compatible(obj, action), update=selection_changed)


def unregister_properties():
    del bpy.types.Object.mw4_preview_action
    _item_cache.clear()


def activate(obj, action, context):
    if action is not None and not compatible(obj, action):
        raise ValueError('Animation does not belong to this rig or its rest hierarchy has changed')
    ad = obj.animation_data_create()
    if any(not track.mute and not strip.mute for track in ad.nla_tracks for strip in track.strips):
        raise ValueError('Mute active NLA strips before switching MW4 animations')
    slots = [s for s in action.slots if s.target_id_type == 'OBJECT'] if action else []
    if action and len(slots) != 1:
        raise ValueError('Expected one imported Object Action slot')
    if ad.action: ad.action.use_fake_user = True
    ad.action = None
    for pb in obj.pose.bones:
        pb.location = (0,0,0); pb.rotation_mode = 'QUATERNION'
        pb.rotation_quaternion = (1,0,0,0); pb.scale = (1,1,1)
    if action:
        obj.data.pose_position = 'POSE'
        action.use_fake_user = True; ad.action = action; ad.action_slot = slots[0]
        fps = float(action['mw4_fps']); duration = float(action['mw4_duration'])
        context.scene.render.fps = max(1, round(fps))
        context.scene.render.fps_base = context.scene.render.fps / fps
        context.scene.frame_start = 1
        context.scene.frame_end = max(1, math.ceil(1+duration*fps))
    sync_selection(obj, action)
    obj['mw4_animation_status'] = ''
    context.scene.frame_set(1); context.view_layer.update()
    if context.screen:
        for area in context.screen.areas: area.tag_redraw()


def items(self, context):
    global _items
    if context is None: return _items
    rows = tuple((a.name, a.name, a.get('mw4_archive_member', 'Imported MW4 animation'))
                 for a in actions_for(root(context)))
    if rows not in _item_cache: _item_cache[rows] = list(rows)
    _items = _item_cache[rows]
    return _items


class MW4ANIM_OT_choose_animation(bpy.types.Operator):
    bl_idname = 'mw4.choose_animation'
    bl_label = 'Choose MW4 Animation'
    bl_options = {'REGISTER', 'UNDO'}
    bl_property = 'animation'
    animation: bpy.props.EnumProperty(name='Animation', items=items)

    @classmethod
    def poll(cls, context): return root(context) is not None

    def invoke(self, context, event):
        if not actions_for(root(context)):
            self.report({'WARNING'}, 'No compatible imported animations found'); return {'CANCELLED'}
        context.window_manager.invoke_search_popup(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        try:
            action = bpy.data.actions.get(self.animation)
            if action is None: raise ValueError('Animation no longer exists')
            activate(root(context), action, context)
        except (ValueError, RuntimeError, KeyError) as exc:
            self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
        return {'FINISHED'}


class MW4ANIM_OT_step_animation(bpy.types.Operator):
    bl_idname = 'mw4.step_animation'
    bl_label = 'Previous / Next MW4 Animation'
    bl_options = {'REGISTER', 'UNDO'}
    direction: bpy.props.IntProperty(default=1)
    @classmethod
    def poll(cls, context): return root(context) is not None
    def execute(self, context):
        obj = root(context); actions = actions_for(obj)
        if not actions:
            self.report({'WARNING'}, 'No imported animations found'); return {'CANCELLED'}
        current = obj.animation_data.action if obj.animation_data else None
        index = actions.index(current) if current in actions else (-1 if self.direction > 0 else 0)
        try: activate(obj, actions[(index+self.direction) % len(actions)], context)
        except (ValueError, RuntimeError, KeyError) as exc:
            self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
        return {'FINISHED'}


class MW4ANIM_OT_rest_pose(bpy.types.Operator):
    bl_idname = 'mw4.rest_pose'
    bl_label = 'Show MW4 Rest Pose'
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context): return root(context) is not None
    def execute(self, context):
        try: activate(root(context), None, context)
        except (ValueError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
        return {'FINISHED'}


def recover_actions(obj, files, context, fps=30):
    """Add absent native clips, preserving existing compatible edited Actions."""
    import tempfile
    from pathlib import Path
    from . import codec, animscript
    ad = obj.animation_data_create()
    if any(not t.mute and not strip.mute for t in ad.nla_tracks for strip in t.strips):
        raise ValueError('Mute active NLA strips before loading animations')
    previous = ad.action
    available = actions_for(obj)
    existing = {animscript.resource_key(a.get('mw4_archive_member', '')) for a in available}
    result = {'discovered': 0, 'imported': 0, 'existing': 0, 'errors': []}
    with tempfile.TemporaryDirectory(prefix='mw4_clips_') as td:
        path = Path(td) / 'clip.mw4anim'
        for name, data in sorted(files.items()):
            if not name.casefold().endswith('.mw4anim'): continue
            result['discovered'] += 1
            if animscript.resource_key(name) in existing:
                result['existing'] += 1; continue
            before = set(bpy.data.actions)
            try:
                codec.loads(data)
                path.write_bytes(data)
                action = rig.import_action(path, context, obj, fps)
                action['mw4_archive_member'] = name
                available.append(action); existing.add(animscript.resource_key(name))
                result['imported'] += 1
            except (ValueError, RuntimeError, OSError, KeyError) as exc:
                ad.action = None
                for action in set(bpy.data.actions) - before:
                    bpy.data.actions.remove(action)
                result['errors'].append({'name': name, 'error': str(exc)})
    chosen = previous if previous and compatible(obj, previous) else animscript.choose_action(available, files)
    if chosen is None and available: chosen = available[0]
    activate(obj, chosen, context)
    return result


class MW4ANIM_OT_load_animations(bpy.types.Operator):
    bl_idname = 'mw4.load_animations'
    bl_label = 'Load Missing MW4 Animations'
    bl_options = {'REGISTER', 'UNDO'}
    directory: bpy.props.StringProperty(name='MW4 installation directory', subtype='DIR_PATH')
    filter_folder: bpy.props.BoolProperty(default=True, options={'HIDDEN'})
    from_installation: bpy.props.BoolProperty(default=False, options={'HIDDEN'})
    fps: bpy.props.FloatProperty(name='Timeline FPS', default=30, min=1, max=240)
    @classmethod
    def poll(cls, context): return root(context) is not None
    def invoke(self, context, event):
        if not self.from_installation: return self.execute(context)
        from . import game_import
        obj = root(context); prefs = game_import.preferences(context)
        self.directory = obj.get('mw4_game_directory', '') or (prefs.game_directory if prefs else '')
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    def execute(self, context):
        import io, zipfile
        from . import archives, meshes, embedded, game_import, hierarchy, animscript
        obj = root(context)
        try:
            text = bpy.data.texts.get(obj.get('mw4_resource_bundle', ''))
            files, report = meshes.read_bundle(io.BytesIO(embedded.decode(text.as_string()))) if text else ({}, {'resources': []})
            if self.from_installation:
                prefs = game_import.preferences(context)
                catalog = archives.Catalog(bpy.path.abspath(self.directory),
                    bpy.path.abspath(prefs.key_source) if prefs and prefs.key_source else '')
                source = json.loads(obj.get('mw4_archive_source', '{}')) or report.get('source', {})
                name = source.get('name', '')
                candidates = [r for r in catalog.models() if animscript.resource_key(r['name']) == animscript.resource_key(name)]
                preferred = [r for r in candidates if catalog.archives[r['archive']]['relative'] == source.get('archive')]
                row = catalog.unique(preferred or candidates)
                if row is None: raise ValueError('Cannot find the original model in this installation; use its original resource bundle')
                collected, scan = catalog.collect(row)
                # Validate exact source hierarchy before binding shared clips to this rig.
                nodes = []
                for n, data in collected.items():
                    match = hierarchy.PATTERN.fullmatch(n)
                    if match: nodes.extend(hierarchy.read_records(data, match[2], n))
                expected = json.loads(obj['mw4_hierarchy'])['nodes']
                signature = lambda rows: sorted((n['name'], n['parent'] or '', tuple(n['matrix'])) for n in rows)
                if signature(nodes) != signature(expected):
                    raise ValueError('Installation hierarchy differs from this rig; animations were not imported')
                for n, data in collected.items():
                    if n.endswith(('.mw4anim', '.animscript')): files[n] = data
                report['animation_dependencies'] = scan.get('animation_dependencies', {})
                report['animation_scan_errors'] = scan.get('errors', [])
                report['animation_scan_warnings'] = scan.get('warnings', [])
                obj['mw4_game_directory'] = str(catalog.root)
                if prefs: prefs.game_directory = str(catalog.root)
            result = recover_actions(obj, files, context, self.fps)
            report['animation_recovery'] = result
            report['animation_files'] = sorted(n for n in files if n.endswith('.mw4anim'))
            obj['mw4_animation_discovered'] = result['discovered']
            obj['mw4_animation_import_enabled'] = True
            obj['mw4_animation_import_errors'] = len(result['errors'])
            rpt = bpy.data.texts.get(obj.get('mw4_resource_report', '')) or bpy.data.texts.new(obj.name+' · MW4 resource report')
            rpt.from_string(json.dumps(report, indent=2)); rpt.use_fake_user=True
            obj['mw4_resource_report'] = rpt.name
            if text:
                packed = io.BytesIO(); archives.write_bundle(packed, files, report)
                text.from_string(embedded.encode(packed.getvalue()))
            count = len(actions_for(obj))
            deps = report.get('animation_dependencies', {})
            issues = len(deps.get('missing', [])) + len(deps.get('errors', []))
            status = f"{count} available; {result['imported']} added; {len(result['errors'])} import errors"
            if issues: status += f'; {issues} dependency issues (Copy diagnostics)'
            if not count: status += '; no usable clips. Scan installation or copy diagnostics.'
            obj['mw4_animation_load_status'] = status
            self.report({'INFO'} if count and not result['errors'] else {'WARNING'}, status)
        except (ValueError, OSError, RuntimeError, KeyError, zipfile.BadZipFile) as exc:
            obj['mw4_animation_load_status'] = str(exc)
            self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
        return {'FINISHED'}


class MW4ANIM_OT_copy_diagnostics(bpy.types.Operator):
    bl_idname = 'mw4.copy_diagnostics'
    bl_label = 'Copy MW4 Diagnostics'
    @classmethod
    def poll(cls, context): return root(context) is not None
    def execute(self, context):
        from . import bl_info
        obj = root(context); ad = obj.animation_data
        rpt = bpy.data.texts.get(obj.get('mw4_resource_report',''))
        try: report = json.loads(rpt.as_string()) if rpt else {}
        except ValueError: report = {'report_error':'Invalid resource report JSON'}
        mats = {slot.material for child in obj.children_recursive if child.type == 'MESH'
                for slot in child.material_slots if slot.material}
        result = {'addon_version':list(bl_info['version']), 'blender':bpy.app.version_string,
            'rig':obj.name, 'rig_id':obj.get('mw4_rig_id'),
            'active_action':ad.action.name if ad and ad.action else None,
            'selected_action':obj.mw4_preview_action.name if obj.mw4_preview_action else None,
            'compatible_actions':len(actions_for(obj)),
            'imported_actions_in_file':sum('mw4_rig_metadata' in a for a in bpy.data.actions),
            'animation_status':obj.get('mw4_animation_status',''),
            'animation_load_status':obj.get('mw4_animation_load_status',''),
            'animation_import_enabled':obj.get('mw4_animation_import_enabled'),
            'animation_files':report.get('animation_files'),
            'animation_dependencies':report.get('animation_dependencies'),
            'animation_import':report.get('animation_import'),
            'animation_recovery':report.get('animation_recovery'),
            'animation_scan_errors':report.get('animation_scan_errors'),
            'animation_scan_warnings':report.get('animation_scan_warnings'),
            'resource_errors':report.get('errors'),
            'resource_warnings':report.get('warnings'),
            'action_inventory':[{'name':a.name,'rig_id':a.get('mw4_rig_id'),
                'metadata_present':bpy.data.texts.get(a.get('mw4_rig_metadata','')) is not None,
                'compatible':compatible(obj,a)} for a in bpy.data.actions if 'mw4_rig_metadata' in a],
            'pose_position':obj.data.pose_position,
            'mesh_import':report.get('mesh_import'),
            'shape_references':report.get('shape_references'),
            'texture_resources':report.get('texture_resources'),
            'texture_import':report.get('texture_import'),
            'materials':[{'name':m.name,'reference':m.get('mw4_texture_reference'),
                'images':[{'name':n.image.name,'size':list(n.image.size),'packed':bool(n.image.packed_file)}
                    for n in m.node_tree.nodes if n.type=='TEX_IMAGE' and n.image] if m.node_tree else []}
                for m in sorted(mats,key=lambda m:m.name)],
            'viewport_shading':[space.shading.type for area in context.screen.areas
                for space in area.spaces if space.type=='VIEW_3D'] if context.screen else []}
        payload = json.dumps(result,indent=2)
        text = bpy.data.texts.get(obj.get('mw4_diagnostics','')) or bpy.data.texts.new(obj.name+' · MW4 diagnostics')
        text.from_string(payload); obj['mw4_diagnostics'] = text.name
        context.window_manager.clipboard = payload
        self.report({'INFO'}, 'Diagnostics copied; also available in the Text Editor')
        return {'FINISHED'}


CLASSES = (MW4ANIM_OT_load_animations, MW4ANIM_OT_choose_animation, MW4ANIM_OT_step_animation, MW4ANIM_OT_rest_pose, MW4ANIM_OT_copy_diagnostics)
