// Copyright 2026 The cronet-go Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/cronet/tls_cipher_suite_mapper.h"

#include <string_view>

#include "base/logging.h"
#include "base/strings/string_util.h"

namespace cronet {

namespace {

struct CipherSuiteEntry {
  std::string_view name;
  uint16_t id;
};

// Keep the legacy names and wire values stable. Unknown and unsupported values
// are ignored by NamesToIds, as they were by the legacy implementation.
constexpr CipherSuiteEntry kCipherSuites[] = {
    {"TLS_GREASE", 0},
    {"TLS_AES_128_GCM_SHA256", 0x1301},
    {"TLS_AES_256_GCM_SHA384", 0x1302},
    {"TLS_CHACHA20_POLY1305_SHA256", 0x1303},
    {"TLS_AES_128_CCM_SHA256", 0x1304},
    {"TLS_AES_128_CCM_8_SHA256", 0x1305},
    {"TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256", 0xc02b},
    {"TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384", 0xc02c},
    {"TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305_SHA256", 0xcca9},
    {"TLS_ECDHE_ECDSA_WITH_AES_128_CBC_SHA", 0xc009},
    {"TLS_ECDHE_ECDSA_WITH_AES_256_CBC_SHA", 0xc00a},
    {"TLS_ECDHE_ECDSA_WITH_AES_128_CBC_SHA256", 0xc023},
    {"TLS_ECDHE_ECDSA_WITH_AES_256_CBC_SHA384", 0xc024},
    {"TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256", 0xc02f},
    {"TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384", 0xc030},
    {"TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256", 0xcca8},
    {"TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA", 0xc013},
    {"TLS_ECDHE_RSA_WITH_AES_256_CBC_SHA", 0xc014},
    {"TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA256", 0xc027},
    {"TLS_ECDHE_RSA_WITH_AES_256_CBC_SHA384", 0xc028},
    {"TLS_RSA_WITH_AES_128_GCM_SHA256", 0x009c},
    {"TLS_RSA_WITH_AES_256_GCM_SHA384", 0x009d},
    {"TLS_RSA_WITH_AES_128_CBC_SHA", 0x002f},
    {"TLS_RSA_WITH_AES_256_CBC_SHA", 0x0035},
    {"TLS_RSA_WITH_AES_128_CBC_SHA256", 0x003c},
    {"TLS_RSA_WITH_AES_256_CBC_SHA256", 0x003d},
    {"TLS_RSA_WITH_3DES_EDE_CBC_SHA", 0x000a},
    {"TLS_ECDHE_RSA_WITH_3DES_EDE_CBC_SHA", 0xc012},
    {"TLS_ECDHE_ECDSA_WITH_3DES_EDE_CBC_SHA", 0xc008},
};

}  // namespace

// static
uint16_t TLSCipherSuiteMapper::NameToId(const std::string& name) {
  const std::string normalized = base::ToUpperASCII(
      base::TrimWhitespaceASCII(name, base::TRIM_ALL));
  for (const auto& entry : kCipherSuites) {
    if (normalized == entry.name) {
      return entry.id;
    }
  }
  LOG(WARNING) << "Unknown TLS cipher suite \"" << name << "\"";
  return 0;
}

// static
std::vector<uint16_t> TLSCipherSuiteMapper::NamesToIds(
    const std::vector<std::string>& names) {
  std::vector<uint16_t> ids;
  ids.reserve(names.size());
  for (const std::string& name : names) {
    const uint16_t id = NameToId(name);
    // TLS_GREASE is a placeholder. BoringSSL 159 enables cipher GREASE on the
    // SSL_CTX and generates its value independently for each connection.
    if (id != 0) {
      ids.push_back(id);
    }
  }
  return ids;
}

}  // namespace cronet
