"""Exercise actual Blender properties/callbacks and path-derived categories."""
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
import io_scene_mw4anim as addon
from io_scene_mw4anim import game_import as ui,resource_browser as browser
addon.register()
rows=[{'name':n,'archive':0} for n in ['content/mechs/uller/uller.contents',
 'Mechs\\uller\\body.erf','missions/desert/air_control_tower.erf',
 'missions/arctic/radio_tower.erf','vehicles/tank/tank.contents','root.erf']]
ui.configure_models(SimpleNamespace(archives=[{'relative':'props.mw4'}]),rows)
# Register a property group with the operator properties to drive RNA callbacks.
class FilterProbe(bpy.types.PropertyGroup):
 reset_model=ui.MW4ANIM_OT_game_model.reset_model
 reset_category=ui.MW4ANIM_OT_game_model.reset_category
 reset_scope=ui.MW4ANIM_OT_game_model.reset_scope
 __annotations__={k:v for k,v in ui.MW4ANIM_OT_game_model.__annotations__.items()
                  if k in ('category','subfolder','resource_type','model','search')}
bpy.utils.register_class(FilterProbe)
bpy.types.Scene.mw4_filter_probe=bpy.props.PointerProperty(type=FilterProbe)
p=bpy.context.scene.mw4_filter_probe
p.resource_type='ERF';p.category='missions'
assert len(ui.model_items(p,None))==2
p.subfolder='missions/desert';assert p.model=='2'
p.search='air tower';assert p.model=='2'
p.search='no such asset';assert p.model=='__NONE__'
p.search='';p.category='mechs';assert p.subfolder==browser.ALL and p.model=='1'
p.resource_type='CONTENTS';assert p.model=='0'
p.category='vehicles';assert p.model=='4'
p.category=browser.ALL;assert len(ui.model_items(p,None))==2
p.category='missions';assert p.resource_type=='ERF'
p.subfolder='missions/desert';assert p.model=='2'
p.resource_type='CONTENTS';assert p.model=='__NONE__'
p.subfolder='missions/arctic';assert p.resource_type=='ERF' and p.model=='3'
assert {item[0] for item in ui.category_items(p,None)}=={browser.ALL,browser.ROOT,'mechs','missions','vehicles'}
# Returned enum strings/items persist across calls (Blender dynamic enum lifetime).
assert ui.model_items(p,None) is ui.model_items(p,None)
rows.append(dict(name='maps/test/test.erf',archive=0,map_root=True))
ui.configure_models(SimpleNamespace(archives=[{'relative':'props.mw4'}]),rows)
p.resource_type='CONTENTS';p.category='maps'
assert p.resource_type=='MAP' and p.model=='6'
p.search='missing';assert p.model=='__NONE__' and p.resource_type=='MAP'
p.search='';assert p.model=='6'
p.category='mechs';assert p.resource_type=='CONTENTS' and p.model=='0'
del bpy.types.Scene.mw4_filter_probe;bpy.utils.unregister_class(FilterProbe)
addon.unregister()
print('Category/folder/search/type filtering and empty-selection callbacks PASS')
