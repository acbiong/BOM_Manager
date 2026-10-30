"""Reuse complete build-time screenshots when their UI inputs have not changed."""
import hashlib
import json
import os
from pathlib import Path

MANIFEST = 'build_cache.json'


def input_digest(root):
    root = Path(root)
    paths = list((root / 'src' / 'ui').glob('*.py'))
    paths += list((root / 'src' / 'domain').glob('*.py'))
    paths += list((root / 'tools').glob('help*.py'))
    paths += [root / 'tools' / 'generate_help_screenshots.py']
    paths += list((root / 'resources' / 'help_screenshots').glob('*'))
    digest = hashlib.sha256()
    # An explicitly selected example project must not reuse another project's images.
    digest.update(os.environ.get("BOM_HELP_CONFIG", "").encode("utf-8"))
    for path in sorted(set(paths)):
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode('utf-8'))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def reusable(root, output, expected):
    output = Path(output)
    try:
        data = json.loads((output / MANIFEST).read_text(encoding='utf-8'))
        if data.get('inputs') != input_digest(root):return False
        images = data['images']
        if not all(name + '.png' in images for name in expected):return False
        return bool(images) and all(
            Path(name).name == name and
            hashlib.sha256((output / name).read_bytes()).hexdigest() == digest
            for name, digest in images.items())
    except (OSError, ValueError, KeyError, TypeError):
        return False


def record(root, output):
    output = Path(output)
    paths = list(output.glob('*.png')) + list(output.glob('actions.json'))
    data = {'inputs': input_digest(root), 'images': {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}}
    (output / MANIFEST).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
