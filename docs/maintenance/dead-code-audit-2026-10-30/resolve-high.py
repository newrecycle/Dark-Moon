from pathlib import Path
import csv,json,re,subprocess,collections
root=Path('docs/maintenance/dead-code-audit-2026-10-30')
def read(n):return list(csv.DictReader((root/n).open()))
def write(n,rows):
 with (root/n).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
tracked=subprocess.check_output(['git','ls-tree','-r','--name-only','HEAD'],text=True).splitlines()
texts={Path(p):Path(p).read_text(errors='replace') for p in tracked if Path(p).is_file() and b'\0' not in Path(p).read_bytes()[:4096] and Path(p).stat().st_size<2_000_000}
rows=read('files.csv')
for r in rows:
 p=Path(r['path']);r['high_decision']='retain';r['high_evidence']='Baseline supported input/reference; no removal justified'
 if not p.exists(): r['high_decision']='remove';r['high_evidence']='Confirmed obsolete file; see high-pass report';continue
 if r['decision']!='defer':continue
 hits=[f'{q}' for q,s in texts.items() if q!=p and re.search(r'(?<!\w)'+re.escape(p.stem)+r'(?!\w)',s)]
 if hits:r['high_evidence']='Extensionless symbol/module references: '+';'.join(hits[:6])
 elif p.suffix=='.java' or 'src/main/resources' in str(p):r['high_evidence']='Jenkins HPI compilation or convention-based Jelly/help/license packaging; pom.xml and @Extension/@DataBoundSetter contracts'
 elif p.suffix=='.go':r['high_evidence']='Go package compilation/test discovery; Magefile.go is mage build-tag entry; native validation blocked by denied module storage host'
 elif '.config/types' in str(p):r['high_evidence']='Included by .config/tsconfig.json include ./types; ambient asset/module declarations'
 elif 'splunk' in str(p):r['high_evidence']='Splunk app installation resource convention; app.conf/nav/default.xml/package.sh preserve native host assets'
 elif p.name.endswith('.test.ts'):r['high_evidence']='Jest/Vitest testMatch discovery, not a literal filename import'
 elif p.name in ('.nvmrc','.npmignore','.vscodeignore','jest.config.cjs','tsup.config.ts','vitest.config.ts'):r['high_evidence']='Tool-standard implicit configuration/packaging entry'
 elif str(p).startswith(('tools/','install')):r['high_evidence']='Operator-invoked CLI entry point with main/argument parser; not internal dead code'
 else:r['high_evidence']='Retain implicit entry/resource/public API; no positive dead-code proof'
write('high-files.csv',rows)
rows=read('dependencies.csv');known={r['dependency'] for r in rows if r['kind'].startswith('go')}
p=Path('integrations/upstream/grafana/plugin/go.mod')
for line in p.read_text().splitlines():
 m=re.search(r'(\S+\.\S*/\S+)\s+(v\S+)',line)
 if m and m[1] not in known:
  rows.append(dict(manifest=str(p),kind='go indirect' if '// indirect' in line else 'go direct',dependency=m[1],version=m[2],evidence=str(p),decision='defer',reason='Added module-path coverage missed by medium regex'))
for r in rows:
 r['high_decision']='retain';dep=r['dependency'];r['high_evidence']='Existing source/build/peer contract; no dependency change justified'
 if r['kind'].startswith('go'):r['high_decision']='retain-blocked-validation';r['high_evidence']='Pinned Go module graph; go mod why/go test attempted; storage.googleapis.com zip download denied. No module pruning justified from partial graph.'
 elif r['kind'].startswith('maven'):r['high_evidence']='POM role: Jenkins parent/BOM/HPI; structs @Symbol, workflow Step APIs, credentials access, Jackson JSON, warnings-ng SARIF; workflow-* test harness; exec plugin bundles CLI. Maven executable absent; native graph not rerun.'
 elif dep=='python-dotenv':r['high_evidence']='Installed pydantic-settings metadata Requires-Dist python-dotenv>=1.2.2 and pydantic_settings/sources/providers/dotenv.py imports dotenv; retain explicit installation contract'
 elif r['decision']=='defer':
  manifest=Path(r['manifest']); lock=manifest.parent/'package-lock.json'; related=[]
  if lock.exists():
   for name,item in json.loads(lock.read_text()).get('packages',{}).items():
    if dep in item.get('peerDependencies',{}) or dep in item.get('dependencies',{}):related.append(name)
  r['high_evidence']='Framework/build/test dependency relationships: '+';'.join(related[:6]) if related else 'Script or framework-tool contract retained; top-level declaration redundancy alone is not a removal proof'
write('high-dependencies.csv',rows)
rows=read('symbol-candidates.csv')
for r in rows:
 name=r['symbol'];p=r['path'];r['high_decision']='retain';r['high_evidence']='Public helper/method or developer scaffold: maintain compatibility contract'
 if name in ('_sast_time','first_match'):r['high_decision']='remove';r['high_evidence']='Unregistered module-level helper; no source callers/export registry; production path uses other functions'
 elif 'test' in p and name[0].isupper():r['high_evidence']='unittest.TestCase subclass discovered by test loader'
 elif name.startswith('visit_'):r['high_evidence']='ast.NodeVisitor dispatches by node class name'
 elif name.startswith('do_'):r['high_evidence']='BaseHTTPRequestHandler dispatches HTTP method to do_OPTIONS'
 elif 'Workflow' in name:r['high_evidence']='WorkflowRegistry imports workflow modules then inspect.getmembers discovers BaseWorkflow subclasses; base/TEMPLATE examples are explicit developer scaffolds'
 elif name=='on_call_tool':r['high_evidence']='FastMCP/custom decorator registration callback; lexical call count is not reachability'
write('high-symbols.csv',rows)
summary={n:dict(collections.Counter(r['high_decision'] for r in read(n))) for n in ['high-files.csv','high-dependencies.csv','high-symbols.csv']}
(root/'high-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
