"""External sample regression: core.zip props.zip output.json (no assets bundled).
Checks every clip and three poses against raw parent-local transform composition.
Root motion types 0/4 remain preserved data, as in previous releases.
"""
import bisect,json,sys,tempfile,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
from mathutils import Matrix,Quaternion,Vector
from io_scene_mw4anim import codec,hierarchy,rig,animscript
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
corepath,propspath,out=map(Path,args)

def affine(v):return Matrix((v[:4],v[4:8],v[8:12],(0,0,0,1)))
def sample(tr,t):
    j=max(0,min(bisect.bisect_right(tr.times,t)-1,len(tr.times)-1))
    if j+1==len(tr.times):return tr.values[j]
    f=max(0,min(1,(t-tr.times[j])/(tr.times[j+1]-tr.times[j])))
    return [a+(b-a)*f for a,b in zip(tr.values[j],tr.values[j+1])]

results={'blender':bpy.app.version_string,'scope':'Raw hierarchy/clip transforms; no ERF polygons supplied; root motion/state-machine blending excluded','models':{}}
with zipfile.ZipFile(corepath) as core,zipfile.ZipFile(propspath) as props,tempfile.TemporaryDirectory() as td:
    models=sorted({n.split('/')[0] for n in core.namelist() if n.endswith('.contents')})
    for model in models:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        path=Path(td)/'hierarchy.zip'
        with zipfile.ZipFile(path,'w') as z:
            for name in core.namelist():
                if name.startswith(model+'/') and hierarchy.PATTERN.fullmatch(name):z.writestr(name,core.read(name))
        obj=rig.build_armature(path,bpy.context);info=json.loads(obj['mw4_hierarchy'])
        result={'bones':len(info['nodes']),'clips':0,'byte_identical_exports':0,'joint_pose_checks':0,'max_matrix_error':0,'unbound':[]}
        names=sorted(n for n in props.namelist() if n.startswith(model+'/') and n.endswith('.mw4anim'))
        for name in names:
            raw=props.read(name);clip=codec.loads(raw);cp=Path(td)/'clip.mw4anim';cp.write_bytes(raw)
            action=rig.import_action(cp,bpy.context,obj);action['mw4_archive_member']=name
            assert rig.export_action(obj)==raw,name
            result['byte_identical_exports']+=1;result['clips']+=1
            result['unbound']+=json.loads(bpy.data.texts[action['mw4_rig_metadata']].as_string())['unbound_names']
            for fraction in (0,.37,1):
                t=clip.start+fraction*(clip.end-clip.start);frame=1+(t-clip.start)*30
                bpy.context.scene.frame_set(int(frame),subframe=frame-int(frame));bpy.context.view_layer.update()
                local={n['name']:affine(n['matrix']) for n in info['nodes']}
                for tr in clip.tracks:
                    bone=clip.channels[tr.channel].name
                    if bone not in local or tr.kind not in (1,2):continue
                    v=sample(tr,t)
                    if tr.kind==1:local[bone].translation=Vector(v)
                    else:
                        translation=local[bone].translation.copy();q=Quaternion((v[3],v[0],v[1],v[2]));q.normalize()
                        local[bone]=q.to_matrix().to_4x4();local[bone].translation=translation
                world={}
                for n in info['nodes']:
                    bone=n['name'];world[bone]=world[n['parent']]@local[bone] if n['parent'] else local[bone]
                    correction=Quaternion(n['bone_correction']).to_matrix().to_4x4()
                    actual=obj.pose.bones[bone].matrix@correction.inverted()
                    error=max(abs(actual[i][j]-world[bone][i][j]) for i in range(4) for j in range(4))
                    result['max_matrix_error']=max(result['max_matrix_error'],error);result['joint_pose_checks']+=1
                    assert error<0.0002,(model,name,bone,fraction,error)
        result['unbound']=sorted(set(result['unbound']))
        script=animscript.parse(props.read(model+'/'+model+'.animscript'))
        result['script_paths']=len(script['paths']);result['script_errors']=script['errors'];result['preferred']=script['preferred']
        actions=list(bpy.data.actions)
        preview=animscript.choose_action(actions,{model+'.animscript':props.read(model+'/'+model+'.animscript')})
        result['available_preview']=preview.get('mw4_archive_member') if preview else None
        if model=='uller':
            assert len(names)==7 and preview is None
            assert any('/cougar/' in p for p in script['paths'])
        results['models'][model]=result
        print(model,json.dumps(result),flush=True)
out.write_text(json.dumps(results,indent=2))
