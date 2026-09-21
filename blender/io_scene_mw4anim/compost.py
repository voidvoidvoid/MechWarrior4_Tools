"""FGD6 terrain composition and padded BID images. See COMPOST_TEXTURES.md.

Uses NumPy shipped with Blender; never substitutes arbitrary layer textures.
The supported operations correspond to the recovered native compositor modes.
"""
import configparser
import hashlib
import struct
import zlib
import numpy as np
from . import archives, erf
from .codec import FormatError

MAX_PIXELS = 16384*16384


def string(r):
    n = r.u32()
    if n > 4096: raise FormatError('Excessive FGD string length')
    if not n: return ''
    raw = r.take(n+1)
    if raw[-1]: raise FormatError('Unterminated FGD string')
    return raw[:-1].decode('cp1252').casefold()


def read_fgd(data):
    r = erf.Reader(data)
    if r.u32() != 6: raise FormatError('Close terrain textures require FGD version 6')
    count = r.u32()
    if not 0 < count <= 4096: raise FormatError('Invalid FGD feature count')
    features = {}
    for index in range(count):
        if r.u32() != 1: raise FormatError('Unsupported unnamed FGD feature')
        name = string(r)
        values = struct.unpack('<8i',r.take(32))
        refs = [string(r) for _ in range(4)]
        surface, flags, identifier = struct.unpack('<3I',r.take(12))
        if not name or name in features or min(values[:2]) <= 0 or max(values[:2]) > 32768:
            raise FormatError('Invalid FGD feature name or extent')
        if not refs[0] or refs[2] or any(v < 0 or v > 12 for v in values[4:]):
            raise FormatError('Unsupported FGD texture/mask configuration: '+name)
        mode = flags & 0x3fc0
        if mode not in (0x40,0x80,0xc0,0x100,0x180,0x1c0,0x280):
            raise FormatError(f'Unsupported FGD blend mode {mode:#x}: {name}')
        if mode in (0x100,0x1c0,0x280) and not refs[1]:
            raise FormatError('Missing FGD mask/lightmap: '+name)
        features[name] = dict(name=name,index=index,size=values[:2],scales=values[4:6],
            refs=refs,flags=flags,mode=mode,surface=surface,identifier=identifier)
    version, shift, rows, columns, count = struct.unpack('<5I',r.take(20))
    if version != 6 or not 0 < shift <= 12 or not min(rows,columns) or not count or count > 1000000:
        raise FormatError('Invalid FGD placement grid')
    width,height = columns*(1<<shift),rows*(1<<shift)
    if width*height > MAX_PIXELS: raise FormatError('FGD composition exceeds pixel limit')
    instances = []
    for _ in range(count):
        if r.u32() != 1: raise FormatError('Unsupported unnamed FGD placement')
        name = string(r)
        x,y,byte0,byte1,ox,oy = struct.unpack('<HHBBii',r.take(14))
        if name not in features: raise FormatError('Missing FGD feature '+name)
        instances.append(dict(feature=features[name],x=x,y=y,offset=(ox,oy),metadata=(byte0,byte1)))
    if r.p != len(data): raise FormatError('Unconsumed FGD data')
    # Native 006df180 sorts by feature table index, not material ID or file order.
    instances.sort(key=lambda i:i['feature']['index'])
    return dict(features=features,instances=instances,width=width,height=height,shift=shift)


def read_index(data):
    cfg = configparser.ConfigParser(interpolation=None,strict=True)
    try: cfg.read_string(data.decode('cp1252'))
    except (ValueError,configparser.Error) as exc: raise FormatError('Invalid compost TCF index') from exc
    result = {}
    for section in cfg.sections():
        try:
            name=cfg[section]['Name'].casefold()
            kind=int(cfg[section]['Type']);w=int(cfg[section]['Width']);h=int(cfg[section]['Height'])
        except (KeyError,ValueError) as exc: raise FormatError('Invalid compost TCF entry') from exc
        if name in result or min(w,h)<=0 or w*h>MAX_PIXELS or kind not in (1,2,3,5):
            raise FormatError('Unsupported compost image entry: '+name)
        if '/' in name or '\\' in name or '..' in name: raise FormatError('Invalid compost image name')
        result[name] = dict(name=name,kind=kind,width=w,height=h)
    return result


def read_bid(data, entry):
    w,h,kind = entry['width'],entry['height'],entry['kind']
    bpp = 2 if kind in (1,2) else 1
    levels = range(3) if kind in (1,2,5) else range(1)
    size = sum(((w>>n)+2)*((h>>n)+2)*bpp for n in levels)
    if len(data) != size: raise FormatError(f'BID extent mismatch: {entry["name"]}: {len(data)} != {size}')
    # Retain the one-pixel border: scaled mask interpolation reads it at edges.
    raw = np.frombuffer(data,dtype='<u2' if bpp==2 else 'u1',count=(w+2)*(h+2)).reshape(h+2,w+2)
    if kind == 1:
        pixels = np.stack(((raw>>10)&31,(raw>>5)&31,raw&31),axis=-1).astype(np.int32)*8
    elif kind == 2:
        # Native 006e3cc0: high-to-low nibbles are R,G,B,A.
        pixels = np.stack(((raw>>12)&15,(raw>>8)&15,(raw>>4)&15,raw&15),axis=-1).astype(np.int32)*16
    else: pixels = raw.astype(np.int32)[...,None]
    return dict(**entry,pixels=pixels)


def sample_color(image, x, y, flags):
    w,h = image['width'],image['height']
    ix=x%w;iy=y%h
    if flags&1: ix=w-1-ix
    if flags&2: iy=h-1-iy
    return image['pixels'][iy[:,None]+1,ix[None,:]+1]


def sample_mask(image, x, y, scales, flags, direct=False):
    w,h = image['width'],image['height']
    sx,sy = (1,1) if direct else (1<<scales[0],1<<scales[1])
    # Recovered mirror arithmetic includes the fractional part, not just texels.
    x = w*sx-x-1 if flags&4 else x
    y = h*sy-y-1 if flags&8 else y
    ix=x//sx;iy=y//sy;fx=x%sx;fy=y%sy
    if min(ix.min(),iy.min())<0 or ix.max()>=w or iy.max()>=h:
        raise FormatError('FGD mask sampling exceeds its declared extent')
    a=image['pixels'][iy[:,None]+1,ix[None,:]+1]
    if direct:return a
    a=a.astype(np.int64)
    b=image['pixels'][iy[:,None]+1,ix[None,:]+2]
    c=image['pixels'][iy[:,None]+2,ix[None,:]+1]
    d=image['pixels'][iy[:,None]+2,ix[None,:]+2]
    fx=fx[None,:,None].astype(np.int64);fy=fy[:,None,None].astype(np.int64)
    return ((a*(sx-fx)+b*fx)*(sy-fy)+(c*(sx-fx)+d*fx)*fy)//(sx*sy)


def compose(fgd, images, rectangle):
    left,top,width,height=rectangle
    if min(left,top)<0 or min(width,height)<=0 or left+width>fgd['width'] or top+height>fgd['height']:
        raise FormatError('Terrain UV rectangle exceeds the FGD grid')
    result=np.zeros((height,width,3),dtype=np.uint8)
    for instance in fgd['instances']:
        f=instance['feature'];x,y=instance['x'],instance['y'];w,h=f['size']
        x0=max(left,x);y0=max(top,y);x1=min(left+width,x+w);y1=min(top+height,y+h)
        if x0>=x1 or y0>=y1:continue
        # Bounded strips keep full-map backgrounds and light maps inexpensive.
        for row in range(y0,y1,128):
            stop=min(row+128,y1);xx=np.arange(x0,x1,dtype=np.int32)-x;yy=np.arange(row,stop,dtype=np.int32)-y
            target=result[row-top:stop-top,x0-left:x1-left]
            mode=f['mode'];flags=f['flags']
            if mode==0x1c0:
                if images[f['refs'][1]]['kind']!=1:raise FormatError('FGD lightmap requires RGB555 BID')
                light=sample_mask(images[f['refs'][1]],xx,yy,f['scales'],flags)
                target[:]=((target.astype(np.int32)*light[:,:,:3])>>8).astype(np.uint8)
                continue
            color=sample_color(images[f['refs'][0]],xx-instance['offset'][0],yy-instance['offset'][1],flags)
            if mode==0x40: target[:]=color[:,:,:3]
            elif mode==0x80:target[:]=np.minimum(target.astype(np.int32)+color[:,:,:3],255)
            elif mode==0xc0:target[:]=(target.astype(np.int32)*color[:,:,:3])>>8
            else:
                if mode==0x180:
                    if color.shape[2]!=4:raise FormatError('FGD alpha mode requires RGBA4444 BID')
                    alpha=color[:,:,3:4];inverse=240-alpha
                else:
                    mask=images[f['refs'][1]]
                    if mask['kind'] not in (3,5):raise FormatError('FGD alpha mask is not an 8-bit image')
                    alpha=sample_mask(mask,xx,yy,f['scales'],flags,direct=mode==0x280)
                    inverse=255-alpha
                blended=(color[:,:,:3]*alpha+target.astype(np.int32)*inverse)>>8
                # The engine leaves destination bytes untouched at alpha zero.
                target[:]=np.where(alpha!=0,blended,target).astype(np.uint8)
    return result


def png(rgb):
    h,w,_=rgb.shape
    def chunk(tag,data):
        return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data)&0xffffffff)
    # Sub filtering compresses terrain detail better than unfiltered scanlines.
    filtered=rgb.copy();filtered[:,1:]=rgb[:,1:]-rgb[:,:-1]
    rows=np.empty((h,w*3+1),dtype=np.uint8);rows[:,0]=1;rows[:,1:]=filtered.reshape(h,-1)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>2I5B',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(rows.tobytes(),6))+chunk(b'IEND',b'')


def prepare(catalog, files, report, decoded, preferred, progress=None, excluded_refs=()):
    """Collect exact source-archive inputs and replace the baked texture mapping.

    On unsupported/missing input, retain the original far textures and report a
    visible failure. Never silently pretend a partial composite is full detail.
    """
    info=dict(status='fallback',errors=[],images=[],source_images=[],resolution='Native FGD pixels')
    report['terrain_composition']=info
    try:
        source=archives.normalized(report['source']['name']);stem=source[:-4]
        model=stem.rsplit('/',1)[-1]
        index={}
        for row in catalog.rows:index.setdefault(archives.normalized(row['name']).removeprefix('content/'),[]).append(row)
        def get(path):
            # Bundles retain original inputs; no global archive ordering guessed.
            aliases=(path,path.removeprefix('content/'),'content/'+path.removeprefix('content/'))
            for alias in aliases:
                if alias in files:return files[alias]
            row=catalog.unique(index.get(path.removeprefix('content/'),[]),preferred)
            if row is None:raise FormatError('Missing close-view terrain resource: '+path)
            raw,method=catalog.read(row);name=archives.normalized(row['name'])
            files[name]=raw
            report['resources'].append(dict(catalog.describe(row),**method,
                sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)))
            return raw
        fgd=read_fgd(get(stem+'.fgd'))
        entries=read_index(get('textures/composttexture/'+model+'.index.tcf'))
        needed={ref for f in fgd['features'].values() for ref in f['refs'][:3] if ref}
        images={}
        for name in sorted(needed):
            if name not in entries:raise FormatError('Missing compost index entry: '+name)
            path='textures/composttexture/'+name+'.bid'
            images[name]=read_bid(get(path),entries[name]);info['source_images'].append(path)
        grid=report['terrain_grid'];ox,oz=grid['origin'];sx,sz=grid['cell_size']
        maxx=ox+sx*grid['columns'];maxz=oz+sz*grid['rows']
        scale_x=fgd['width']/(maxx-ox);scale_y=fgd['height']/(maxz-oz)
        rectangles={}
        for name,zone in decoded:
            for mesh in zone['meshes']:
                ref=mesh['texture']
                if ref in excluded_refs:continue
                x0,z0,x1,z1=mesh['texture_bounds']
                raw=((maxx-x1)*scale_x,(maxz-z1)*scale_y,(x1-x0)*scale_x,(z1-z0)*scale_y)
                rect=tuple(round(v) for v in raw)
                if any(abs(a-b)>0.01 for a,b in zip(raw,rect)):raise FormatError('Non-integral terrain/FGD texture alignment')
                if ref in rectangles and rectangles[ref]!=rect:raise FormatError('One terrain texture has conflicting UV bounds')
                rectangles[ref]=rect
        generated={};mapping={}
        for i,(ref,rect) in enumerate(sorted(rectangles.items())):
            if progress:progress(i,len(rectangles),ref)
            pixels=compose(fgd,images,rect)
            path=f'mw4_generated/terrain/{model}/{i:03d}.png'
            generated[path]=png(pixels);mapping[ref]=path
            info['images'].append(dict(reference=ref,path=path,width=rect[2],height=rect[3],
                sha256=hashlib.sha256(generated[path]).hexdigest()))
        # Commit mapping only once every requested composite succeeded.
        files.update(generated)
        report['texture_resources']['mapping'].update(mapping)
        for ref in mapping:
            report['texture_resources'].get('hint_mapping',{}).pop(ref,None)
            report['texture_resources'].setdefault('resolutions',{})[ref]={'resource':mapping[ref],'method':'fgd_compost_native'}
        for key in ('missing','errors'):
            report['texture_resources'][key]=[e for e in report['texture_resources'].get(key,[]) if e.get('reference') not in mapping]
        info.update(status='full',fgd_size=[fgd['width'],fgd['height']],features=len(fgd['features']),
            placements=len(fgd['instances']),generated_bytes=sum(map(len,generated.values())))
    except (ValueError,KeyError,OSError) as exc:
        info['errors'].append(str(exc))
        report['warnings'].append('Close-view terrain composition failed; using baked far textures: '+str(exc))
    return info
