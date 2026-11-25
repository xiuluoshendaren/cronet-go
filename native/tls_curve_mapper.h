// Copyright 2026 The cronet-go Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CRONET_TLS_CURVE_MAPPER_H_
#define COMPONENTS_CRONET_TLS_CURVE_MAPPER_H_

#include <string>
#include <vector>

#include "net/ssl/ssl_config_service.h"

namespace cronet {

class TLSCurveMapper {
 public:
  static net::SSLNamedGroupInfo NameToGroupInfo(const std::string& name);
  static std::vector<net::SSLNamedGroupInfo> NamesToGroupInfos(
      const std::vector<std::string>& names);
};

}  // namespace cronet

#endif  // COMPONENTS_CRONET_TLS_CURVE_MAPPER_H_
