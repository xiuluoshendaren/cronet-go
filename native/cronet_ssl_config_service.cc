// Copyright 2026 The cronet-go Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/cronet/cronet_ssl_config_service.h"

#include <utility>

namespace cronet {

CronetSSLConfigService::CronetSSLConfigService(
    std::vector<uint16_t> cipher_suites,
    std::vector<net::SSLNamedGroupInfo> supported_named_groups) {
  if (!cipher_suites.empty()) {
    config_.ordered_cipher_suites = std::move(cipher_suites);
  }
  if (!supported_named_groups.empty()) {
    config_.supported_named_groups = std::move(supported_named_groups);
  }
}

CronetSSLConfigService::~CronetSSLConfigService() = default;

net::SSLContextConfig CronetSSLConfigService::GetSSLContextConfig() {
  return config_;
}

}  // namespace cronet
