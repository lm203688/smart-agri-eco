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
    out['python_loc_by_top'][top] = sum(len(p.read_text(encoding='utf-8').splitlines()) for p in (ROOT/top).rglob('*.py'))

recipes = []
for p in (ROOT/'data/env_recipes').glob('*.json'):
    r = load(p)
    env = r.get('environment') or {}
    sources = r.get('sources') or []
    recipes.append({
        'crop': (r.get('crop') or {}).get('species'),
        'stage': r.get('stage'),
        'device': (r.get('device_profile') or {}).get('device_class'),
        'license': r.get('license'),
        'empty_urls': sum(not (s.get('url') or '').strip() for s in sources),
        'unverified': sum(bool(s.get('url_unverified')) for s in sources),
        'sources': len(sources),
        'source_spans': len(r.get('source_spans') or []),
        'execution_entries': len(r.get('execution_log') or []),
        'outcome': bool(r.get('outcome')),
        'sowing_method': (r.get('sowing_depth_cm') or {}).get('method'),
        'sowing_unsafe': (r.get('sowing_depth_cm') or {}).get('estimated_unsafe_for_execution') is True,
        'dli_deprecated': (env.get('dli_umol_m2_day') or {}).get('deprecated') is True,
        'shortwave': 'shortwave_photon_equivalent' in env,
        'par_dli_null': (env.get('par_dli') or {}).get('value') is None,
    })
out['recipes'] = {
    'count': len(recipes),
    'unique_crops': len({r['crop'] for r in recipes}),
    'stages': dict(collections.Counter(r['stage'] for r in recipes)),
    'devices': dict(collections.Counter(r['device'] for r in recipes)),
    'top_licenses': dict(collections.Counter(r['license'] for r in recipes)),
    'empty_source_urls': sum(r['empty_urls'] for r in recipes),
    'unverified_source_urls': sum(r['unverified'] for r in recipes),
    'total_sources': sum(r['sources'] for r in recipes),
    'recipes_with_source_spans': sum(r['source_spans'] > 0 for r in recipes),
    'total_source_spans': sum(r['source_spans'] for r in recipes),
    'execution_entries': sum(r['execution_entries'] for r in recipes),
    'nonempty_outcomes': sum(r['outcome'] for r in recipes),
    'sowing_methods': dict(collections.Counter(r['sowing_method'] for r in recipes)),
    'sowing_marked_unsafe': sum(r['sowing_unsafe'] for r in recipes),
    'dli_deprecated': sum(r['dli_deprecated'] for r in recipes),
    'shortwave_split': sum(r['shortwave'] for r in recipes),
    'par_dli_null': sum(r['par_dli_null'] for r in recipes),
}
execution = load(ROOT/'data/execution_log.json')
out['execution_log'] = {
    'count': len(execution),
    'sources': dict(collections.Counter(x.get('source') for x in execution)),
    'not_executed': sum(bool((x.get('shadow_context') or {}).get('not_executed')) for x in execution),
}
out['feedback_count'] = len(load(ROOT/'data/feedback_log.json'))
manifest = load(ROOT/'harness/manifest.json')
out['manifest'] = {
    'generated_at': manifest.get('generated_at'),
    'tool_count': manifest['mcp']['tool_count'],
    'skill_count': manifest['skills']['count'],
    'eval_pending': manifest['eval_baseline']['pending'],
    'rsi': {k:manifest['rsi'][k] for k in ['autonomy_level','hci','open_gates']},
}
reg_path = ROOT/'data/grow_batches/registry.json'
events_path = ROOT/'data/grow_batches/events.jsonl'
if reg_path.exists():
    reg = load(reg_path)
    batches = list((reg.get('batches') or {}).values())
    out['grow_batches'] = {
        'registry_exists': True,
        'plots': len(reg.get('plots') or {}),
        'batches': len(batches),
        'statuses': dict(collections.Counter(b.get('status') for b in batches)),
        'observations': sum(len(b.get('observations') or []) for b in batches),
        'actions': sum(len(b.get('actions') or []) for b in batches),
        'outcomes': sum(len(b.get('outcomes') or []) for b in batches),
        'executed_actions': sum(a.get('status') == 'executed' for b in batches for a in (b.get('actions') or [])),
        'registry_events_seq': reg.get('events_seq'),
        'event_lines': sum(1 for _ in events_path.open(encoding='utf-8')) if events_path.exists() else 0,
    }
else:
    out['grow_batches'] = {'registry_exists': False, 'batches': 0}
html = (ROOT/'app/index.html').read_text(encoding='utf-8')
out['frontend'] = {
    'lines': len(html.splitlines()),
    'fetch_calls': len(re.findall(r'\bfetch\s*\(', html)),
    'event_listeners': len(re.findall(r'addEventListener\s*\(', html)),
    'canvas': len(re.findall(r'<canvas\b',html,re.I)),
    'image_accept': len(re.findall(r'accept=["\'][^"\']*image',html,re.I)),
    'sse': len(re.findall(r'EventSource|text/event-stream',html)),
    'grow_batch_mentions': len(re.findall(r'grow.?batch|GrowBatch|批次',html,re.I)),
}
cases = []
layers = collections.Counter()
for p in (ROOT/'benchmarks/agri_recipe_bench/cases').glob('*.json'):
    d = load(p)
    layers[d.get('evidence_layer','unlabeled')] += 1
    if d.get('axis') == 'target_prediction': cases.append(d)
out['benchmark'] = {'cases': sum(layers.values()), 'target_cases': len(cases), 'evidence_layers': dict(layers)}
imports = collections.Counter()
for top in ['agent','core','engine','mcp']:
    for p in (ROOT/top).rglob('*.py'):
        try: tree = ast.parse(p.read_text(encoding='utf-8'))
        except Exception: continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for a in n.names: imports[a.name.split('.')[0]] += 1
            elif isinstance(n, ast.ImportFrom) and n.module: imports[n.module.split('.')[0]] += 1
out['non_stdlib_suspects'] = sorted(set(imports)-set(__import__('sys').stdlib_module_names)-{'agent','core','engine','mcp','bp_screen','scripts'})
path = ROOT/'project_scan_phase2_2026-10-28.json'
path.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False,indent=2))
