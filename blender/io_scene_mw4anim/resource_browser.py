"""Path-derived resource filters; no assumed game/mod category inventory."""
from .archives import normalized

ALL='__ALL__'
ROOT='__ROOT__'

def path_parts(name):
    path=normalized(name)
    if path.startswith('content/'):path=path[8:]
    return path.split('/')

def category(name):
    parts=path_parts(name)
    return parts[0] if len(parts)>1 else ROOT

def folder(name):
    parts=path_parts(name)
    return '/'.join(parts[:2]) if len(parts)>2 else ROOT

def label(value):
    if value==ROOT:return 'Root resources'
    return value.replace('_',' ').replace('-',' ').title()

def filter_rows(rows,kind='CONTENTS',group=ALL,subfolder=ALL,query=''):
    suffix='.contents' if kind=='CONTENTS' else '.erf'
    words=normalized(query).split()
    return [i for i,r in enumerate(rows) if normalized(r['name']).endswith(suffix)
        and (group==ALL or category(r['name'])==group)
        and (subfolder==ALL or folder(r['name'])==subfolder)
        and all(word in normalized(r['name']) for word in words)]

def choices(rows):
    groups={};folders={}
    for row in rows:
        c=category(row['name']);f=folder(row['name'])
        groups[c]=groups.get(c,0)+1
        folders.setdefault(c,{})[f]=folders.get(c,{}).get(f,0)+1
    categories=[(ALL,'All categories','Show all resource paths',0)]
    categories += [(c,f'{label(c)} ({count})',c,i+1) for i,(c,count) in enumerate(sorted(groups.items()))]
    subfolders={ALL:[(ALL,'All folders','Show all folders',0)]}
    for c,counts in folders.items():
        subfolders[c]=[(ALL,'All folders','Show all folders',0)]+[
            (f,f'{label(f.split("/")[-1])} ({count})',f,i+1) for i,(f,count) in enumerate(sorted(counts.items()))]
    return categories,subfolders
