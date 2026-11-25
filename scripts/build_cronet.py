#!/usr/bin/env python3
"""Build pinned Chromium Cronet inside this repository (no global installs)."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from prepare_cronet import prepare
from patch_clt import patch as patch_clt

ROOT = Path(__file__).resolve().parents[1]
BUILD = (ROOT / os.environ.get('CRONET_BUILD_ROOT', '.build')).resolve()
if not BUILD.is_relative_to(ROOT / '.build'):
    raise RuntimeError('CRONET_BUILD_ROOT must remain inside the project .build directory.')
SRC = BUILD / 'chromium/src'
DEPOT = BUILD / 'depot_tools'
LOCK = ROOT / 'native/cronet.lock.json'


def environment(proxy):
    env = os.environ.copy()
    for name in ['cache/cipd', 'cache/vpython', 'tmp', 'go-cache', 'go-mod', 'go-tmp', 'logs']:
        (BUILD / name).mkdir(parents=True, exist_ok=True)
    env.update(PATH=str(DEPOT) + os.pathsep + env['PATH'], DEPOT_TOOLS_UPDATE='0',
               CIPD_CACHE_DIR=str(BUILD / 'cache/cipd'),
               VPYTHON_VIRTUALENV_ROOT=str(BUILD / 'cache/vpython'),
               TMPDIR=str(BUILD / 'tmp'), GOCACHE=str(BUILD / 'go-cache'),
               GOMODCACHE=str(BUILD / 'go-mod'), GOTMPDIR=str(BUILD / 'go-tmp'),
               PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1')
    if proxy:
        env.update(http_proxy=proxy, https_proxy=proxy, HTTP_PROXY=proxy, HTTPS_PROXY=proxy)
    env.update(no_proxy='localhost,127.0.0.1,::1', NO_PROXY='localhost,127.0.0.1,::1')
    count = int(env.get('GIT_CONFIG_COUNT', '0'))
    git_settings = [('http.version', 'HTTP/1.1'), ('http.sslVersion', 'tlsv1.2'),
                    ('http.lowSpeedLimit', '1'), ('http.lowSpeedTime', '60')]
    if proxy:
        git_settings.append(('http.proxy', proxy))
    for key, value in git_settings:
        env[f'GIT_CONFIG_KEY_{count}'] = key
        env[f'GIT_CONFIG_VALUE_{count}'] = value
        count += 1
    env['GIT_CONFIG_COUNT'] = str(count)
    return env


def run(argv, env, cwd=ROOT):
    print('+', ' '.join(map(str, argv)), flush=True)
    subprocess.run(list(map(str, argv)), cwd=cwd, env=env, check=True)


def skipped_assets(src):
    # Browser/performance test datasets are unrelated to the Cronet target.
    keep = {'src/third_party/llvm-build/Release+Asserts',
            'src/third_party/rust-toolchain', 'src/third_party/llvm-libclang'}
    skip = {p: None for p in [
        'src/third_party/devtools-frontend/src', 'src/third_party/dawn',
        'src/third_party/angle', 'src/third_party/skia', 'src/v8',
        'src/third_party/catapult', 'src/third_party/crossbench',
        'src/third_party/crossbench-web-tests', 'src/third_party/ffmpeg',
        'src/third_party/webrtc', 'src/third_party/pdfium',
    ]}
    for node in ast.walk(ast.parse((src / 'DEPS').read_text())):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)
                    and key.value.startswith('src/')):
                continue
            keep_git = {
                'src/third_party/depot_tools',
                'src/third_party/clang-format/script', 'src/third_party/compiler-rt/src',
                'src/third_party/libc++/src', 'src/third_party/libc++abi/src',
                'src/third_party/libunwind/src', 'src/third_party/llvm-libc/src',
                'src/net/third_party/quiche/src', 'src/third_party/boringssl/src',
                'src/third_party/perfetto', 'src/third_party/icu',
                'src/third_party/re2/src', 'src/third_party/zstd/src',
                'src/third_party/leveldatabase/src', 'src/third_party/snappy/src',
                'src/third_party/googletest/src', 'src/third_party/fuzztest/src',
                'src/third_party/google_benchmark/src', 'src/third_party/libFuzzer/src',
                'src/third_party/libprotobuf-mutator/src', 'src/third_party/libpfm4/src',
                'src/third_party/anonymous_tokens/src', 'src/third_party/crc32c/src',
                'src/third_party/smhasher/src', 'src/third_party/fast_float/src',
                'src/third_party/dragonbox/src', 'src/third_party/colorama/src',
                'src/third_party/ds_store/src', 'src/third_party/farmhash/src',
                'src/third_party/jsoncpp/source',
                'src/third_party/sqlite/src',
                'src/third_party/ced/src',
                'src/third_party/lss',
            }
            if not isinstance(value, ast.Dict):
                if key.value not in keep_git:
                    skip[key.value] = None
                continue
            props = {k.value: v for k, v in zip(value.keys, value.values) if isinstance(k, ast.Constant)}
            kind = props.get('dep_type')
            if 'url' in props and key.value not in keep_git:
                skip[key.value] = None
            if isinstance(kind, ast.Constant) and kind.value == 'gcs' and key.value not in keep:
                skip[key.value] = None
            if isinstance(kind, ast.Constant) and kind.value == 'cipd':
                if key.value not in {'src/buildtools/mac', 'src/buildtools/linux64',
                                     'src/third_party/ninja',
                                     'src/third_party/cpython3/host',
                                     'src/third_party/cpython3/linux-amd64'}:
                    skip[key.value] = None
    return skip


def filter_deps(src, skipped):
    # Current gclient does not apply custom_deps=None to GCS/CIPD entries.
    # Filter their pinned DEPS values explicitly; preserve all kept revisions.
    original = subprocess.check_output(['git', 'show', 'HEAD:DEPS'], cwd=src)
    lines = original.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    edits = []
    for node in ast.walk(ast.parse(original)):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value in skipped:
                edits.append((offsets[value.lineno - 1] + value.col_offset,
                              offsets[value.end_lineno - 1] + value.end_col_offset))
    for start, end in sorted(edits, reverse=True):
        original = original[:start] + b'None' + original[end:]
    (src / 'DEPS').write_bytes(original)


def sync(env, lock):
    if not (DEPOT / '.git').exists():
        run(['git', 'clone', '--depth=1', 'https://chromium.googlesource.com/chromium/tools/depot_tools.git', DEPOT], env)
    pinned_depot = lock.get('depot_tools_revision')
    if pinned_depot:
        actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=DEPOT, text=True).strip()
        if actual != pinned_depot:
            run(['git', 'fetch', '--depth=1', 'origin', pinned_depot], env, DEPOT)
            run(['git', 'checkout', '--detach', pinned_depot], env, DEPOT)
    if not (SRC / '.git').exists():
        SRC.parent.mkdir(parents=True, exist_ok=True)
        run(['git', 'clone', '--depth=1', '--branch', lock['chrome_version'], '--single-branch',
             'https://chromium.googlesource.com/chromium/src.git', SRC], env)
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=SRC, text=True).strip()
    if actual != lock['chromium_revision']:
        raise RuntimeError('Existing Chromium checkout differs from lock; use a separate clean .build directory.')
    # A tag-only clone lacks a remote HEAD. Establish a local pinned ref so
    # gclient does not enumerate the entire upstream ref list.
    run(['git', 'update-ref', 'refs/remotes/origin/cronet-pinned', 'HEAD'], env, SRC)
    run(['git', 'symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/cronet-pinned'], env, SRC)
    skipped = skipped_assets(SRC)
    filter_deps(SRC, skipped)
    config = {'name': 'src', 'url': 'https://chromium.googlesource.com/chromium/src.git',
              'managed': False, 'custom_deps': skipped,
              'custom_vars': {'checkout_configuration': 'small', 'checkout_android': False,
                              'checkout_ios': False, 'checkout_fuchsia': False,
                              'checkout_pgo_profiles': False}}
    (SRC.parent / '.gclient').write_text('solutions = ' + repr([config]) + '\ntarget_os = []\n')
    # Bootstrap once: concurrent GCS wrappers would otherwise race while each
    # tries to install the same depot_tools Python/CIPD packages.
    cache = DEPOT / '.cipd_bin/.cipd/tmp'
    manifests = ['cipd_manifest.txt', 'cipd_manifest.versions', 'cipd_client_version']
    if any(not (cache / ('.' + name)).exists() or
           (cache / ('.' + name)).read_bytes() != (DEPOT / name).read_bytes()
           for name in manifests):
        run([DEPOT / 'cipd', 'ensure', '-log-level', 'warning',
             '-ensure-file', DEPOT / 'cipd_manifest.txt', '-root', DEPOT / '.cipd_bin'], env)
        cache.mkdir(parents=True, exist_ok=True)
        for name in manifests:
            shutil.copy2(DEPOT / name, cache / ('.' + name))
    run([sys.executable, DEPOT / 'gsutil.py', 'version'], env)
    run([sys.executable, DEPOT / 'gclient.py', 'sync', '--nohooks', '--noprehooks',
         '--no-history', '--shallow', '-j', '8'], env, SRC.parent)
    run([sys.executable, SRC / 'build/util/lastchange.py', '-o', SRC / 'build/util/LASTCHANGE'], env, SRC)


def build(args, env, lock):
    prepare(SRC, args.proxy)
    system = 'mac' if sys.platform == 'darwin' else 'linux'
    if system == 'mac':
        if not shutil.which('xcrun'):
            raise RuntimeError('Apple macOS SDK required.')
        developer = subprocess.check_output(['xcode-select', '-print-path'], text=True).strip()
        if developer.endswith('/CommandLineTools'):
            patch_clt(SRC)
    cpu = args.cpu or ('arm64' if platform.machine() in ['arm64', 'aarch64'] else 'x64')
    out = SRC / 'out' / f'Cronet-{system}-{cpu}'
    out.mkdir(parents=True, exist_ok=True)
    flags = {'is_debug': False, 'is_official_build': False, 'is_component_build': False,
             'is_cronet_build': True, 'symbol_level': 0, 'use_remoteexec': False,
             'use_siso': False, 'target_cpu': cpu,
             'use_platform_icu_alternatives': False, 'icu_use_data_file': False,
             'treat_warnings_as_errors': False}
    if system == 'mac':
        flags.update(use_system_xcode=True)
    else:
        flags.update(use_sysroot=True, use_glib=False, use_gio=False, use_gtk=False,
                     use_dbus=False, use_udev=False,
                     use_aura=False, use_ozone=False, use_x11=False)
        run([sys.executable, SRC / 'build/linux/sysroot_scripts/install-sysroot.py',
             '--arch=' + ('amd64' if cpu == 'x64' else 'arm64')], env, SRC)
    (out / 'args.gn').write_text(''.join(f'{k} = {json.dumps(v)}\n' for k, v in flags.items()))
    gn = SRC / 'buildtools' / ('mac' if system == 'mac' else 'linux64') / 'gn'
    for path in ['base/BUILD.gn', 'components/cronet/BUILD.gn', 'components/cronet/native/BUILD.gn',
                 'components/grpc_support/BUILD.gn', 'net/BUILD.gn']:
        run([gn, 'format', SRC / path], env, SRC)
    run([gn, 'gen', out, '--root-target=//components/cronet',
         '--root-pattern=//components/cronet:cronet'], env, SRC)
    run([SRC / 'third_party/ninja/ninja', '-C', out, '-j', str(args.jobs), 'cronet'], env, SRC)
    package(out, system, cpu, lock)


def package(out, system, cpu, lock):
    dest = ROOT / 'dist' / f'{system}-{cpu}'
    (dest / 'include').mkdir(parents=True, exist_ok=True)
    ext = 'dylib' if system == 'mac' else 'so'
    library = out / f'libcronet.{ext}'
    if not library.is_file():
        raise RuntimeError(f'Missing build output: {library}')
    shutil.copy2(library, dest / library.name)
    if system == 'mac':
        subprocess.run(['install_name_tool', '-id', '@rpath/libcronet.dylib',
                        str(dest / library.name)], check=True)
        subprocess.run(['codesign', '--force', '--sign', '-',
                        str(dest / library.name)], check=True)
    for header in ['native/include/cronet_c.h', 'native/include/cronet_export.h', 'native/generated/cronet.idl_c.h']:
        shutil.copy2(SRC / 'components/cronet' / header, dest / 'include')
    shutil.copy2(SRC / 'components/grpc_support/include/bidirectional_stream_c.h', dest / 'include')
    shutil.copy2(SRC / 'AUTHORS', dest / 'AUTHORS')
    shutil.copy2(SRC / 'chrome/VERSION', dest / 'VERSION')
    shutil.copy2(SRC / 'LICENSE', dest / 'LICENSE.chromium')
    subprocess.run([sys.executable, str(SRC / 'tools/licenses/licenses.py'),
                    'license_file', '--gn-out-dir', str(out),
                    '--gn-target', '//components/cronet:cronet', '--format', 'txt',
                    str(dest / 'THIRD_PARTY_LICENSES.txt')], cwd=SRC, check=True)
    manifest = dict(lock, target_os=system, target_cpu=cpu, files={})
    for path in sorted(dest.rglob('*')):
        if path.is_file() and path.name != 'manifest.json':
            manifest['files'][str(path.relative_to(dest))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (dest / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Packaged {dest}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['sync', 'build', 'all'])
    parser.add_argument('--proxy', default='http://127.0.0.1:8897', help='Empty string disables proxy.')
    parser.add_argument('--cpu', choices=['arm64', 'x64'])
    parser.add_argument('--jobs', type=int, default=min(os.cpu_count() or 4, 8))
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    env = environment(args.proxy)
    lock = json.loads(LOCK.read_text())
    if args.command in ['sync', 'all']:
        sync(env, lock)
    if args.command in ['build', 'all']:
        build(args, env, lock)


if __name__ == '__main__':
    main()
