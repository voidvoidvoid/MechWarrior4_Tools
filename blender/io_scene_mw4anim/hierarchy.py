"""Parse extracted MW4 .contents armature records without inventing pivots.

MWMover_LoadChildRecords (006083f0) skips a two-byte prefix, then walks
length-prefixed entity records. The supplied named armature records are 280
bytes; their entity affine matrix begins at +0x1c, inline name at +0x98.
"""
import json
import math
from pathlib import Path
import re
import struct
import zipfile
from .codec import FormatError

PATTERN = re.compile(r'^(.*\.contents)(?:\[([^\]]+)\]\{armature\})?$',re.I)

def read_records(data, parent, source):
    if len(data) < 2:
        raise FormatError(f'{source}: missing two-byte prefix')
    result = []
    offset = 2
    while offset < len(data):
        if offset+4 > len(data):
            raise FormatError(f'{source}: truncated record length')
        size = struct.unpack_from('<I',data,offset)[0]
        if size != 280 or offset+size > len(data):
            raise FormatError(f'{source}: unsupported armature record size {size}')
        record = data[offset:offset+size]
        end = record.find(b'\0',152)
        if end < 0:
            raise FormatError(f'{source}: unterminated node name')
        name = record[152:end].decode('ascii')
        if not re.fullmatch(r'[A-Za-z0-9_ .-]{1,63}',name):
            raise FormatError(f'{source}: unexpected node name {name!r}')
        values = struct.unpack_from('<12f',record,28)
        if not all(math.isfinite(v) for v in values):
            raise FormatError(f'{source}: non-finite transform')
        # Rigid transforms only. Preserve genuine rotations, reject shear/scale
        # until their semantics have been researched rather than dropping them.
        rows = [values[i:i+3] for i in (0,4,8)]
        for i in range(3):
            for j in range(3):
                dot = sum(a*b for a,b in zip(rows[i],rows[j]))
                if abs(dot-(1 if i==j else 0)) > 1e-4:
                    raise FormatError(f'{source}: non-rigid transform')
        determinant = (rows[0][0]*(rows[1][1]*rows[2][2]-rows[1][2]*rows[2][1])
            -rows[0][1]*(rows[1][0]*rows[2][2]-rows[1][2]*rows[2][0])
            +rows[0][2]*(rows[1][0]*rows[2][1]-rows[1][1]*rows[2][0]))
        if abs(determinant-1)>1e-4:
            raise FormatError(f'{source}: reflected transform unsupported')
        result.append({'name':name,'parent':parent,'matrix':list(values),
                       'source':source,'record_offset':offset})
        offset += size
    return result

def load_hierarchy(filepath):
    path = Path(filepath)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            files = {n:z.read(n) for n in z.namelist() if PATTERN.fullmatch(n)}
    else:
        # Select the top-level .contents file. Include sibling named resources.
        if not path.name.lower().endswith('.contents'):
            raise FormatError('Select the main .contents file or an extracted asset ZIP')
        files = {p.name:p.read_bytes() for p in path.parent.iterdir()
                 if p.is_file() and PATTERN.fullmatch(p.name)}
    roots = [n for n in files if n.lower().endswith('.contents')]
    if len(roots) != 1:
        raise FormatError('Choose an asset folder/ZIP containing exactly one main .contents file')
    base = roots[0]
    nodes = []
    for name,data in sorted(files.items()):
        match = PATTERN.fullmatch(name)
        if match.group(1) == base:
            nodes.extend(read_records(data,match.group(2),name))
    mapping = {}
    for node in nodes:
        if node['name'] in mapping:
            raise FormatError('Duplicate hierarchy node: '+node['name'])
        mapping[node['name']] = node
    for node in nodes:
        if node['parent'] is not None and node['parent'] not in mapping:
            raise FormatError('Missing parent: '+node['parent'])
    ordered, done = [],set()
    while len(done) < len(nodes):
        pending = [n for n in nodes if n['name'] not in done and
                   (n['parent'] is None or n['parent'] in done)]
        if not pending:
            raise FormatError('Cycle in armature hierarchy')
        for node in pending:
            ordered.append(node);done.add(node['name'])
    if sum(n['parent'] is None for n in nodes) != 1:
        raise FormatError('Expected one hierarchy root')
    return {'schema':1,'name':Path(base).name[:-9], 'nodes':ordered,
            'source':str(path),'geometry_available':False}
