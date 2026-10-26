package main

import (
	"os"

	"github.com/darkmoon/securityposture/pkg/plugin"
	"github.com/grafana/grafana-plugin-sdk-go/backend/datasource"
	"github.com/grafana/grafana-plugin-sdk-go/backend/log"
)

func main() {
	// datasource.Manage blocks until Grafana shuts the plugin down. The first
	// argument MUST match the datasource plugin id declared in plugin.json.
	if err := datasource.Manage(
		"darkmoon-securityposture-datasource",
		plugin.NewDatasource,
		datasource.ManageOpts{},
	); err != nil {
		log.DefaultLogger.Error(err.Error())
		os.Exit(1)
	}
}
