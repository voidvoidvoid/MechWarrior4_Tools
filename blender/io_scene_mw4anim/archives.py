"""Read-only archive discovery and model resource collection; no bpy dependency."""
import base64
import hashlib
import json
import os
from pathlib import Path
import struct
import zipfile
from . import helm

Error = helm.ExtractError
MAX_TOTAL = 512 * 1024 * 1024


def normalized(name):
    return name.replace('\\', '/').casefold()


def bundled_keys():
    profile = json.loads(Path(__file__).with_name('crypto_profile.json').read_text())
    keys = helm.KeySource.__new__(helm.KeySource)
    keys.keys = {k: base64.b64decode(v, validate=True) for k, v in profile['keys'].items()}
    keys.tables = base64.b64decode(profile['tables'], validate=True)
    digest = hashlib.sha256(keys.keys['mektek'] + keys.keys['secure'] + keys.tables).hexdigest()
    if digest != helm.MATERIAL_SHA256 or digest != profile['material_sha256']:
        raise Error('Bundled decryption profile failed its integrity check')
    keys.schedules = {}
    keys.sha256 = profile['source_sha256']
    return keys


class Catalog:
    def __init__(self, directory, key_source='', progress=None):
        self.root = Path(directory).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise Error('Select the MW4 installation directory')
        self.keys = helm.KeySource(key_source) if key_source else bundled_keys()
        self.archives = []
        self.rows = []
        self.warnings = []
        self.cache = {}
        self.decoded_total = 0
        paths = []
        for parent, dirs, files in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not Path(parent, d).is_symlink()
                             and d.casefold() not in ('backup','backups')
                             and not d.casefold().endswith('.bak'))
            paths.extend(Path(parent, f) for f in sorted(files)
                         if f.lower().endswith('.mw4') and not Path(parent, f).is_symlink())
        for i, path in enumerate(sorted(paths)):
            if progress: progress(i, len(paths), str(path))
            try:
                with path.open('rb') as stream:
                    meta, rows = helm.read_index(stream)
                stat = path.stat()
                archive = {'path': str(path), 'relative': path.relative_to(self.root).as_posix(),
                           'meta': meta, 'signature': (stat.st_size, stat.st_mtime_ns)}
                aid = len(self.archives)
                self.archives.append(archive)
                self.rows.extend(dict(row, archive=aid) for row in rows if row['indexed'])
            except (OSError, ValueError) as exc:
                self.warnings.append(f'{path.relative_to(self.root)}: {exc}')
        if not self.archives:
            raise Error('No readable #VBD v4 .mw4 archives found. Select the game installation or Resource directory.')

    def models(self):
        return [r for r in self.rows if normalized(r['name']).endswith('.contents')
                and '/mechs/' in '/' + normalized(r['name'])]

    def read(self, row):
        key = (row['archive'], row['ordinal'])
        if key in self.cache: return self.cache[key]
        if max(row['decoded_size'], row['stored_size']) > helm.DEFAULT_LIMIT:
            raise Error('Resource exceeds 64 MiB limit: ' + row['name'])
        if self.decoded_total + row['decoded_size'] > MAX_TOTAL:
            raise Error('Selected resource set exceeds 512 MiB limit')
        archive = self.archives[row['archive']]
        path = Path(archive['path'])
        st = path.stat()
        if (st.st_size, st.st_mtime_ns) != archive['signature']:
            raise Error('Archive changed after scanning; scan again: ' + str(path))
        with path.open('rb') as f:
            f.seek(archive['meta']['payload_boundary'] + row['payload_offset'])
            raw = helm.exact_read(f, row['stored_size'])
        data, method = helm.decode_member(raw, row, self.keys, helm.DEFAULT_LIMIT)
        self.decoded_total += len(data)
        self.cache[key] = (data, method)
        return data, method

    def describe(self, row):
        return {'archive': self.archives[row['archive']]['relative'],
                'id': row['id'], 'name': row['name'], 'ordinal': row['ordinal']}

    def unique(self, rows, preferred=None):
        if preferred is not None:
            local = [r for r in rows if r['archive'] == preferred]
            if local: rows = local
        if not rows: return None
        decoded = [(r, self.read(r)[0]) for r in rows]
        if any(data != decoded[0][1] for _, data in decoded[1:]):
            raise Error('Conflicting resources; archive load order is not inferred: ' +
                        '; '.join(str(self.describe(r)) for r in rows))
        return rows[0]

    def collect(self, root):
        """Collect the selected model subtree and independently resolve shape handles.

        Database IDs are runtime bindings, not archive list positions. An ID is
        accepted only if the candidate geometry is also named for this model.
        Ambiguous/missing references remain explicit; never use unrelated IDs.
        """
        prefix = normalized(root['name']).rsplit('/', 1)[0] + '/'
        model = prefix.rstrip('/').split('/')[-1]
        groups = {}
        for row in self.rows:
            if normalized(row['name']).startswith(prefix):
                groups.setdefault(normalized(row['name']), []).append(row)
        report = {'schema': 1, 'model': model, 'source': self.describe(root),
                  'archives': [a['relative'] for a in self.archives],
                  'warnings': list(self.warnings), 'resources': [], 'shape_references': [],
                  'errors': [], 'geometry_imported': False,
                  'scope': 'Decoded archive bytes; no game postprocessor, ERF mesh decoder, or runtime load-order emulation.'}
        files = {}
        chosen = {}
        for name, candidates in sorted(groups.items()):
            try:
                row = self.unique(candidates, root['archive'])
                data, method = self.read(row)
                # Unsafe names never become output paths.
                helm.safe_parts(name)
                files[name] = data
                chosen[name] = row
                report['resources'].append(dict(self.describe(row), **method,
                    sha256=hashlib.sha256(data).hexdigest(), bytes=len(data)))
            except (OSError, ValueError) as exc:
                report['errors'].append({'name': name, 'error': str(exc)})
        for name, data in list(files.items()):
            if not name.endswith('.video'): continue
            try:
                references = shape_handles(data)
            except Error as exc:
                report['errors'].append({'name': name, 'error': str(exc)})
                continue
            for db, rid in sorted(set(references)):
                ref = {'video': name, 'database_id': db, 'resource_id': rid}
                # Prefer named geometry evidence over unverified runtime database IDs.
                candidates = [r for r in self.rows if r['id'] == rid
                    and normalized(r['name']).endswith('.erf')
                    and model in normalized(r['name']).split('/')]
                try:
                    row = self.unique(candidates)
                    if row is None:
                        ref.update(status='unresolved', reason='No unique model-named ERF with this resource ID')
                    else:
                        payload, method = self.read(row)
                        path = normalized(row['name']); helm.safe_parts(path)
                        if path in files and files[path] != payload:
                            raise Error('Resolved geometry conflicts with selected archive subtree: ' + path)
                        if path not in files:
                            files[path] = payload
                            report['resources'].append(dict(self.describe(row), **method,
                                sha256=hashlib.sha256(payload).hexdigest(), bytes=len(payload)))
                        ref.update(status='resolved_by_id_and_model_path', resource=self.describe(row))
                except (OSError, ValueError) as exc:
                    ref.update(status='unresolved', reason=str(exc))
                report['shape_references'].append(ref)
        self.collect_animations(files, report)
        report['geometry_files'] = sorted(n for n in files if n.endswith('.erf'))
        report['animation_files'] = sorted(n for n in files if n.endswith('.mw4anim'))
        report['unresolved_shapes'] = sum(r['status']=='unresolved' for r in report['shape_references'])
        report['complete'] = not report['errors'] and not report['unresolved_shapes']
        return files, report


    def collect_animations(self, files, report):
        from . import animscript
        script_refs = animscript.model_script_references(files)
        script_index = {}
        for row in self.rows:
            if normalized(row['name']).endswith('.animscript'):
                script_index.setdefault(animscript.resource_key(row['name']), []).append(row)
        present = {animscript.resource_key(n) for n in files}
        script_missing, script_errors, scripts_collected = [], [], []
        for ref in script_refs:
            key = animscript.resource_key(ref['path'])
            if key in present: continue
            try:
                row = self.unique(script_index.get(key, []))
                if row is None:
                    script_missing.append(ref['path']); continue
                data, method = self.read(row)
                path = normalized(row['name']); helm.safe_parts(path)
                files[path] = data; present.add(key); scripts_collected.append(path)
                report['resources'].append(dict(self.describe(row), **method,
                    sha256=hashlib.sha256(data).hexdigest(), bytes=len(data)))
            except (OSError, ValueError) as exc:
                script_errors.append(dict(ref, error=str(exc)))
        dependencies = animscript.inspect(files)
        index = {}
        for row in self.rows:
            if normalized(row['name']).endswith('.mw4anim'):
                index.setdefault(animscript.resource_key(row['name']), []).append(row)
        existing = {animscript.resource_key(n) for n in files if n.endswith('.mw4anim')}
        result = dict(preferred=dependencies['preferred'], missing=script_missing,
            errors=script_errors + dependencies['errors'], collected=[],
            script_references=script_refs, scripts_collected=scripts_collected)
        for name in dependencies['paths']:
            key = animscript.resource_key(name)
            if key in existing: continue
            try:
                row = self.unique(index.get(key, []))
                if row is None:
                    result['missing'].append(name); continue
                data, method = self.read(row)
                path = normalized(row['name']); helm.safe_parts(path)
                files[path] = data; existing.add(key)
                report['resources'].append(dict(self.describe(row), **method,
                    sha256=hashlib.sha256(data).hexdigest(), bytes=len(data)))
                result['collected'].append(path)
            except (OSError, ValueError) as exc:
                result['errors'].append({'name': name, 'error': str(exc)})
        report['animation_dependencies'] = result
        return result


def shape_handles(data):
    if len(data) < 4: raise Error('Truncated .video resource')
    count = struct.unpack_from('<I', data)[0]
    if count > 65536: raise Error('Unreasonable .video record count')
    p = 4
    result = []
    for _ in range(count):
        if p + 8 > len(data): raise Error('Truncated .video record')
        size, kind = struct.unpack_from('<II', data, p)
        if size < 8 or p + size > len(data): raise Error('Invalid .video record extent')
        if kind == 0x21e:  # Adept::ShapeComponent: unique byte then packed resource handle.
            if size < 13: raise Error('Truncated ShapeComponent')
            result.append(struct.unpack_from('<HH', data, p+9))
        p += size
    return result


def write_bundle(path, files, report):
    """Only writes to explicitly selected output; preserves archive member paths."""
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            z.writestr('/'.join(helm.safe_parts(name)), data)
        z.writestr('_mw4_resource_report.json', json.dumps(report, indent=2))
