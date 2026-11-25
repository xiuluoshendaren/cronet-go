package cronet

import "testing"

func TestHTTP2SettingsValidation(t *testing.T) {
	p := NewEngineParams()
	defer p.Destroy()
	for _, settings := range []map[uint16]uint32{{2: 1}, {4: 0xffffffff}, {5: 10}, {8: 2}, {9: 2}} {
		if err := p.SetHTTP2Settings(settings, false); err == nil {
			t.Errorf("accepted invalid SETTINGS: %v", settings)
		}
	}
	for _, options := range []string{"null", "[]", "invalid", `{"HTTP2":null}`, `{"HTTP2":[]}`} {
		p.SetExperimentalOptions(options)
		if err := p.SetHTTP2Settings(nil, true); err == nil {
			t.Errorf("accepted non-object options: %s", options)
		}
	}
}
