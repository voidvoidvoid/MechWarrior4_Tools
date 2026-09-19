"""Static animation dependency discovery; never executes game scripts.

Supports the !NAME=value / $(NAME) declarations in supplied MW4 animscripts.
Paths retain mech ownership; only the optional content/ database prefix aliases.
"""
import re
from .archives import normalized

MACRO = re.compile(r'\$\(([^)]+)\)')
DEFINE = re.compile(r'^\s*!([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$')


def resource_key(name):
    name = normalized(name)
    return name[8:] if name.startswith('content/') else name


def parse(data):
    definitions = {}; values = []; errors = []
    for line in data.decode('cp1252').splitlines():
        line = line.split('//', 1)[0].strip()
        match = DEFINE.fullmatch(line)
        if match:
            definitions[match[1].casefold()] = match[2].strip().strip('"')
        elif '=' in line:
            values.append(line.split('=', 1)[1].strip().strip('"'))
    def expand(value, stack=()):
        def replace(match):
            key = match[1].casefold()
            if key in stack: raise ValueError('Cyclic macro: ' + key)
            if key not in definitions: raise ValueError('Undefined macro: ' + key)
            if len(stack) >= 32: raise ValueError('Macro nesting exceeds 32 levels')
            return expand(definitions[key], stack+(key,))
        result = MACRO.sub(replace, value)
        if len(result)>8192: raise ValueError('Expanded value exceeds 8192 characters')
        return result
    def path(value):
        value = normalized(value)
        if '/animation/' not in value: return None
        if not value.endswith('.mw4anim'): value += '.mw4anim'
        if not re.fullmatch(r'[a-z0-9_./\\ -]+', value): return None
        return value
    paths = set(); resolved = {}
    for key, value in list(definitions.items()) + [(None, v) for v in values]:
        try:
            result = path(expand(value))
            if result:
                paths.add(result)
                if key: resolved[key] = result
        except ValueError as exc:
            message = str(exc)
            if message not in errors: errors.append(message)
    return {'paths': sorted(paths), 'preferred': [resolved[k] for k in ('walk','standpose') if k in resolved],
            'errors': errors}


def inspect(files):
    paths=set(); preferred=[]; errors=[]
    for name,data in sorted(files.items()):
        if not name.endswith('.animscript'): continue
        result=parse(data);paths.update(result['paths']);preferred.extend(result['preferred'])
        errors.extend({'script':name,'error':e} for e in result['errors'])
    return {'paths':sorted(paths),'preferred':list(dict.fromkeys(preferred)),'errors':errors}


def choose_action(actions, files):
    """Do not leave a fall/get-up clip active merely because it imported last."""
    by_path={resource_key(a.get('mw4_archive_member','')):a for a in actions}
    for path in inspect(files)['preferred']:
        if resource_key(path) in by_path: return by_path[resource_key(path)]
    for suffix in ('_walk.mw4anim','_standpose.mw4anim'):
        match=next((a for a in actions if a.get('mw4_archive_member','').casefold().endswith(suffix)),None)
        if match is not None:return match
    return None
