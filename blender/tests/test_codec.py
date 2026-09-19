"""Run: python tests/test_codec.py /path/to/bushwacker.zip"""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('mw4_codec',ROOT/'io_scene_mw4anim/codec.py')
codec = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = codec
spec.loader.exec_module(codec)
SAMPLE = Path(sys.argv.pop(1))
ARCHIVE = zipfile.ZipFile(SAMPLE)
CLIPS = {n:ARCHIVE.read(n) for n in ARCHIVE.namelist() if n.endswith('.mw4anim')}

class CodecTests(unittest.TestCase):
    def test_all_samples_rebuild_exactly(self):
        self.assertEqual(len(CLIPS),154)
        for name,data in CLIPS.items():
            with self.subTest(name=name):
                clip = codec.loads(data)
                self.assertEqual(codec.dumps(clip),data)
                self.assertEqual(codec.dumps(clip,force_rebuild=True),data)

    def test_edit_every_track_type(self):
        found = set()
        for data in CLIPS.values():
            clip = codec.loads(data)
            for i,tr in enumerate(clip.tracks):
                if tr.kind in found:
                    continue
                found.add(tr.kind)
                rows = [list(v) for v in tr.values]
                rows[0][0] = rows[0][0] ^ 1 if tr.kind == 3 else rows[0][0]+0.125
                out = codec.loads(codec.dumps(clip,{i:(tr.times,rows)}))
                self.assertEqual(out.tracks[i].values[0][0],rows[0][0])
                self.assertEqual(out.header,clip.header)
                self.assertEqual(out.channel_bytes,clip.channel_bytes)
                self.assertEqual(out.names,clip.names)
                for j,other in enumerate(out.tracks):
                    if j != i:
                        self.assertEqual(other,clip.tracks[j])
        self.assertEqual(found,set(range(5)))

    def test_insert_key_and_relocate_sections(self):
        clip = codec.loads(CLIPS['bushwacker/animation/bw_walk.mw4anim'])
        i = 2
        tr = clip.tracks[i]
        times = list(tr.times)
        rows = list(tr.values)
        times.insert(1,(times[0]+times[1])/2)
        rows.insert(1,tuple((a+b)/2 for a,b in zip(rows[0],rows[1])))
        out = codec.loads(codec.dumps(clip,{i:(times,rows)}))
        self.assertEqual(len(out.tracks[i].times),len(tr.times)+1)
        for j in range(len(clip.tracks)):
            if j != i:
                self.assertEqual(out.tracks[j],clip.tracks[j])

    def test_bad_inputs_and_limits(self):
        data = CLIPS['bushwacker/animation/bw_walk.mw4anim']
        bad = [b'',data[:100],data[:-1],bytes([1])+data[1:]]
        b = bytearray(data);struct.pack_into('<I',b,25,20000);bad.append(b)
        b = bytearray(data);struct.pack_into('<I',b,5,9);bad.append(b)
        for b in bad:
            with self.assertRaises(codec.FormatError):
                codec.loads(b)
        clip = codec.loads(data)
        for times,rows in [([0]*256,[(0,0,0)]*256),
                           ([0,0],[(0,0,0)]*2),
                           ([float('nan')],[(0,0,0)]),
                           ([0],[(float('inf'),0,0)]),
                           ([99],[(0,0,0)])]:
            with self.assertRaises(codec.FormatError):
                codec.dumps(clip,{2:(times,rows)})

    def test_name_table(self):
        self.assertEqual(codec.decode_name(b'#\xad'),'joint_vel')
        self.assertEqual(codec.decode_name(b'#\xa3'),'joint_root')
        self.assertEqual(codec.decode_name(b'site_lfoot'),'site_lfoot')

if __name__ == '__main__':
    unittest.main()
