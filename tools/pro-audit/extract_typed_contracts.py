#!/usr/bin/env python3
"""Read selected user-supplied audit text as AST; never import vendor modules.

Output contains typed declarations and evidence hashes, not proprietary code,
binaries, prompts, runtime responses, or invented default values.
"""
import argparse
import ast
import hashlib
import json
import zipfile
from pathlib import Path

SOURCES = (
    'raw/api/routes_auth.py', 'raw/api/routes_run.pyi', 'raw/api/routes_scheduler.pyi',
    'raw/api/routes_credentials.pyi', 'raw/api/routes_webhooks.pyi', 'raw/api/routes_retest.pyi',
    'raw/remediation/models.pyi', 'raw/remediation/pipeline.pyi', 'raw/remediation/patcher.pyi',
)
ROOT = 'darkmoon-pro-complete-audit/'


def extract(archive):
    models, constants, sources = [], [], []
    with zipfile.ZipFile(archive) as bundle:
        for source in SOURCES:
            info = bundle.getinfo(ROOT + source)
            if info.file_size > 2 * 1024 * 1024:
                raise ValueError('Selected contract source exceeds 2 MiB')
            content = bundle.read(info)
            tree = ast.parse(content.decode('utf-8'), filename=source)
            sources.append({'path':source,'sha256':hashlib.sha256(content).hexdigest()})
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    fields = []
                    for field in node.body:
                        if not isinstance(field, ast.AnnAssign) or not isinstance(field.target, ast.Name):
                            continue
                        annotation = ast.unparse(field.annotation)
                        if field.value is None:
                            default = {'known':True,'kind':'no_default_declaration'}
                        elif isinstance(field.value, ast.Constant) and field.value.value is Ellipsis:
                            default = {'known':False,'reason':'erased_in_stub'}
                        elif isinstance(field.value, ast.Constant) and isinstance(field.value.value, (str,int,float,bool,type(None))):
                            # Request fields only. No module-level auth/runtime constants are exported.
                            default = {'known':True,'value':field.value.value}
                        else:
                            default = {'known':False,'reason':'expression_not_executed'}
                        fields.append({'name':field.target.id,'annotation':annotation,'line':field.lineno,'default':default})
                    if fields:
                        models.append({'module':source,'name':node.name,'line':node.lineno,
                                       'bases':[ast.unparse(base) for base in node.bases],'fields':fields})
                if source.endswith('patcher.pyi') and isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id in {'_PATCH_SYSTEM','_JUDGE_SYSTEM'}:
                            text = node.value.value if isinstance(node.value, ast.Constant) and isinstance(node.value.value,str) else None
                            constants.append({'name':target.id,'source':source,'line':node.lineno,
                                              'text_recovered':text is not None,
                                              'characters':len(text) if text is not None else None,
                                              'sha256':hashlib.sha256(text.encode()).hexdigest() if text is not None else None})
    return {'evidence_level':'static_declarations_only','genuine_vendor_runtime_executed':False,
            'vendor_image':'ascit/opencode-darkmoon-pro@sha256:48248382877ec1fd7362d2268656956268129d5ea565befab3a24436ea2fc907',
            'unknown_defaults_policy':'Ellipses in generated stubs stay unknown; optional annotations do not establish default values or update semantics.',
            'sources':sources,'models':models,'prompt_constants_metadata_only':constants}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    result = extract(args.archive)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'models':len(result['models']),'fields':sum(len(m['fields']) for m in result['models']),
                      'unknown_defaults':sum(not f['default']['known'] for m in result['models'] for f in m['fields']),
                      'prompt_metadata':len(result['prompt_constants_metadata_only']),'output':str(args.output)}))


if __name__ == '__main__':
    main()
