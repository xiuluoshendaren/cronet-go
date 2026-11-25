package cronet

// #include <stdlib.h>
// #include <stdbool.h>
// #include <cronet_c.h>
import "C"

import (
	"fmt"
	"net"
	"net/url"
	"strings"
	"unsafe"
)

// SetProxyCredentials configures authentication for this engine's HTTP proxies.
// Credentials are sent to proxies only; the origin User-Agent is unchanged.
func (p EngineParams) SetProxyCredentials(username, password string) {
	u, s := C.CString(username), C.CString(password)
	defer C.free(unsafe.Pointer(u))
	defer C.free(unsafe.Pointer(s))
	C.Cronet_EngineParams_proxy_username_set(p.ptr, u)
	C.Cronet_EngineParams_proxy_password_set(p.ptr, s)
}

// ProxyRules returns the configured Chromium proxy rules, without credentials.
func (p EngineParams) ProxyRules() string {
	return C.GoString(C.Cronet_EngineParams_proxy_rules_get(p.ptr))
}

// SetIgnoreCertificateErrors explicitly disables TLS certificate verification
// for requests and HTTPS proxies using this engine. The default is false.
func (p EngineParams) SetIgnoreCertificateErrors(ignore bool) {
	C.Cronet_EngineParams_ignore_certificate_errors_set(p.ptr, C.bool(ignore))
}

func (p EngineParams) IgnoreCertificateErrors() bool {
	return bool(C.Cronet_EngineParams_ignore_certificate_errors_get(p.ptr))
}

func parseProxyConfig(value string) (rules, username, password string, err error) {
	value = strings.TrimSpace(value)
	if strings.ContainsAny(value, "\x00\r\n") {
		return "", "", "", fmt.Errorf("proxy configuration contains a control character")
	}
	if value == "" {
		return "", "", "", nil
	}
	// Chromium rules may specify different proxies per scheme or fallbacks.
	if strings.ContainsAny(value, "=;,") && !strings.Contains(value, "@") {
		return value, "", "", nil
	}
	if !strings.Contains(value, "://") {
		value = "http://" + value
	}
	u, parseErr := url.Parse(value)
	if parseErr != nil {
		// url.Error includes the original URI; do not expose proxy credentials.
		return "", "", "", fmt.Errorf("invalid proxy URL")
	}
	u.Scheme = strings.ToLower(u.Scheme)
	if u.Scheme != "http" && u.Scheme != "https" && u.Scheme != "socks4" && u.Scheme != "socks5" {
		return "", "", "", fmt.Errorf("unsupported proxy scheme")
	}
	if u.Hostname() == "" || u.RawQuery != "" || u.Fragment != "" || (u.Path != "" && u.Path != "/") {
		return "", "", "", fmt.Errorf("proxy URL must contain only scheme, credentials and host")
	}
	if u.Port() != "" {
		if _, portErr := net.LookupPort("tcp", u.Port()); portErr != nil {
			return "", "", "", fmt.Errorf("invalid proxy port")
		}
	}
	if u.User != nil {
		if u.Scheme == "socks4" || u.Scheme == "socks5" {
			return "", "", "", fmt.Errorf("authenticated SOCKS proxies are not supported by Chromium")
		}
		username = u.User.Username()
		password, _ = u.User.Password()
	}
	if strings.ContainsAny(username+password, "\x00\r\n") || strings.Contains(username, ":") {
		return "", "", "", fmt.Errorf("invalid proxy credentials")
	}
	u.User = nil
	u.Path = ""
	return u.String(), username, password, nil
}
