import hashlib
import json
import re
import unicodedata
from pathlib import Path

from .entity_types import ENTITY_TYPES, normalize_entity_type, normalize_alias_map
from .relations import RELATION_TYPES, normalize_relation
ROOT = Path(__file__).resolve().parents[1]

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest().upper()

def norm(text):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', text)).casefold()

def file_identity(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    sha = h.hexdigest()
    return 'DOC_' + sha.upper(), sha

def validate(graph, formal=False):
    from jsonschema import Draft202012Validator
    schema = read(ROOT / 'schema' / 'graph.schema.json')
    Draft202012Validator.check_schema(schema)
    errors = [f'{list(e.path)}: {e.message}' for e in Draft202012Validator(schema).iter_errors(graph)]
    if errors:
        raise ValueError('\n'.join(errors))
    all_ids = [x['id'] for key in ('entities', 'relations', 'evidence') for x in graph[key]]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError('Duplicate IDs')
    entities = {e['id'] for e in graph['entities']}
    evidence = {e['id']: e for e in graph['evidence']}
    docs = {d['document_id'] for d in graph['metadata'].get('documents', [])}
    docs.add(graph['metadata']['document_id'])
    page_counts = {d['document_id']: d.get('page_count') for d in graph['metadata'].get('documents', [])}
    for ev in evidence.values():
        if ev['document_id'] not in docs:
            raise ValueError('Unregistered evidence document')
        page_count = page_counts.get(ev['document_id'])
        if page_count is not None and ev['page'] is not None and ev['page'] > page_count:
            raise ValueError('Evidence page is outside the source PDF')
        if not formal and (ev['page'] is None or ev['quote'] is None) and graph['metadata'].get('status') != 'pending_review':
            raise ValueError('Null evidence must be marked pending_review')
    for item in graph['entities'] + graph['relations']:
        if any(eid not in evidence for eid in item['evidence_ids']):
            raise ValueError('Dangling evidence reference')
        if formal and not item['evidence_ids']:
            raise ValueError('Formal item has no evidence')
        if formal and any(evidence[eid]['page'] is None or not evidence[eid]['quote'] for eid in item['evidence_ids']):
            raise ValueError('Unverifiable evidence in formal graph')
    for rel in graph['relations']:
        if rel['source'] not in entities or rel['target'] not in entities:
            raise ValueError('Dangling entity reference')
        if rel['source'] == rel['target']:
            raise ValueError('Self relation requires manual review')
        if rel['type'] != '相关' and rel.get('directed') is False:
            raise ValueError('Risk/causal relations must have a supported direction')
    return True

def canonical(name, typ, alias_map):
    # Only user-reviewed aliases are authoritative. Model aliases are retained,
    # but cannot silently merge two medical concepts.
    mapping, seen = normalize_alias_map(alias_map).get(normalize_entity_type(typ), {}), set()
    while name in mapping:
        if name in seen:
            raise ValueError('Alias map contains a cycle')
        seen.add(name)
        name = mapping[name]
        if not isinstance(name, str) or not name.strip():
            raise ValueError('Invalid canonical alias name')
    return name.strip()

def merge(graphs, alias_map=None):
    alias_map = alias_map or {}
    entities, relations, evidence, documents = {}, {}, {}, {}
    for graph in graphs:
        validate(graph, formal=True)
        for doc in graph['metadata'].get('documents', []):
            old = documents.get(doc['document_id'])
            if old and old.get('sha256') != doc.get('sha256'):
                raise ValueError('Document ID collision')
            documents[doc['document_id']] = doc
        for ev in graph['evidence']:
            if ev['id'] in evidence and evidence[ev['id']] != ev:
                raise ValueError('Evidence ID collision')
            evidence[ev['id']] = ev
        idmap = {}
        for ent in graph['entities']:
            name = canonical(ent['name'], ent['type'], alias_map)
            key = (norm(name), ent['type'])
            if key not in entities:
                entities[key] = dict(ent, name=name, aliases=list(ent['aliases']), evidence_ids=list(ent['evidence_ids']))
            target = entities[key]
            target['aliases'] = sorted(set(target['aliases'] + ent['aliases'] + ([ent['name']] if ent['name'] != name else [])) - {name})
            target['evidence_ids'] = sorted(set(target['evidence_ids'] + ent['evidence_ids']))
            idmap[ent['id']] = target['id']
        for rel in graph['relations']:
            source, target = idmap[rel['source']], idmap[rel['target']]
            if source == target:
                raise ValueError('Alias map collapses relation endpoints; review alias map')
            directed = rel.get('directed', rel['type'] != '相关')
            if not directed:
                source, target = sorted((source, target))
            key = (source, target, rel['type'], directed)
            if key not in relations:
                relations[key] = dict(rel, source=source, target=target, directed=directed, evidence_ids=[])
            relations[key]['evidence_ids'] = sorted(set(relations[key]['evidence_ids'] + rel['evidence_ids']))
    doc_ids = sorted(documents)
    result = {
        'metadata': {'schema_version': '1.0', 'extractor': 'RAGFlow',
                     'document_id': doc_ids[0] if len(doc_ids) == 1 else 'MERGED_' + digest(doc_ids),
                     'documents': [documents[x] for x in doc_ids], 'status': 'evidence_checked'},
        'entities': sorted(entities.values(), key=lambda x: x['id']),
        'relations': sorted(relations.values(), key=lambda x: x['id']),
        'evidence': sorted(evidence.values(), key=lambda x: x['id']),
    }
    validate(result, formal=True)
    return result

def g6(graph):
    validate(graph, formal=True)
    return {
        'metadata': graph['metadata'],
        'nodes': [{'id': e['id'], 'data': {'label': e['name'], 'entity_type': e['type'],
                   'aliases': e['aliases'], 'evidence_ids': e['evidence_ids']}} for e in graph['entities']],
        'edges': [{'id': r['id'], 'source': r['source'], 'target': r['target'],
                   'data': {'label': r['type'], 'relation_type': r['type'],
                            'directed': r.get('directed', r['type'] != '相关'),
                            'evidence_ids': r['evidence_ids']},
                   'style': {'endArrow': r.get('directed', r['type'] != '相关')}} for r in graph['relations']],
        'evidence': graph['evidence'],
    }

def convert(raw_rows, pages, document, decisions=None, alias_map=None):
    """Convert actual RAGFlow _source rows; never invent facts from page text.

    Relations require a content-bound review decision. Quote matching is a
    provenance check, not a medical semantic/causality proof.
    """
    decisions, alias_map = decisions or {}, alias_map or {}
    doc_id = document['document_id']
    entities, relations, evidence, pending, candidates = [], [], {}, [], []
    names = {}

    def find_evidence(payload, row_id):
        found = []
        evs = payload.get('evidence') or []
        if not isinstance(evs, list):
            evs = []
        for ev in evs:
            quote = ev.get('quote') if isinstance(ev, dict) else None
            if not isinstance(quote, str) or not quote.strip():
                continue
            matches = [p['page'] for p in pages if norm(quote) in norm(p['text'])]
            # A repeated quote cannot establish one page unambiguously.
            page = matches[0] if len(matches) == 1 else None
            eid = f'{doc_id}_EV_{digest([page, quote])}'
            evidence[eid] = {'id': eid, 'document_id': doc_id, 'page': page, 'quote': quote if matches else None}
            found.append(eid)
            if page is None:
                pending.append({'row_id': row_id, 'reason': 'quote_missing_or_page_ambiguous', 'evidence_id': eid})
        if not found:
            eid = f'{doc_id}_EV_{digest([row_id, None])}'
            evidence[eid] = {'id': eid, 'document_id': doc_id, 'page': None, 'quote': None}
            found.append(eid)
            pending.append({'row_id': row_id, 'reason': 'missing_verbatim_evidence', 'evidence_id': eid})
        return found

    parsed = []
    for row in raw_rows:
        payload = row.get('content_with_weight')
        try:
            payload = json.loads(payload) if isinstance(payload, str) else payload
        except (ValueError, TypeError):
            payload = None
        if not isinstance(payload, dict):
            pending.append({'row_id': row.get('id'), 'reason': 'invalid_payload'})
            continue
        parsed.append((row, payload))
    for row, payload in parsed:
        kind = row.get('knowledge_graph_kwd')
        if kind not in ('entity', ['entity']):
            continue
        typ, name = normalize_entity_type(payload.get('type')), payload.get('name', '')
        if typ not in ENTITY_TYPES or not isinstance(name, str) or not name.strip():
            pending.append({'row_id': row.get('id'), 'reason': 'undefined_entity_type_or_name', 'payload': payload})
            continue
        canonical_name = canonical(name, typ, alias_map)
        eid = f'{doc_id}_E_{digest([canonical_name, typ])}'
        ev_ids = find_evidence(payload, row.get('id'))
        aliases = payload.get('aliases') or []
        aliases = [aliases] if isinstance(aliases, str) else aliases
        aliases = [a for a in aliases if isinstance(a, str)]
        entities.append({'id': eid, 'name': canonical_name, 'type': typ, 'aliases': aliases, 'evidence_ids': ev_ids})
        for term in (name, canonical_name):
            names.setdefault(norm(term), set()).add(eid)
    for row, payload in parsed:
        if row.get('knowledge_graph_kwd') not in ('relation', ['relation']):
            continue
        typ = normalize_relation(payload.get('type'))
        source = payload.get('source', payload.get('from', ''))
        target = payload.get('target', payload.get('to', ''))
        candidate_id = doc_id + '_C_' + digest([row, payload])
        ev_ids = find_evidence(payload, row.get('id'))
        candidate = {'candidate_id': candidate_id, 'row_id': row.get('id'), 'payload': payload,
                     'evidence_ids': ev_ids, 'reason': 'requires_semantic_review'}
        candidates.append(candidate)
        if typ not in RELATION_TYPES or not isinstance(source, str) or not isinstance(target, str):
            candidate['reason'] = 'undefined_relation_type_or_endpoints'
            continue
        srcs, tgts = names.get(norm(source), set()), names.get(norm(target), set())
        if len(srcs) != 1 or len(tgts) != 1:
            candidate['reason'] = 'missing_or_ambiguous_endpoint'
            continue
        decision = decisions.get(candidate_id, {})
        if not (decision.get('approved') is True and decision.get('reviewer') and decision.get('rationale')):
            continue
        if typ in ('导致', '增加风险') and decision.get('direction_confirmed') is not True:
            candidate['reason'] = 'direction_not_confirmed'
            continue
        if typ == '导致' and decision.get('explicit_causality_confirmed') is not True:
            candidate['reason'] = 'causality_not_confirmed'
            continue
        if any(evidence[x]['page'] is None or evidence[x]['quote'] is None for x in ev_ids):
            candidate['reason'] = 'unverified_evidence'
            continue
        source_id, target_id = next(iter(srcs)), next(iter(tgts))
        if source_id == target_id:
            candidate['reason'] = 'self_relation'
            continue
        # Association alone carries no implied arrow; store a canonical pair.
        directed = typ != '相关'
        if not directed:
            source_id, target_id = sorted((source_id, target_id))
        relations.append({'id': doc_id + '_R_' + digest([source_id, target_id, typ]),
                          'source': source_id, 'target': target_id, 'type': typ,
                          'directed': directed, 'evidence_ids': ev_ids})
        candidate['reason'] = 'approved'
    # Entities may be present alone, but only with individually verified quotes.
    verified_entities = []
    for ent in entities:
        ent['evidence_ids'] = [x for x in ent['evidence_ids'] if evidence[x]['page'] is not None and evidence[x]['quote']]
        if ent['evidence_ids']:
            verified_entities.append(ent)
    supported = {e['id'] for e in verified_entities}
    relations = [r for r in relations if r['source'] in supported and r['target'] in supported]
    # Merge repeated rows before calling strict duplicate-ID validation.
    dedup_ent, dedup_rel = {}, {}
    for items, table in ((verified_entities, dedup_ent), (relations, dedup_rel)):
        for item in items:
            if item['id'] not in table:
                table[item['id']] = item
            else:
                table[item['id']]['evidence_ids'] = sorted(set(table[item['id']]['evidence_ids'] + item['evidence_ids']))
                if 'aliases' in item:
                    table[item['id']]['aliases'] = sorted(set(table[item['id']]['aliases'] + item['aliases']))
    used_ev = {x for e in list(dedup_ent.values()) + list(dedup_rel.values()) for x in e['evidence_ids']}
    graph = {'metadata': {'schema_version': '1.0', 'extractor': 'RAGFlow', 'document_id': doc_id,
                          'documents': [document], 'status': 'evidence_checked'},
             'entities': list(dedup_ent.values()), 'relations': list(dedup_rel.values()),
             'evidence': [evidence[x] for x in sorted(used_ev)]}
    validate(graph, formal=True)
    review = {'document': document, 'candidates': candidates, 'issues': pending,
              'evidence': list(evidence.values()), 'notice': 'Pending relations are excluded from graph.json. Quotes alone do not prove semantic correctness.'}
    return graph, review
