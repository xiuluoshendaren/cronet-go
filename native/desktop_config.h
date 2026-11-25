// Copyright 2026 cronet-go contributors. BSD-style license; see LICENSE.
#ifndef COMPONENTS_CRONET_DESKTOP_CONFIG_H_
#define COMPONENTS_CRONET_DESKTOP_CONFIG_H_

#include <memory>
#include <string>

namespace net {
class CertVerifier;
class ProxyDelegate;
} // namespace net

namespace cronet {
std::unique_ptr<net::CertVerifier> CreateInsecureCertVerifier();
std::unique_ptr<net::ProxyDelegate>
CreateDesktopProxyDelegate(const std::string &username,
                           const std::string &password);
} // namespace cronet
#endif
