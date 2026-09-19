"""MW4ANIM 2.1 reader/writer. No Blender or third-party dependencies.

The engine layout is documented in FORMAT.md. Unknown header/channel bytes
are retained. Editing tracks rebuilds section offsets without inventing rig data.
"""
from dataclasses import dataclass, replace
import math
import struct

JOINT_NAMES = (
    'joint_cage', 'joint_centertorsofront', 'joint_centertorsorear', 'joint_head',
    'joint_hip', 'joint_hipabove', 'joint_hipbelow', 'joint_lankle',
    'joint_lbelowankle', 'joint_lbtoe', 'joint_ldleg', 'joint_lefttorsofront',
    'joint_lfoot', 'joint_lftoe', 'joint_lgun', 'joint_lgunabove', 'joint_litoe',
    'joint_lmissile', 'joint_lmleg', 'joint_lotoe', 'joint_ltoe', 'joint_luarm',
    'joint_luleg', 'joint_rankle', 'joint_rbelowankle', 'joint_rbtoe',
    'joint_rdleg', 'joint_rfoot', 'joint_rftoe', 'joint_rgun', 'joint_rgunabove',
    'joint_righttorsofront', 'joint_ritoe', 'joint_rmissile', 'joint_rmleg',
    'joint_root', 'joint_rotoe', 'joint_rtoe', 'joint_ruarm', 'joint_ruleg',
    'joint_specialone', 'joint_specialtwo', 'joint_torso', 'joint_torsoabove',
    'joint_torsobelow', 'joint_vel', 'joint_world',
)
KINDS = {0: 'position_and_linear_motion', 1: 'position', 2: 'quaternion',
         3: 'variant_bits', 4: 'quaternion_and_angular_motion'}
STRIDES = {0: 24, 1: 12, 2: 16, 3: 4, 4: 28}

class FormatError(ValueError):
    pass

@dataclass(frozen=True)
class Channel:
    name: str
    encoded_name: bytes
    first_track: int
    track_count: int
    raw: bytes

@dataclass(frozen=True)
class Track:
    stride: int
    kind: int
    flag: int
    channel: int
    times: tuple
    values: tuple
    raw_values: bytes
    raw_times: bytes

@dataclass(frozen=True)
class Clip:
    name: str
    start: float
    end: float
    channels: tuple
    tracks: tuple
    original: bytes
    header: bytes
    names: bytes
    channel_bytes: bytes

def _require(ok, message):
    if not ok:
        raise FormatError(message)

def decode_name(raw):
    if len(raw) == 2 and raw[0] == 35 and raw[1] >= 128:
        idx = raw[1] - 128
        return JOINT_NAMES[idx] if idx < len(JOINT_NAMES) else f'joint_id_{idx}'
    return raw.decode('latin1')

def loads(data):
    data = bytes(data)
    _require(len(data) >= 101, 'Truncated header (requires 101 bytes)')
    _require(data[0] == 0, 'Only extracted, zero-prefix MW4ANIM files are supported')
    b = data[1:]
    _require(struct.unpack_from('<II', b) == (2, 1), 'Only animation version 2.1 is supported')
    start, end = struct.unpack_from('<ff', b, 8)
    _require(math.isfinite(start) and math.isfinite(end) and end >= start,
             'Invalid animation time range')
    size = struct.unpack_from('<I', b, 16)[0]
    _require(size == len(b), 'Header end offset does not match file length')
    c, n, v, t, d = struct.unpack_from('<5I', b, 24)
    _require(100 <= c <= n <= v <= t <= d <= size, 'Invalid section offsets')
    _require((n-c) % 12 == 0 and (size-d) % 16 == 0, 'Misaligned channel/track table')
    nc, nt = (n-c)//12, (size-d)//16
    _require(0 < nc <= 255 and 0 < nt <= 255, 'Unsupported channel/track count (1..255)')
    names = b[n:v]
    channels = []
    for i in range(nc):
        raw = b[c+i*12:c+(i+1)*12]
        noff, first = struct.unpack_from('<II', raw)
        count = raw[8]
        _require(noff < len(names), f'Channel {i}: name offset outside name table')
        stop = names.find(b'\0', noff)
        _require(stop != -1, f'Channel {i}: unterminated name')
        encoded = names[noff:stop]
        _require(first + count <= nt, f'Channel {i}: track range outside table')
        channels.append(Channel(decode_name(encoded), encoded, first, count, raw))
    tracks = []
    for i in range(nt):
        stride, voff, toff, count, kind, flag, channel = struct.unpack_from('<IIIBBBB', b, d+i*16)
        _require(kind in STRIDES and stride == STRIDES[kind],
                 f'Track {i}: unsupported type/stride {kind}/{stride}')
        _require(0 < count <= 255 and channel < nc, f'Track {i}: invalid count/channel')
        _require(voff + count*stride <= t-v and toff + count*4 <= d-t,
                 f'Track {i}: keyframes outside section')
        raw_values = b[v+voff:v+voff+count*stride]
        raw_times = b[t+toff:t+toff+count*4]
        times = struct.unpack('<'+'f'*count, raw_times)
        _require(all(math.isfinite(x) for x in times) and
                 all(x < y for x,y in zip(times,times[1:])),
                 f'Track {i}: non-finite or non-increasing key times')
        _require(times[0] >= start-1e-5 and times[-1] <= end+1e-5,
                 f'Track {i}: keys outside clip range')
        fmt = '<I' if kind == 3 else '<'+'f'*(stride//4)
        values = tuple(struct.unpack_from(fmt, raw_values, k*stride) for k in range(count))
        _require(kind == 3 or all(math.isfinite(x) for row in values for x in row),
                 f'Track {i}: non-finite value')
        ch = channels[channel]
        _require(ch.first_track <= i < ch.first_track+ch.track_count,
                 f'Track {i}: channel table disagrees with descriptor')
        tracks.append(Track(stride,kind,flag,channel,tuple(times),values,raw_values,raw_times))
    name = b[44:100].split(b'\0',1)[0].decode('latin1')
    return Clip(name,start,end,tuple(channels),tuple(tracks),data,b[:c],names,b[c:n])

def dumps(clip, replacements=None, *, start=None, end=None, force_rebuild=False):
    """Replace track index -> (times, value rows); retain all other metadata.

    Track type/order/channel mapping cannot be changed through this interface.
    Unchanged tracks retain their exact bytes, including negative zero.
    """
    replacements = replacements or {}
    _require(all(isinstance(i,int) and 0 <= i < len(clip.tracks) for i in replacements),
             'Unknown replacement track')
    start = clip.start if start is None else float(start)
    end = clip.end if end is None else float(end)
    if not replacements and start == clip.start and end == clip.end and not force_rebuild:
        return clip.original
    vb, tb, descriptors = bytearray(), bytearray(), bytearray()
    for i,tr in enumerate(clip.tracks):
        if i in replacements:
            times, values = replacements[i]
            _require(len(times) == len(values) and 1 <= len(times) <= 255,
                     f'Track {i}: requires 1..255 matching keys/times')
            try:
                time_raw = struct.pack('<'+'f'*len(times), *times)
                fmt = '<I' if tr.kind == 3 else '<'+'f'*(tr.stride//4)
                value_raw = b''.join(struct.pack(fmt,*row) for row in values)
            except (struct.error, OverflowError, TypeError) as e:
                raise FormatError(f'Track {i}: invalid key data: {e}') from e
            count = len(times)
        else:
            time_raw, value_raw, count = tr.raw_times, tr.raw_values, len(tr.times)
        descriptors.extend(struct.pack('<IIIBBBB',tr.stride,len(vb),len(tb),count,
                                       tr.kind,tr.flag,tr.channel))
        vb.extend(value_raw)
        tb.extend(time_raw)
    header = bytearray(clip.header)
    c = len(header)
    n = c + len(clip.channel_bytes)
    v = n + len(clip.names)
    t = v + len(vb)
    d = t + len(tb)
    struct.pack_into('<ffI',header,8,start,end,d+len(descriptors))
    struct.pack_into('<5I',header,24,c,n,v,t,d)
    out = b'\0' + header + clip.channel_bytes + clip.names + vb + tb + descriptors
    loads(out)  # Validate before returning bytes to a caller that may write them.
    return bytes(out)
