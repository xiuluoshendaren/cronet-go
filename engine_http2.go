package cronet

import (
	"encoding/json"
	"fmt"
)

// SetHTTP2Settings merges custom HTTP/2 SETTINGS and Chromium's per-connection
// SETTINGS GREASE into the existing experimental options. Enable HTTP/2 separately.
// Settings not present in the map retain Chromium defaults. Call before startup.
func (p EngineParams) SetHTTP2Settings(settings map[uint16]uint32, grease bool) error {
	for id, value := range settings {
		switch id {
		case 2:
			if value != 0 {
				return fmt.Errorf("HTTP/2 server push is unsupported; setting 2 must be zero")
			}
		case 4:
			if value > 0x7fffffff {
				return fmt.Errorf("HTTP/2 initial window size exceeds 2^31-1")
			}
		case 5:
			if value < 16384 || value > 16777215 {
				return fmt.Errorf("HTTP/2 maximum frame size must be in [16384,16777215]")
			}
		case 8, 9:
			if value > 1 {
				return fmt.Errorf("HTTP/2 setting %d must be zero or one", id)
			}
		}
	}
	options := map[string]json.RawMessage{}
	if current := p.ExperimentalOptions(); current != "" {
		if err := json.Unmarshal([]byte(current), &options); err != nil || options == nil {
			return fmt.Errorf("experimental options must be a JSON object")
		}
	}
	http2 := map[string]json.RawMessage{}
	if current, ok := options["HTTP2"]; ok {
		if err := json.Unmarshal(current, &http2); err != nil || http2 == nil {
			return fmt.Errorf("HTTP2 experimental options must be a JSON object")
		}
	}
	http2["settings"], _ = json.Marshal(settings)
	http2["enable_settings_grease"], _ = json.Marshal(grease)
	options["HTTP2"], _ = json.Marshal(http2)
	encoded, err := json.Marshal(options)
	if err != nil {
		return err
	}
	p.SetExperimentalOptions(string(encoded))
	return nil
}
