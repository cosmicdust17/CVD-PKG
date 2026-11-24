"""Lossless, deterministic short-ID export of reviewed document bundles."""
import argparse
import copy
from pathlib import Path
from .core import ROOT, read, write
from .relations import normalize_relation
from .entity_types import translate_entity_fields

EXPORT_VERSION = '2.1'

def translate_relation_fields(value):
    if isinstance(value, list):
        return [translate_relation_fields(x) for x in value]
    if isinstance(value, dict):
        return {normalize_relation(k): normalize_relation(v) if k in ('relation', 'type') and isinstance(v, str)
                else translate_relation_fields(v) for k, v in value.items()}
    return value

def replace_references(value, mapping):
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        return [replace_references(x, mapping) for x in value]
    if isinstance(value, dict):
        return {mapping.get(k, k): replace_references(v, mapping) for k, v in value.items()}
    return value

def normalize_bundle(graph, old_triples, prefix, candidates=None):
    if prefix not in ('D1', 'D2', 'D3'):
        raise ValueError('Document prefix must be explicitly registered as D1, D2 or D3')
    graph, old_triples = translate_entity_fields(copy.deepcopy(graph)), translate_entity_fields(copy.deepcopy(old_triples))
    mapping = {}
    for key, code in [('entities', 'E'), ('relations', 'R'), ('evidence', 'EV')]:
        for i, item in enumerate(graph[key], 1):
            mapping[item['id']] = f'{prefix}_{code}{i:03d}'
    raw_candidates = [t for p in (candidates or {}).get('pages', []) for t in p['triples']]
    candidate_ids = list(dict.fromkeys([t['candidate_id'] for t in raw_candidates] +
                         [x for t in old_triples.get('triples', []) for x in t.get('source_candidate_ids', [])]))
    for i, old_id in enumerate(candidate_ids, 1):
        mapping[old_id] = f'{prefix}_C{i:03d}'
    old_doc = graph['metadata']['document_id']
    mapping[old_doc] = prefix
    graph = replace_references(graph, mapping)
    graph['metadata']['document_id'] = prefix
    for rel in graph['relations']:
        rel['type'] = normalize_relation(rel['type'])
    triples = []
    by_relation = {r['id']: r for r in graph['relations']}
    entities = {e['id']: e for e in graph['entities']}
    for original in old_triples['triples']:
        triple = replace_references(original, mapping)
        rel = by_relation[triple['id']]
        source_id = triple.get('source_id', rel['source'])
        target_id = triple.get('target_id', rel['target'])
        # Retain the names; source and target themselves now reference entities.
        triple['source_name'] = entities[source_id]['name']
        triple['target_name'] = entities[target_id]['name']
        triple['source'] = triple['source_id'] = source_id
        triple['target'] = triple['target_id'] = target_id
        triple['type'] = triple['relation'] = normalize_relation(triple.get('type', triple.get('relation', rel['type'])))
        triple['evidence_ids'] = list(rel['evidence_ids'])
        triples.append(triple)
        # The canonical relation also retains all qualifiers and provenance.
        for field in ('qualifiers', 'evidence_contexts', 'source_candidate_ids'):
            if field in triple:
                rel[field] = copy.deepcopy(triple[field])
    metadata = translate_relation_fields(replace_references(old_triples.get('metadata', {}), mapping))
    metadata.update(graph['metadata'])
    metadata['export_schema_version'] = EXPORT_VERSION
    metadata['entity_language'] = 'zh-CN'
    metadata['relation_language'] = 'zh-CN'
    metadata['id_format'] = f'{prefix}_E001 / {prefix}_R001 / {prefix}_EV001'
    metadata['entity_count'] = len(graph['entities'])
    metadata['relation_count'] = len(graph['relations'])
    metadata['evidence_count'] = len(graph['evidence'])
    graph['metadata'] = metadata
    exported = {**copy.deepcopy(graph), 'triples': triples}
    trace = {'document_id': prefix, 'old_to_new': mapping,
             'notice': 'Original identifiers are retained only in this migration/provenance map.'}
    return graph, exported, trace

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', required=True)
    parser.add_argument('--prefix', required=True)
    args = parser.parse_args()
    out = Path(args.directory)
    graph = read(out / 'graph.json')
    if graph['metadata'].get('export_schema_version') in ('2.0', EXPORT_VERSION):
        # Refresh legacy metadata labels without rebuilding the migration map.
        graph = translate_entity_fields(translate_relation_fields(graph))
        triples = translate_entity_fields(translate_relation_fields(read(out / 'triples.json')))
        if graph['metadata']['document_id'] != args.prefix:
            raise ValueError('Requested prefix differs from the existing document')
        for bundle in (graph, triples):
            bundle['metadata'].update(export_schema_version=EXPORT_VERSION, entity_language='zh-CN')
        from .core import validate
        from jsonschema import Draft202012Validator
        validate(graph, formal=True)
        Draft202012Validator(read(ROOT / 'schema/triples.schema.json')).validate(triples)
        write(out / 'graph.json', graph)
        write(out / 'triples.json', triples)
        pending = out / 'pending-review.json'
        if pending.exists():
            write(pending, translate_entity_fields(read(pending)))
        report_path = out / 'extraction-report.json'
        if report_path.exists():
            report = translate_entity_fields(translate_relation_fields(read(report_path)))
            report['document_id'] = args.prefix
            report['export_schema_version'] = EXPORT_VERSION
            report['entity_language'] = 'zh-CN'
            write(report_path, report)
        print('Chinese entity/endpoint types normalized; existing short IDs and prior mapping preserved.')
        return
    candidates = read(out / 'candidates.json') if (out / 'candidates.json').exists() else None
    graph, triples, trace = normalize_bundle(graph, read(out / 'triples.json'), args.prefix, candidates)
    from .core import validate
    validate(graph, formal=True)
    write(out / 'id-mapping.json', trace)
    write(out / 'graph.json', graph)
    write(out / 'triples.json', triples)
    pending = out / 'pending-review.json'
    if pending.exists():
        write(pending, translate_entity_fields(translate_relation_fields(replace_references(read(pending), trace['old_to_new']))))
    report_path = out / 'extraction-report.json'
    if report_path.exists():
        report = translate_entity_fields(translate_relation_fields(replace_references(read(report_path), trace['old_to_new'])))
        report['export_schema_version'] = EXPORT_VERSION
        report['entity_language'] = 'zh-CN'
        write(report_path, report)
    print(f'{args.prefix}: normalized {len(graph["entities"])} entities, {len(graph["relations"])} relations, {len(graph["evidence"])} evidence; no model calls')

if __name__ == '__main__':
    main()
