#!/usr/bin/env python3
"""Support Apple's actual CommandLineTools SDK for this non-app library build."""
from pathlib import Path
from prepare_cronet import replace


def patch(src: Path):
    info = src / 'build/config/apple/sdk_info.py'
    anchor = '    lines = (\n'
    replacement = '''    # cronet-go: a dylib needs the macOS SDK and tools, not Xcode.app.
    clt = subprocess.check_output(['xcode-select', '-print-path'], text=True).strip()
    if clt.endswith('/CommandLineTools'):
        receipt = plistlib.loads(subprocess.check_output(
            ['pkgutil', '--pkg-info-plist', 'com.apple.pkg.CLTools_Executables']))
        version = '.'.join(receipt['pkg-version'].split('.')[:3])
        settings['xcode_version'] = FormatVersion(version)
        settings['xcode_version_int'] = int(settings['xcode_version'], 10)
        settings['xcode_version_verbatim'] = version
        settings['xcode_build'] = 'CLT-' + receipt['pkg-version']
        return

''' + anchor
    replace(info, anchor, replacement)
    anchor = "    settings['sdk_platform_path'] = (\n"
    replacement = '''    clt = subprocess.check_output(['xcode-select', '-print-path'], text=True).strip()
    if clt.endswith('/CommandLineTools') and platform == 'macosx':
        settings['sdk_platform_path'] = clt
        settings['sdk_build'] = subprocess.check_output(
            ['xcrun', '-sdk', platform, '--show-sdk-build-version'], text=True).strip()
        settings['toolchains_path'] = clt
        return

''' + anchor
    replace(info, anchor, replacement)
    find = src / 'build/mac/find_sdk.py'
    anchor = "    sdk_dir = os.path.join(dev_dir, 'Platforms/MacOSX.platform/Developer/SDKs')"
    replace(find, anchor, anchor + "\n    if dev_dir.endswith('/CommandLineTools'):\n        sdk_dir = os.path.join(dev_dir, 'SDKs')")
    anchor = "        bin_path = 'Toolchains/XcodeDefault.xctoolchain/usr/bin/'"
    replace(find, anchor, anchor + "\n        if dev_dir.endswith('/CommandLineTools'):\n            bin_path = 'usr/bin/'")
