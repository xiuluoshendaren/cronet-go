#!/usr/bin/env python3
"""Build both Linux ABIs in Docker while reusing project-local Git objects."""
import argparse
import ast
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    print('+', ' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), check=True, **kwargs)


def seed_git(source, destination, revision, sparse=False):
    if (destination / '.git').exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    # The project is mounted at its original absolute path so Git alternates
    # remain valid. Only immutable object storage is shared with the macOS build.
    run(['git', 'clone', '--shared', '--no-checkout', source, destination])
    if sparse:
        # Chromium's browser/UI test trees account for most checkout files.
        # Keep the networking build inputs and upstream metadata available.
        (destination / '.git/info/sparse-checkout').write_text(
            '/*\n!/chrome/browser/\n!/chrome/test/\n!/third_party/blink/\n'
            '!/content/\n!/ash/\n!/ios/\n!/android_webview/\n')
        run(['git', '-C', destination, 'config', 'core.sparseCheckout', 'true'])
    run(['git', '-C', destination, 'checkout', '--detach', revision])
    run(['git', '-C', destination, 'update-ref', 'refs/remotes/origin/cronet-pinned', 'HEAD'])
    run(['git', '-C', destination, 'symbolic-ref', 'refs/remotes/origin/HEAD',
         'refs/remotes/origin/cronet-pinned'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpu', choices=['x64', 'arm64', 'all'], default='all')
    parser.add_argument('--proxy', default='http://host.docker.internal:8897')
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--seed-only', action='store_true',
                        help='Prepare portable Git checkouts on the host before Docker builds.')
    args = parser.parse_args()
    os.chdir(ROOT)
    os.environ['CRONET_BUILD_ROOT'] = '.build/linux'
    mac = ROOT / '.build'
    linux = ROOT / '.build/linux'
    for directory in ['home', 'tmp', 'logs']:
        (linux / directory).mkdir(parents=True, exist_ok=True)
    lock = json.loads((ROOT / 'native/cronet.lock.json').read_text())
    if (mac / 'chromium/src/.git').exists():
        seed_git(mac / 'chromium/src', linux / 'chromium/src', lock['chromium_revision'], sparse=True)
        run(['git', '-C', linux / 'chromium/src', 'remote', 'set-url', 'origin',
             'https://chromium.googlesource.com/chromium/src.git'])
    if (mac / 'depot_tools/.git').exists():
        seed_git(mac / 'depot_tools', linux / 'depot_tools', lock['depot_tools_revision'])
    entries = mac / 'chromium/.gclient_entries'
    if entries.exists():
        from build_cronet import skipped_assets
        skipped = skipped_assets(linux / 'chromium/src')
        for path, url in ast.literal_eval(entries.read_text().split('=', 1)[1]).items():
            source = mac / 'chromium' / path
            if (path == 'src' or any(path == skip or path.startswith(skip + '/') for skip in skipped)
                    or not isinstance(url, str) or '@' not in url):
                continue
            if not (source / '.git').exists():
                continue
            revision = url.rsplit('@', 1)[1]
            result = subprocess.run(['git', '-C', source, 'cat-file', '-e', revision],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if result.returncode == 0:
                seed_git(source, linux / 'chromium' / path, revision)
                run(['git', '-C', linux / 'chromium' / path, 'remote', 'set-url',
                     'origin', url.rsplit('@', 1)[0]])
    if args.seed_only:
        return
    common = ['--proxy', args.proxy, '--jobs', str(args.jobs)]
    run([sys.executable, 'scripts/build_cronet.py', 'sync', *common])
    cpus = ['x64', 'arm64'] if args.cpu == 'all' else [args.cpu]
    for cpu in cpus:
        run([sys.executable, 'scripts/build_cronet.py', 'build', '--cpu', cpu, *common])
        library = ROOT / 'dist' / f'linux-{cpu}' / 'libcronet.so'
        run(['file', library])
        run(['readelf', '-h', library])


if __name__ == '__main__':
    main()
