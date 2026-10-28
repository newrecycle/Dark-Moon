package plugin

import (
 "context"
 "encoding/json"
 "fmt"
 "net/http"
 "net/http/httptest"
 "strings"
 "sync/atomic"
 "testing"

 "github.com/grafana/grafana-plugin-sdk-go/backend"
 "github.com/darkmoon/securityposture/pkg/models"
)

func TestGrafanaRedirectNeverForwardsBearer(t *testing.T) {
 var followed atomic.Int64
 destination:=httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){
  followed.Add(1)
  if r.Header.Get("Authorization")!="" {t.Error("credential forwarded across redirect")}
 }))
 defer destination.Close()
 origin:=httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){
  if r.Header.Get("Authorization")!="Bearer local-only-secret" {t.Error("origin bearer missing")}
  http.Redirect(w,r,destination.URL+"/other",http.StatusFound)
 }))
 defer origin.Close()
 settings:=backend.DataSourceInstanceSettings{
  JSONData:json.RawMessage(fmt.Sprintf(`{"baseUrl":%q}`,origin.URL)),
  DecryptedSecureJSONData:map[string]string{"darkmoonToken":"local-only-secret"},
 }
 instance,err:=NewDatasource(context.Background(),settings)
 if err!=nil {t.Fatal(err)}
 d:=instance.(*Datasource)
 defer d.Dispose()
 _,status,err:=d.doGet(context.Background(),"/redirect",nil)
 if err!=nil||status!=http.StatusFound {t.Fatalf("redirect contract: status=%d error=%v",status,err)}
 if followed.Load()!=0 {t.Fatal("redirect was followed")}
 if _,e:=d.get(context.Background(),"/redirect",nil);e==nil||e.Error==nil {t.Fatal("redirect was treated as success")}
}

func TestGrafanaEvidenceMetadataProxyRedactsEverythingElse(t *testing.T) {
 upstream:=httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){
  if r.URL.Path!="/api/v1/vulnerabilities/finding_1/evidence-meta" {http.NotFound(w,r);return}
  payload:=map[string]any{
   "vuln_id":"finding_1","has_evidence":true,"has_screenshot":false,
   "has_extracted_data":false,"redacted":true,
   "description":"SENSITIVE-DESCRIPTION","evidence":"SENSITIVE-EVIDENCE",
   "raw":"SENSITIVE-RAW","token":"SENSITIVE-TOKEN",
   "counts":map[string]any{"commands":1,"payloads":0,"screenshots":0,"logs":0,"requests":2},
  }
  _=json.NewEncoder(w).Encode(payload)
 }))
 defer upstream.Close()
 d:=&Datasource{settings: &models.PluginSettings{BaseURL:upstream.URL},httpClient:upstream.Client()}
 request:=httptest.NewRequest("GET","/finding-meta?id=finding_1",nil)
 response:=httptest.NewRecorder()
 d.newResourceMux().ServeHTTP(response,request)
 if response.Code!=200 {t.Fatalf("metadata read: %d %s",response.Code,response.Body)}
 text:=response.Body.String()
 for _,secret:=range []string{"SENSITIVE-DESCRIPTION","SENSITIVE-EVIDENCE","SENSITIVE-RAW","SENSITIVE-TOKEN"} {
  if strings.Contains(text,secret) {t.Errorf("sensitive metadata exposed: %s",secret)}
 }
 var decoded map[string]any
 if err:=json.Unmarshal(response.Body.Bytes(),&decoded);err!=nil {t.Fatal(err)}
 if decoded["vuln_id"]!="finding_1" || decoded["counts"]==nil {t.Fatal("safe evidence counts were lost")}
}
