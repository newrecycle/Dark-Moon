package models

import (
	"encoding/json"
	"fmt"
	"strings"

	"github.com/grafana/grafana-plugin-sdk-go/backend"
)

// Mode reflects which Darkmoon edition the datasource talks to.
const (
	ModeAuto = "auto"
	ModeOSS  = "oss"
	ModePro  = "pro"
)

// PluginSettings holds the non-secret datasource configuration (jsonData).
type PluginSettings struct {
	BaseURL string `json:"baseUrl"`
	Mode    string `json:"mode"`

	// Secrets is populated from DecryptedSecureJSONData. The token itself is
	// never serialized back out (json:"-") so it cannot leak through a frame,
	// a log line or an API response.
	Secrets *SecretPluginSettings `json:"-"`
}

// SecretPluginSettings holds the decrypted secure fields.
type SecretPluginSettings struct {
	Token string
}

// LoadPluginSettings parses the datasource instance settings.
func LoadPluginSettings(source backend.DataSourceInstanceSettings) (*PluginSettings, error) {
	settings := PluginSettings{}
	if len(source.JSONData) > 0 {
		if err := json.Unmarshal(source.JSONData, &settings); err != nil {
			return nil, fmt.Errorf("could not unmarshal PluginSettings json: %w", err)
		}
	}

	settings.BaseURL = strings.TrimRight(strings.TrimSpace(settings.BaseURL), "/")
	settings.Mode = strings.ToLower(strings.TrimSpace(settings.Mode))
	if settings.Mode == "" {
		settings.Mode = ModeAuto
	}

	settings.Secrets = loadSecretPluginSettings(source.DecryptedSecureJSONData)
	return &settings, nil
}

func loadSecretPluginSettings(source map[string]string) *SecretPluginSettings {
	return &SecretPluginSettings{
		Token: source["darkmoonToken"],
	}
}
