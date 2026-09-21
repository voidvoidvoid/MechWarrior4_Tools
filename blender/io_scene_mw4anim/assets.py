"""Asset-neutral standalone ERF import using the existing reversible mesh pipeline."""
from pathlib import Path
import bpy
from . import archives, erf


erf_bundle = archives.erf_bundle


def erf_hierarchy(name):
    return {'schema':1,'name':Path(name).stem,'source':name,'geometry_available':True,
        'nodes':[{'name':'asset_root','parent':None,
            'matrix':[1,0,0,0,0,1,0,0,0,0,1,0]}]}


class MW4ANIM_OT_erf_import(bpy.types.Operator):
    bl_idname='import_scene.mw4_erf'
    bl_label='Import Standalone MW4 ERF'
    bl_options={'REGISTER','UNDO'}
    filepath:bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob:bpy.props.StringProperty(default='*.erf',options={'HIDDEN'})
    def invoke(self,context,event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    def execute(self,context):
        from . import game_import,textures
        try:
            path=Path(self.filepath)
            if path.stat().st_size>archives.helm.DEFAULT_LIMIT:raise ValueError('ERF exceeds 64 MiB')
            files,report=erf_bundle(path.name,path.read_bytes())
            prefs=game_import.preferences(context)
            directory=bpy.path.abspath(prefs.game_directory) if prefs and prefs.game_directory else ''
            if directory:
                try:
                    catalog=archives.Catalog(directory,bpy.path.abspath(prefs.key_source) if prefs.key_source else '')
                    textures.collect(catalog,files,report)
                except (OSError,ValueError,RuntimeError) as exc:
                    report['warnings'].append('Texture lookup: '+str(exc))
            obj,report=game_import.import_resource_files(files,report,context,False,game_directory=directory)
            if obj is None:raise ValueError('ERF import failed; see resource report')
        except (OSError,ValueError,RuntimeError) as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        tx=report.get('texture_import',{})
        missing=len(tx.get('missing',[]));errors=len(tx.get('errors',[]))+len(report.get('texture_resources',{}).get('errors',[]))
        message=f"{obj['mw4_mesh_count']} mesh objects; {len(tx.get('images',[]))} textures, {missing} missing, {errors} errors"
        if missing or errors:message+=textures.problem_summary(report)+' Use Load / Reload Textures from MW4 and Copy diagnostics.'
        self.report({'WARNING'} if missing or errors else {'INFO'},message)
        return {'FINISHED'}


CLASSES=(MW4ANIM_OT_erf_import,)
