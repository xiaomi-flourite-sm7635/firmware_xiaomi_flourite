#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Package raw stock OTA partitions, never files collected from a phone."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zipfile

PART_BYTES = 1900 * 1024 * 1024
INCREMENTALS = {
    'OS3.0.306.0.WPRMIXM': '16OS3.1.260912.004820804.QCPEGL.S',
    'OS3.0.318.0.WPRCNXM': '16OS3.1.260921.212522566.QCPECN.S',
}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def package(ota, label, expected, extractor, output):
    with zipfile.ZipFile(ota) as archive:
        metadata = archive.read('META-INF/com/android/metadata').decode()
        properties = dict(line.split('=', 1) for line in metadata.splitlines() if '=' in line)
        if (properties.get('post-build-incremental') != INCREMENTALS[expected]
                or properties.get('pre-device') != 'flourite'
                or properties.get('ota-type') != 'AB'):
            raise ValueError(f'Unexpected stock version: {ota.name}')
        payload = archive.getinfo('payload.bin')
        if payload.compress_type != zipfile.ZIP_STORED:
            raise ValueError('Expected uncompressed payload.bin inside the full OTA')
        with ota.open('rb') as stream:
            stream.seek(payload.header_offset)
            header = stream.read(30)
        if header[:4] != b'PK\x03\x04':
            raise ValueError('Invalid ZIP local header')
        name_len, extra_len = struct.unpack_from('<HH', header, 26)
        offset = payload.header_offset + 30 + name_len + extra_len
    images = output / label
    images.mkdir()
    subprocess.run([str(extractor), f'--payload={ota}', f'--payload_offset={offset}',
                    f'--output_dir={images}', '--operation_threads=2', '--verity_threads=2'], check=True)
    entries = sorted(images.iterdir())
    if not entries or any(not p.is_file() or p.suffix != '.img' for p in entries):
        raise ValueError('Unexpected extractor output')
    info = {'release': expected, 'incremental': INCREMENTALS[expected],
            'ota': ota.name, 'ota_sha256': digest(ota),
            'partitions': {p.name: {'size': p.stat().st_size, 'sha256': digest(p)} for p in entries}}
    tar = subprocess.Popen(['tar', '--sort=name', '--mtime=@0', '--owner=0', '--group=0',
                            '--numeric-owner', '-cf', '-', '-C', str(images), '.'], stdout=subprocess.PIPE)
    zstd = subprocess.Popen(['zstd', '-T2', '-3', '-c'], stdin=tar.stdout, stdout=subprocess.PIPE)
    tar.stdout.close()
    parts = []
    part_stream = None
    remaining = 0
    try:
        while chunk := zstd.stdout.read(1024 * 1024):
            if remaining == 0:
                if part_stream:
                    part_stream.close()
                path = output / f'{label}-raw.tar.zst.part{len(parts):03d}'
                parts.append(path)
                part_stream = path.with_suffix(path.suffix + '.partial').open('xb')
                remaining = PART_BYTES
            part_stream.write(chunk)
            remaining -= len(chunk)
        if part_stream:
            part_stream.close()
        if zstd.wait() or tar.wait():
            raise RuntimeError('Archive creation failed; partial files retained')
    finally:
        if part_stream:
            part_stream.close()
        zstd.stdout.close()
        for process in (zstd, tar):
            if process.poll() is None:
                process.terminate()
                process.wait()
    for path in parts:
        path.with_suffix(path.suffix + '.partial').rename(path)
    info['parts'] = {p.name: {'size': p.stat().st_size, 'sha256': digest(p)} for p in parts}
    return info


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--global-ota', required=True, type=Path)
    parser.add_argument('--china-ota', required=True, type=Path)
    parser.add_argument('--extractor', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = {}
    for label, ota, release in [('global-306', args.global_ota, 'OS3.0.306.0.WPRMIXM'),
                                 ('china-318', args.china_ota, 'OS3.0.318.0.WPRCNXM')]:
        sources[label] = package(ota.resolve(), label, release, args.extractor.resolve(), output)
        (output / 'sources.json').write_text(json.dumps(sources, indent=2) + '\n')
    sums = [f'{part["sha256"]}  {name}' for source in sources.values() for name, part in source['parts'].items()]
    sums.append(f'{digest(output / "sources.json")}  sources.json')
    (output / 'SHA256SUMS').write_text('\n'.join(sums) + '\n')
    print('Complete stock dump packages ready:', output, flush=True)


if __name__ == '__main__':
    main()
