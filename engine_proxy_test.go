package cronet

import (
	"strings"
	"testing"
)

func TestParseProxyConfig(t *testing.T) {
	for _, tt := range []struct {
		input, rules, user, password string
		invalid                      bool
	}{
		{input: ""},
		{input: "127.0.0.1:8897", rules: "http://127.0.0.1:8897"},
		{input: "http://user:p%40ss@localhost:8080/", rules: "http://localhost:8080", user: "user", password: "p@ss"},
		{input: "socks5://[::1]:1080", rules: "socks5://[::1]:1080"},
		{input: "http=localhost:8080;https=localhost:8081", rules: "http=localhost:8080;https=localhost:8081"},
		{input: "http://secret:password@localhost:99999", invalid: true},
		{input: "socks5://user:password@localhost:1080", invalid: true},
		{input: "ftp://localhost:21", invalid: true},
		{input: "http://localhost:80/path", invalid: true},
		{input: "http://localhost:80\r\nInjected: yes", invalid: true},
	} {
		t.Run(strings.ReplaceAll(tt.input, "\r\n", "_"), func(t *testing.T) {
			rules, user, password, err := parseProxyConfig(tt.input)
			if (err != nil) != tt.invalid {
				t.Fatalf("unexpected validation result: %v", err)
			}
			if err != nil {
				if strings.Contains(err.Error(), "password") || strings.Contains(err.Error(), "secret") {
					t.Fatal("validation error exposes credentials")
				}
				return
			}
			if rules != tt.rules || user != tt.user || password != tt.password {
				t.Fatalf("parsed configuration differs: rules=%q user=%q", rules, user)
			}
		})
	}
}

func TestEngineProxyParameters(t *testing.T) {
	p := NewEngineParams()
	defer p.Destroy()
	if p.IgnoreCertificateErrors() {
		t.Fatal("certificate verification must be enabled by default")
	}
	p.SetIgnoreCertificateErrors(true)
	if !p.IgnoreCertificateErrors() {
		t.Fatal("certificate bypass flag did not round trip")
	}
	if err := p.SetProxyServer("http://user:password@127.0.0.1:8897"); err != nil {
		t.Fatal(err)
	}
	if p.ProxyRules() != "http://127.0.0.1:8897" {
		t.Fatal("credentials must be removed from proxy rules")
	}
	if err := p.SetProxyServer("ftp://localhost"); err == nil {
		t.Fatal("unsupported proxy accepted")
	}
	if p.ProxyRules() != "http://127.0.0.1:8897" {
		t.Fatal("invalid configuration mutated existing rules")
	}
}
