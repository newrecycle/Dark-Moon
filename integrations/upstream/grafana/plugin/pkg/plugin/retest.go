package plugin

import (
	"context"
	"encoding/json"
	"fmt"
	"net/url"
	"reflect"
	"regexp"
	"strings"

	"github.com/grafana/grafana-plugin-sdk-go/backend"
	"github.com/grafana/grafana-plugin-sdk-go/data"
)

var retestIdentity = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.-]{0,199}$`)

// Retests expose lifecycle state independently of comparison rows. The fork
// initially stores verdicts: [] and adds findings only once comparison finishes.
func (d *Datasource) queryRetest(ctx context.Context, qm queryModel) backend.DataResponse {
	if !retestIdentity.MatchString(qm.RetestID) {
		return errResp(fmt.Errorf("a valid saved retest_id is required"))
	}
	body, failed := d.get(ctx, "/api/v1/retest/"+url.PathEscape(qm.RetestID), nil)
	if failed != nil { return *failed }
	var header map[string]any
	if json.Unmarshal(body, &header) != nil || header == nil {
		return errResp(fmt.Errorf("invalid retest response"))
	}
	identity := false
	for _, key := range []string{"retest_id", "id"} {
		if value, exists := header[key]; exists {
			if id, ok := value.(string); !ok || id != qm.RetestID {
				return errResp(fmt.Errorf("retest response identity does not match"))
			}
			identity = true
		}
	}
	status, valid := header["status"].(string)
	if !identity || !valid || strings.TrimSpace(status) == "" {
		return errResp(fmt.Errorf("retest response needs identity and lifecycle state"))
	}
	references := map[string]string{}
	for _, key := range []string{"base_campaign_id", "campaign_id", "new_campaign_id", "target_id", "run_id"} {
		value, exists := header[key]
		if !exists || value == nil { continue }
		id, ok := value.(string)
		if !ok || strings.TrimSpace(id) == "" {
			return errResp(fmt.Errorf("invalid retest reference"))
		}
		references[key] = id
	}
	if references["campaign_id"] != "" && references["new_campaign_id"] != "" && references["campaign_id"] != references["new_campaign_id"] {
		return errResp(fmt.Errorf("retest campaign references conflict"))
	}
	newCampaign := firstNonEmpty(references["new_campaign_id"], references["campaign_id"])

	var rows []any
	for _, key := range []string{"findings", "verdicts"} {
		if value, exists := header[key]; exists {
			array, ok := value.([]any)
			if !ok { return errResp(fmt.Errorf("retest comparisons need an array")) }
			if rows != nil && !reflect.DeepEqual(rows, array) {
				return errResp(fmt.Errorf("retest comparison aliases disagree"))
			}
			rows = array
		}
	}
	if rows == nil && status == "completed" {
		return errResp(fmt.Errorf("completed retest is missing comparison results"))
	}
	state := data.NewFrame("retest_state",
		data.NewField("retest_id", nil, []string{qm.RetestID}),
		data.NewField("status", nil, []string{status}),
		data.NewField("base_campaign_id", nil, []string{references["base_campaign_id"]}),
		data.NewField("new_campaign_id", nil, []string{newCampaign}),
		data.NewField("target_id", nil, []string{references["target_id"]}),
		data.NewField("run_id", nil, []string{references["run_id"]}),
	)
	findingID, currentID, verdict, severity, base, current := mk(), mk(), mk(), mk(), mk(), mk()
	seen := map[string]bool{}
	for _, value := range rows {
		row, ok := value.(map[string]any)
		if !ok { return errResp(fmt.Errorf("invalid retest comparison row")) }
		id, validID := row["finding_id"].(string)
		outcome, validOutcome := row["verdict"].(string)
		if !validID || strings.TrimSpace(id) == "" || !validOutcome || strings.TrimSpace(outcome) == "" || seen[id] {
			return errResp(fmt.Errorf("retest comparisons need unique finding identities and verdicts"))
		}
		seen[id] = true
		for _, key := range []string{"current_finding_id", "severity", "base_status", "new_status"} {
			if value, exists := row[key]; exists && value != nil {
				if _, ok := value.(string); !ok { return errResp(fmt.Errorf("invalid retest comparison metadata")) }
			}
		}
		findingID = append(findingID, id)
		currentID = append(currentID, s(row, "current_finding_id"))
		verdict = append(verdict, outcome)
		severity = append(severity, s(row, "severity"))
		base = append(base, s(row, "base_status"))
		current = append(current, s(row, "new_status"))
	}
	frame := data.NewFrame("retest",
		data.NewField("finding_id", nil, findingID),
		data.NewField("current_finding_id", nil, currentID),
		data.NewField("verdict", nil, verdict),
		data.NewField("severity", nil, severity),
		data.NewField("base_status", nil, base),
		data.NewField("new_status", nil, current),
	)
	return backend.DataResponse{Frames: data.Frames{state, frame}}
}
