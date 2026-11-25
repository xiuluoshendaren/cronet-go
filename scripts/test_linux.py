#!/usr/bin/env python3
"""Build and execute both Linux Go test binaries inside the builder container."""
import argparse
import hashlib
import os
from pathlib import Path
import platform
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / '.build/linux/chromium/src'


def test(cpu):
    architecture = 'amd64' if cpu == 'x64' else 'arm64'
    triple = 'x86_64-linux-gnu' if cpu == 'x64' else 'aarch64-linux-gnu'
    sysroot = SRC / 'build/linux' / f'debian_bullseye_{architecture}-sysroot'
    clang = SRC / 'third_party/llvm-build/Release+Asserts/bin/clang'
    libraries = ROOT / 'dist' / f'linux-{cpu}'
    output = ROOT / '.build/bin' / f'cronet-linux-{cpu}.test'
    output.parent.mkdir(parents=True, exist_ok=True)
    compiler = output.with_suffix('.cc.sh')
    # Keep CC a single executable path; Go then passes cgo's arguments unchanged.
    import shlex
    compiler.write_text('#!/bin/sh\nexec ' + shlex.quote(str(clang)) +
                        ' --target=' + triple + ' --sysroot=' + shlex.quote(str(sysroot)) +
                        ' -fuse-ld=lld -Wno-unused-command-line-argument "$@"\n')
    compiler.chmod(0o755)
    env = os.environ.copy()
    for key, name in [('GOCACHE', 'go-cache'), ('GOMODCACHE', 'go-mod'),
                      ('GOTMPDIR', 'go-tmp'), ('TMPDIR', 'tmp')]:
        directory = ROOT / '.build/linux' / name
        directory.mkdir(parents=True, exist_ok=True)
        env[key] = str(directory)
    env.update(GOOS='linux', GOARCH=architecture, CGO_ENABLED='1', CC=str(compiler),
               CGO_CFLAGS='-I' + str(libraries / 'include'),
               CGO_LDFLAGS=f'-L{libraries} -lcronet -Wl,-rpath,{libraries}')
    digest = hashlib.sha256((libraries / 'libcronet.so').read_bytes()).hexdigest()
    command = [str(ROOT / '.build/linux/toolchains/go/bin/go'), 'test', '-c', '-race',
               '-ldflags=-buildid=' + digest, '-o', str(output), '.']
    print('+', ' '.join(command), flush=True)
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    command = [str(output), '-test.v', '-test.timeout=120s', '-test.count=1']
    if cpu == 'arm64':
        # Docker Desktop's VM is arm64 on Apple Silicon. Use the target sysroot
        # loader explicitly so no arm64 libraries need installing in the amd64 image.
        loaders = list((sysroot / 'lib/aarch64-linux-gnu').glob('ld-*.so'))
        if len(loaders) != 1:
            raise RuntimeError('Expected one arm64 dynamic loader in the pinned sysroot.')
        paths = [libraries, sysroot / 'lib/aarch64-linux-gnu',
                 sysroot / 'usr/lib/aarch64-linux-gnu']
        command = [str(loaders[0]), '--library-path', ':'.join(map(str, paths)), *command]
    print('+', ' '.join(command), 'container host:', platform.machine(), flush=True)
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpu', choices=['x64', 'arm64', 'all'], default='all')
    args = parser.parse_args()
    for cpu in (['x64', 'arm64'] if args.cpu == 'all' else [args.cpu]):
        test(cpu)


if __name__ == '__main__':
    main()
