// Copyright 2026 The cronet-go Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CRONET_TLS_CIPHER_SUITE_MAPPER_H_
#define COMPONENTS_CRONET_TLS_CIPHER_SUITE_MAPPER_H_

#include <cstdint>
#include <string>
#include <vector>

namespace cronet {

class TLSCipherSuiteMapper {
 public:
  static uint16_t NameToId(const std::string& name);
  static std::vector<uint16_t> NamesToIds(
      const std::vector<std::string>& names);
};

}  // namespace cronet

#endif  // COMPONENTS_CRONET_TLS_CIPHER_SUITE_MAPPER_H_
