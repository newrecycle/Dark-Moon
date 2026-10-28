package plugin

import (
 "context"
 "encoding/json"
 "net/http"
 "net/http/httptest"
 "net/url"
 "strings"
 "testing"
 "time"

 "github.com/darkmoon/securityposture/pkg/models"
 "github.com/grafana/grafana-plugin-sdk-go/backend"
)

func grafanaFixture(t *testing.T, payload any) (*Datasource, *url.Values, func()) {
 t.Helper()
 got := &url.Values{}
 server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
  *got = r.URL.Query()
  w.Header().Set("Content-Type","application/json")
  if err := json.NewEncoder(w).Encode(payload); err != nil { t.Errorf("fixture response: %v",err) }
 }))
 return &Datasource{settings:&models.PluginSettings{BaseURL:server.URL},httpClient:server.Client()},got,server.Close
}

func retestFixture(t *testing.T, payload any) backend.DataResponse {
 t.Helper()
 d,_,closeServer := grafanaFixture(t,payload)
 defer closeServer()
 return d.queryRetest(context.Background(),queryModel{RetestID:"retest_1"})
}

func TestGrafanaIncompleteRetestPreservesIdentity(t *testing.T) {
 for _,status := range []string{"queued","running","failed","interrupted"} {
  t.Run(status,func(t *testing.T) {
   got:=retestFixture(t,map[string]any{"id":"retest_1","status":status,
    "base_campaign_id":"campaign_old","campaign_id":"campaign_new",
    "target_id":"target_1","run_id":"run_1","verdicts":[]any{}})
   if got.Error!=nil || len(got.Frames)!=2 { t.Fatalf("incomplete retest: %+v",got) }
   state,comparisons:=got.Frames[0],got.Frames[1]
   if state.Rows()!=1 || comparisons.Rows()!=0 { t.Fatalf("row shape: %d/%d",state.Rows(),comparisons.Rows()) }
   for i,want:=range []string{"retest_1",status,"campaign_old","campaign_new","target_1","run_1"} {
    if value:=state.Fields[i].At(0);value!=want { t.Errorf("%s = %v, want %s",state.Fields[i].Name,value,want) }
   }
  })
 }
}

func TestGrafanaRetestStrictComparisons(t *testing.T) {
 base:=func()map[string]any{return map[string]any{
  "id":"retest_1","status":"completed","base_campaign_id":"campaign_old",
  "campaign_id":"campaign_new","target_id":"target_1","run_id":"run_1"}}
 if got:=retestFixture(t,base());got.Error==nil {t.Fatal("completed retest without an explicit comparison array accepted")}
 empty:=base();empty["findings"]=[]any{}
 if got:=retestFixture(t,empty);got.Error!=nil || got.Frames[1].Rows()!=0 {t.Fatalf("valid empty comparison: %+v",got)}
 row:=func(id string)map[string]any {return map[string]any{"finding_id":id,"verdict":"not_observed","current_finding_id":"current_"+id}}
 valid:=base();valid["findings"]=[]any{row("finding_1")}
 got:=retestFixture(t,valid)
 if got.Error!=nil || got.Frames[1].Rows()!=1 {t.Fatalf("valid comparison: %+v",got)}
 if got.Frames[1].Fields[1].At(0)!="current_finding_1" || got.Frames[1].Fields[2].At(0)!="not_observed" {t.Fatal("finding lineage or unresolved verdict altered")}
 cases:=map[string]func(map[string]any){
  "null":func(m map[string]any){m["verdicts"]=nil},
  "object":func(m map[string]any){m["findings"]=map[string]any{}},
  "malformed":func(m map[string]any){m["findings"]=[]any{"broken"}},
  "missing verdict":func(m map[string]any){m["findings"]=[]any{map[string]any{"finding_id":"a"}}},
  "duplicate identity":func(m map[string]any){m["findings"]=[]any{row("a"),row("a")}},
  "conflicting aliases":func(m map[string]any){m["findings"]=[]any{row("a")};m["verdicts"]=[]any{row("b")}},
  "foreign retest":func(m map[string]any){m["retest_id"]="different"},
  "conflicting new campaign":func(m map[string]any){m["new_campaign_id"]="foreign"},
  "foreign comparison campaign":func(m map[string]any){r:=row("a");r["campaign_id"]="foreign";m["findings"]=[]any{r}},
  "foreign comparison base":func(m map[string]any){r:=row("a");r["base_campaign_id"]="foreign";m["findings"]=[]any{r}},
  "foreign comparison target":func(m map[string]any){r:=row("a");r["target_id"]="foreign";m["findings"]=[]any{r}},
  "foreign comparison run":func(m map[string]any){r:=row("a");r["run_id"]="foreign";m["findings"]=[]any{r}},
 }
 for name,change:=range cases {
  t.Run(name,func(t *testing.T){m:=base();change(m);if got:=retestFixture(t,m);got.Error==nil{t.Fatalf("invalid retest accepted: %+v",m)}})
 }
}

func TestGrafanaSelectedTimeRangeOverridesStaleFilters(t *testing.T) {
 d,received,closeServer:=grafanaFixture(t,map[string]any{"series":[]any{}})
 defer closeServer()
 from:=time.Date(2025,1,2,1,30,0,0,time.FixedZone("MST",-6*3600))
 to:=from.Add(24*time.Hour)
 qm:=queryModel{Metric:"severity",Params:map[string]string{"from":"2020-01-01T00:00:00Z","to":"2020-02-01T00:00:00Z","target_id":"target_5"}}
 if got:=d.queryTimeseries(context.Background(),qm,backend.TimeRange{From:from,To:to});got.Error!=nil{t.Fatal(got.Error)}
 if received.Get("from")!=from.UTC().Format(time.RFC3339Nano)||received.Get("to")!=to.UTC().Format(time.RFC3339Nano)||received.Get("target_id")!="target_5" {t.Fatalf("Grafana range not authoritative: %v",*received)}
 if got:=d.queryTimeseries(context.Background(),qm,backend.TimeRange{});got.Error!=nil||received.Get("from")!="2020-01-01T00:00:00Z" {t.Fatalf("explicit range ignored: %v",got.Error)}
 for _,params:=range []map[string]string{
  {"from":"invalid","to":"2025-01-01T00:00:00Z"},
  {"from":"2025-01-02T00:00:00Z","to":"2025-01-01T00:00:00Z"},
  {"unexpected":"x"},
 } {
  if got:=d.queryTimeseries(context.Background(),queryModel{Params:params},backend.TimeRange{});got.Error==nil {t.Errorf("invalid bounds accepted: %v",params)}
 }
}

func TestGrafanaISOWeeksAndSparseNullGaps(t *testing.T) {
 monday:=time.Date(2024,12,30,0,0,0,0,time.UTC)
 if !parseTime("2025-W01").Equal(monday)||!parseTime("2020-W53").Equal(time.Date(2020,12,28,0,0,0,0,time.UTC)) {t.Fatal("ISO week/year boundary mapped incorrectly")}
 for _,value:=range []string{"2021-W53","2025-W53","2025-W00","2025-W54","2025-W1"} {
  if !parseTime(value).IsZero(){t.Errorf("invalid ISO week accepted: %s",value)}
 }
 d,_,closeServer:=grafanaFixture(t,map[string]any{"series":[]any{
  map[string]any{"key":"critical","points":[]any{map[string]any{"t":"2025-W01","value":2},map[string]any{"t":"2025-W02","value":0}}},
  map[string]any{"key":"high","points":[]any{map[string]any{"t":"2024-W52","value":3}}},
 }})
 defer closeServer()
 result:=d.queryTimeseries(context.Background(),queryModel{},backend.TimeRange{})
 if result.Error!=nil {t.Fatal(result.Error)}
 f:=result.Frames[0]
 if f.Rows()!=3||len(f.Fields)!=3 {t.Fatalf("sparse frame shape %d, %d",f.Rows(),len(f.Fields))}
 if actual:=f.Fields[0].At(1).(time.Time);!actual.Equal(monday){t.Errorf("week timestamp %v",actual)}
 if x:=f.Fields[1].At(0).(*float64);x!=nil {t.Errorf("null gap became %v",x)}
 if x:=f.Fields[2].At(2).(*float64);x!=nil {t.Errorf("null gap became %v",x)}
 if x:=f.Fields[1].At(2).(*float64);x==nil||*x!=0 {t.Errorf("zero was lost: %v",x)}
}

func TestGrafanaFindingCampaignAndNullableCVSS(t *testing.T) {
 d,_,closeServer:=grafanaFixture(t,map[string]any{"data":[]any{
  map[string]any{"id":"f1","campaign_id":"c1","cvss_score":0.0,"description":"TOP SECRET","evidence":"TOP SECRET"},
  map[string]any{"id":"f2","campaign_id":"c2","cvss_score":nil},
  map[string]any{"id":"f3","campaign_id":"c3","cvss_score":"invalid"},
 }})
 defer closeServer()
 got:=d.queryFindings(context.Background(),queryModel{})
 if got.Error!=nil {t.Fatal(got.Error)}
 f:=got.Frames[0]
 campaign,cvss:=-1,-1
 for i,field:=range f.Fields {if field.Name=="campaign_id"{campaign=i};if field.Name=="cvss_score"{cvss=i};if strings.Contains(field.Name,"evidence")||field.Name=="description"{t.Fatal("sensitive column was exposed")}}
 if campaign<0||cvss<0 {t.Fatal("identity or CVSS column missing")}
 for i,want:=range []string{"c1","c2","c3"} {if f.Fields[campaign].At(i)!=want {t.Errorf("wrong campaign on row %d",i)}}
 scores:=f.Fields[cvss]
 if v:=scores.At(0).(*float64);v==nil||*v!=0 {t.Errorf("legitimate CVSS zero was lost")}
 if scores.At(1).(*float64)!=nil||scores.At(2).(*float64)!=nil {t.Fatal("missing/invalid CVSS should remain null")}
}
