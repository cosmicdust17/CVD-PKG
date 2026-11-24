"""Apply content-bound source review; emit JSON only, without G6 or vectors."""
import argparse
import collections
import copy
from pathlib import Path
from .core import ROOT, ENTITY_TYPES, RELATION_TYPES, canonical, digest, read, validate, write
from .triples_only import locate_quote, now
from .relations import normalize_relation
from .entity_types import normalize_entity_type, translate_entity_fields

def finalize(candidates, decisions, pages):
    meta = candidates['metadata']
    if meta['status'] != 'extraction_complete_pending_review' or meta['errors']:
        raise ValueError('A complete successful actual extraction run is required')
    if decisions['run_fingerprint'] != meta['fingerprint']:
        raise ValueError('Review decisions belong to a different extraction run')
    document = meta['document']
    doc_id = document['document_id']
    lookup = {p['page']: p['text'] for p in pages}
    chosen = {d['candidate_id']: d for d in decisions['decisions']}
    raw_triples = [t for page in candidates['pages'] for t in page['triples']]
    if set(chosen) != {t['candidate_id'] for t in raw_triples}:
        raise ValueError('Every actual candidate must have exactly one review decision')
    aliases = decisions.get('aliases', {})
    entities, relations, evidence, pending, details = {}, {}, {}, [], {}

    def add_evidence(ev):
        page, quote = ev['page'], ev['quote']
        if page not in lookup or locate_quote(quote, lookup[page]) != quote:
            raise ValueError('Reviewed evidence is not an exact source-page substring')
        eid = doc_id + '_EV_' + digest([page, quote])
        evidence[eid] = {'id': eid, 'document_id': doc_id, 'page': page, 'quote': quote}
        return eid

    def add_entity(endpoint, evidence_ids):
        typ = normalize_entity_type(endpoint['type'])
        if typ not in ENTITY_TYPES:
            raise ValueError('Undefined entity type')
        name = canonical(endpoint['name'], typ, aliases)
        eid = doc_id + '_E_' + digest([name, typ])
        if eid not in entities:
            entities[eid] = {'id': eid, 'name': name, 'type': typ, 'aliases': [], 'evidence_ids': []}
        ent = entities[eid]
        ent['evidence_ids'] = sorted(set(ent['evidence_ids'] + evidence_ids))
        if endpoint['name'] != name:
            ent['aliases'] = sorted(set(ent['aliases'] + [endpoint['name']]))
        return eid

    for candidate in raw_triples:
        decision = chosen[candidate['candidate_id']]
        if not decision.get('reason'):
            raise ValueError('Every review decision requires a reason')
        if decision.get('approved') is not True:
            pending.append({'status': 'pending_review', 'reason': decision['reason'], 'candidate': candidate})
            continue
        triple = copy.deepcopy(candidate)
        for field in ('source', 'target', 'relation', 'qualifiers'):
            if field in decision.get('corrections', {}):
                triple[field] = decision['corrections'][field]
        triple['relation'] = normalize_relation(triple['relation'])
        if triple['relation'] not in RELATION_TYPES:
            raise ValueError('Undefined relation type')
        if triple['relation'] == '导致' and decision.get('explicit_causality_confirmed') is not True:
            raise ValueError('Unconfirmed causal direction')
        ev_ids = [add_evidence(ev) for ev in triple['evidence']]
        source = add_entity(triple['source'], ev_ids)
        target = add_entity(triple['target'], ev_ids)
        directed = triple['relation'] != '相关'
        if not directed:
            source, target = sorted((source, target))
        rid = doc_id + '_R_' + digest([source, target, triple['relation'], directed])
        if rid not in relations:
            relations[rid] = {'id': rid, 'source': source, 'target': target, 'type': triple['relation'],
                              'directed': directed, 'evidence_ids': []}
            details[rid] = {'qualifiers': [], 'source_candidate_ids': [], 'evidence_contexts': []}
        relation, detail = relations[rid], details[rid]
        relation['evidence_ids'] = sorted(set(relation['evidence_ids'] + ev_ids))
        if triple.get('qualifiers'):
            detail['qualifiers'] = sorted(set(detail['qualifiers'] + [triple['qualifiers']]))
        detail['source_candidate_ids'].append(candidate['candidate_id'])
        detail['evidence_contexts'].append({'evidence_ids': ev_ids, 'qualifiers': triple.get('qualifiers', ''),
                                            'review_reason': decision['reason']})

    for page in candidates['pages']:
        for issue in page['issues']:
            entry = {'status': 'pending_review', 'extraction_page': page['page'], 'issue': issue}
            raw = issue.get('raw')
            ev_page = raw.get('page') if isinstance(raw, dict) else None
            quote = raw.get('quote') if isinstance(raw, dict) else None
            exact = locate_quote(quote, lookup.get(ev_page, '')) if isinstance(ev_page, int) else None
            entry['evidence'] = {'document_id': doc_id, 'page': ev_page if exact else None, 'quote': exact}
            pending.append(entry)
    graph = {'metadata': {'schema_version': '1.0', 'extractor': 'RAGFlow', 'document_id': doc_id,
                           'documents': [document], 'status': 'evidence_checked'},
             'entities': sorted(entities.values(), key=lambda x: x['id']),
             'relations': sorted(relations.values(), key=lambda x: x['id']),
             'evidence': sorted(evidence.values(), key=lambda x: x['id'])}
    validate(graph, formal=True)
    triples = []
    for relation in graph['relations']:
        source, target = entities[relation['source']], entities[relation['target']]
        triples.append({'id': relation['id'], 'source': source['name'], 'source_id': source['id'],
                        'source_type': source['type'], 'relation': relation['type'],
                        'target': target['name'], 'target_id': target['id'], 'target_type': target['type'],
                        'directed': relation['directed'], 'qualifiers': details[relation['id']]['qualifiers'],
                        'evidence': [evidence[x] for x in relation['evidence_ids']],
                        'evidence_contexts': details[relation['id']]['evidence_contexts'],
                        'source_candidate_ids': details[relation['id']]['source_candidate_ids']})
    report = {'generated_at': now(), 'document_id': doc_id, 'model': meta['model_name'],
              'mode': 'RAGFlow chat API; local PDF text; no native Graph compiler, embeddings, indexes or G6',
              'prompt_fingerprint': meta['fingerprint'], 'total_pdf_pages': document['page_count'],
              'processed_body_pages': meta['processed_pages'], 'skipped_bibliography_pages': meta['skipped_pages'],
              'raw_candidate_count': len(raw_triples), 'accepted_candidates_before_dedup': sum(d['approved'] for d in chosen.values()),
              'pending_candidates': sum(not d['approved'] for d in chosen.values()),
              'entity_count': len(entities), 'relation_count': len(relations), 'evidence_count': len(evidence),
              'entity_type_counts': dict(collections.Counter(e['type'] for e in entities.values())),
              'relation_type_counts': dict(collections.Counter(r['type'] for r in relations.values())),
              'review_method': decisions['review_method'], 'embedding_requests': 0,
              'vector_index_created': False, 'g6_generated': False, 'schema_and_references': 'passed',
              'all_final_quotes_exactly_located_on_source_pdf_page': True,
              'all_final_items_have_evidence': True}
    return graph, {'metadata': report, 'triples': triples}, {'metadata': {'status': 'pending_review', 'document': document}, 'items': pending}, report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', default=str(ROOT / 'output' / 'primary-prevention-triples'))
    args = parser.parse_args()
    out = Path(args.directory)
    candidates = read(out / 'candidates.json')
    doc_id = candidates['metadata']['document']['document_id']
    pages = read(ROOT / 'data' / 'pdf-audit' / doc_id / 'pages.json')
    graph, triples, pending, report = finalize(candidates, read(out / 'review-decisions.json'), pages)
    from .normalize import normalize_bundle, EXPORT_VERSION
    registry = read(ROOT / 'config' / 'documents.json')
    prefix = next(k for k,v in registry.items() if v['sha256'] == candidates['metadata']['document']['sha256'])
    graph, triples, trace = normalize_bundle(graph, triples, prefix, candidates)
    write(out / 'id-mapping.json', trace)
    write(out / 'graph.json', graph)
    write(out / 'triples.json', triples)
    from .normalize import replace_references, translate_relation_fields
    pending = translate_entity_fields(translate_relation_fields(replace_references(pending, trace['old_to_new'])))
    write(out / 'pending-review.json', pending)
    report['document_id'] = prefix
    report['export_schema_version'] = EXPORT_VERSION
    report['entity_language'] = 'zh-CN'
    write(out / 'extraction-report.json', report)
    print(f'Actual final entities={report["entity_count"]}, triples={report["relation_count"]}, evidence={report["evidence_count"]}; embeddings=0; G6 not generated')

if __name__ == '__main__':
    main()
