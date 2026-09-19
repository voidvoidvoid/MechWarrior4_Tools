"""Build a deterministic add-on ZIP from an explicit source/documentation allowlist."""
import argparse
import ast
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED


def main():
    root = Path(__file__).resolve().parents[1]
    source = root / 'blender'
    tree = ast.parse((source / 'io_scene_mw4anim' / '__init__.py').read_text())
    info = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'bl_info' for t in n.targets))
    release = info['version'][1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=root / 'downloads' / f'MW4-Blender-Animation-R{release}.zip')
    args = parser.parse_args()
    files = list((source / 'io_scene_mw4anim').glob('*.py'))
    files += [source / 'io_scene_mw4anim' / 'crypto_profile.json']
    files += list(source.glob('*.md'))
    files += list((source / 'docs').glob('*.md'))
    files += list((source / 'tests').glob('*.py'))
    files += list((source / 'validation').glob('*.json'))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.output, 'w', compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files):
            data = path.read_bytes()
            if path.suffix == '.py': ast.parse(data, filename=str(path))
            item = ZipInfo(path.relative_to(source).as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
            item.compress_type = ZIP_DEFLATED
            item.create_system = 3
            item.external_attr = 0o100644 << 16
            archive.writestr(item, data, compress_type=ZIP_DEFLATED, compresslevel=9)
    print(f'{args.output}: {len(files)} source, documentation and report files')


if __name__ == '__main__':
    main()
