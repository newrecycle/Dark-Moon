package plugin

import "testing"

func TestPickEnforcesRedaction(t *testing.T) {
	in := map[string]any{
		"id":          "F-1",
		"title":       "SQLi",
		"description": "SHOULD NOT LEAK",
		"evidence":    "SHOULD NOT LEAK",
		"raw":         "SHOULD NOT LEAK",
		"token":       "SHOULD NOT LEAK",
	}
	// Even if a denied key is (mistakenly) requested, it must never be returned.
	out := pick(in, "id", "title", "description", "evidence", "raw", "token")
	if _, ok := out["description"]; ok {
		t.Fatal("description leaked through pick()")
	}
	if _, ok := out["evidence"]; ok {
		t.Fatal("evidence leaked through pick()")
	}
	if _, ok := out["raw"]; ok {
		t.Fatal("raw leaked through pick()")
	}
	if _, ok := out["token"]; ok {
		t.Fatal("token leaked through pick()")
	}
	if out["id"] != "F-1" || out["title"] != "SQLi" {
		t.Fatalf("allowlisted keys missing: %+v", out)
	}
}

func TestExtractListEnvelopes(t *testing.T) {
	bare := []byte(`[{"id":"1"},{"id":"2"}]`)
	if rows, err := extractList(bare); err != nil || len(rows) != 2 {
		t.Fatalf("bare array: rows=%d err=%v", len(rows), err)
	}
	env := []byte(`{"campaigns":[{"id":"1"}]}`)
	if rows, err := extractList(env, "campaigns"); err != nil || len(rows) != 1 {
		t.Fatalf("enveloped array: rows=%d err=%v", len(rows), err)
	}
}
