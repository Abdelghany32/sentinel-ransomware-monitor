"""Fail a release build when browser assets are missing from its wheel."""
from pathlib import Path
from zipfile import ZipFile

wheel = max(Path('dist').glob('*.whl'), key=lambda path: path.stat().st_mtime)
with ZipFile(wheel) as archive:
    names = set(archive.namelist())
    for name in ('index.html', 'style.css', 'app.js'):
        if f'sentinel/static/{name}' not in names:
            raise SystemExit(f'Missing packaged asset: {name}')
print(f'Browser assets verified in {wheel.name}')
