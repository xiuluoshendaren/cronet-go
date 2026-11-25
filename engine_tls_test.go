package cronet

import (
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"reflect"
	"testing"
	"time"
)

func TestTLSExperimentalOptionsMerge(t *testing.T) {
	p := NewEngineParams()
	defer p.Destroy()
	p.SetExperimentalOptions(`{"QUIC":{"max_server_configs_stored_in_properties":7}}`)
	if err := p.SetTLSCipherSuites([]string{"TLS_AES_128_GCM_SHA256"}); err != nil {
		t.Fatal(err)
	}
	if err := p.SetTLSCurves(nil); err != nil {
		t.Fatal(err)
	}
	var options map[string]json.RawMessage
	if err := json.Unmarshal([]byte(p.ExperimentalOptions()), &options); err != nil {
		t.Fatal(err)
	}
	if options["QUIC"] == nil || string(options["tls_cipher_suites"]) != `["TLS_AES_128_GCM_SHA256"]` ||
		string(options["tls_curves"]) != `[]` {
		t.Fatalf("unexpected experimental options: %s", p.ExperimentalOptions())
	}
	for _, invalid := range []string{"null", "[]", "invalid"} {
		p.SetExperimentalOptions(invalid)
		if err := p.SetTLSCipherSuites(nil); err == nil {
			t.Errorf("accepted non-object options: %s", invalid)
		}
	}
}

type capturedClientHello struct {
	cipherSuites []uint16
	groups       []uint16
	keyShares    []uint16
}

type clientHelloResult struct {
	hello capturedClientHello
	err   error
}

func readClientHello(conn net.Conn) (capturedClientHello, error) {
	var hello capturedClientHello
	header := make([]byte, 5)
	if _, err := io.ReadFull(conn, header); err != nil {
		return hello, err
	}
	if header[0] != 22 {
		return hello, fmt.Errorf("TLS record type = %d, want handshake", header[0])
	}
	record := make([]byte, binary.BigEndian.Uint16(header[3:5]))
	if _, err := io.ReadFull(conn, record); err != nil {
		return hello, err
	}
	if len(record) < 4 || record[0] != 1 {
		return hello, fmt.Errorf("not a ClientHello")
	}
	body := record[4:]
	if record[1] != 0 || int(binary.BigEndian.Uint16(record[2:4])) != len(body) || len(body) < 35 {
		return hello, fmt.Errorf("fragmented or truncated ClientHello")
	}
	pos := 34 // legacy_version and random
	readByte := func() (byte, error) {
		if pos >= len(body) {
			return 0, io.ErrUnexpectedEOF
		}
		value := body[pos]
		pos++
		return value, nil
	}
	readUint16 := func() (uint16, error) {
		if pos+2 > len(body) {
			return 0, io.ErrUnexpectedEOF
		}
		value := binary.BigEndian.Uint16(body[pos : pos+2])
		pos += 2
		return value, nil
	}
	sessionLength, err := readByte()
	if err != nil || pos+int(sessionLength)+2 > len(body) {
		return hello, io.ErrUnexpectedEOF
	}
	pos += int(sessionLength)
	cipherBytes, err := readUint16()
	if err != nil || cipherBytes%2 != 0 || pos+int(cipherBytes) > len(body) {
		return hello, fmt.Errorf("invalid cipher suite list")
	}
	for end := pos + int(cipherBytes); pos < end; pos += 2 {
		hello.cipherSuites = append(hello.cipherSuites, binary.BigEndian.Uint16(body[pos:pos+2]))
	}
	compressionLength, err := readByte()
	if err != nil || pos+int(compressionLength)+2 > len(body) {
		return hello, io.ErrUnexpectedEOF
	}
	pos += int(compressionLength)
	extensionBytes, err := readUint16()
	if err != nil || pos+int(extensionBytes) != len(body) {
		return hello, fmt.Errorf("invalid extension list")
	}
	end := pos + int(extensionBytes)
	for pos < end {
		extensionType, err := readUint16()
		if err != nil {
			return hello, err
		}
		extensionLength, err := readUint16()
		if err != nil || pos+int(extensionLength) > end {
			return hello, fmt.Errorf("invalid extension %d", extensionType)
		}
		value := body[pos : pos+int(extensionLength)]
		pos += int(extensionLength)
		switch extensionType {
		case 10: // supported_groups
			if len(value) < 2 || int(binary.BigEndian.Uint16(value)) != len(value)-2 ||
				(len(value)-2)%2 != 0 {
				return hello, fmt.Errorf("invalid supported_groups")
			}
			for i := 2; i < len(value); i += 2 {
				hello.groups = append(hello.groups, binary.BigEndian.Uint16(value[i:i+2]))
			}
		case 51: // key_share
			if len(value) < 2 || int(binary.BigEndian.Uint16(value)) != len(value)-2 {
				return hello, fmt.Errorf("invalid key_share")
			}
			for i := 2; i < len(value); {
				if i+4 > len(value) {
					return hello, fmt.Errorf("invalid key_share entry")
				}
				hello.keyShares = append(hello.keyShares, binary.BigEndian.Uint16(value[i:i+2]))
				next := i + 4 + int(binary.BigEndian.Uint16(value[i+2:i+4]))
				if next > len(value) {
					return hello, fmt.Errorf("truncated key_share entry")
				}
				i = next
			}
		}
	}
	return hello, nil
}

func isGREASE(value uint16) bool {
	return value>>8 == value&0xff && value&0x0f0f == 0x0a0a
}

func TestTransportTLSParameters(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	captured := make(chan clientHelloResult, 1)
	go func() {
		conn, err := listener.Accept()
		if err != nil {
			captured <- clientHelloResult{err: err}
			return
		}
		defer conn.Close()
		listener.Close()
		conn.SetDeadline(time.Now().Add(5 * time.Second))
		hello, err := readClientHello(conn)
		captured <- clientHelloResult{hello: hello, err: err}
	}()

	transport := testTransport(t, "", true, func(p EngineParams) {
		if err := p.SetTLSCipherSuites([]string{
			"TLS_CHACHA20_POLY1305_SHA256",
			"TLS_AES_128_GCM_SHA256",
			"TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384",
			"TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256",
		}); err != nil {
			t.Error(err)
		}
		if err := p.SetTLSCurves([]string{"P-256", "X25519", "P-384"}); err != nil {
			t.Error(err)
		}
	})
	client := &http.Client{Transport: transport, Timeout: 5 * time.Second}
	if response, _ := client.Get("https://" + listener.Addr().String()); response != nil {
		response.Body.Close()
	}

	select {
	case result := <-captured:
		if result.err != nil {
			t.Fatal(result.err)
		}
		var ciphers []uint16
		for _, id := range result.hello.cipherSuites {
			if !isGREASE(id) {
				ciphers = append(ciphers, id)
			}
		}
		if want := []uint16{0x1303, 0x1301, 0xc030, 0xc02f}; !reflect.DeepEqual(ciphers, want) {
			t.Fatalf("ClientHello cipher suites = %#v, want %#v", ciphers, want)
		}
		var groups []uint16
		for _, id := range result.hello.groups {
			if !isGREASE(id) {
				groups = append(groups, id)
			}
		}
		if want := []uint16{23, 29, 24}; !reflect.DeepEqual(groups, want) {
			t.Fatalf("ClientHello supported_groups = %#v, want %#v", groups, want)
		}
		var keyShares []uint16
		for _, id := range result.hello.keyShares {
			if !isGREASE(id) {
				keyShares = append(keyShares, id)
			}
		}
		if want := []uint16{29}; !reflect.DeepEqual(keyShares, want) {
			t.Fatalf("ClientHello key_share groups = %#v, want %#v", keyShares, want)
		}
	case <-time.After(6 * time.Second):
		t.Fatal("timed out recording ClientHello")
	}
}
