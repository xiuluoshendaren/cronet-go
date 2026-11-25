package cronet

import (
	"encoding/json"
	"fmt"
)

// SetTLSCipherSuites sets the legacy ordered TLS cipher-suite name list.
// Empty retains Chromium defaults. Call before startup.
func (p EngineParams) SetTLSCipherSuites(names []string) error {
	return p.setTLSNames("tls_cipher_suites", names)
}

// SetTLSCurves sets the legacy ordered TLS supported-groups name list.
// Empty retains Chromium defaults. Call before startup.
func (p EngineParams) SetTLSCurves(names []string) error {
	return p.setTLSNames("tls_curves", names)
}

func (p EngineParams) setTLSNames(key string, names []string) error {
	options := map[string]json.RawMessage{}
	if current := p.ExperimentalOptions(); current != "" {
		if err := json.Unmarshal([]byte(current), &options); err != nil || options == nil {
			return fmt.Errorf("experimental options must be a JSON object")
		}
	}
	if names == nil {
		names = []string{}
	}
	encoded, err := json.Marshal(names)
	if err != nil {
		return err
	}
	options[key] = encoded
	encoded, err = json.Marshal(options)
	if err != nil {
		return err
	}
	p.SetExperimentalOptions(string(encoded))
	return nil
}
