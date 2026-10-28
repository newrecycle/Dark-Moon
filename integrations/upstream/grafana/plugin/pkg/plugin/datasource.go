package plugin

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"sort"
		"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/darkmoon/securityposture/pkg/models"
	"github.com/grafana/grafana-plugin-sdk-go/backend"
	"github.com/grafana/grafana-plugin-sdk-go/backend/instancemgmt"
	"github.com/grafana/grafana-plugin-sdk-go/backend/log"
	"github.com/grafana/grafana-plugin-sdk-go/backend/resource/httpadapter"
	"github.com/grafana/grafana-plugin-sdk-go/data"
)

// Compile-time interface checks.
var (
	_ backend.QueryDataHandler      = (*Datasource)(nil)
	_ backend.CheckHealthHandler    = (*Datasource)(nil)
	_ backend.CallResourceHandler   = (*Datasource)(nil)
	_ instancemgmt.InstanceDisposer = (*Datasource)(nil)
)

const httpTimeout = 15 * time.Second

// Datasource is the Darkmoon Security Posture backend datasource instance.
type Datasource struct {
	settings   *models.PluginSettings
	httpClient *http.Client
	resHandler backend.CallResourceHandler
}

// NewDatasource creates a new datasource instance.
func NewDatasource(_ context.Context, s backend.DataSourceInstanceSettings) (instancemgmt.Instance, error) {
	settings, err := models.LoadPluginSettings(s)
	if err != nil {
		return nil, err
	}

	ds := &Datasource{
		settings: settings,
		// TLS is verified by default; a 15s timeout bounds every call.
		httpClient: &http.Client{Timeout: httpTimeout, CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse }},
	}
	ds.resHandler = httpadapter.New(ds.newResourceMux())
	return ds, nil
}

// Dispose cleans up datasource instance resources.
func (d *Datasource) Dispose() {
	if d.httpClient != nil {
		d.httpClient.CloseIdleConnections()
	}
}

// ---------------------------------------------------------------------------
// HTTP plumbing
// ---------------------------------------------------------------------------

// doGet performs an authenticated GET against {baseUrl}{path} with optional
// query parameters. The bearer token is only attached when configured and is
// never logged or returned.
func (d *Datasource) doGet(ctx context.Context, path string, params url.Values) ([]byte, int, error) {
	if d.settings.BaseURL == "" {
		return nil, 0, fmt.Errorf("baseUrl is not configured")
	}

	u := d.settings.BaseURL + path
	if len(params) > 0 {
		u += "?" + params.Encode()
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, 0, err
	}
	req.Header.Set("Accept", "application/json")
	if token := d.token(); token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}

	resp, err := d.httpClient.Do(req)
	if err != nil {
		return nil, 0, err
	}
	defer func() { _ = resp.Body.Close() }()

	body, err := io.ReadAll(io.LimitReader(resp.Body, (32<<20)+1))
	if err != nil {
		return nil, resp.StatusCode, err
	}
	if len(body) > 32<<20 { return nil, resp.StatusCode, fmt.Errorf("upstream response exceeds the size limit") }
	return body, resp.StatusCode, nil
}

func (d *Datasource) token() string {
	if d.settings.Secrets == nil {
		return ""
	}
	return d.settings.Secrets.Token
}

// ---------------------------------------------------------------------------
// Redaction allowlist
// ---------------------------------------------------------------------------

// deniedKeys can never reach a frame, regardless of query type. Even if the
// upstream API over-returns, frames are built exclusively from the per-type
// allowlists below, and pick() enforces the denial defensively.
var deniedKeys = map[string]struct{}{
	"description":    {},
	"evidence":       {},
	"raw":            {},
	"logs":           {},
	"commands":       {},
	"payloads":       {},
	"payload":        {},
	"extracted_data": {},
	"token":          {},
	"darkmoontoken":  {},
	"authorization":  {},
	"secret":         {},
}

// pick returns a copy of m containing only the allowlisted keys, and never any
// denied key. This is the single choke point that guarantees hostile finding
// data (evidence, descriptions, raw output, tokens) cannot be surfaced.
func pick(m map[string]any, allow ...string) map[string]any {
	out := make(map[string]any, len(allow))
	for _, k := range allow {
		if _, denied := deniedKeys[strings.ToLower(k)]; denied {
			continue
		}
		if v, ok := m[k]; ok {
			switch value := v.(type) {
			case string: out[k] = value
			case bool: out[k] = value
			case float64: if !math.IsNaN(value) && !math.IsInf(value, 0) { out[k] = value }
			case json.Number: out[k] = value
			}
		}
	}
	return out
}

// ---------------------------------------------------------------------------
// Value coercion helpers
// ---------------------------------------------------------------------------

func asString(v any) string {
	switch t := v.(type) {
	case nil:
		return ""
	case string:
		return t
	case float64:
		return strconv.FormatFloat(t, 'f', -1, 64)
	case bool:
		return strconv.FormatBool(t)
	case json.Number:
		return t.String()
	default:
		return ""
	}
}

func asFloat(v any) float64 {
	var value float64
	switch typed := v.(type) {
	case float64: value = typed
	case json.Number: value, _ = typed.Float64()
	default: return 0
	}
	if math.IsNaN(value) || math.IsInf(value, 0) { return 0 }
	return value
}

func asInt(v any) int64 {
	value := asFloat(v)
	if value < 0 || value >= float64(math.MaxInt64) || math.Trunc(value) != value { return 0 }
	return int64(value)
}

func nullableCount(row map[string]any, key string) *int64 {
	value, ok := row[key].(float64)
	if !ok || value < 0 || value >= float64(math.MaxInt64) || math.IsNaN(value) || math.IsInf(value, 0) || math.Trunc(value) != value { return nil }
	count := int64(value)
	return &count
}

func s(m map[string]any, k string) string  { return asString(m[k]) }
func f(m map[string]any, k string) float64 { return asFloat(m[k]) }
func i(m map[string]any, k string) int64   { return asInt(m[k]) }

// asObject converts an arbitrary decoded JSON value to a map.
func asObject(v any) map[string]any {
	if m, ok := v.(map[string]any); ok {
		return m
	}
	return map[string]any{}
}

// extractList finds an array in the decoded payload. It accepts a bare array or
// an object wrapping the array under one of the provided keys (falling back to
// common envelope keys).
func extractList(raw []byte, keys ...string) ([]map[string]any, error) {
	var top any
	if err := json.Unmarshal(raw, &top); err != nil {
		return nil, err
	}
	if arr, ok := top.([]any); ok {
		rows := toMaps(arr)
		if len(rows) != len(arr) { return nil, fmt.Errorf("upstream list contains invalid rows") }
		return rows, nil
	}
	obj, ok := top.(map[string]any)
	if !ok { return nil, fmt.Errorf("upstream list needs an object or array") }
	candidates := append(append([]string{}, keys...), "data", "items", "results", "list")
	for _, k := range candidates {
		if value, exists := obj[k]; exists {
			arr, valid := value.([]any)
			if !valid { return nil, fmt.Errorf("upstream list envelope needs an array") }
			rows := toMaps(arr)
			if len(rows) != len(arr) { return nil, fmt.Errorf("upstream list contains invalid rows") }
			return rows, nil
		}
	}
	return nil, fmt.Errorf("upstream response has no recognized list")
}

func toMaps(arr []any) []map[string]any {
	out := make([]map[string]any, 0, len(arr))
	for _, el := range arr {
		if m, ok := el.(map[string]any); ok {
			out = append(out, m)
		}
	}
	return out
}

// ---------------------------------------------------------------------------
// CheckHealth
// ---------------------------------------------------------------------------

func (d *Datasource) CheckHealth(ctx context.Context, _ *backend.CheckHealthRequest) (*backend.CheckHealthResult, error) {
	if d.settings.BaseURL == "" {
		return &backend.CheckHealthResult{
			Status:  backend.HealthStatusError,
			Message: "Base URL is not set. Configure the Darkmoon API base URL.",
		}, nil
	}

	body, status, err := d.doGet(ctx, "/api/v1/campaigns", nil)
	if err != nil || status < 200 || status >= 300 {
		return &backend.CheckHealthResult{Status: backend.HealthStatusError, Message: "Protected campaign read failed; check the URL, token and account permissions."}, nil
	}
	if _, err := extractList(body, "campaigns"); err != nil {
		return &backend.CheckHealthResult{Status: backend.HealthStatusError, Message: "Campaign response did not match the integration contract."}, nil
	}
	return &backend.CheckHealthResult{Status: backend.HealthStatusOk, Message: "Authenticated campaign read succeeded."}, nil
}

func firstNonEmpty(vals ...string) string {
	for _, v := range vals {
		if v != "" {
			return v
		}
	}
	return ""
}

// ---------------------------------------------------------------------------
// QueryData
// ---------------------------------------------------------------------------

// queryModel is the per-query payload sent by the frontend.
type queryModel struct {
	QueryType string `json:"queryType"`

	// Findings / targets filters (pass-through).
	Severity   string `json:"severity"`
	Status     string `json:"status"`
	Category   string `json:"category"`
	CampaignID string `json:"campaign_id"`
	TargetID   string `json:"target_id"`
	ProjectID  string `json:"project_id"`
	RiskLevel  string `json:"risk_level"`

	// Timeseries.
	Metric string            `json:"metric"`
	Group  string            `json:"group"`
	Params map[string]string `json:"params"`

	// Retest.
	RetestID string `json:"retest_id"`
}

func (d *Datasource) QueryData(ctx context.Context, req *backend.QueryDataRequest) (*backend.QueryDataResponse, error) {
	resp := backend.NewQueryDataResponse()
	for _, q := range req.Queries {
		resp.Responses[q.RefID] = d.handleQuery(ctx, q)
	}
	return resp, nil
}

func (d *Datasource) handleQuery(ctx context.Context, q backend.DataQuery) backend.DataResponse {
	var qm queryModel
	if len(q.JSON) > 0 {
		if err := json.Unmarshal(q.JSON, &qm); err != nil {
			return errResp(fmt.Errorf("invalid query json: %w", err))
		}
	}
	queryType := qm.QueryType
	if queryType == "" {
		queryType = q.QueryType // backend.DataQuery may carry it separately
	}
	queryType = strings.ToLower(strings.TrimSpace(queryType))

	switch queryType {
	case "", "overview":
		return d.queryOverview(ctx)
	case "campaigns":
		return d.queryCampaigns(ctx)
	case "findings", "vulnerabilities":
		return d.queryFindings(ctx, qm)
	case "targets":
		return d.queryTargets(ctx, qm)
	case "timeseries":
		return d.queryTimeseries(ctx, qm)
	case "pullrequests", "pull-requests":
		return d.queryPullRequests(ctx, qm)
	case "remediation":
		return d.queryRemediation(ctx, qm)
	case "retest":
		return d.queryRetest(ctx, qm)
	default:
		return errResp(fmt.Errorf("unsupported queryType %q", queryType))
	}
}

func errResp(err error) backend.DataResponse {
	return backend.ErrDataResponse(backend.StatusBadGateway, err.Error())
}

// get is a small wrapper that fails the DataResponse on transport/HTTP errors.
func (d *Datasource) get(ctx context.Context, path string, params url.Values) ([]byte, *backend.DataResponse) {
	body, status, err := d.doGet(ctx, path, params)
	if err != nil {
		r := errResp(fmt.Errorf("upstream request failed; response details are withheld"))
		return nil, &r
	}
	if status < 200 || status >= 300 {
		r := errResp(fmt.Errorf("GET %s returned HTTP %d", path, status))
		return nil, &r
	}
	return body, nil
}

// ---- overview -------------------------------------------------------------

func (d *Datasource) queryOverview(ctx context.Context) backend.DataResponse {
	body, status, requestError := d.doGet(ctx, "/api/v1/dashboard/posture", nil)
	modern := status != http.StatusNotFound
	if requestError != nil { return errResp(fmt.Errorf("workspace posture read failed")) }
	if !modern {
		var failed *backend.DataResponse
		body, failed = d.get(ctx, "/api/v1/dashboard/overview", nil)
		if failed != nil { return *failed }
	} else if status < 200 || status >= 300 { return errResp(fmt.Errorf("workspace posture read returned HTTP %d", status)) }
	var obj map[string]any
	if json.Unmarshal(body, &obj) != nil || obj == nil { return errResp(fmt.Errorf("invalid overview response")) }
	if modern {
		if s(obj, "cohort") != "all_retained_records_current_state" { return errResp(fmt.Errorf("unknown posture cohort")) }
		totals := asObject(obj["totals"])
		obj["projects_count"] = totals["projects"]; obj["targets_count"] = totals["targets"]
		obj["campaigns_count"] = totals["campaigns"]; obj["total_vulnerabilities"] = totals["findings"]
	}

	for _, key := range []string{"projects_count", "targets_count", "campaigns_count", "total_vulnerabilities"} {
		if nullableCount(obj, key) == nil { return errResp(fmt.Errorf("overview response needs valid aggregate counts")) }
	}
	safe := pick(obj, "projects_count", "targets_count", "campaigns_count", "total_vulnerabilities")

	overview := data.NewFrame("overview",
		data.NewField("projects_count", nil, []int64{i(safe, "projects_count")}),
		data.NewField("targets_count", nil, []int64{i(safe, "targets_count")}),
		data.NewField("campaigns_count", nil, []int64{i(safe, "campaigns_count")}),
		data.NewField("total_vulnerabilities", nil, []int64{i(safe, "total_vulnerabilities")}),
	)

	frames := data.Frames{overview}
	if sf := distributionFrame("severity_distribution", asObject(obj["severity_distribution"])); sf != nil {
		frames = append(frames, sf)
	}
	if sf := distributionFrame("status_distribution", asObject(obj["status_distribution"])); sf != nil {
		frames = append(frames, sf)
	}
	return backend.DataResponse{Frames: frames}
}

// distributionFrame emits a long-format (key, value) frame from a map.
func distributionFrame(name string, m map[string]any) *data.Frame {
	if len(m) == 0 {
		return nil
	}
	keys := make([]string, 0, len(m))
	vals := make([]int64, 0, len(m))
	allowed := []string{"critical", "high", "medium", "low", "info"}
	if name == "status_distribution" { allowed = []string{"exploited", "confirmed", "unconfirmed", "remediated", "false_positive", "accepted"} }
	for _, key := range allowed {
		if value, ok := m[key].(float64); ok && value >= 0 && math.Trunc(value) == value && !math.IsInf(value, 0) {
			keys = append(keys, key); vals = append(vals, int64(value))
		}
	}
	return data.NewFrame(name,
		data.NewField("key", nil, keys),
		data.NewField("value", nil, vals),
	)
}

// ---- campaigns ------------------------------------------------------------

func (d *Datasource) queryCampaigns(ctx context.Context) backend.DataResponse {
	body, e := d.get(ctx, "/api/v1/campaigns", nil)
	if e != nil {
		return *e
	}
	rows, err := extractList(body, "campaigns")
	if err != nil {
		return errResp(err)
	}

	var (
		id, targetID, status, risk, date        = []string{}, []string{}, []string{}, []string{}, []string{}
		total, crit, high, med, low, info       = []*int64{}, []*int64{}, []*int64{}, []*int64{}, []*int64{}, []*int64{}
	)
	for _, r := range rows {
		if s(r, "id") == "" { return errResp(fmt.Errorf("upstream row has no string identity")) }
		safe := pick(r, "id", "target_id", "status", "overall_risk", "date")
		stats := asObject(r["stats"])
		id = append(id, s(safe, "id"))
		targetID = append(targetID, s(safe, "target_id"))
		status = append(status, s(safe, "status"))
		risk = append(risk, s(safe, "overall_risk"))
		date = append(date, s(safe, "date"))
		total = append(total, nullableCount(stats, "total_findings"))
		crit = append(crit, nullableCount(stats, "critical"))
		high = append(high, nullableCount(stats, "high"))
		med = append(med, nullableCount(stats, "medium"))
		low = append(low, nullableCount(stats, "low"))
		info = append(info, nullableCount(stats, "info"))
	}

	frame := data.NewFrame("campaigns",
		data.NewField("id", nil, id),
		data.NewField("target_id", nil, targetID),
		data.NewField("status", nil, status),
		data.NewField("overall_risk", nil, risk),
		data.NewField("date", nil, date),
		data.NewField("total_findings", nil, total),
		data.NewField("critical", nil, crit),
		data.NewField("high", nil, high),
		data.NewField("medium", nil, med),
		data.NewField("low", nil, low),
		data.NewField("info", nil, info),
	)
	return backend.DataResponse{Frames: data.Frames{frame}}
}

// ---- findings -------------------------------------------------------------

func (d *Datasource) queryFindings(ctx context.Context, qm queryModel) backend.DataResponse {
	params := url.Values{}
	addParam(params, "severity", qm.Severity)
	addParam(params, "status", qm.Status)
	addParam(params, "category", qm.Category)
	addParam(params, "campaign_id", qm.CampaignID)
	addParam(params, "target_id", qm.TargetID)
	addParam(params, "project_id", qm.ProjectID)

	body, e := d.get(ctx, "/api/v1/vulnerabilities", params)
	if e != nil {
		return *e
	}
	rows, err := extractList(body, "vulnerabilities", "findings")
	if err != nil {
		return errResp(err)
	}

	var (
		id, title, sev, status, cat, cve, mitre, endpoint = mk(), mk(), mk(), mk(), mk(), mk(), mk(), mk()
		cvss                                              = []float64{}
	)
	for _, r := range rows {
		// NOTE: description, evidence, raw, payloads are intentionally excluded.
		if s(r, "id") == "" { return errResp(fmt.Errorf("upstream row has no string identity")) }
		safe := pick(r, "id", "title", "severity", "status", "category", "cve", "cvss_score", "mitre_attack_id", "endpoint")
		id = append(id, s(safe, "id"))
		title = append(title, s(safe, "title"))
		sev = append(sev, s(safe, "severity"))
		status = append(status, s(safe, "status"))
		cat = append(cat, s(safe, "category"))
		cve = append(cve, s(safe, "cve"))
		cvss = append(cvss, f(safe, "cvss_score"))
		mitre = append(mitre, s(safe, "mitre_attack_id"))
		endpoint = append(endpoint, metadataURL(s(safe, "endpoint")))
	}

	frame := data.NewFrame("findings",
		data.NewField("id", nil, id),
		data.NewField("title", nil, title),
		data.NewField("severity", nil, sev),
		data.NewField("status", nil, status),
		data.NewField("category", nil, cat),
		data.NewField("cve", nil, cve),
		data.NewField("cvss_score", nil, cvss),
		data.NewField("mitre_attack_id", nil, mitre),
		data.NewField("endpoint", nil, endpoint),
	)
	return backend.DataResponse{Frames: data.Frames{frame}}
}

// ---- targets --------------------------------------------------------------

func (d *Datasource) queryTargets(ctx context.Context, qm queryModel) backend.DataResponse {
	params := url.Values{}
	addParam(params, "risk_level", qm.RiskLevel)

	body, e := d.get(ctx, "/api/v1/targets", params)
	if e != nil {
		return *e
	}
	rows, err := extractList(body, "targets")
	if err != nil {
		return errResp(err)
	}

	id, host, risk, status := mk(), mk(), mk(), mk()
	openVuln := []*int64{}
	for _, r := range rows {
		if s(r, "id") == "" { return errResp(fmt.Errorf("upstream row has no string identity")) }
		safe := pick(r, "id", "host", "risk_level", "status", "open_vuln")
		id = append(id, s(safe, "id"))
		host = append(host, s(safe, "host"))
		risk = append(risk, s(safe, "risk_level"))
		status = append(status, s(safe, "status"))
		openVuln = append(openVuln, nullableCount(safe, "open_vuln"))
	}

	frame := data.NewFrame("targets",
		data.NewField("id", nil, id),
		data.NewField("host", nil, host),
		data.NewField("risk_level", nil, risk),
		data.NewField("status", nil, status),
		data.NewField("open_vuln", nil, openVuln),
	)
	return backend.DataResponse{Frames: data.Frames{frame}}
}

// ---- timeseries -----------------------------------------------------------

func (d *Datasource) queryTimeseries(ctx context.Context, qm queryModel) backend.DataResponse {
	params := url.Values{}
	addParam(params, "metric", qm.Metric)
	addParam(params, "group", qm.Group)
	for k, v := range qm.Params {
		addParam(params, k, v)
	}

	body, e := d.get(ctx, "/api/v1/metrics/timeseries", params)
	if e != nil {
		return *e
	}

	var top map[string]any
	if err := json.Unmarshal(body, &top); err != nil {
		return errResp(err)
	}

	seriesRaw, valid := top["series"].([]any)
	if !valid { return errResp(fmt.Errorf("timeseries response needs a series array")) }
	type seriesValues struct { name string; values map[int64]float64 }
	series := []seriesValues{}
	instants := map[int64]time.Time{}
	names := map[string]bool{}
	for _, raw := range seriesRaw {
		row, ok := raw.(map[string]any)
		if !ok { return errResp(fmt.Errorf("invalid timeseries row")) }
		name := s(row, "key")
		points, ok := row["points"].([]any)
		if name == "" || names[name] || !ok { return errResp(fmt.Errorf("timeseries needs unique keys and point arrays")) }
		names[name] = true
		values := map[int64]float64{}
		for _, rawPoint := range points {
			point, ok := rawPoint.(map[string]any)
			if !ok { return errResp(fmt.Errorf("invalid timeseries point")) }
			instant := parseTime(s(point, "t"))
			value, ok := point["value"].(float64)
			if instant.IsZero() || !ok || math.IsNaN(value) || math.IsInf(value, 0) { return errResp(fmt.Errorf("invalid timeseries timestamp or value")) }
			key := instant.UnixNano()
			if _, exists := values[key]; exists { return errResp(fmt.Errorf("duplicate timeseries timestamp")) }
			values[key] = value; instants[key] = instant
		}
		series = append(series, seriesValues{name: name, values: values})
	}
	keys := make([]int64, 0, len(instants))
	for key := range instants { keys = append(keys, key) }
	sort.Slice(keys, func(a, b int) bool { return keys[a] < keys[b] })
	times := make([]time.Time, len(keys))
	for index, key := range keys { times[index] = instants[key] }
	fields := []*data.Field{data.NewField("t", nil, times)}
	for _, row := range series {
		values := make([]*float64, len(keys))
		for index, key := range keys { if value, ok := row.values[key]; ok { copy := value; values[index] = &copy } }
		fields = append(fields, data.NewField(row.name, nil, values))
	}
	frame := data.NewFrame("timeseries", fields...)
	frame.Meta = &data.FrameMeta{Type: data.FrameTypeTimeSeriesWide}
	return backend.DataResponse{Frames: data.Frames{frame}}
}

func firstNonNil(vals ...any) any {
	for _, v := range vals {
		if v != nil {
			return v
		}
	}
	return nil
}

func parseTime(v string) time.Time {
	if v == "" {
		return time.Time{}
	}
	for _, layout := range []string{time.RFC3339Nano, time.RFC3339, "2006-01-02T15:04:05", "2006-01-02"} {
		if t, err := time.Parse(layout, v); err == nil {
			return t
		}
	}
	// epoch seconds / millis fallback
	if n, err := strconv.ParseInt(v, 10, 64); err == nil {
		if n > 1e12 {
			return time.UnixMilli(n)
		}
		return time.Unix(n, 0)
	}
	return time.Time{}
}

// ---- pull requests --------------------------------------------------------

func (d *Datasource) queryPullRequests(ctx context.Context, qm queryModel) backend.DataResponse {
	params := url.Values{}
	addParam(params, "campaign_id", qm.CampaignID)

	body, e := d.get(ctx, "/api/v1/pull-requests", params)
	if e != nil {
		return *e
	}
	rows, err := extractList(body, "pull_requests", "pullRequests")
	if err != nil {
		return errResp(err)
	}

	id, provider, repo, state, urlf, findingIDs := mk(), mk(), mk(), mk(), mk(), mk()
	number := []*int64{}
	for _, r := range rows {
		published, explicit := r["published"].(bool)
		if explicit && !published || !explicit && (s(r, "provider") == "" || i(r, "number") <= 0) { continue }
		safe := pick(r, "id", "provider", "repo", "number", "state", "url")
		id = append(id, s(safe, "id"))
		provider = append(provider, s(safe, "provider"))
		repo = append(repo, s(safe, "repo"))
		number = append(number, nullableCount(safe, "number"))
		state = append(state, s(safe, "state"))
		urlf = append(urlf, metadataURL(s(safe, "url")))
		findingIDs = append(findingIDs, joinIDs(r["finding_ids"]))
	}

	frame := data.NewFrame("pullrequests",
		data.NewField("id", nil, id),
		data.NewField("provider", nil, provider),
		data.NewField("repo", nil, repo),
		data.NewField("number", nil, number),
		data.NewField("state", nil, state),
		data.NewField("url", nil, urlf),
		data.NewField("finding_ids", nil, findingIDs),
	)
	return backend.DataResponse{Frames: data.Frames{frame}}
}

func joinIDs(v any) string {
	arr, ok := v.([]any)
	if !ok {
		return asString(v)
	}
	parts := make([]string, 0, len(arr))
	for _, el := range arr {
		if id, valid := el.(string); valid { parts = append(parts, id) }
	}
	return strings.Join(parts, ",")
}

// ---- local remediation proposals (never a published-PR count) ---------------
func (d *Datasource) queryRemediation(ctx context.Context, qm queryModel) backend.DataResponse {
	params := url.Values{}
	addParam(params, "campaign_id", qm.CampaignID)
	body, failed := d.get(ctx, "/api/v1/pull-requests", params)
	if failed != nil { return *failed }
	rows, err := extractList(body, "pull_requests", "pullRequests")
	if err != nil { return errResp(err) }
	ids, campaigns, findings, statuses, confidence := mk(), mk(), mk(), mk(), mk()
	for _, row := range rows {
		published, explicit := row["published"].(bool)
		if !explicit || published { continue }
		if s(row, "id") == "" { return errResp(fmt.Errorf("proposal has no identity")) }
		ids = append(ids, s(row, "id")); campaigns = append(campaigns, s(row, "campaign_id"))
		findings = append(findings, joinIDs(row["finding_ids"])); statuses = append(statuses, s(row, "status"))
		confidence = append(confidence, s(row, "confidence"))
	}
	frame := data.NewFrame("local_proposals", data.NewField("proposal_id", nil, ids), data.NewField("campaign_id", nil, campaigns),
		data.NewField("finding_ids", nil, findings), data.NewField("status", nil, statuses), data.NewField("judge_confidence", nil, confidence))
	return backend.DataResponse{Frames: data.Frames{frame}}
}

// ---- retest ---------------------------------------------------------------

func (d *Datasource) queryRetest(ctx context.Context, qm queryModel) backend.DataResponse {
	if qm.RetestID == "" {
		return errResp(fmt.Errorf("retest_id is required for the retest query"))
	}
	body, e := d.get(ctx, "/api/v1/retest/"+url.PathEscape(qm.RetestID), nil)
	if e != nil {
		return *e
	}
	var header map[string]any
	if json.Unmarshal(body, &header) != nil || s(header, "retest_id") != qm.RetestID { return errResp(fmt.Errorf("retest response identity does not match")) }
	state := data.NewFrame("retest_state", data.NewField("retest_id", nil, []string{qm.RetestID}), data.NewField("status", nil, []string{s(header, "status")}))
	rows, err := extractList(body, "findings")
	if err != nil {
		return errResp(err)
	}

	findingID, verdict, sev, base, nw := mk(), mk(), mk(), mk(), mk()
	for _, r := range rows {
		safe := pick(r, "finding_id", "verdict", "severity", "base_status", "new_status")
		findingID = append(findingID, s(safe, "finding_id"))
		verdict = append(verdict, s(safe, "verdict"))
		sev = append(sev, s(safe, "severity"))
		base = append(base, s(safe, "base_status"))
		nw = append(nw, s(safe, "new_status"))
	}

	frame := data.NewFrame("retest",
		data.NewField("finding_id", nil, findingID),
		data.NewField("verdict", nil, verdict),
		data.NewField("severity", nil, sev),
		data.NewField("base_status", nil, base),
		data.NewField("new_status", nil, nw),
	)
	return backend.DataResponse{Frames: data.Frames{state, frame}}
}

// ---------------------------------------------------------------------------
// CallResource — safe metadata proxy
// ---------------------------------------------------------------------------

func (d *Datasource) CallResource(ctx context.Context, req *backend.CallResourceRequest, sender backend.CallResourceResponseSender) error {
	return d.resHandler.CallResource(ctx, req, sender)
}

func (d *Datasource) newResourceMux() *http.ServeMux {
	mux := http.NewServeMux()
	// /finding-meta?id=<id> -> GET /api/v1/vulnerabilities/{id}/evidence-meta
	// Returns evidence *metadata* only (counts, types) — safe by construction.
	mux.HandleFunc("/finding-meta", func(w http.ResponseWriter, r *http.Request) {
		id := strings.TrimSpace(r.URL.Query().Get("id"))
		if id == "" {
			http.Error(w, `{"error":"id is required"}`, http.StatusBadRequest)
			return
		}
		body, status, err := d.doGet(r.Context(), "/api/v1/vulnerabilities/"+url.PathEscape(id)+"/evidence-meta", nil)
		if err != nil {
			log.DefaultLogger.Error("finding-meta proxy failed")
			http.Error(w, `{"error":"upstream request failed"}`, http.StatusBadGateway)
			return
		}
		if status < 200 || status >= 300 { http.Error(w, `{"error":"upstream metadata read failed"}`, status); return }
		var source map[string]any
		if json.Unmarshal(body, &source) != nil || s(source, "vuln_id") != id { http.Error(w, `{"error":"invalid metadata response"}`, http.StatusBadGateway); return }
		output := pick(source, "vuln_id", "has_evidence", "has_screenshot", "has_extracted_data", "redacted")
		counts := map[string]any{}
		for _, key := range []string{"commands", "payloads", "screenshots", "logs", "requests"} {
			value, ok := asObject(source["counts"])[key].(float64)
			if !ok || value < 0 || math.Trunc(value) != value || math.IsInf(value, 0) { http.Error(w, `{"error":"invalid metadata counts"}`, http.StatusBadGateway); return }
			counts[key] = value
		}
		output["counts"] = counts
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(output)
	})
	return mux
}

// ---------------------------------------------------------------------------
// small helpers
// ---------------------------------------------------------------------------

func metadataURL(value string) string {
	fields := strings.Fields(value)
	if len(fields) > 1 { switch strings.ToUpper(fields[0]) { case "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS": value = strings.TrimSpace(strings.TrimPrefix(value, fields[0])) } }
	parts := strings.SplitN(value, "?", 2)
	value = strings.SplitN(parts[0], "#", 2)[0]
	if parsed, err := url.Parse(value); err == nil && parsed.Host != "" { parsed.User = nil; return parsed.String() }
	return value
}

func mk() []string { return []string{} }

func addParam(v url.Values, key, val string) {
	if strings.TrimSpace(val) != "" {
		v.Set(key, val)
	}
}
