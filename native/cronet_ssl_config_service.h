// Copyright 2026 The cronet-go Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CRONET_CRONET_SSL_CONFIG_SERVICE_H_
#define COMPONENTS_CRONET_CRONET_SSL_CONFIG_SERVICE_H_

#include <cstdint>
#include <vector>

#include "net/ssl/ssl_config_service_defaults.h"

namespace cronet {

class CronetSSLConfigService : public net::SSLConfigServiceDefaults {
 public:
  CronetSSLConfigService(
      std::vector<uint16_t> cipher_suites,
      std::vector<net::SSLNamedGroupInfo> supported_named_groups);
  ~CronetSSLConfigService() override;

  net::SSLContextConfig GetSSLContextConfig() override;

 private:
  net::SSLContextConfig config_;
};

}  // namespace cronet

#endif  // COMPONENTS_CRONET_CRONET_SSL_CONFIG_SERVICE_H_
