// Copyright 2026 cronet-go contributors. BSD-style license; see LICENSE.
#include "components/cronet/desktop_config.h"

#include <utility>

#include "base/base64.h"
#include "net/base/net_errors.h"
#include "net/base/proxy_delegate.h"
#include "net/cert/cert_verifier.h"
#include "net/cert/cert_verify_result.h"
#include "net/http/http_request_headers.h"

namespace cronet {
namespace {
// Installed only when the caller explicitly disables certificate verification.
class InsecureCertVerifier final : public net::CertVerifier {
public:
  int Verify(const RequestParams &params, net::CertVerifyResult *result,
             net::CompletionOnceCallback callback,
             std::unique_ptr<Request> *request,
             const net::NetLogWithSource &net_log) override {
    result->Reset();
    result->verified_cert = params.certificate();
    request->reset();
    return net::OK;
  }
  void Verify2QwacBinding(
      const std::string &binding, const std::string &hostname,
      const scoped_refptr<net::X509Certificate> &tls_cert,
      base::OnceCallback<void(const scoped_refptr<net::X509Certificate> &)>
          callback,
      const net::NetLogWithSource &net_log) override {
    std::move(callback).Run(nullptr);
  }
  void SetConfig(const Config &config) override {}
  void AddObserver(Observer *observer) override {}
  void RemoveObserver(Observer *observer) override {}
};

class DesktopProxyDelegate final : public net::ProxyDelegate {
public:
  DesktopProxyDelegate(const std::string &username, const std::string &password)
      : authorization_("Basic " +
                       base::Base64Encode(username + ":" + password)) {}

  void OnResolveProxy(const GURL &url, const net::NetworkAnonymizationKey &key,
                      const std::string &method,
                      const net::ProxyRetryInfoMap &retry_info,
                      net::ProxyInfo *result) override {}
  void OnFallback(const net::ProxyChain &chain, int error) override {}
  void OnSuccessfulRequestAfterFailures(
      const net::ProxyRetryInfoMap &retry_info) override {}
  base::expected<net::HttpRequestHeaders, net::Error>
  OnBeforeTunnelRequest(const net::ProxyChain &chain, size_t index,
                        OnBeforeTunnelRequestCallback callback) override {
    net::HttpRequestHeaders headers;
    headers.SetHeader(net::HttpRequestHeaders::kProxyAuthorization,
                      authorization_);
    return headers;
  }
  net::Error
  OnTunnelHeadersReceived(const net::ProxyChain &chain, size_t index,
                          const net::HttpResponseHeaders &headers,
                          net::CompletionOnceCallback callback) override {
    return net::OK;
  }
  void
  SetProxyResolutionService(net::ProxyResolutionService *service) override {}

private:
  const std::string authorization_;
};
} // namespace

std::unique_ptr<net::CertVerifier> CreateInsecureCertVerifier() {
  return std::make_unique<InsecureCertVerifier>();
}

std::unique_ptr<net::ProxyDelegate>
CreateDesktopProxyDelegate(const std::string &username,
                           const std::string &password) {
  return std::make_unique<DesktopProxyDelegate>(username, password);
}
} // namespace cronet
