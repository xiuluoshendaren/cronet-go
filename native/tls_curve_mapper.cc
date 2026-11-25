// Copyright 2026 The cronet-go Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/cronet/tls_curve_mapper.h"

#include "base/logging.h"
#include "base/strings/string_util.h"
#include "third_party/boringssl/src/include/openssl/ssl.h"

namespace cronet {

// static
net::SSLNamedGroupInfo TLSCurveMapper::NameToGroupInfo(
    const std::string& name) {
  const std::string normalized = base::ToUpperASCII(
      base::TrimWhitespaceASCII(name, base::TRIM_ALL));
  if (normalized == "X25519MLKEM768") {
    return {SSL_GROUP_X25519_MLKEM768, true};
  }
  if (normalized == "X25519") {
    return {SSL_GROUP_X25519, true};
  }
  if (normalized == "P-256" || normalized == "SECP256R1") {
    return {SSL_GROUP_SECP256R1, false};
  }
  if (normalized == "P-384" || normalized == "SECP384R1") {
    return {SSL_GROUP_SECP384R1, false};
  }
  if (normalized == "X25519KYBER768" ||
      normalized == "X25519KYBER768DRAFT00") {
    LOG(WARNING) << "TLS curve \"" << name
                 << "\" is unsupported: BoringSSL 159 removed draft Kyber groups";
    return {};
  }
  LOG(WARNING) << "Unknown TLS curve \"" << name << "\"";
  return {};
}

// static
std::vector<net::SSLNamedGroupInfo> TLSCurveMapper::NamesToGroupInfos(
    const std::vector<std::string>& names) {
  std::vector<net::SSLNamedGroupInfo> groups;
  groups.reserve(names.size());
  for (const std::string& name : names) {
    net::SSLNamedGroupInfo group = NameToGroupInfo(name);
    if (group.group_id != 0) {
      groups.push_back(group);
    }
  }
  return groups;
}

}  // namespace cronet
