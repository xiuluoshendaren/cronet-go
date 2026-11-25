package cronet

import (
	"context"
	"crypto/tls"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func testTransport(t *testing.T, proxy string, insecure bool, configure ...func(EngineParams)) *RoundTripper {
	t.Helper()
	p := NewEngineParams()
	p.SetEnableHTTP2(true)
	p.SetEnableQuic(false)
	p.SetUserAgent("cronet-go-test")
	p.SetIgnoreCertificateErrors(insecure)
	for _, apply := range configure {
		apply(p)
	}
	if err := p.SetProxyServer(proxy); err != nil {
		p.Destroy()
		t.Fatal(err)
	}
	e := NewEngine()
	result := e.StartWithParams(p)
	p.Destroy()
	if result != ResultSuccess {
		e.Destroy()
		t.Fatalf("engine startup: %v", result)
	}
	tr := &RoundTripper{Engine: e, closeEngine: true, FollowRedirect: true}
	t.Cleanup(func() {
		// Cancellation callbacks release native requests asynchronously.
		deadline := time.Now().Add(5 * time.Second)
		for {
			if err := tr.Close(); err == nil {
				return
			} else if time.Now().After(deadline) {
				t.Error(err)
				return
			}
			time.Sleep(10 * time.Millisecond)
		}
	})
	return tr
}

func TestTransportHTTP2Settings(t *testing.T) {
	certServer := httptest.NewTLSServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
	certificates := certServer.TLS.Certificates
	certServer.Close()
	listener, err := tls.Listen("tcp", "127.0.0.1:0", &tls.Config{
		Certificates: certificates, NextProtos: []string{"h2"}, MinVersion: tls.VersionTLS12,
	})
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	frames := make(chan map[uint16]uint32, 1)
	go func() {
		conn, err := listener.Accept()
		if err != nil {
			frames <- nil
			return
		}
		defer conn.Close()
		conn.SetDeadline(time.Now().Add(5 * time.Second))
		preface := make([]byte, 24)
		if _, err := io.ReadFull(conn, preface); err != nil || string(preface) != "PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n" {
			frames <- nil
			return
		}
		header := make([]byte, 9)
		if _, err := io.ReadFull(conn, header); err != nil || header[3] != 4 {
			frames <- nil
			return
		}
		size := int(header[0])<<16 | int(header[1])<<8 | int(header[2])
		payload := make([]byte, size)
		if size%6 != 0 || size > 65536 {
			frames <- nil
			return
		}
		if _, err := io.ReadFull(conn, payload); err != nil {
			frames <- nil
			return
		}
		settings := map[uint16]uint32{}
		for i := 0; i < size; i += 6 {
			settings[binary.BigEndian.Uint16(payload[i:])] = binary.BigEndian.Uint32(payload[i+2:])
		}
		frames <- settings
	}()
	client := &http.Client{Transport: testTransport(t, "", true, func(p EngineParams) {
		p.SetExperimentalOptions(`{"QUIC":{"max_server_configs_stored_in_properties":7}}`)
		if err := p.SetHTTP2Settings(map[uint16]uint32{0xf123: 32060719, 6: 300000}, true); err != nil {
			t.Fatal(err)
		}
		var options map[string]json.RawMessage
		if err := json.Unmarshal([]byte(p.ExperimentalOptions()), &options); err != nil || options["QUIC"] == nil {
			t.Fatal("existing experimental options lost")
		}
	}), Timeout: 5 * time.Second}
	// The peer records SETTINGS then closes; no HTTP response is expected.
	if response, _ := client.Get("https://" + listener.Addr().String()); response != nil {
		response.Body.Close()
	}
	select {
	case settings := <-frames:
		if settings[0xf123] != 32060719 || settings[6] != 300000 {
			t.Fatalf("custom SETTINGS absent from wire: %v", settings)
		}
		for id := range settings {
			if id&0x0f0f == 0x0a0a {
				return
			}
		}
		t.Fatalf("GREASE SETTINGS absent from wire: %v", settings)
	case <-time.After(6 * time.Second):
		t.Fatal("timed out recording HTTP/2 SETTINGS")
	}
}

// Some io.Reader implementations return the final bytes together with io.EOF.
type finalChunkReader struct{ data string }

func (r *finalChunkReader) Read(p []byte) (int, error) {
	n := copy(p, r.data)
	r.data = r.data[n:]
	if r.data == "" {
		return n, io.EOF
	}
	return n, nil
}

func TestTransportUnknownLengthUpload(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, err := io.ReadAll(r.Body)
		if err != nil {
			t.Error(err)
		}
		w.Write(body)
	}))
	defer server.Close()
	client := &http.Client{Transport: testTransport(t, "", false), Timeout: 5 * time.Second}
	for _, length := range []int64{-1, 0} {
		req, err := http.NewRequest(http.MethodPost, server.URL, &finalChunkReader{data: "final upload bytes"})
		if err != nil {
			t.Fatal(err)
		}
		req.ContentLength = length
		response, err := client.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		body, err := io.ReadAll(response.Body)
		response.Body.Close()
		if err != nil || string(body) != "final upload bytes" {
			t.Fatalf("upload truncated for ContentLength=%d: %q, %v", length, body, err)
		}
	}
}

func TestEngineVersion(t *testing.T) {
	e := NewEngine()
	defer e.Destroy()
	if version := e.Version(); !strings.Contains(version, "159.0.8154.34") {
		t.Fatalf("unexpected native version: %q", version)
	}
}

func TestTransportHTTP(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("User-Agent") != "cronet-go-test" {
			t.Error("User-Agent changed")
		}
		if r.Header.Get("Proxy-Authorization") != "" {
			t.Error("proxy credentials leaked to origin")
		}
		io.WriteString(w, strings.Repeat("response", 8192))
	}))
	defer server.Close()
	client := &http.Client{Transport: testTransport(t, "", false), Timeout: 10 * time.Second}
	for i := 0; i < 5; i++ {
		resp, err := client.Get(server.URL)
		if err != nil {
			t.Fatal(err)
		}
		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil || string(body) != strings.Repeat("response", 8192) {
			t.Fatalf("response body mismatch: bytes=%d err=%v", len(body), err)
		}
		if resp.Status != "200 OK" {
			t.Fatalf("invalid HTTP status: %q", resp.Status)
		}
	}
}

func TestTransportTLS(t *testing.T) {
	server := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, "secure response")
	}))
	server.EnableHTTP2 = true
	server.StartTLS()
	defer server.Close()
	for _, insecure := range []bool{false, true} {
		client := &http.Client{Transport: testTransport(t, "", insecure), Timeout: 10 * time.Second}
		resp, err := client.Get(server.URL)
		if !insecure {
			if err == nil {
				resp.Body.Close()
				t.Fatal("untrusted certificate accepted by default")
			}
			continue
		}
		if err != nil {
			t.Fatal(err)
		}
		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil || string(body) != "secure response" || resp.ProtoMajor != 2 {
			t.Fatalf("TLS/HTTP2 response: proto=%s body=%q err=%v", resp.Proto, body, err)
		}
	}
}

func TestTransportProxyAuthentication(t *testing.T) {
	wantAuth := "Basic " + base64.StdEncoding.EncodeToString([]byte("local-user:local-password"))
	var authenticated atomic.Int32
	proxy := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Proxy-Authorization") != wantAuth {
			w.Header().Set("Proxy-Authenticate", `Basic realm="local-test"`)
			w.WriteHeader(http.StatusProxyAuthRequired)
			return
		}
		authenticated.Add(1)
		if r.Method == http.MethodConnect {
			upstream, err := net.DialTimeout("tcp", r.Host, 3*time.Second)
			if err != nil {
				http.Error(w, err.Error(), http.StatusBadGateway)
				return
			}
			downstream, buffered, err := w.(http.Hijacker).Hijack()
			if err != nil {
				upstream.Close()
				return
			}
			defer upstream.Close()
			defer downstream.Close()
			buffered.WriteString("HTTP/1.1 200 Connection Established\r\n\r\n")
			buffered.Flush()
			go io.Copy(upstream, buffered)
			io.Copy(downstream, upstream)
			return
		}
		if r.Header.Get("User-Agent") != "cronet-go-test" {
			t.Error("proxy authentication changed User-Agent")
		}
		io.WriteString(w, "via proxy")
	}))
	defer proxy.Close()
	origin := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Proxy-Authorization") != "" {
			t.Error("CONNECT credentials leaked to origin")
		}
		if r.Header.Get("User-Agent") != "cronet-go-test" {
			t.Error("origin User-Agent changed")
		}
		io.WriteString(w, "via tunnel")
	}))
	defer origin.Close()
	proxyURL := strings.Replace(proxy.URL, "://", "://local-user:local-password@", 1)
	client := &http.Client{Transport: testTransport(t, proxyURL, true), Timeout: 10 * time.Second}
	for _, tt := range []struct{ url, body string }{
		{"http://origin.invalid/test", "via proxy"},
		{origin.URL, "via tunnel"},
	} {
		resp, err := client.Get(tt.url)
		if err != nil {
			t.Fatal(err)
		}
		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil || string(body) != tt.body {
			t.Fatalf("proxy response: body=%q err=%v", body, err)
		}
	}
	if authenticated.Load() < 2 {
		t.Fatal("proxy was bypassed")
	}
}

func TestTransportCancellation(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		<-r.Context().Done()
	}))
	defer server.Close()
	client := &http.Client{Transport: testTransport(t, "", false)}
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, server.URL, nil)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := client.Do(req); err == nil {
		t.Fatal("canceled request succeeded")
	}
}
