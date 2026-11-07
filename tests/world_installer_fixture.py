"""Small fake payload for real installer runtimes; never a playable game map."""
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_state_payload import BUNDLE_DOWNLOAD, CHECKSUM_DOWNLOAD, build_state_payload, state_manifest, manifest_bytes, MANIFEST_PATH


def make_world_source(source):
    descriptor = source / 'descriptor.mod'
    text = descriptor.read_text(encoding='utf-8-sig')
    import re
    text = re.sub(r'version="[^"]+"', 'version="2.0.0-alpha2"', text)
    descriptor.write_text(text + 'replace_path="history/countries"\n', encoding='utf-8')
    (source / 'common/bookmarks/Y89_bookmarks.txt').write_text('bookmarks={ bookmark={name=RW26_BOOKMARK_2026 date=2026.1.1.12} bookmark={date=1936.1.1.12} }', encoding='utf-8')
    for filename in ['the_gathering_storm.txt', 'blitzkrieg.txt']:
        (source / 'common/bookmarks' / filename).write_text('# No vanilla campaign.\n', encoding='utf-8')
    states = source / 'history/states'
    states.mkdir(exist_ok=True)
    for sid in range(1, 1256):
        (states / f'{sid}-Reworkl.txt').write_text(f'state={{ id={sid} }}', encoding='utf-8')
    for name in ['map/provinces.bmp','map/definition.csv','map/default.map','map/terrain.bmp',
                 'map/rivers.bmp','map/heightmap.bmp','map/trees.bmp','map/cities.bmp',
                 'map/world_normal.bmp','map/unitstacks.txt','map/reworkl_world_manifest.txt',
                 'map/reworkl_asset_manifest.txt','licenses/Millennium-Dawn-CC-BY-SA-4.0.txt',
                 'licenses/flag-icons-MIT.txt','THIRD_PARTY.txt','WORLD_2026_RU.txt']:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(('installer fixture: ' + name).encode())
    (source / MANIFEST_PATH).write_bytes(manifest_bytes(state_manifest(source)))


def add_recovery_bundle(source):
    bundle, checksum = build_state_payload(source)
    shutil.copy2(bundle, source.parent / BUNDLE_DOWNLOAD)
    shutil.copy2(checksum, source.parent / CHECKSUM_DOWNLOAD)
