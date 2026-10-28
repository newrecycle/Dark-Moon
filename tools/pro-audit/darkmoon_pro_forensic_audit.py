#!/usr/bin/env python3
"""Read-only DarkMoon Pro artifact and fork parity auditor.

Standard run: image metadata/files + contracts + frontend + fork comparison + reports.
Optional late work: native symbol/disassembly, Ghidra pseudocode, authorized live HTTP,
passive browser observations. No license circumvention, scans, or API write requests.
"""
from __future__ import annotations
import argparse, ast, concurrent.futures, csv, datetime, hashlib, io, json, os, pathlib
import re, shutil, subprocess, sys, tarfile, time, traceback, urllib.error, urllib.parse
import urllib.request, zipfile
from collections import Counter, defaultdict

PIN = "ascit/opencode-darkmoon-pro@sha256:48248382877ec1fd7362d2268656956268129d5ea565befab3a24436ea2fc907"
ROOTS = {
 "api": "/opt/darkmoon/mcp/server/api", "remediation": "/opt/darkmoon/mcp/server/src/remediation",
 "tests": "/opt/darkmoon/mcp/server/tests", "dashboard": "/opt/darkmoon/dashboard",
 "nginx-dashboard.conf": "/etc/nginx/nginx-dashboard.conf",
 "server.py": "/opt/darkmoon/mcp/server/src/server.py",
 "mcp_monitoring.py": "/opt/darkmoon/mcp/server/src/mcp_monitoring.py",
 "WORKFLOW_GUIDE.md": "/opt/darkmoon/mcp/server/WORKFLOW_GUIDE.md",
}
STAGES = ("inventory", "contracts", "frontend", "fork", "native", "discovery", "runtime", "browser", "ghidra", "report", "pack")
SECRET = re.compile(r"password|passwd|secret|token|authorization|api[-_]?key|private[-_]?key|cookie|credential|evidence|raw[-_]?output|session[-_]?id", re.I)
SECURITY_HEADERS = {"content-type", "cache-control", "www-authenticate", "allow", "access-control-allow-origin"}
URL_BASE = re.compile(r"^https?://", re.I)
ROUTE_DECO = {"get", "post", "put", "patch", "delete", "options", "head"}
UI_ROUTES = ["/", "/login", "/change-password", "/new-campaign", "/scheduler", "/history", "/projects", "/project/:id", "/campaign/:id", "/report/:id", "/vulnerability/:id", "/infra/:id", "/pull-request/:id"]
SAFE_DEFAULT_GETS = ["/api/v1/system/info", "/openapi.json", "/health"]
RE_SUSPECT_VALUE = re.compile(r"(?i)(bearer\s+[\w.\-]+|(?:(?:sk|ghp|glpat|xox[baprs])-)[\w-]{12,})")


def cmd(args, *, timeout=180, cwd=None, check=True, stdout_file=None):
    if stdout_file:
        with open(stdout_file, "wb") as f:
            p = subprocess.run(args, stdout=f, stderr=subprocess.PIPE, timeout=timeout, cwd=cwd, check=False)
        res = p.stderr.decode("utf-8", "replace")
    else:
        p = subprocess.run(args, capture_output=True, timeout=timeout, cwd=cwd, check=False)
        res = p.stdout.decode("utf-8", "replace")
    if check and p.returncode:
        raise RuntimeError(f"Command failed ({p.returncode}): {args[:6]}\n{p.stderr.decode('utf-8','replace')[-1500:]}")
    return res


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def outjson(path, data):
    path = pathlib.Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def readjson(path, default=None):
    try: return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError): return default


def write(path, content):
    path = pathlib.Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def append(path, line):
    with open(path, "a", encoding="utf-8") as f: f.write(line + "\n")


def sanitized(s):
    return RE_SUSPECT_VALUE.sub("[REDACTED]", str(s))[:240]


def shape(data, depth=0):
    if depth > 10: return "[depth limit]"
    if isinstance(data, dict):
        return {str(k): "[redacted]" if SECRET.search(str(k)) else shape(v, depth+1) for k,v in data.items()}
    if isinstance(data, list):
        # Preserve variety, not full private data or unbounded arrays.
        variants = []; seen = set()
        for v in data[:60]:
            t=shape(v, depth+1); k=json.dumps(t,sort_keys=True)
            if k not in seen: seen.add(k);variants.append(t)
            if len(variants)>=4:break
        return {"type":"array", "count":len(data), "item_shapes":variants}
    if data is None:return "null"
    if isinstance(data, bool):return "boolean"
    if isinstance(data, int):return "integer"
    if isinstance(data, float):return "number"
    return "string" if isinstance(data,str) else type(data).__name__


def check_url(url, allow_remote):
    if not URL_BASE.match(url): raise ValueError("Only http(s) URLs supported")
    parsed = urllib.parse.urlsplit(url)
    # Require explicit consent before contacting any service outside local loopback.
    if parsed.hostname not in ("127.0.0.1", "localhost", "::1") and not allow_remote:
        raise ValueError("Remote URL requires --allow-remote (only services you own/are authorized to test)")
    if parsed.username or parsed.password: raise ValueError("Do not put credentials in URL")
    return url.rstrip("/")


def safe_archive_extract(src, dest):
    with zipfile.ZipFile(src) as z:
        for member in z.infolist():
            name=pathlib.PurePosixPath(member.filename)
            if member.is_dir() or name.is_absolute() or ".." in name.parts or member.file_size>300*1024*1024: continue
            if (member.external_attr >> 16) & 0o170000 == 0o120000: continue
            rel=pathlib.PurePosixPath(*name.parts[1:]) if name.parts and name.parts[0]=="extracted" else name
            if not rel.parts:continue
            if any(part in (".env", "users.json", "config.json", "secrets.json") for part in rel.parts):continue
            target=dest.joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(member) as source, target.open("wb") as f: shutil.copyfileobj(source,f)


def stage_inventory(a, root):
    raw=root/"raw";raw.mkdir(exist_ok=True)
    if a.archives_dir:
        src=pathlib.Path(a.archives_dir)
        found=0
        for name in ("darkmoon-pro-contracts.zip", "darkmoon-pro-frontend.zip", "darkmoon-pro-native-modules.zip"):
            if (src/name).exists():
                safe_archive_extract(src/name,raw);found+=1
        if not found:raise RuntimeError("No expected archives present in --archives-dir")
        for n in ("file-manifest.json", "image-inspect.json", "image-history.txt", "files-all.txt"):
            if (src/n).exists(): shutil.copy2(src/n,root/n)
        print("  imported",found,"archive(s) into",raw)
    else:
        if not shutil.which("docker"):raise RuntimeError("Docker unavailable; use --archives-dir with prior extraction ZIPs")
        metadata=json.loads(cmd(["docker","image","inspect",a.image],timeout=45))[0]
        outjson(root/"image-metadata.json", {
            "image_id":metadata.get("Id"), "repo_digests":metadata.get("RepoDigests"),
            "created":metadata.get("Created"), "architecture":metadata.get("Architecture"),
            "size":metadata.get("Size"), "entrypoint":(metadata.get("Config") or {}).get("Entrypoint"),
            "exposed_ports":list(((metadata.get("Config") or {}).get("ExposedPorts") or {}).keys()),
        })
        history=cmd(["docker","history","--no-trunc","--format","{{.CreatedBy}}",a.image],timeout=60)
        write(root/"build-history-sanitized.txt", "\n".join(sanitized(x) for x in history.splitlines())+"\n")
        cid=cmd(["docker","create",a.image],timeout=90).strip()
        try:
            for name, path in ROOTS.items():
                target=raw/name
                if target.exists() and not a.refresh:continue
                if target.exists() and a.refresh:
                    if target.is_dir():shutil.rmtree(target)
                    else:target.unlink()
                try:
                    cmd(["docker","cp",f"{cid}:{path}",str(target)],timeout=500)
                    print("  extracted",name)
                except Exception as e: append(root/"warnings.txt",f"copy skipped {name}: {sanitized(e)}")
            if a.full_inventory:
                p1=subprocess.Popen(["docker","export",cid],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                p2=subprocess.Popen(["tar","-tf","-"],stdin=p1.stdout,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                p1.stdout.close()
                out,err=p2.communicate(timeout=600)
                p1.wait(timeout=60)
                if p1.returncode or p2.returncode:raise RuntimeError("docker export / tar index failed: "+err[-300:])
                write(root/"files-all.txt",out)
        finally:
            cmd(["docker","rm",cid],check=False,timeout=35)
    manifest=[]
    for p in sorted(raw.rglob("*")):
        if p.is_file() and not p.is_symlink():
            manifest.append({"path":p.relative_to(raw).as_posix(),"size":p.stat().st_size,"sha256":sha(p)})
    outjson(root/"manifest.json",{"image":a.image,"created_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"files":manifest})
    print("  local artifacts:",len(manifest))


def decompile_ast_record(p):
    src=p.read_text(errors="replace")
    try: t=ast.parse(src,filename=str(p))
    except Exception as e:return {"source":str(p),"parse_error":str(e),"lines":len(src.splitlines())}
    res={"source":str(p),"classes":[],"functions":[],"constants":[],"imports":[],"tests":[],"decorated_routes":[],"strings":[],"calls":[]}
    def signature(n):
        try: args=ast.unparse(n.args)
        except:args="?"
        ret=ast.unparse(n.returns) if n.returns else None
        return {"name":n.name,"line":n.lineno,"args":args[:3000],"returns":ret}
    class Visitor(ast.NodeVisitor):
        parent=[]
        def visit_ClassDef(self,n):
            fields=[]
            for s in n.body:
                if isinstance(s,ast.AnnAssign) and isinstance(s.target,ast.Name):
                    fields.append({"name":s.target.id,"annotation":ast.unparse(s.annotation),"default":ast.unparse(s.value)[:1000] if s.value else None})
            res["classes"].append({"name":n.name,"line":n.lineno,"bases":[ast.unparse(x) for x in n.bases],"fields":fields,"methods":[signature(x) for x in n.body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))]})
            self.parent.append(n.name);self.generic_visit(n);self.parent.pop()
        def visit_FunctionDef(self,n):self.fn(n)
        def visit_AsyncFunctionDef(self,n):self.fn(n)
        def fn(self,n):
            sig=signature(n);sig["qualified_name"]=".".join(self.parent+[n.name]);sig["async"]=isinstance(n,ast.AsyncFunctionDef)
            raises=[];assertions=[];calls=[];conditions=[]
            for k in ast.walk(n):
                if isinstance(k,ast.Raise):raises.append(ast.unparse(k.exc)[:500] if k.exc else "re-raise")
                elif isinstance(k,ast.Assert): assertions.append(ast.unparse(k.test)[:500])
                elif isinstance(k,ast.Call):calls.append(ast.unparse(k.func)[:160])
                elif isinstance(k,ast.If):conditions.append(ast.unparse(k.test)[:300])
            sig.update({"errors":raises[:30],"assertions":assertions[:100],"calls":list(dict.fromkeys(calls))[:250],"conditions":conditions[:100]})
            res["functions"].append(sig)
            if n.name.startswith("test_"):res["tests"].append(sig)
            for d in n.decorator_list:
                if not isinstance(d,ast.Call) or not isinstance(d.func,ast.Attribute):continue
                if d.func.attr.lower() not in ROUTE_DECO:continue
                try: route=ast.literal_eval(d.args[0])
                except (IndexError,ValueError):continue
                res["decorated_routes"].append({"method":d.func.attr.upper(),"subpath":route,"handler":sig["qualified_name"],"line":n.lineno,"return":sig["returns"],"parameters":sig["args"],"raises":raises[:30]})
            self.parent.append(n.name);self.generic_visit(n);self.parent.pop()
        def visit_Import(self,n):res["imports"] += [x.name for x in n.names]
        def visit_ImportFrom(self,n):res["imports"].append(n.module or "")
        def visit_Assign(self,n):
            if n.value and isinstance(n.value,ast.Constant) and isinstance(n.value.value,(str,int,bool,float)):
                keys=[ast.unparse(x) for x in n.targets]
                value=n.value.value
                if any(re.search(r'PROMPT|TEMPLATE|INSTRUCTION|SYSTEM_MESSAGE',v,re.I) for v in keys) and isinstance(value,str):
                    res["strings"].append({"names":keys,"line":n.lineno,"text":value[:300000]})
                elif len(str(value))<400 and not any(SECRET.search(k) for k in keys):
                    res["constants"].append({"names":keys,"line":n.lineno,"value":value})
            self.generic_visit(n)
    Visitor().visit(t)
    return res


def stage_contracts(a,root):
    raw=root/"raw";files=sorted({*raw.rglob("*.py"),*raw.rglob("*.pyi")})
    if not files:raise RuntimeError("No extracted .py or .pyi files; run inventory first")
    records=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
        for rec in pool.map(decompile_ast_record,files):
            rec["source"]=str(pathlib.Path(rec["source"]).relative_to(raw));records.append(rec)
    routes=[];prompts=[];tests=[];errors=[]
    for rec in records:
        p=rec["source"]
        for d in rec.get("decorated_routes",[]):routes.append(dict(d,source=p))
        for d in rec.get("strings",[]):prompts.append(dict(d,source=p))
        for d in rec.get("tests",[]):tests.append({"source":p,**d})
        for d in rec.get("functions",[]):
            if d["errors"]:errors.append({"source":p,"name":d["qualified_name"],"errors":d["errors"]})
    # Router prefixes from readable original entrypoint, including any mounted groups.
    app=raw/"api"/"api_server.py"; mounts={}
    if app.exists():
        txt=app.read_text(errors="replace")
        for var,prefix in re.findall(r'app\.include_router\((\w+)_router,\s*prefix=[\'\"]([^\'\"]+)',txt):
            mounts[var]=prefix
    application_routes = [r for r in routes if pathlib.Path(r["source"]).stem == "api_server"]
    routes = [r for r in routes if pathlib.Path(r["source"]).stem != "api_server"]
    outjson(root/"contracts"/"root-app-routes.json",application_routes)
    for r in routes:
        stem=pathlib.Path(r["source"]).stem
        key=stem[7:] if stem.startswith("routes_") else stem
        if key=="vulnerabilities":key="vulns" if "vulns" in mounts else key
        if key=="pull_requests":key="pull_requests"
        r["path"]=(mounts.get(key,"[unresolved-prefix]")+r["subpath"]).replace("//","/")
    outjson(root/"contracts"/"ast-index.json",records)
    outjson(root/"contracts"/"api-decorators.json",routes)
    outjson(root/"contracts"/"original-mounts.json",mounts)
    outjson(root/"contracts"/"remediation-prompts.json",prompts)
    outjson(root/"contracts"/"test-expectations.json",tests)
    outjson(root/"contracts"/"error-branches.json",errors)
    with (root/"contracts"/"api-decorators.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=["method","path","handler","source","line","return","parameters","raises"],extrasaction="ignore")
        w.writeheader()
        for r in routes:
            r=dict(r);r["raises"]=" | ".join(r["raises"]);w.writerow(r)
    print("  AST files",len(records),"API declarations",len(routes),"tests",len(tests),"prompt constants",len(prompts))


def scan_js(p):
    text=p.read_text(errors="replace");res={"bundle":p.name,"bytes":p.stat().st_size,"sha256":sha(p),"selectors":[],"api_paths":[],"ui_routes":[],"events":[],"control_literals":[],"validation_refs":[],"network_refs":[],"angular_ops":[],"components":[],"snippets":{}}
    rules={
      "selectors":r'(?:(?:selectors:|selectors\s*=)\s*\[\[\s*[\'\"]([^\'\"]{1,100})[\'\"])',
      "api_paths":r'(?<!\w)(/api/v1/[\w\-/{}:$?=&.]+)',
      "ui_routes":r'\bpath\s*:\s*[\'\"]([^\'\"]{0,110})[\'\"]',
      "events":r'[\'\"]((?:campaign|finding|pr|retest|scheduler|run|webhook|event)\.[\w-]{2,50})[\'\"]',
      "control_literals":r'(?:formControlName|placeholder|aria-label|type|name|routerLink|mat-dialog-title)\s*[:=]\s*[\'\"]([^\'\"]{1,160})[\'\"]',
      "validation_refs":r'\b(?:Validators\.[\w]+|setValidators|markAsTouched|invalid|touched|dirty|validate\w+|required|minLength|maxLength|pattern)\b',
      "network_refs":r'\b(?:fetch|EventSource|WebSocket|HttpClient|HttpInterceptor|Authorization|API_URL|createPdf|requestSession|localStorage|sessionStorage)\b',
      "angular_ops":r'ɵɵ(?:listener|property|twoWayListener|elementStart|elementEnd|template|conditional|repeaterCreate|styleProp|classProp|textInterpolate|attribute|pipeBind\w+)',
      "components":r'\b(?:ɵcmp|ɵdir|ɵfac|ɵmod|ɵinj|ɵpipe)\b',
    }
    for label,pattern in rules.items():
        matches=list(re.finditer(pattern,text))
        vals=[(m.group(1) if m.lastindex else m.group(0)) for m in matches]
        res[label]=list(dict.fromkeys(vals))[:12000]
        # Context samples, enough to locate interactions without inventing semantic behavior.
        res["snippets"][label]=[{"offset":m.start(),"context":text[max(0,m.start()-130):m.end()+230][:500]} for m in matches[:400]]
        res[label+"_total_occurrences"]=len(matches)
    return res


def stage_frontend(a,root):
    dashboard=root/"raw"/"dashboard";js=sorted(dashboard.rglob("*.js"))
    if not js:raise RuntimeError("No JS bundles; run inventory stage")
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
        results=list(pool.map(scan_js,js))
    outjson(root/"frontend"/"bundle-analysis.json",results)
    aggregate={k:sorted(set(x for r in results for x in r[k])) for k in ("selectors","api_paths","ui_routes","events","control_literals","validation_refs","network_refs","angular_ops","components")}
    aggregate["reference_spa_routes"] = UI_ROUTES
    aggregate["bundle_count"] =len(results)
    aggregate["source_maps_present"]=[str(p.relative_to(dashboard)) for p in dashboard.rglob("*.map")]
    outjson(root/"frontend"/"component-and-interaction-index.json",aggregate)
    outjson(root/"frontend"/"network-call-sites.json",[{"bundle":r["bundle"],"sites":r["snippets"]["network_refs"]} for r in results if r["network_refs_total_occurrences"]])
    htmls=[]
    for p in dashboard.rglob("*.html"):
        body=p.read_text(errors="replace")
        htmls.append({"file":p.name,"forms":len(re.findall(r'<form\b',body,re.I)),"scripts":re.findall(r'<script[^>]+src=[\'\"]([^\'\"]+)',body),"styles":re.findall(r'<link[^>]+href=[\'\"]([^\'\"]+)',body)})
    outjson(root/"frontend"/"html-entrypoints.json",htmls)
    print("  JS bundles",len(js),"selectors",len(aggregate["selectors"]),"source maps",len(aggregate["source_maps_present"]))


def stage_fork(a,root):
    if a.fork_path:
        repo=pathlib.Path(a.fork_path).resolve()
    else:
        repo=root/"fork-checkout"
        if not repo.exists():
            cmd(["git","clone","--depth","1","--filter=blob:none","--single-branch","--branch",a.fork_branch,a.fork_repo,str(repo)],timeout=420)
    if not (repo/"mcp/community/api.py").exists():raise RuntimeError("Fork path is not the expected project checkout")
    try: head=cmd(["git","-C",str(repo),"rev-parse","HEAD"],timeout=15).strip()
    except:head="local-worktree"
    fork_files=[p for prefix in ("mcp/community", "tests/community") for p in (repo/prefix).rglob("*.py")]
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool: records=list(pool.map(decompile_ast_record,sorted(fork_files)))
    for r in records:r["source"]=str(pathlib.Path(r["source"]).relative_to(repo))
    outjson(root/"fork"/"python-index.json",records)
    forkpaths={p.as_posix().replace(str(repo)+"/",""):sha(p) for p in sorted((repo/"mcp/community/static").glob("*.js"))}
    outjson(root/"fork"/"snapshot.json",{"repository":a.fork_repo,"branch":a.fork_branch,"commit":head,"js":forkpaths,"indexed_python":len(records)})
    endpoints=readjson(root/"contracts"/"api-decorators.json",[]) or []
    api=(repo/"mcp/community/api.py").read_text(errors="replace")
    server=(repo/"mcp/community/server.py").read_text(errors="replace")
    candidates=[]
    for e in endpoints:
        path=e.get("path","");fragments=[x for x in path.split("/") if x and not (x.startswith("{") or x.startswith("<"))]
        evidence=[f for f in fragments if f not in ("api","v1")]
        hits=sum(bool(re.search(r'[\'\"]'+re.escape(s)+r'[\'\"]',api+server)) for s in evidence)
        candidates.append({"method":e["method"],"original":path,"fork_static_token_matches":hits,"tokens_searched":evidence,"status":"candidate only - dynamic dispatcher cannot be verified by text matching"})
    outjson(root/"fork"/"route-review-candidates.json",candidates)
    append(root/"fork"/"README.txt", "Static token matches are triage hints ONLY; method+path behavior requires fork server tests.")
    print("  fork HEAD",head,"indexed",len(records),"Python files")


def native_job(item,root,full=False):
    src,rel=item;dest=root/"native"/rel;dest.parent.mkdir(parents=True,exist_ok=True)
    record={"module":str(rel),"sha256":sha(src),"bytes":src.stat().st_size,"tools":{}}
    operations={"file":["file",str(src)],"symbols":["nm","-D","--defined-only",str(src)],"elf":["readelf","-Wh",str(src)],"strings":["strings","-a","-n","7",str(src)]}
    if full:operations["disassembly"]=["objdump","-d","-C",str(src)]
    for key,argv in operations.items():
        if not shutil.which(argv[0]):record["tools"][key]="unavailable";continue
        target=dest.with_name(dest.name+"."+key+".txt")
        if target.exists():record["tools"][key]="cached";continue
        try:cmd(argv,stdout_file=target,timeout=900 if key=="disassembly" else 100);record["tools"][key]="ok"
        except Exception as e:record["tools"][key]=sanitized(e)
    return record


def stage_native(a,root):
    raw=root/"raw"
    native=[(p,p.relative_to(raw)) for p in raw.rglob("*.so") if p.name.endswith(".so") and ("api" in p.parts or "remediation" in p.parts)]
    if not native:raise RuntimeError("No native modules found")
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(a.workers,4)) as pool:
        records=list(pool.map(lambda x:native_job(x,root,False),native))
    outjson(root/"native"/"module-analysis.json",records)
    print("  native modules indexed",len(native))


def stage_disasm(a,root):
    raw=root/"raw"
    native=[(p,p.relative_to(raw)) for p in raw.rglob("*.so") if p.name.endswith(".so") and ("api" in p.parts or "remediation" in p.parts)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(2,a.workers)) as pool:
        records=list(pool.map(lambda x:native_job(x,root,True),native))
    outjson(root/"native"/"full-disassembly-summary.json",records)
    print("  generated native disassembly indexes for",len(native),"modules")


def http_get(url,token,timeout):
    request=urllib.request.Request(url,headers={"Accept":"application/json, text/plain;q=0.8", **({"Authorization":"Bearer "+token} if token else {})},method="GET")
    try:
        with urllib.request.urlopen(request,timeout=timeout) as res:
            return res.status, dict(res.headers),res.read(4_000_000)
    except urllib.error.HTTPError as e:return e.code,dict(e.headers),e.read(4_000_000)


def parse_response(body,headers):
    typ=headers.get("Content-Type",headers.get("content-type",""))
    try:return shape(json.loads(body)),"json"
    except (ValueError,UnicodeDecodeError):
        return {"type":"non-json","media_type":typ,"bytes":len(body)},"opaque"


def substitute(path,ids):
    unresolved=[]
    def repl(match):
        key=match.group(1)
        if key not in ids:unresolved.append(key);return match.group(0)
        return urllib.parse.quote(str(ids[key]),safe="")
    sub=re.sub(r"\{([^{}]+)\}",repl,path)
    return None if unresolved else sub


def stage_runtime(a,root):
    if not a.pro_url:raise RuntimeError("--pro-url is required to perform authorized live checks")
    urls={"original":check_url(a.pro_url,a.allow_remote)}
    if a.fork_url:urls["fork"]=check_url(a.fork_url,a.allow_remote)
    ids=readjson(a.ids_file,{}) if a.ids_file else {}
    token=os.environ.get(a.auth_token_env,"") if a.auth_token_env else ""
    routes=readjson(root/"contracts"/"api-decorators.json",[]) or []
    allowed=set(SAFE_DEFAULT_GETS)
    if a.runtime_all_get:allowed.update(r.get("path","") for r in routes if r.get("method")=="GET")
    results={}
    for label,base in urls.items():
        rows=[]
        for path in sorted(allowed):
            full=substitute(path,ids)
            if full is None:
                rows.append({"method":"GET","path":path,"status":"skipped: missing placeholder ID"});continue
            try:
                code,headers,body=http_get(base+full,token,a.http_timeout)
                h={k:v for k,v in headers.items() if k.lower() in SECURITY_HEADERS}
                schema,_=parse_response(body,headers)
                rows.append({"method":"GET","path":path,"http_status":code,"headers":h,"response_shape":schema,"bytes":len(body)})
            except Exception as e:rows.append({"path":path,"error":sanitized(e)})
        results[label]=rows
    outjson(root/"runtime"/"read-only-responses.json",results)
    if "fork" in results:
        a_by={x.get("path"):x for x in results["original"]};b_by={x.get("path"):x for x in results["fork"]}
        outjson(root/"runtime"/"schema-differences.json",[{'path':p,'original':a_by[p],'fork':b_by[p]} for p in a_by if p in b_by and (a_by[p].get('http_status'),a_by[p].get('response_shape')) != (b_by[p].get('http_status'),b_by[p].get('response_shape'))])
    print("  read-only requests made",{k:sum('http_status' in row for row in v) for k,v in results.items()})


def stage_browser(a,root):
    if not a.pro_url:raise RuntimeError("--pro-url required for browser visit")
    base=check_url(a.pro_url,a.allow_remote)
    try:from playwright.sync_api import sync_playwright
    except ImportError:raise RuntimeError("Install optional dependency: python3 -m pip install playwright && python3 -m playwright install chromium")
    ids=readjson(a.ids_file,{}) if a.ids_file else {}
    snapshots=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        ctx=browser.new_context(viewport={"width":1440,"height":900},accept_downloads=False)
        for route in UI_ROUTES:
            route=re.sub(r":(id|project_id|campaign_id)",lambda m:str(ids.get(m.group(1),"")),route)
            if ":" in route or any(v=="" for v in route.split("/")[1:] if v==""):continue
            page=ctx.new_page();logs=[];network=[]
            page.on("console",lambda m:logs.append({"type":m.type,"message":sanitized(m.text)[:150]}))
            page.on("response",lambda r: network.append({"path":urllib.parse.urlsplit(r.url).path,"status":r.status}) if len(network)<250 else None)
            try:
                resp=page.goto(base+route,wait_until="domcontentloaded",timeout=int(a.http_timeout*1000))
                page.wait_for_timeout(1200)
                controls=page.evaluate("""() => [...document.querySelectorAll('button,a,input,textarea,select,[role=dialog],[role=tab],[role=menuitem],form')].slice(0,400).map(x => ({tag:x.tagName,role:x.getAttribute('role'),type:x.getAttribute('type'),name:x.getAttribute('name'),aria:x.getAttribute('aria-label'),required:x.required||false,disabled:x.disabled||false,href:x.tagName==='A'?new URL(x.href).pathname:null,visible:!!(x.offsetWidth||x.offsetHeight||x.getClientRects().length)}))""")
                row={"route":route,"status":resp.status if resp else None,"url_path":urllib.parse.urlsplit(page.url).path,"title":sanitized(page.title()),"controls":controls,"console":logs[:100],"network":network}
                if a.screenshots:
                    d=root/"browser"/"screenshots";d.mkdir(parents=True,exist_ok=True)
                    f=d/((route.strip('/').replace('/','_') or 'root')+'.png');page.screenshot(path=str(f),full_page=True,animations="disabled");row["screenshot"]=str(f.relative_to(root))
                snapshots.append(row)
            except Exception as e:snapshots.append({"route":route,"error":sanitized(e)})
            finally:page.close()
        browser.close()
    outjson(root/"browser"/"passive-ui-observations.json",snapshots)
    print("  passive pages visited",len(snapshots),"(no clicks or submissions)")

JS_HELPER = r'''
const fs=require('fs'), parser=require(process.argv[2]);
const output=process.argv[3], files=process.argv.slice(4);
const rows=[];
function name(n){if(!n)return '';if(n.type==='Identifier')return n.name;
 if(n.type==='MemberExpression'||n.type==='OptionalMemberExpression')return name(n.object)+'.'+(n.property?.name||n.property?.value||'?');
 return n.type||'';}
for(const file of files){
 const src=fs.readFileSync(file,'utf8'); const r={file:file.split('/').pop(),nodes:0,events:[],api_calls:[],bindings:[],routing:[],validation:[],errors:[]};
 try{
  const ast=parser.parse(src,{sourceType:'unambiguous',errorRecovery:true,plugins:['jsx'],allowReturnOutsideFunction:true});
  const stack=[ast];
  while(stack.length){const n=stack.pop();if(!n||typeof n!=='object')continue;
   if(Array.isArray(n)){for(let i=n.length-1;i>=0;i--)stack.push(n[i]);continue;}
   if(typeof n.type!=='string')continue;r.nodes++;
   if(n.type==='ObjectProperty'){
    const k=n.key?.name||n.key?.value;
    if(['path','redirectTo','loadComponent','loadChildren','canActivate'].includes(k))r.routing.push({key:k,code:src.slice(n.value.start,n.value.end).slice(0,500),at:n.start});
    if(['selectors','inputs','outputs','template','styles','providers','hostBindings'].includes(k))r.bindings.push({key:k,code:src.slice(n.value.start,n.value.end).slice(0,500),at:n.start});
   }
   if(n.type==='CallExpression'){
    const callee=name(n.callee),args=(n.arguments||[]).slice(0,4).map(x=>src.slice(x.start,x.end).slice(0,350));
    const row={callee,args,at:n.start};
    if(/ɵɵlistener|ɵɵtwoWayListener|addEventListener/.test(callee))r.events.push(row);
    if(/ɵɵproperty|ɵɵattribute|ɵɵstyleProp|ɵɵclassProp/.test(callee))r.bindings.push(row);
    if(/\.get$|\.post$|\.put$|\.patch$|\.delete$|\.request$|fetch$|EventSource$|WebSocket$|\.createPdf$|\.requestSession$/.test(callee))r.api_calls.push(row);
    if(/Validators|setValidators|setErrors|markAsTouched|validate/i.test(callee))r.validation.push(row);
   }
   for(const [k,v] of Object.entries(n))if(k!=='loc'&&k!=='comments'&&k!=='extra'&&v&&typeof v==='object')stack.push(v);
  }
 }catch(e){r.errors.push(String(e).slice(0,300));}
 for(const k of ['events','api_calls','bindings','routing','validation'])if(r[k].length>50000){r[k]=r[k].slice(0,50000);r.errors.push(k+' truncated');}
 rows.push(r);
}
fs.writeFileSync(output,JSON.stringify(rows,null,2)+'\n');
'''


def js_modules(a, root):
    tools=root/'js-tools';node_modules=tools/'node_modules'
    if (node_modules/'prettier').is_dir() and (node_modules/'@babel'/'parser').is_dir():return tools
    if not a.install_js_tools:raise RuntimeError('Rerun with --install-js-tools to install Babel/parser and Prettier locally (optional npm downloads)')
    cmd(['npm','install','--prefix',str(tools),'--ignore-scripts','--no-audit','--no-fund','--no-save','@babel/parser@7','prettier@3'],timeout=300)
    return tools


def stage_js_ast(a, root):
    tools=js_modules(a,root);script=tools/'scan.cjs';write(script,JS_HELPER)
    files=sorted((root/'raw'/'dashboard').rglob('*.js')); dest=root/'frontend'/'babel-ast';dest.mkdir(parents=True,exist_ok=True)
    def one(p):
        o=dest/(p.stem+'.json')
        if o.exists() and not a.refresh:return 'cached'
        try:
            cmd(['node','--max-old-space-size=4096',str(script),str(tools/'node_modules'/'@babel'/'parser'),str(o),str(p)],timeout=300)
            return 'ok'
        except Exception as e:return 'failed: '+sanitized(e)
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(a.workers,3)) as pool:res=list(pool.map(one,files))
    outjson(root/'frontend'/'babel-parse-results.json',dict(Counter(res)))
    print('  deep Angular AST scans:',len(files),Counter(res))


def stage_prettify(a, root):
    tools=js_modules(a,root);files=sorted((root/'raw'/'dashboard').rglob('*.js'))
    dest=root/'frontend'/'readable-js';dest.mkdir(parents=True,exist_ok=True)
    def one(p):
        o=dest/p.name
        if o.exists() and not a.refresh:return 'cached'
        try:
            with o.open('wb') as f:
                x=subprocess.run(['node',str(tools/'node_modules'/'prettier'/'bin'/'prettier.cjs'),'--parser','babel','--no-config',str(p)],stdout=f,stderr=subprocess.PIPE,timeout=300)
            if x.returncode:o.unlink(missing_ok=True);return 'failed'
            return 'ok'
        except Exception:
            o.unlink(missing_ok=True);return 'failed'
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(a.workers,2)) as pool:res=list(pool.map(one,files))
    outjson(root/'frontend'/'format-results.json',dict(Counter(res)))
    print('  formatted Angular JS bundles:',len(files),Counter(res))


def stage_browser_record(a, root):
    if not a.pro_url:raise RuntimeError('--pro-url is required')
    base=check_url(a.pro_url,a.allow_remote)
    try:from playwright.sync_api import sync_playwright
    except ImportError:raise RuntimeError('Install optional playwright module and Chromium')
    instrument="""(() => {window.__dmAudit=[];
      for(const kind of ['click','submit','change'])document.addEventListener(kind,e=>{
      const t=e.target; if(window.__dmAudit.length<10000)window.__dmAudit.push({kind,
      tag:t?.tagName,type:t?.getAttribute?.('type'),name:t?.getAttribute?.('name'),
      id:t?.id||null,role:t?.getAttribute?.('role'),path:location.pathname});},true);
    })();"""
    network=[];pages=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=not a.headed)
        context=browser.new_context(accept_downloads=False)
        context.add_init_script(script=instrument)
        def observe(pg):
            pages.append(pg)
            pg.on('request',lambda req:network.append({'kind':'request','method':req.method,'path':urllib.parse.urlsplit(req.url).path}) if len(network)<10000 else None)
            pg.on('response',lambda res:network.append({'kind':'response','status':res.status,'path':urllib.parse.urlsplit(res.url).path}) if len(network)<10000 else None)
        context.on('page',observe)
        page=context.new_page();page.goto(base,wait_until='domcontentloaded',timeout=30000)
        print('  Manual browser opened. Interact only with owned/test data, no values or HTTP bodies are recorded.')
        page.wait_for_timeout(max(2,a.observe_seconds)*1000)
        interactions=[]
        for pg in pages:
            if pg.is_closed():continue
            try:interactions.extend(pg.evaluate('window.__dmAudit || []'))
            except:pass
        browser.close()
    outjson(root/'browser'/'manual-interactions.json',{'dom_events':interactions,'requests_responses':network})
    print('  user-driven interactions:',len(interactions),'network metadata:',len(network))

GHIDRA_JAVA = r'''// @category DarkMoonAudit
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.listing.Function;
import java.io.*;
import java.nio.charset.StandardCharsets;
public class DarkMoonDecompile extends GhidraScript {
  public void run() throws Exception {
    String[] args=getScriptArgs();
    File out=new File(args[0]); int limit=Integer.parseInt(args[1]);
    DecompInterface di=new DecompInterface();
    di.openProgram(currentProgram);
    try(PrintWriter pw=new PrintWriter(new OutputStreamWriter(new FileOutputStream(out),StandardCharsets.UTF_8))){
      int attempted=0,successful=0;
      for(Function fn:currentProgram.getFunctionManager().getFunctions(true)){
        if(monitor.isCancelled())break;
        if(fn.isExternal()||fn.isThunk())continue;
        if(limit>0 && attempted>=limit)break;
        attempted++;
        pw.println("\n/* FUNCTION "+fn.getName()+" @ "+fn.getEntryPoint()+" */");
        try{
          DecompileResults r=di.decompileFunction(fn,30,monitor);
          if(r.decompileCompleted()&&r.getDecompiledFunction()!=null){
            pw.println(r.getDecompiledFunction().getC()); successful++;
          }else pw.println("/* NO_PSEUDOCODE: "+r.getErrorMessage()+" */");
        } catch(Exception e){pw.println("/* ERROR: "+e.getClass().getSimpleName()+" */");}
        if(attempted%50==0)pw.flush();
      }
      pw.println("\n/* ATTEMPTED="+attempted+" DECOMPILED="+successful+" */");
    }
    di.dispose();
  }
}
'''


def stage_ghidra(a,root):
    if not a.ghidra_bin:raise RuntimeError("--ghidra-bin /path/to/support/analyzeHeadless required")
    gh=pathlib.Path(a.ghidra_bin)
    if not gh.is_file():raise RuntimeError("Ghidra headless executable not found")
    scriptdir=root/"ghidra"/"scripts";scriptdir.mkdir(parents=True,exist_ok=True)
    write(scriptdir/"DarkMoonDecompile.java",GHIDRA_JAVA)
    binaries=sorted(p for p in (root/"raw").rglob("*.so") if "api" in p.parts or "remediation" in p.parts)
    if a.ghidra_modules:
        wanted=set(a.ghidra_modules.split(','));binaries=[p for p in binaries if p.name.split('.')[0] in wanted]
    project=root/"ghidra"/"projects";project.mkdir(parents=True,exist_ok=True)
    complete=[]
    for i,p in enumerate(binaries):
        dest=root/"ghidra"/"decompiled"/(p.name+'.c.txt');dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists() and not a.refresh:
            complete.append({"module":p.name,"status":"cached"});continue
        work=root/"ghidra"/"logs";work.mkdir(parents=True,exist_ok=True)
        argv=[str(gh),str(project),f"module_{i}","-import",str(p),"-scriptPath",str(scriptdir),"-postScript","DarkMoonDecompile.java",str(dest),str(a.ghidra_max_functions),"-analysisTimeoutPerFile",str(a.ghidra_timeout),"-deleteProject","-log",str(work/(str(i)+".log"))]
        try:
            cmd(argv,timeout=a.ghidra_timeout+600,stdout_file=work/(str(i)+".stdout"))
            complete.append({"module":p.name,"status":"decompiled" if dest.exists() else "no output","bytes":dest.stat().st_size if dest.exists() else 0})
        except Exception as e:complete.append({"module":p.name,"status":"failed","error":sanitized(e)})
        outjson(root/"ghidra"/"progress.json",complete)
        print("  ghidra",i+1,"/",len(binaries),p.name)
    print("  Ghidra outputs are C pseudocode guesses, NOT original Python algorithms")


def stage_discovery(a,root):
    """Identify possible undocumented APIs, feature flags, event names and modules.

    Reports hypotheses only; absence of a reference is not proof of no feature.
    """
    raw=root/"raw"
    data={"configuration_keys":defaultdict(list),"feature_markers":defaultdict(list),"event_names":defaultdict(list),"imports":defaultdict(list),"unused_api_paths":[],"notes":[]}
    codefiles=[p for p in raw.rglob("*") if p.is_file() and p.suffix.lower() in (".py", ".pyi", ".js", ".html", ".conf", ".md")]
    for p in codefiles:
        rel=p.relative_to(raw).as_posix()
        s=p.read_text(errors="replace")
        for m in set(re.findall(r"\b(?:DARKMOON|DM|OPENCODE|OPENAI|ANTHROPIC|JWT|CRED|SCM)_[A-Z][A-Z0-9_]{2,}\b",s)):
            data["configuration_keys"][m].append(rel)
        for m in set(re.findall(r"(?i)(?:feature[_ -]?flag|TODO|FIXME|not implemented|unsupported|deprecated|experimental|license[_ -]?gate)",s)):
            data["feature_markers"][m.lower()].append(rel)
        for m in set(re.findall(r"(?:campaign|finding|pr|retest|scheduler|run|webhook|event)\.[a-z][a-z_-]{2,40}",s)):
            data["event_names"][m].append(rel)
        if p.suffix in (".py", ".pyi"):
            try: t=ast.parse(s)
            except:continue
            for node in t.body:
                if isinstance(node,ast.Import):
                    for k in node.names: data["imports"][k.name].append(rel)
                if isinstance(node,ast.ImportFrom) and node.module:
                    data["imports"][node.module].append(rel)
    frontend=readjson(root/"frontend"/"component-and-interaction-index.json",{}) or {}
    api=readjson(root/"contracts"/"api-decorators.json",[]) or []
    # Dynamic URL constructions may not contain a literal API path, so this is advisory.
    refs=set(frontend.get("api_paths",[]))
    for item in api:
        path=item.get("path","")
        if path and not any(p==path for p in refs):
            data["unused_api_paths"].append({"method":item["method"],"path":path,"status":"No exact literal in Angular bundles; dynamic calls are possible"})
    for k in ("configuration_keys","feature_markers","event_names","imports"):
        data[k]={x:sorted(set(v)) for x,v in sorted(data[k].items())}
    data["notes"]=["No matching literal is not evidence that a feature is unused: JS may construct URLs dynamically.",
                   "Environment key names are indexed without copying their deployment values.",
                   "Discovery is bounded by packaged files, so truly removed/private features remain unknown."]
    outjson(root/"discovery"/"unexplored-features.json",data)
    print("  config keys",len(data["configuration_keys"]),"events",len(data["event_names"]),"feature hints",len(data["feature_markers"]))


def stage_report(a,root):
    manifest=readjson(root/"manifest.json",{}) or {};md=[]
    routes=readjson(root/"contracts"/"api-decorators.json",[]) or []
    ui=readjson(root/"frontend"/"component-and-interaction-index.json",{}) or {}
    tests=readjson(root/"contracts"/"test-expectations.json",[]) or []
    fork=readjson(root/"fork"/"snapshot.json",{}) or {}
    md += ["# Actual Pro artifact investigation — evidence report", "",f"- Image reference: `{a.image}`",f"- Copied/verified extracted files: **{len(manifest.get('files',[]))}**",f"- Original REST declarations extracted: **{len(routes)}** (including aliases)",f"- Angular bundles inspected: **{ui.get('bundle_count','not run')}**",f"- Angular selectors found: **{len(ui.get('selectors',[]))}**",f"- Original packaged tests indexed: **{len(tests)}**",f"- Fork SHA: `{fork.get('commit','not inspected')}`", "", "## Methodology and limits", "", "A static Python AST index extracts declarations, annotations, defaults, error branches, calls, class fields, prompts, and packaged test assertions. A JS string/Angular-operator index extracts routes, event references, controls, validators and call sites. These are partial semantic evidence; not proof of every runtime state. Ghidra (optional) generates approximate native C pseudocode, not exact original Python. No vendor license bypass is attempted. Browser/live steps are opt-in and read-only, and do not submit assessments or remediation jobs.","", "## Original API endpoints", "", "| Method | Path | Handler | Source |", "|---|---|---|---|"]
    for r in routes:md.append(f"| {r.get('method')} | `{r.get('path')}` | `{r.get('handler')}` | `{r.get('source')}` |")
    md += ["", "## Compiled Angular observations", "", "Known vendor SPA routes: "+", ".join('`'+x+'`' for x in UI_ROUTES)+".","", "Angular selectors: "+", ".join('`'+x+'`' for x in ui.get('selectors',[])[:250])+".","", "## Original backend and fork comparison", "", "The path/name tokens in `fork/route-review-candidates.json` are **not** wire compatibility results; use successful authorized test responses and contracts. Do not remove stronger security features solely to match historical vendor behavior.","", "## Unverified / unanswered", "", "1. Full Python original algorithms cannot be mathematically recovered from native Cython extensions; pseudocode is best-effort and lossy.", "2. Original Angular TypeScript sources / templates may not be recoverable if source maps were not shipped.", "3. API bodies, defaults, error codes and side effects are not established from a decorator alone.", "4. Executing vendor tests requires a properly licensed and isolated runtime; no licensing modification is part of this tool.", "5. Passive browser inspection does not exercise modals/actions, submission flows, or destructive transitions. Generate controlled test fixtures for each case.", "6. Unknown features require ongoing artifact search; no finite inventory proves nothing is missing."]
    write(root/"REPORT.md", "\n".join(md)+"\n")
    # Acceptance matrix intentionally includes unknowns and tested/not-tested gates.
    tasks=[]
    for r in routes:
        tasks.append({"category":"api","id":f"{r['method']} {r['path']}","expectations":["Successful request/response schema", "Auth: anonymous/viewer/admin", "Invalid and missing identifiers", "Error status and content type", "Pagination/filters/defaults", "Sensitive output redaction", "Response side effects and idempotency", "Against real Pro reference and fork"],"verification":"pending genuine vendor response", "side_effect_safe_default":r["method"]=="GET"})
    for path in UI_ROUTES:
        tasks.append({"category":"ui","id":path,"expectations":["Initial page state and controls", "Required fields and validators", "Modal/dialog transitions", "Keyboard/focus/accessibility", "Loading/empty/error/success states", "Back/deep-link/mobile viewport", "Backend request correlation", "User-confirmed safe interaction"],"verification":"pending controlled browser fixture"})
    for s in ("source discovery","candidate rank","LLM edit generation","adversarial review","exact patch application","exploit reproduction baseline","variants and normal-behavior probes","Docker sandbox","PR creation","retest verdict","failure/retry/cleanup"):
        tasks.append({"category":"remediation","id":s,"expectations":["Inputs and defaults", "Output/state persistence", "Failure and retry transitions", "Security gate/authorization", "Real disposable owned-lab validation"],"verification":"pending"})
    outjson(root/"acceptance-test-matrix.json",tasks)
    print("  report and",len(tasks),"test plan rows generated")


def stage_pack(a,root):
    packages={"analyses":[],"contracts":[],"frontend":[],"native":[],"readable-js":[],"decompiled":[]}
    for p in root.rglob('*'):
        if not p.is_file() or p.is_symlink():continue
        rel=p.relative_to(root)
        if "fork-checkout" in rel.parts or "projects" in rel.parts or "screenshots" in rel.parts:continue
        if rel.parts[0]=="raw":
            if len(rel.parts)>1 and rel.parts[1]=="dashboard":
                if a.pack_source:packages["frontend"].append(p)
            elif p.suffix==".so":
                if a.pack_native:packages["native"].append(p)
            elif a.pack_source:
                packages["contracts"].append(p)
        elif rel.parts[0]=="ghidra" and "decompiled" in rel.parts:
            packages["decompiled"].append(p)
        elif rel.parts[:2]==("frontend","readable-js"):
            packages["readable-js"].append(p)
        elif rel.parts[0] not in ("packages", "ghidra"):
            if p.stat().st_size<=30*1024*1024:packages["analyses"].append(p)
    for name,files in packages.items():
        if not files:continue
        dest=root/"packages"/(f"darkmoon-pro-{name}.zip");dest.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(dest,"w",zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
            for p in sorted(files):
                # No runtime secrets, local cached user data or personal deployment state.
                if any(x.lower() in (".env","users.json","secrets.json","credentials.json","auth.json","runtime-hashes.env") for x in p.parts):continue
                z.write(p,p.relative_to(root).as_posix())
        print("  archive",dest.name,dest.stat().st_size,"bytes")


def main():
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--out",default="~/darkmoon-pro-complete-audit",help="Audit output directory")
    ap.add_argument("--image",default=PIN,help="Pinned original commercial image digest")
    ap.add_argument("--archives-dir",help="Use previously extracted 3 ZIP archives instead of Docker image")
    ap.add_argument("--stages",default="inventory,contracts,frontend,fork,native,discovery,report,pack",help="Comma-separated stages. Extra: disasm, js-ast, prettify, runtime, browser, browser-record, ghidra")
    ap.add_argument("--workers",type=int,default=4)
    ap.add_argument("--full-inventory",action="store_true",help="Stream complete Docker filesystem path list; may be slower")
    ap.add_argument("--fork-path",help="Use existing checkout rather than shallow clone")
    ap.add_argument("--fork-repo",default="https://github.com/newrecycle/Dark-Moon.git")
    ap.add_argument("--fork-branch",default="pro")
    ap.add_argument("--pro-url",help="Authorized, already-running original Pro instance URL")
    ap.add_argument("--fork-url",help="Optional already-running fork instance for shape comparison")
    ap.add_argument("--allow-remote",action="store_true",help="Explicitly allow non-loopback server; must be user-owned/authorized")
    ap.add_argument("--auth-token-env",default="",help="Environment variable holding an existing authorized bearer token (not printed)")
    ap.add_argument("--ids-file",help="JSON mapping placeholders such as run_id, campaign_id, target_id to allowed fixture IDs")
    ap.add_argument("--runtime-all-get",action="store_true",help="Opt in to reading all known GET endpoints; may access sensitive assessment data, output is schema-only")
    ap.add_argument("--http-timeout",type=int,default=12)
    ap.add_argument("--screenshots",action="store_true",help="Opt in to saving UI screenshots; never share if they show real secrets/data")
    ap.add_argument("--install-js-tools",action="store_true",help="Opt in to npm install of Babel parser and Prettier under output directory")
    ap.add_argument("--headed",action="store_true",help="Launch visible browser for operator-driven recording")
    ap.add_argument("--observe-seconds",type=int,default=120,help="Manual UI recording duration")
    ap.add_argument("--ghidra-bin",help="Path to Ghidra support/analyzeHeadless")
    ap.add_argument("--ghidra-modules",help="Comma-separated .so module stems for a targeted decompile; blank = all")
    ap.add_argument("--ghidra-max-functions",type=int,default=0,help="0 = all functions (very slow)")
    ap.add_argument("--ghidra-timeout",type=int,default=2400,help="Seconds per .so module")
    ap.add_argument("--pack-source",action="store_true",help="Include extracted readable code and compiled Angular assets in shareable ZIPs")
    ap.add_argument("--pack-native",action="store_true",help="Include original native .so files in separate ZIP")
    ap.add_argument("--refresh",action="store_true",help="Rebuild stages even if .done markers exist")
    a=ap.parse_args();a.workers=max(1,min(a.workers,16))
    root=pathlib.Path(a.out).expanduser().resolve();root.mkdir(parents=True,exist_ok=True)
    funcs={"inventory":stage_inventory,"contracts":stage_contracts,"frontend":stage_frontend,"fork":stage_fork,"native":stage_native,"discovery":stage_discovery,"disasm":stage_disasm,"runtime":stage_runtime,"browser":stage_browser,"browser-record":stage_browser_record,"js-ast":stage_js_ast,"prettify":stage_prettify,"ghidra":stage_ghidra,"report":stage_report,"pack":stage_pack}
    todo=[x.strip() for x in a.stages.split(',') if x.strip()]
    if any(x not in funcs for x in todo):ap.error("Unknown stages: "+str(set(todo)-set(funcs)))
    append(root/"audit.log",f"Audit invocation started {datetime.datetime.now(datetime.timezone.utc).isoformat()} stages={','.join(todo)}")
    failed=[]
    for stage in todo:
        done=root/"stage-markers"/(stage+".done");done.parent.mkdir(parents=True,exist_ok=True)
        if done.exists() and not a.refresh and stage not in ("report", "pack"):
            print(f"[skip] {stage}: completed previously (--refresh to rerun)");continue
        print(f"[start] {stage}",flush=True);t=time.monotonic()
        try:
            funcs[stage](a,root)
            write(done,datetime.datetime.now(datetime.timezone.utc).isoformat()+"\n")
            print(f"[done] {stage}: {time.monotonic()-t:.1f}s",flush=True)
            append(root/"audit.log",f"PASS {stage} {time.monotonic()-t:.1f}s")
        except Exception as e:
            failed.append(stage);print("[FAIL]",stage,sanitized(e),flush=True)
            append(root/"audit.log",f"FAILED {stage}: {sanitized(e)}\n{traceback.format_exc()[-2000:]}")
            # Dependent stages may continue if artifacts from previous run exist.
    print("\nArtifacts:",root,"\nStage failures:",failed or "none")
    sys.exit(2 if failed else 0)

if __name__=="__main__":main()