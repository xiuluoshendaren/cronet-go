#!/usr/bin/env python3
"""Download the verified Linux Go test toolchain into this project."""
import argparse
import hashlib
import json
from pathlib import Path
import ssl
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proxy', default='http://127.0.0.1:8897')
    args = parser.parse_args()
    lock = json.loads((ROOT / 'native/go-test.lock.json').read_text())
    archive = ROOT / '.build/cache' / lock['filename']
    destination = ROOT / '.build/linux/toolchains'
    if (destination / 'go/VERSION').exists():
        if (destination / 'go/VERSION').read_text().splitlines()[0] == lock['version']:
            return
        raise RuntimeError('Existing Linux Go toolchain differs from the lock.')
    if not archive.exists():
        context = ssl.create_default_context()
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({'http': args.proxy, 'https': args.proxy} if args.proxy else {}),
            urllib.request.HTTPSHandler(context=context))
        archive.parent.mkdir(parents=True, exist_ok=True)
        partial = archive.with_suffix('.partial')
        with opener.open('https://dl.google.com/go/' + lock['filename'], timeout=120) as response:
            with partial.open('wb') as output:
                while data := response.read(1024 * 1024):
                    output.write(data)
        partial.rename(archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != lock['sha256']:
        raise RuntimeError('Go archive SHA256 mismatch.')
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as source:
        source.extractall(destination, filter='data')
    print('Prepared', destination / 'go', flush=True)


if __name__ == '__main__':
    main()
