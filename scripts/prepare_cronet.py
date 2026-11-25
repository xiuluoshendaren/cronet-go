#!/usr/bin/env python3
"""Restore Chromium's desktop Cronet ABI and apply the local desktop extensions."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
FIELDS = [('proxy_rules', 'string'), ('proxy_username', 'string'),
          ('proxy_password', 'string'), ('ignore_certificate_errors', 'bool')]


def replace(path, old, new):
    text = path.read_text()
    if (new and new in text) or (not new and old not in text):
        return
    if text.count(old) != 1:
        raise RuntimeError(f'{path}: expected one matching upstream anchor, got {text.count(old)}')
    path.write_text(text.replace(old, new, 1))


def restore_archive(item, destination, proxy):
    archive = ROOT / '.build/cache' / item['filename']
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        opener = urllib.request.build_opener(urllib.request.ProxyHandler(
            {'http': proxy, 'https': proxy} if proxy else {}))
        with opener.open(item['url'], timeout=120) as response:
            archive.write_bytes(response.read())
    if hashlib.sha256(archive.read_bytes()).hexdigest() != item['sha256']:
        raise RuntimeError(f'Archive SHA256 mismatch: {archive}')
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tf:
        tf.extractall(destination, filter='data')


def extend_c_api(native):
    idl = native / 'cronet.idl'
    additions = '\n  // cronet-go desktop engine configuration.\n'
    for name, kind in FIELDS:
        additions += f'  {kind} {name}' + (' = false' if kind == 'bool' else '') + ';\n'
    replace(idl, '  string user_agent;\n', '  string user_agent;\n' + additions)
    # Reproducible extensions of the restored generated ABI. Keep IDL, members,
    # accessors and copy/move semantics in sync; upstream constructors are defaulted.
    members, declarations, definitions = [], [], []
    for name, kind in FIELDS:
        ctype = 'bool' if kind == 'bool' else 'Cronet_String'
        members.append(f'  bool {name} = false;' if kind == 'bool' else f'  std::string {name};')
        declarations += [f'CRONET_EXPORT void Cronet_EngineParams_{name}_set(Cronet_EngineParamsPtr self, const {ctype} value);',
                         f'CRONET_EXPORT {ctype} Cronet_EngineParams_{name}_get(const Cronet_EngineParamsPtr self);']
        value = f'self->{name}' if kind == 'bool' else f'self->{name}.c_str()'
        definitions.append(f'''void Cronet_EngineParams_{name}_set(Cronet_EngineParamsPtr self, const {ctype} value) {{
  DCHECK(self);
  self->{name} = value;
}}
{ctype} Cronet_EngineParams_{name}_get(const Cronet_EngineParamsPtr self) {{
  DCHECK(self);
  return {value};
}}
''')
    replace(native / 'generated/cronet.idl_impl_struct.h', '  std::string user_agent;\n',
            '  std::string user_agent;\n' + '\n'.join(members) + '\n')
    replace(native / 'generated/cronet.idl_c.h', '// Struct Cronet_HttpHeader.',
            '\n'.join(declarations) + '\n\n// Struct Cronet_HttpHeader.')
    replace(native / 'generated/cronet.idl_impl_struct.cc', '// Struct Cronet_HttpHeader.',
            '\n'.join(definitions) + '\n// Struct Cronet_HttpHeader.')


def prepare(src, proxy):
    lock = json.loads((ROOT / 'native/cronet.lock.json').read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=src, text=True).strip()
    if revision != lock['chromium_revision']:
        raise RuntimeError(f'Chromium revision mismatch: {revision}')
    replace(src / '.gn', 'import("//third_party/angle/dotfile_settings.gni")',
            '# cronet-go: the desktop network library does not use ANGLE.')
    replace(src / '.gn', '    angle_dotfile_settings.exec_script_allowlist +\n', '')
    replace(src / '.gn', 'buildconfig = "//build/config/BUILDCONFIG.gn"',
            'root = "//components/cronet"\nroot_patterns = [ "//components/cronet:cronet" ]\nbuildconfig = "//build/config/BUILDCONFIG.gn"')
    compat = ROOT / '.build/compat/cronet-144'
    if not (compat / 'native/engine.cc').exists():
        restore_archive(lock['archives']['cronet'], compat, proxy)
    grpc = ROOT / '.build/compat/grpc-support-144'
    if not (grpc / 'bidirectional_stream.cc').exists():
        restore_archive(lock['archives']['grpc_support'], grpc, proxy)
    cronet = src / 'components/cronet'
    global_state = cronet / 'cronet_global_state_stubs.cc'
    replace(global_state, '#include "base/at_exit.h"',
            '#include "base/at_exit.h"\n#include "base/command_line.h"\n#include "base/i18n/icu_util.h"')
    replace(global_state, '  base::FeatureList::InitInstance(std::string(), std::string());',
            '''  if (!base::CommandLine::InitializedForCurrentProcess()) {
    base::CommandLine::Init(0, nullptr);
  }
  CHECK(base::i18n::InitializeICU());
  base::FeatureList::InitInstance(std::string(), std::string());''')
    # These directories were removed upstream; restore only the compatibility
    # interface, not the old //net implementation or old common Cronet classes.
    if not (cronet / 'native').exists():
        shutil.copytree(compat / 'native', cronet / 'native')
    if not (src / 'components/grpc_support').exists():
        shutil.copytree(grpc, src / 'components/grpc_support')
    extend_c_api(cronet / 'native')
    replace(src / 'net/BUILD.gn',
            'if (is_cronet_build) {\n  _test_target_type = "cronet_test"',
            'if (is_cronet_build && is_android) {\n  _test_target_type = "cronet_test"')
    # Desktop Cronet still uses POSIX path/proxy helpers that upstream only
    # includes for full desktop Linux builds.
    replace(src / 'base/BUILD.gn',
            'if (!is_cronet_build) {\n      # These dependencies are not required on Android.',
            'if (!is_cronet_build || is_linux) {\n      # These dependencies are not required on Android.')
    for filename in [
            'cronet_ssl_config_service.cc', 'cronet_ssl_config_service.h',
            'desktop_config.cc', 'desktop_config.h',
            'tls_cipher_suite_mapper.cc', 'tls_cipher_suite_mapper.h',
            'tls_curve_mapper.cc', 'tls_curve_mapper.h']:
        shutil.copy2(ROOT / 'native' / filename, cronet / filename)

    cfg = cronet / 'url_request_context_config.h'
    config_impl = cronet / 'url_request_context_config.cc'
    # Older iterations inserted the four desktop fields separately. Remove
    # that historical block when a later run added the complete TLS block,
    # otherwise an existing checkout retains duplicate struct members.
    legacy_fields = '''  std::string proxy_rules;
  std::string proxy_username;
  std::string proxy_password;
  bool ignore_certificate_errors = false;
'''
    cfg_text = cfg.read_text()
    while legacy_fields + '\n' + legacy_fields in cfg_text:
        cfg_text = cfg_text.replace(
            legacy_fields + '\n' + legacy_fields, legacy_fields, 1)
    if cfg_text != cfg.read_text():
        cfg.write_text(cfg_text)
    replace(config_impl, '#include <algorithm>', '#include <algorithm>\n#include <cmath>')
    replace(config_impl, '    } else if (iter->first == kSpdyGoAwayOnIpChange) {', '''    } else if (iter->first == "HTTP2" && iter->second.is_dict()) {
      const auto& options = iter->second.GetDict();
      session_params->enable_http2_settings_grease =
          options.FindBool("enable_settings_grease").value_or(false);
      if (const auto* settings = options.FindDict("settings")) {
        for (const auto item : *settings) {
          unsigned id = 0;
          if (!base::StringToUint(item.first, &id) || id > 65535 ||
              (!item.second.is_int() && !item.second.is_double())) {
            continue;
          }
          const double value = item.second.GetDouble();
          if (value >= 0 && value <= 4294967295.0 && std::floor(value) == value) {
            session_params->http2_settings[static_cast<uint16_t>(id)] =
                static_cast<uint32_t>(value);
          }
        }
      }
    } else if (iter->first == kSpdyGoAwayOnIpChange) {''')
    replace(cfg, '  const bool enable_quic;\n', '''  std::string proxy_rules;
  std::string proxy_username;
  std::string proxy_password;
  bool ignore_certificate_errors = false;
  std::vector<std::string> tls_cipher_suites;
  std::vector<std::string> tls_curves;

  const bool enable_quic;
''')
    replace(config_impl, '''  }
}

void URLRequestContextConfig::SetContextBuilderExperimentalOptions(''',
            '''  }

  const auto parse_names = [](const base::Value* value, const char* option) {
    std::vector<std::string> names;
    const base::ListValue* list = value->GetIfList();
    if (!list) {
      LOG(WARNING) << "Cronet experimental option \\"" << option
                   << "\\" must be a string array";
      return names;
    }
    for (const base::Value& item : *list) {
      if (const std::string* name = item.GetIfString()) {
        names.push_back(*name);
      } else {
        LOG(WARNING) << "Ignoring non-string item in Cronet experimental option \\""
                     << option << "\\"";
      }
    }
    return names;
  };
  if (const base::Value* value =
          experimental_options.Find("tls_cipher_suites")) {
    tls_cipher_suites = parse_names(value, "tls_cipher_suites");
    experimental_options.Remove("tls_cipher_suites");
  }
  if (const base::Value* value = experimental_options.Find("tls_curves")) {
    tls_curves = parse_names(value, "tls_curves");
    experimental_options.Remove("tls_curves");
  }
}

void URLRequestContextConfig::SetContextBuilderExperimentalOptions(''')
    engine = cronet / 'native/engine.cc'
    native_request = cronet / 'native/url_request.cc'
    replace(native_request, '''  void OnResponseStarted(int http_status_code,
                         const std::string& http_status_text,
                         const net::HttpResponseHeaders* headers,
                         bool was_cached,
                         const std::string& negotiated_protocol,
                         const std::string& proxy_server,
                         int64_t received_byte_count) override;''', '''  void OnResponseStarted(int http_status_code,
                         const std::string& http_status_text,
                         const net::HttpResponseHeaders* headers,
                         bool was_cached,
                         const std::string& negotiated_protocol,
                         const std::string& proxy_server,
                         int64_t received_byte_count,
                         bool is_proxied) override;''')
    anchor = '''void Cronet_UrlRequestImpl::NetworkTasks::OnResponseStarted(
    int http_status_code,
    const std::string& http_status_text,
    const net::HttpResponseHeaders* headers,
    bool was_cached,
    const std::string& negotiated_protocol,
    const std::string& proxy_server,
    int64_t received_byte_count) {'''
    replace(native_request, anchor, anchor.replace('int64_t received_byte_count) {',
                                                   'int64_t received_byte_count,\n    bool is_proxied) {'))
    replace(engine, '''      net::HashValue pin_hash;
      if (!pin_hash.FromString(pin_sha256))
        return CheckResult(Cronet_RESULT_ILLEGAL_ARGUMENT_INVALID_PIN);
      pkp->pin_hashes.push_back(pin_hash);''', '''      auto pin_hash = net::HashValue::FromString(pin_sha256);
      if (!pin_hash)
        return CheckResult(Cronet_RESULT_ILLEGAL_ARGUMENT_INVALID_PIN);
      pkp->pin_hashes.push_back(*pin_hash);''')
    replace(src / 'components/grpc_support/bidirectional_stream.h',
            '      const quiche::HttpHeaderBlock& response_headers) override;',
            '      const quiche::HttpHeaderBlock& response_headers,\n      const net::ProxyInfo& used_proxy_info) override;')
    replace(src / 'components/grpc_support/bidirectional_stream.cc',
            'void BidirectionalStream::OnHeadersReceived(\n    const quiche::HttpHeaderBlock& response_headers) {',
            'void BidirectionalStream::OnHeadersReceived(\n    const quiche::HttpHeaderBlock& response_headers,\n    const net::ProxyInfo& used_proxy_info) {')
    anchor = '      context_config_builder.Build();'
    replace(engine, anchor, anchor + '''
  config->proxy_rules = params->proxy_rules;
  config->proxy_username = params->proxy_username;
  config->proxy_password = params->proxy_password;
  config->ignore_certificate_errors = params->ignore_certificate_errors;
''')

    context = cronet / 'cronet_context.cc'
    context_includes = [
        'components/cronet/cronet_ssl_config_service.h',
        'components/cronet/desktop_config.h',
        'components/cronet/tls_cipher_suite_mapper.h',
        'components/cronet/tls_curve_mapper.h',
        'net/proxy_resolution/proxy_config.h',
    ]
    content = context.read_text()
    for include in context_includes:
        content = content.replace(f'#include "{include}"\n', '')
    context.write_text(content)
    additions = '\n'.join(f'#include "{include}"' for include in context_includes)
    replace(context, '#include "components/cronet/cronet_global_state.h"',
            '#include "components/cronet/cronet_global_state.h"\n' + additions)
    replace(context, '''void CronetContext::NetworkTasks::SetSharedURLRequestContextBuilderConfig(
    net::URLRequestContextBuilder* context_builder) {
''', '''void CronetContext::NetworkTasks::SetSharedURLRequestContextBuilderConfig(
    net::URLRequestContextBuilder* context_builder) {
  context_builder->set_ssl_config_service(
      std::make_unique<CronetSSLConfigService>(
          TLSCipherSuiteMapper::NamesToIds(context_config_->tls_cipher_suites),
          TLSCurveMapper::NamesToGroupInfos(context_config_->tls_curves)));

''')
    anchor = '  context_builder.set_proxy_resolution_service(\n'
    replace(context, anchor, '''  if (!context_config_->proxy_rules.empty()) {
    net::ProxyConfig proxy_config;
    proxy_config.proxy_rules().ParseFromString(context_config_->proxy_rules);
    // Explicit engine proxy rules also apply to loopback test and local hosts.
    proxy_config.proxy_rules().bypass_rules.AddRulesToSubtractImplicit();
    proxy_config_service = std::make_unique<net::ProxyConfigServiceFixed>(
        net::ProxyConfigWithAnnotation(proxy_config, MISSING_TRAFFIC_ANNOTATION));
  }
  if (!context_config_->proxy_username.empty() ||
      !context_config_->proxy_password.empty()) {
    context_builder.set_proxy_delegate(CreateDesktopProxyDelegate(
        context_config_->proxy_username, context_config_->proxy_password));
  }
  if (context_config_->ignore_certificate_errors) {
    context_builder.SetCertVerifier(CreateInsecureCertVerifier());
  }

''' + anchor)
    # Expose credentials only to the native request delegate, never to origin
    # headers. They are immutable after the engine has started.
    replace(cronet / 'cronet_context.h', '  void InitRequestContextOnInitThread();', '''  const std::string& proxy_username() const { return proxy_username_; }
  const std::string& proxy_password() const { return proxy_password_; }
  void InitRequestContextOnInitThread();''')
    replace(cronet / 'cronet_context.h', '  // |network_tasks_| is owned by |this|.',
            '  const std::string proxy_username_;\n  const std::string proxy_password_;\n\n  // |network_tasks_| is owned by |this|.')
    replace(context, '      network_tasks_(\n', '''      proxy_username_(context_config->proxy_username),
      proxy_password_(context_config->proxy_password),
      network_tasks_(
''')
    request = cronet / 'cronet_url_request.cc'
    tag_block = '''  if (traffic_stats_tag_set_ || traffic_stats_uid_set_) {
    url_request_->set_socket_tag(net::SocketTag(
        traffic_stats_uid_set_ ? traffic_stats_uid_ : net::SocketTag::UNSET_UID,
        traffic_stats_tag_set_ ? traffic_stats_tag_
                               : net::SocketTag::UNSET_TAG));
  }'''
    replace(request, tag_block, '#if BUILDFLAG(IS_ANDROID)\n' + tag_block + '\n#endif')
    # JNI audit hooks are Android-specific; retain them on Android only.
    for include in ['base/android/jni_android.h', 'base/android/jni_string.h',
                    'components/cronet/android/cronet_jni_headers/CronetPccAuditLogger_jni.h']:
        replace(request, f'#include "{include}"', f'#if BUILDFLAG(IS_ANDROID)\n#include "{include}"\n#endif')
    # build_config must precede the conditional JNI includes.
    replace(request, '#include "components/cronet/cronet_url_request.h"',
            '#include "components/cronet/cronet_url_request.h"\n#include "build/build_config.h"\n#include "base/strings/utf_string_conversions.h"\n#include "net/http/http_auth.h"\n#include "net/base/auth.h"')
    content = request.read_text()
    import re
    content = re.sub(r'(?<!#if BUILDFLAG\(IS_ANDROID\)\n)(  \{\n    JNIEnv\* env = base::android::AttachCurrentThread\(\);.*?\n  \})',
                     r'#if BUILDFLAG(IS_ANDROID)\n\1\n#endif', content, flags=re.S)
    request.write_text(content)
    header = cronet / 'cronet_url_request.h'
    replace(header, '    void OnSSLCertificateError(', '''    void OnAuthRequired(net::URLRequest* request,
                        const net::AuthChallengeInfo& auth_info) override;
    std::string proxy_username_;
    std::string proxy_password_;
    bool proxy_auth_attempted_ = false;

    void OnSSLCertificateError(''')
    replace(request, 'void CronetURLRequest::NetworkTasks::OnSSLCertificateError(', '''void CronetURLRequest::NetworkTasks::OnAuthRequired(
    net::URLRequest* request, const net::AuthChallengeInfo& auth_info) {
  if (auth_info.is_proxy && !proxy_auth_attempted_ &&
      (!proxy_username_.empty() || !proxy_password_.empty())) {
    proxy_auth_attempted_ = true;
    request->SetAuth(net::AuthCredentials(base::UTF8ToUTF16(proxy_username_),
                                         base::UTF8ToUTF16(proxy_password_)));
    return;
  }
  request->CancelAuth();
}

void CronetURLRequest::NetworkTasks::OnSSLCertificateError(''')
    replace(request, '  DCHECK(context->IsOnNetworkThread());', '''  DCHECK(context->IsOnNetworkThread());
  proxy_username_ = context->proxy_username();
  proxy_password_ = context->proxy_password();''')
    # The latest metrics helper has an additional //net dependency. Keep the
    # existing target and all current common implementation sources.
    build = cronet / 'BUILD.gn'
    # Regenerate this owned build file from the pinned upstream baseline so
    # evolving desktop target definitions cannot accumulate nested wrappers.
    upstream_build = subprocess.check_output(
        ['git', 'show', 'HEAD:components/cronet/BUILD.gn'], cwd=src, text=True)
    build.write_text(upstream_build)
    replace(build, 'import("//build/config/android/rules.gni")', '''if (is_android) {
  import("//build/config/android/rules.gni")
}''')
    block = '''proto_java_library("request_context_config_java_proto") {
  proto_path = "."
  sources = [ "proto/request_context_config.proto" ]
}'''
    replace(build, block, 'if (is_android) {\n' + block + '\n}')
    replace(build, '    "//components/cronet/android:cronet_jni_headers",\n', '')
    replace(build, '    "cronet_context.cc",', '    "desktop_config.cc",\n    "desktop_config.h",\n    "cronet_context.cc",')
    replace(build, '    "desktop_config.cc",', '''    "cronet_ssl_config_service.cc",
    "cronet_ssl_config_service.h",
    "desktop_config.cc",''')
    replace(build, '    "desktop_config.h",', '''    "desktop_config.h",
    "tls_cipher_suite_mapper.cc",
    "tls_cipher_suite_mapper.h",
    "tls_curve_mapper.cc",
    "tls_curve_mapper.h",''')
    replace(build, '''    "//components/prefs",
    "//net",
  ]

  public_deps''', '''    "//components/prefs",
    "//net",
    "//third_party/boringssl",
  ]

  public_deps''')
    block = '''group("cronet_package") {
  testonly = true
  deps = [ "//components/cronet/android:cronet_package_android" ]
}'''
    replace(build, block, '''if (is_android) {
''' + block + '''
} else {
  shared_library("cronet") {
    output_name = "cronet"
    sources = [ "cronet_global_state_stubs.cc" ]
    deps = [
      "//base",
      "//base:i18n",
      "//components/cronet:cronet_common",
      "//components/cronet/native:cronet_native_impl",
      "//net",
    ]
    configs += [ "//build/config/compiler:no_exit_time_destructors" ]
  }
  group("cronet_package") {
    deps = [ ":cronet" ]
  }
}''')
    ssl_config = src / 'net/ssl/ssl_config_service.h'
    replace(ssl_config, '  // This configures a compliance policy that sets the cipher order for',
            '''  // Ordered TLS 1.2 and TLS 1.3 cipher suites supplied by the embedder.
  // Empty retains Chromium's built-in policy. BoringSSL writes TLS 1.3 suites
  // before TLS 1.2 suites; order is preserved within each protocol group.
  std::vector<uint16_t> ordered_cipher_suites;

  // This configures a compliance policy that sets the cipher order for''')
    socket = src / 'net/socket/ssl_client_socket_impl.cc'
    replace(socket, '''  if (!SSL_set_strict_cipher_list(ssl_.get(), command.c_str())) {
    LOG(ERROR) << "SSL_set_cipher_list('" << command << "') failed";
    return ERR_UNEXPECTED;
  }
''', '''  if (!SSL_set_strict_cipher_list(ssl_.get(), command.c_str())) {
    LOG(ERROR) << "SSL_set_cipher_list('" << command << "') failed";
    return ERR_UNEXPECTED;
  }
  const std::vector<uint16_t>& ordered_cipher_suites =
      context_->config().ordered_cipher_suites;
  if (!ordered_cipher_suites.empty() &&
      !SSL_set_cipher_list_with_order(ssl_.get(), ordered_cipher_suites.data(),
                                      ordered_cipher_suites.size())) {
    LOG(ERROR) << "SSL_set_cipher_list_with_order failed";
    return ERR_UNEXPECTED;
  }
''')
    bssl = src / 'third_party/boringssl/src'
    replace(bssl / 'ssl/ssl_lib.cc', '#include <utility>',
            '#include <utility>\n#include <vector>')
    replace(bssl / 'ssl/ssl_lib.cc',
            'const char *SSL_get_servername(const SSL *ssl, const int type) {',
            '''int SSL_set_cipher_list_with_order(SSL *ssl, const uint16_t *cipher_ids,
                                    size_t num_cipher_ids) {
  if (ssl == nullptr || cipher_ids == nullptr || num_cipher_ids == 0) {
    return 0;
  }
  auto *ssl_impl = FromOpaque(ssl);
  if (!ssl_impl->config) {
    return 0;
  }

  std::vector<uint16_t> tls12_cipher_ids;
  std::vector<uint16_t> tls13_cipher_ids;
  for (size_t i = 0; i < num_cipher_ids; i++) {
    const SSL_CIPHER *cipher = SSL_get_cipher_by_value(cipher_ids[i]);
    if (cipher == nullptr) {
      continue;
    }
    if (SSL_CIPHER_get_min_version(cipher) == TLS1_3_VERSION) {
      tls13_cipher_ids.push_back(cipher_ids[i]);
    } else {
      tls12_cipher_ids.push_back(cipher_ids[i]);
    }
  }
  if (tls12_cipher_ids.empty() && tls13_cipher_ids.empty()) {
    return 0;
  }

  UniquePtr<SSLCipherPreferenceList> cipher_list =
      MakeUnique<SSLCipherPreferenceList>();
  Array<bool> in_group_flags;
  if (!cipher_list || !in_group_flags.Init(tls12_cipher_ids.size()) ||
      !cipher_list->Init(Span(tls12_cipher_ids), in_group_flags)) {
    return 0;
  }
  if (!tls13_cipher_ids.empty()) {
    if (!set_tls13_ciphers(tls13_cipher_ids.data(), nullptr,
                           tls13_cipher_ids.size(),
                           &ssl_impl->config->tls13_cipher_list)) {
      return 0;
    }
  } else {
    // Do not silently restore default TLS 1.3 suites when the embedder only
    // requested TLS 1.2 suites.
    ssl_impl->config->tls13_cipher_list.Reset();
  }
  ssl_impl->config->cipher_list = std::move(cipher_list);
  return 1;
}

const char *SSL_get_servername(const SSL *ssl, const int type) {''')
    replace(bssl / 'include/openssl/ssl.h', '\n\n// TLS 1.3 Ciphers.\n',
            '''

// SSL_set_cipher_list_with_order sets the exact client cipher order. TLS 1.3
// suites are configured separately by BoringSSL and are emitted before TLS 1.2
// suites on the wire. Cipher IDs unknown to this BoringSSL build are ignored.
OPENSSL_EXPORT int SSL_set_cipher_list_with_order(SSL *ssl,
                                                  const uint16_t *cipher_ids,
                                                  size_t num_cipher_ids);


// TLS 1.3 Ciphers.
''')
    print(f'Prepared native C ABI for Chrome {lock["chrome_version"]}: {src}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / '.build/chromium/src')
    parser.add_argument('--proxy', default='http://127.0.0.1:8897')
    args = parser.parse_args()
    prepare(args.source.resolve(), args.proxy)
