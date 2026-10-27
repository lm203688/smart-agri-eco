from pathlib import Path
import ast, collections, json, re
ROOT = Path(__file__).resolve().parent

def load(path):
    with path.open(encoding='utf-8') as f:
        return json.load(f)

out = {}
files = [p for p in ROOT.rglob('*') if p.is_file() and '.workbuddy' not in p.parts and '_archive' not in p.parts]
out['files_scoped'] = len(files)
out['python_loc_by_top'] = {}
for top in ['agent','core','engine','mcp','app','bp_screen','scripts','firmware']:
    loc = 0
    for p in (ROOT/top).rglob('*.py'):
        loc += len(p.read_text(encoding='utf-8').splitlines())
    out['python_loc_by_top'][top] = loc

recipes = []
for p in (ROOT/'data/env_recipes').glob('*.json'):
    r = load(p)
    sources = r.get('sources', [])
    recipes.append({
        'file': p.name,
        'crop': (r.get('crop') or {}).get('species'),
        'stage': r.get('stage'),
        'device': (r.get('device_profile') or {}).get('device_class'),
        'license': r.get('license'),
        'license_scope': r.get('license_scope',''),
        'source_licenses': [s.get('source_license') for s in sources],
        'url_empty': sum(not (s.get('url') or '').strip() for s in sources),
        'url_unverified': sum(bool(s.get('url_unverified')) for s in sources),
        'sources': len(sources),
        'execution_log': len(r.get('execution_log') or []),
        'outcome_nonempty': bool(r.get('outcome')),
        'dli': ((r.get('environment') or {}).get('dli_umol_m2_day') or {}).get('value'),
        'sowing_method': (r.get('sowing_depth_cm') or {}).get('method'),
    })
out['recipes'] = {
    'count': len(recipes),
    'unique_crops': len({r['crop'] for r in recipes}),
    'stages': dict(collections.Counter(r['stage'] for r in recipes)),
    'devices': dict(collections.Counter(r['device'] for r in recipes)),
    'top_licenses': dict(collections.Counter(r['license'] for r in recipes)),
    'empty_source_urls': sum(r['url_empty'] for r in recipes),
    'unverified_source_urls': sum(r['url_unverified'] for r in recipes),
    'total_sources': sum(r['sources'] for r in recipes),
    'execution_entries': sum(r['execution_log'] for r in recipes),
    'nonempty_outcomes': sum(r['outcome_nonempty'] for r in recipes),
    'sowing_methods': dict(collections.Counter(r['sowing_method'] for r in recipes)),
    'dli_examples': sorted({r['dli'] for r in recipes if r['dli'] is not None})[:20],
}
execution = load(ROOT/'data/execution_log.json')
out['execution_log'] = {'count':len(execution),'sources':dict(collections.Counter(x.get('source') for x in execution)), 'not_executed':sum(bool((x.get('shadow_context') or {}).get('not_executed')) for x in execution)}
feedback = load(ROOT/'data/feedback_log.json')
out['feedback_count'] = len(feedback)
manifest = load(ROOT/'harness/manifest.json')
out['manifest_eval'] = manifest['eval_baseline']
out['manifest_rsi'] = {k:manifest['rsi'][k] for k in ['autonomy_level','hci','open_gates']}
html = (ROOT/'app/index.html').read_text(encoding='utf-8')
out['frontend'] = {
    'lines': len(html.splitlines()),
    'fetch_calls': len(re.findall(r'\bfetch\s*\(', html)),
    'event_listeners': len(re.findall(r'addEventListener\s*\(', html)),
    'canvas': len(re.findall(r'<canvas\b',html,re.I)),
    'file_inputs': len(re.findall(r'type=["\']file["\']',html,re.I)),
    'image_accept': len(re.findall(r'accept=["\'][^"\']*image',html,re.I)),
    'sse': len(re.findall(r'EventSource|text/event-stream',html)),
    'session_references': len(re.findall(r'session_id|agri_session',html)),
}
# Parse benchmark cases to detect expectation duplication and tolerances.
cases = []
for p in (ROOT/'benchmarks/agri_recipe_bench/cases').glob('*.json'):
    d=load(p)
    if d.get('axis')=='target_prediction': cases.append((p.name,d))
out['target_cases'] = len(cases)
# Static import check for optional dependencies.
imports=collections.Counter()
for top in ['agent','core','engine','mcp']:
    for p in (ROOT/top).rglob('*.py'):
        try: tree=ast.parse(p.read_text(encoding='utf-8'))
        except Exception: continue
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):
                for a in n.names: imports[a.name.split('.')[0]]+=1
            elif isinstance(n,ast.ImportFrom) and n.module: imports[n.module.split('.')[0]]+=1
out['non_stdlib_suspects'] = sorted(set(imports)-set(__import__('sys').stdlib_module_names)-{'agent','core','engine','mcp','bp_screen','scripts'})
(ROOT/'project_scan_2026-10-26.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False,indent=2))
