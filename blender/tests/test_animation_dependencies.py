"""Asset-free archive/dependency regression. Run with Blender Python."""
import json,struct,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from io_scene_mw4anim import archives,animscript

def vbd(path, entries):
    index=[];payload=bytearray()
    for rid,(name,data) in enumerate(entries,1):
        nb=name.encode();index.append(struct.pack('<QIIIHB',0,len(data),len(data),len(payload),rid,len(nb))+nb);payload+=data
    index=b''.join(index)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(struct.pack('<4sIIIHH',b'#VBD',4,0,20+len(index),len(entries),len(entries))+index+payload)

script=b'''!MODEL=SharedDonor
!PATH=content\\Mechs
!Walk=$(PATH)\\$(MODEL)\\animation\\donor_walk
!StandPose=$(PATH)\\$(MODEL)\\animation\\donor_standpose
!Absent=$(PATH)\\$(MODEL)\\animation\\donor_missing
[WalkState]
Anim=$(Walk)
'''
with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    vbd(root/'Resource'/'core.mw4',[
        ('mechs/recipient/recipient.contents',b'\0\0'),
        ('mechs/recipient/recipient.animscript',script),
        ('mechs/recipient/animation/local_getup.mw4anim',b'local fixture')])
    vbd(root/'Resource'/'props.mw4',[
        ('mechs/shareddonor/animation/donor_walk.mw4anim',b'walk fixture'),
        ('CONTENT/MECHS/SHAREDDONOR/animation/donor_standpose.mw4anim',b'stand fixture'),
        ('mechs/unrelated/animation/donor_missing.mw4anim',b'wrong mech')])
    catalog=archives.Catalog(root);files,report=catalog.collect(catalog.models()[0]);dep=report['animation_dependencies']
    assert len(dep['collected'])==2 and len(dep['missing'])==1 and not dep['errors'],dep
    assert len(report['animation_files'])==3
    assert not any('/unrelated/' in n for n in files)
    actions=[{'mw4_archive_member':n} for n in report['animation_files']]
    assert animscript.choose_action(actions,files)['mw4_archive_member'].endswith('donor_walk.mw4anim')
    only_fall=[{'mw4_archive_member':'mechs/recipient/animation/local_getup.mw4anim'}]
    assert animscript.choose_action(only_fall,files) is None
    vbd(root/'conflict.mw4',[('mechs/shareddonor/animation/donor_walk.mw4anim',b'conflicting fixture')])
    catalog=archives.Catalog(root);_,report=catalog.collect(catalog.models()[0])
    assert report['animation_dependencies']['errors']
assert animscript.parse(b'!a=$(b)\n!b=$(a)')['errors']
assert animscript.parse(b'Anim=$(missing)')['errors']
assert not animscript.parse(b'// !Walk=ignored/animation/test')['paths']
print(json.dumps({'passed':True,'checks':['shared clips across archives','content prefix and case aliases','missing and conflicting dependencies','no unrelated same-basename fallback','explicit preview choice','rest fallback','cyclic and undefined macro diagnostics']}))
