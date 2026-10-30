import ast,csv,hashlib,json,re,subprocess,collections,xml.etree.ElementTree as ET
from pathlib import Path
root=Path.cwd(); out=Path('docs/maintenance/dead-code-audit-2026-10-30');out.mkdir(parents=True,exist_ok=True)
original=subprocess.check_output(['git','ls-tree','-r','--name-only','HEAD'],text=True).splitlines()
files=[Path(p) for p in original if Path(p).is_file()]
texts={p:p.read_text(errors='replace') for p in files if b'\0' not in p.read_bytes()[:4096] and p.stat().st_size<2_000_000}
def write(name,rows,fields):
 with (out/name).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)
def refs(terms,exclude=None,scope=None):
 return [str(p) for p,s in texts.items() if p!=exclude and (scope is None or p.is_relative_to(scope)) and any(t and t in s for t in terms)]
rows=[];duplicates=collections.defaultdict(list)
for name in original:
 p=Path(name)
 if not p.exists(): rows.append(dict(path=name,bytes=0,sha256='',category='staged removal',decision='remove',reference_files='',reason='Previously verified obsolete override/archive, duplicate environment or unused image'));continue
 duplicates[hashlib.sha256(p.read_bytes()).hexdigest()].append(name)
 rr=refs([name,p.name],p)
 category=('evidence' if name.startswith(('docs/handoff/','docs/pro-audit/','docs/validation/')) else 'test/fixture' if any(x in p.parts for x in ('tests','test','fixtures','e2e')) else 'documentation' if p.suffix=='.md' else 'manifest/build/config' if p.name in ('package.json','pom.xml','go.mod') or p.suffix in ('.yml','.yaml','.json','.toml','.sum') or p.name.startswith(('Dockerfile','requirements')) else 'code' if p.suffix in ('.py','.ts','.tsx','.js','.mjs','.cjs','.go','.java','.sh') else 'asset/resource')
 # Lack of textual references is only a review signal, never a deletion proof.
 decision='retain' if category in ('evidence','test/fixture','documentation','manifest/build/config') or rr or p.name in ('LICENSE','.gitignore','__init__.py') else 'defer'
 rows.append(dict(path=name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),category=category,decision=decision,reference_files=';'.join(rr),reason='Retained evidence/test/document/build input or textual reference' if decision=='retain' else 'No filename reference found; implicit entry point, resource registration or dynamic/cross-package usage needs high pass'))
write('files.csv',rows,list(rows[0]))
write('duplicates.csv',[{'sha256':h,'paths':';'.join(ps),'decision':'retain/defer; package-local copies may be required'} for h,ps in duplicates.items() if len(ps)>1],['sha256','paths','decision'])
deps=[]
for p in files:
 if p.name=='package.json':
  j=json.loads(p.read_text())
  for kind in ('dependencies','devDependencies','peerDependencies','optionalDependencies'):
   for dep,version in j.get(kind,{}).items():
    aliases=[dep]
    if dep.startswith('@types/'): aliases+=[dep[7:]]
    aliases+=[{'typescript':'tsc','@grafana/sign-plugin':'sign-plugin','typescript-eslint':'typescript-eslint','rimraf':'rimraf'}.get(dep,dep)]
    rr=[q for q in refs(aliases,p,p.parent) if not q.endswith(('package-lock.json','go.sum'))]
    deps.append(dict(manifest=str(p),kind=kind,dependency=dep,version=version,evidence=';'.join(rr),decision='retain' if rr or kind=='peerDependencies' else 'defer',reason='Textual package/tool/type reference; may be build-only' if rr else 'Host contract, config resolution or transitive use needs high pass'))
 elif p.name=='requirements.txt':
  mapping={'python-dotenv':'dotenv','PyJWT':'jwt','pypdf':'pypdf','pyHanko':'pyhanko','reportlab':'reportlab','cryptography':'cryptography','tzdata':'zoneinfo'}
  for line in p.read_text().splitlines():
   if not line.strip() or line.startswith('#'): continue
   dep=re.split(r'[\[<>=!~; ]',line)[0]; rr=refs([mapping.get(dep,dep.replace('-','_'))],p,Path('mcp'))
   deps.append(dict(manifest=str(p),kind='python direct',dependency=dep,version=line,evidence=';'.join(rr),decision='retain' if rr else 'defer',reason='Import or related module reference' if rr else 'No direct reference; framework/transitive coupling requires high pass'))
 elif p.name=='go.mod':
  for line in p.read_text().splitlines():
   match=re.search(r'(github.com/\S+|golang.org/\S+|google.golang.org/\S+|gopkg.in/\S+|go\.(?:opentelemetry|uber)\.\S+)\s+(v\S+)',line)
   if match:
    dep,ver=match.groups();rr=refs([dep],p,p.parent);rr=[q for q in rr if not q.endswith('go.sum')]
    indirect='// indirect' in line
    deps.append(dict(manifest=str(p),kind='go indirect' if indirect else 'go direct',dependency=dep,version=ver,evidence=';'.join(rr),decision='defer' if indirect else 'retain',reason='Module graph edge; do not prune by import grep' if indirect else 'Direct Grafana SDK import'))
 elif p.name=='pom.xml':
  ns={'m':'http://maven.apache.org/POM/4.0.0'};tree=ET.parse(p)
  for kind,xpath in [('maven dependency','.//m:dependency'),('maven plugin','.//m:plugin'),('maven parent','.//m:parent')]:
   for el in tree.findall(xpath,ns):
    dep=':'.join(el.findtext('m:'+x,default='',namespaces=ns) for x in ('groupId','artifactId'));version=el.findtext('m:version',default='managed',namespaces=ns)
    deps.append(dict(manifest=str(p),kind=kind,dependency=dep,version=version,evidence=str(p),decision='defer',reason='Jenkins extension/BOM/plugin resolution; cross-package review deferred'))
write('dependencies.csv',deps,list(deps[0]))
installs=[]
for p,s in texts.items():
 if p.suffix in ('.sh','.py','.yml','.yaml') or p.name.startswith('Dockerfile'):
  for i,line in enumerate(s.splitlines(),1):
   if re.search(r'(apt-get install|apt install|pip install|npm (?:install|ci)|go install|gem install|cargo install|git clone|curl .*https://)',line): installs.append(dict(path=str(p),line=i,declaration=line.strip(),decision='retain/defer: installation/build or assessment-tool inventory, no blind pruning'))
write('install-sites.csv',installs,['path','line','declaration','decision'])
token_counts=collections.Counter(token for text in texts.values() for token in re.findall(r"\b\w+\b",text))
definitions=[]
for p,s in texts.items():
 if p.suffix!='.py':continue
 try:t=ast.parse(s)
 except SyntaxError:continue
 for n in ast.walk(t):
  if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and not n.name.startswith(('test','__')):
   hits=token_counts[n.name]
   if hits==1: definitions.append(dict(path=str(p),line=n.lineno,symbol=n.name,decision='defer',reason='Single textual occurrence; decorator/reflection/protocol use may be required'))
write('symbol-candidates.csv',definitions,['path','line','symbol','decision','reason'])
summary={'base':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'tracked_files_accounted':len(rows),'file_decisions':dict(collections.Counter(r['decision'] for r in rows)),'dependency_declarations':len(deps),'dependency_decisions':dict(collections.Counter(r['decision'] for r in deps)),'installation_sites':len(installs),'python_symbol_candidates':len(definitions)}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
