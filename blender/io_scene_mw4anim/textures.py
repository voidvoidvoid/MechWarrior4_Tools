"""Exact archive texture lookup and packed Blender materials.

MW4 004cd390 resolves content/textures/<name>.tga, then .png.
The @ prefix is literal (004cd680); runtime skin compositing is separate.
"""
import base64
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import zipfile
import bpy
from . import archives, erf, embedded


def references(files):
    result = set()
    for name, data in files.items():
        if not name.endswith('.erf'): continue
        try:
            shape = erf.loads(data)
            for lod in shape['lods']:
                for mesh in lod['meshes']:
                    if mesh['texture']: result.add(mesh['texture'])
        except ValueError:
            pass  # The mesh importer records unsupported geometry separately.
    return sorted(result)


def texture_key(name):
    """The engine's content/ mount prefix is not always stored in VBD names."""
    name = archives.normalized(name)
    return name[8:] if name.startswith('content/') else name


def texture_paths(reference):
    stem = texture_key(reference)
    if not stem.startswith('textures/'): stem = 'textures/' + stem
    return [stem] if stem.endswith(('.tga', '.png')) else [stem+'.tga', stem+'.png']


def collect(catalog, files, report, refs=None, overrides=None):
    index = {}
    for row in catalog.rows:
        index.setdefault(texture_key(row['name']), []).append(row)
    mappings = {}; hints = {}; missing = []; errors = []
    overrides = overrides or {}
    def get(name):
        candidates = index.get(texture_key(name), [])
        row = catalog.unique(candidates)
        if row is None: return None
        data, method = catalog.read(row)
        name = archives.normalized(row['name'])
        archives.helm.safe_parts(name)
        if name in files and files[name] != data:
            raise ValueError('Texture conflicts with collected resource: ' + name)
        files[name] = data
        if not any(archives.normalized(r['name']) == name for r in report['resources']):
            report['resources'].append(dict(catalog.describe(row), **method,
                sha256=hashlib.sha256(data).hexdigest(), bytes=len(data)))
        return name
    for ref in refs if refs is not None else references(files):
        names = texture_paths(overrides.get(ref, ref))
        try:
            for path in names:
                actual = get(path)
                if actual is not None:
                    mappings[ref] = actual
                    hint = get(path+'{hint}')
                    if hint is not None: hints[ref] = hint
                    break
            else: missing.append({'reference': ref, 'searched': [p for n in names for p in (n, 'content/'+n)]})
        except (OSError, ValueError) as exc:
            errors.append({'reference': ref, 'error': str(exc)})
    texture_archives = [i for i, a in enumerate(catalog.archives)
                        if Path(a['relative']).name.casefold() == 'textures.mw4']
    diagnostic_rows = [r for r in catalog.rows if r['archive'] in texture_archives]
    report['texture_resources'] = {'mapping': mappings, 'hint_mapping': hints,
        'missing': missing, 'errors': errors,
        'lookup': 'Full texture paths; optional content/ prefix, case and slash normalization',
        'archive_diagnostics': {'texture_archives': [catalog.archives[i]['relative'] for i in texture_archives],
            'indexed_members': len(diagnostic_rows),
            'sample_image_names': [r['name'] for r in diagnostic_rows
                if archives.normalized(r['name']).endswith(('.tga','.png','.dds'))][:16]},
        'scope': 'Original detail images; runtime camouflage/team/pilot substitution is not emulated.'}
    return report['texture_resources']


def material_references(root):
    return sorted({slot.material['mw4_texture_reference']
        for obj in root.children_recursive if obj.type == 'MESH'
        for slot in obj.material_slots if slot.material
        and slot.material.get('mw4_texture_reference')
        and slot.material['mw4_texture_reference'] != 'Untextured'})


def show_textures(context):
    # The import operator can finish from a file browser rather than a viewport.
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.shading.type = 'MATERIAL'


def apply(files, report, root):
    mapping = report.get('texture_resources', {}).get('mapping', {})
    result = {'materials': 0, 'images': [], 'missing': [], 'errors': []}
    materials = {}
    for obj in root.children_recursive:
        if obj.type != 'MESH': continue
        for slot in obj.material_slots:
            mat = slot.material
            if mat and mat.get('mw4_texture_reference'):
                materials.setdefault(mat.as_pointer(), (mat, []))[1].append(slot)
    with tempfile.TemporaryDirectory(prefix='mw4_textures_') as tmp:
        for mat, slots in materials.values():
            ref = mat['mw4_texture_reference']
            if ref == 'Untextured': continue
            path = mapping.get(ref)
            # Older bundles can already contain directly named images.
            if not path and 'texture_resources' not in report:
                path = next((p for n in texture_paths(ref) for p in (n, 'content/'+n) if p in files), None)
            if not path or path not in files:
                result['missing'].append(ref); continue
            try:
                data = files[path]; digest = hashlib.sha256(data).hexdigest()
                img = next((i for i in bpy.data.images if i.get('mw4_sha256') == digest and i.packed_file), None)
                if img is None:
                    local = Path(tmp) / (digest + Path(path).suffix)
                    local.write_bytes(data)
                    img = bpy.data.images.load(str(local), check_existing=False)
                    if not img.size[0] or not img.size[1]:
                        bpy.data.images.remove(img)
                        raise ValueError('Blender could not decode image')
                    img.name = 'MW4 · '+Path(path).name
                    img['mw4_sha256'] = digest; img['mw4_archive_member'] = path
                    img.pack()
                    img.filepath = '//mw4_textures/'+digest+Path(path).suffix
                # A private material prevents changing other imported models/skins.
                target = mat.copy(); target.use_nodes = True
                target.name = root.name+' · '+ref
                nodes = target.node_tree.nodes; links = target.node_tree.links
                shader = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
                if shader is None: raise ValueError('Material has no Principled shader')
                for old in list(nodes):
                    if old.get('mw4_texture_node'): nodes.remove(old)
                node = nodes.new('ShaderNodeTexImage'); node.image = img
                node['mw4_texture_node'] = True; node.location = (-450, 200)
                links.new(node.outputs['Color'], shader.inputs['Base Color'])
                hint_name = report.get('texture_resources', {}).get('hint_mapping', {}).get(ref, path+'{hint}')
                hint = files.get(hint_name, b'')
                fmt = (struct.unpack('<I', hint)[0] >> 16) & 255 if len(hint) == 4 else None
                # Skin detail alpha is a camouflage mask, not surface transparency.
                alpha = (not ref.startswith('@') or ref.casefold() in ('@pilot', '@team')) and fmt in (1, 2)
                for link in list(shader.inputs['Alpha'].links): links.remove(link)
                shader.inputs['Alpha'].default_value = 1
                if alpha:
                    links.new(node.outputs['Alpha'], shader.inputs['Alpha'])
                    target.surface_render_method = 'DITHERED'
                target['mw4_texture_image_missing'] = False
                target['mw4_texture_archive_member'] = path
                for slot in slots: slot.material = target
                result['materials'] += 1
                if path not in result['images']: result['images'].append(path)
            except (OSError, ValueError, RuntimeError) as exc:
                result['errors'].append({'reference': ref, 'error': str(exc)})
    report['texture_import'] = result
    if 'mesh_import' in report:
        report['mesh_import']['textures'] = f"{len(result['images'])} packed images; {len(result['missing'])} unresolved materials"
    root['mw4_texture_count'] = len(result['images'])
    root['mw4_texture_status'] = (f"{len(result['images'])} textures; "
        f"{len(result['missing'])} missing; "
        f"{len(result['errors']) + len(report.get('texture_resources', {}).get('errors', []))} errors")
    return result


class MW4ANIM_OT_textures(bpy.types.Operator):
    bl_idname = 'import_scene.mw4_textures'
    bl_label = 'Load Textures from MW4 Installation'
    bl_options = {'REGISTER', 'UNDO'}
    directory: bpy.props.StringProperty(name='MW4 installation directory', subtype='DIR_PATH')
    filter_folder: bpy.props.BoolProperty(default=True, options={'HIDDEN'})
    overrides: bpy.props.StringProperty(name='Texture overrides (JSON)', default='{}',
        description='Optional exact reference-to-texture mapping, for example {"@team":"my_insignia"}')

    @classmethod
    def poll(cls, context):
        from . import clip_root
        root = clip_root(context.object)
        return root is not None and bool(material_references(root))

    def invoke(self, context, event):
        from . import clip_root, game_import
        root = clip_root(context.object); prefs = game_import.preferences(context)
        self.directory = root.get('mw4_game_directory', '') or (prefs.game_directory if prefs else '')
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        from . import clip_root, meshes, game_import
        root = clip_root(context.object)
        try:
            overrides = json.loads(self.overrides)
            if not isinstance(overrides, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k,v in overrides.items()):
                raise ValueError('Texture overrides must be a JSON object with string names')
            prefs = game_import.preferences(context)
            catalog = archives.Catalog(bpy.path.abspath(self.directory),
                bpy.path.abspath(prefs.key_source) if prefs and prefs.key_source else '')
            text = bpy.data.texts.get(root.get('mw4_resource_bundle', ''))
            if text is not None:
                files, report = meshes.read_bundle(io.BytesIO(embedded.decode(text.as_string())))
            else:
                files, report = {}, {'resources': []}
            collect(catalog, files, report, refs=material_references(root), overrides=overrides)
            result = apply(files, report, root)
            if text is not None:
                packed = io.BytesIO(); archives.write_bundle(packed, files, report)
                text.from_string(embedded.encode(packed.getvalue()))
            rpt = bpy.data.texts.get(root.get('mw4_resource_report', ''))
            if rpt is None:
                rpt = bpy.data.texts.new(root.name + ' · MW4 texture report')
                root['mw4_resource_report'] = rpt.name
            rpt.clear(); rpt.write(json.dumps(report, indent=2))
            show_textures(context)
            root['mw4_game_directory'] = str(catalog.root)
            if prefs: prefs.game_directory = str(catalog.root)
        except (ValueError, OSError, RuntimeError, KeyError, zipfile.BadZipFile) as exc:
            self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
        errors = len(result['errors']) + len(report['texture_resources']['errors'])
        self.report({'WARNING'} if result['missing'] or errors else {'INFO'},
            f"{len(result['images'])} textures packed; {len(result['missing'])} unresolved materials; {errors} errors. Use Material Preview to view textures.")
        return {'FINISHED'}


class MW4ANIM_OT_material_preview(bpy.types.Operator):
    bl_idname = 'mw4.material_preview'
    bl_label = 'Show Textures (Material Preview)'
    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'
    def execute(self, context):
        context.space_data.shading.type = 'MATERIAL'
        return {'FINISHED'}


CLASSES = (MW4ANIM_OT_textures, MW4ANIM_OT_material_preview)
