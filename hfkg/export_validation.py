"""Strict Chinese/short-ID validation, including source PDF and migration checks."""
import argparse
import collections
import hashlib
from pathlib import Path
from .core import ROOT, read, validate, write, file_identity
from .normalize import replace_references
from .relations import RELATION_TYPES, normalize_relation
from .entity_types import ENTITY_TYPES, normalize_entity_type, translate_entity_fields
from .triples_only import locate_quote, now

def check(condition, message):
    if not condition: raise ValueError(message)

def validate_export(out):
    from jsonschema import Draft202012Validator
    out=Path(out); bundle=read(out/'triples.json'); graph=read(out/'graph.json')
    Draft202012Validator(read(ROOT/'schema/triples.schema.json')).validate(bundle)
    validate(graph,formal=True)
    for key in ('metadata','entities','relations','evidence'):
        check(bundle[key]==graph[key],f'Companion JSON mismatch: {key}')
    prefix=graph['metadata']['document_id']
    check(prefix in ('D1','D2','D3'),'Invalid document ID')
    doc=graph['metadata']['documents'][0]; audit_id='DOC_'+doc['sha256'].upper()
    check(file_identity(doc['path'])[1]==doc['sha256'],'Source PDF SHA-256 changed')
    from pypdf import PdfReader
    reader=PdfReader(doc['path'])
    lookup={p['page']:p['text'] for p in read(ROOT/'data/pdf-audit'/audit_id/'pages.json')}
    ids=[]
    for key,code in [('entities','E'),('relations','R'),('evidence','EV')]:
        actual=[x['id'] for x in graph[key]]
        check(actual==[f'{prefix}_{code}{i:03d}' for i in range(1,len(actual)+1)],f'Invalid sequential {key} IDs')
        ids.extend(actual)
    check(len(ids)==len(set(ids)),'Duplicate IDs')
    entities={e['id']:e for e in graph['entities']}; evidence={e['id']:e for e in graph['evidence']}
    check(all(e['type'] in ENTITY_TYPES for e in entities.values()),'Invalid Chinese entity type')
    relations={r['id']:r for r in graph['relations']}
    check(len(bundle['triples'])==len(relations),'Triple count mismatch')
    check({t['id'] for t in bundle['triples']}==set(relations),'Duplicate or missing triple IDs')
    seen=set(); candidates=set(read(out/'id-mapping.json')['old_to_new'].values())
    for t in bundle['triples']:
        r=relations[t['id']]
        check(t['type']==t['relation']==r['type'] and r['type'] in RELATION_TYPES,'Invalid Chinese relation type')
        for ep in ('source','target'):
            check(t[ep]==t[ep+'_id']==r[ep],'Endpoint reference mismatch')
            ent=entities[t[ep]]
            check(t[ep+'_name']==ent['name'] and t[ep+'_type']==ent['type'],'Endpoint content mismatch')
        check(t['directed']==r['directed']==(r['type']!='相关'),'Unsupported direction')
        pair=(r['source'],r['target']) if r['directed'] else tuple(sorted((r['source'],r['target'])))
        key=(pair,r['type'],r['directed']);check(key not in seen,'Duplicate semantic relation');seen.add(key)
        check(set(t['evidence_ids'])==set(r['evidence_ids'])=={e['id'] for e in t['evidence']},'Evidence reference mismatch')
        for c in t.get('evidence_contexts',[]):check(set(c['evidence_ids']).issubset(r['evidence_ids']),'Dangling context evidence')
        for field in ('qualifiers','evidence_contexts','source_candidate_ids'):
            check(t.get(field)==r.get(field),'Canonical relation provenance mismatch')
        check(set(t.get('source_candidate_ids',[])).issubset(candidates),'Dangling provenance candidate')
        for ev in t['evidence']:check(ev==evidence[ev['id']],'Embedded evidence changed')
    for ev in evidence.values():
        check(ev['document_id']==prefix,'Wrong source document')
        check(locate_quote(ev['quote'],lookup.get(ev['page'],''))==ev['quote'],'Quote not located in actual PDF')
    for number in {ev['page'] for ev in evidence.values()}:
        actual_text=reader.pages[number-1].extract_text() or ''
        for ev in evidence.values():
            if ev['page']==number:check(ev['quote'] in actual_text,'Quote not a literal substring of re-read source PDF')
    keys=[(e['name'],e['type']) for e in entities.values()]
    check(len(keys)==len(set(keys)),'Duplicate same-type entity')
    active=read(out/'active-run.json');run=Path(active['run_dir']);manifest=read(run/'manifest.json')
    check(manifest['status']=='extraction_complete_pending_review' and not manifest['errors'],'Extraction incomplete')
    routes=[];calls=0
    for p in (run/'requests').glob('*.response.json'):
        event=read(p);check(event['http_status']==200 and event['response'].get('code')==0,'Saved API call failed')
        route=(event['method'],event['path']);check(route in {('GET','/models/default'),('POST','/chat/to_model')},'Unexpected API route')
        routes.append(route);calls+=route[0]=='POST'
    result={'checked_at':now(),'result':'passed','document_id':prefix,'file':str(out/'triples.json'),
            'entity_count':len(entities),'relation_count':len(relations),'evidence_count':len(evidence),
            'relation_counts':dict(collections.Counter(r['type'] for r in relations.values())),
            'entity_type_counts':dict(collections.Counter(e['type'] for e in entities.values())),
            'actual_successful_model_calls_including_review':calls,'allowed_request_routes':sorted(set(routes)),
            'all_short_ids_unique_and_sequential':True,'all_references_resolved':True,
            'all_quotes_verified_against_pdf':True,'source_pdf_sha256_verified':True,
            'source_pdf_reopened_and_evidence_pages_reparsed':True,'relation_language':'zh-CN',
            'entity_language':'zh-CN','all_entity_and_endpoint_types_chinese':True,'embedding_requests':0}
    write(out/'validation-report.json',result)
    return result,ids

def verify_d1_preservation(backup):
    oldg=read(Path(backup)/'output/primary-prevention-triples/graph.json')
    oldt=read(Path(backup)/'output/primary-prevention-triples/triples.json')
    out=ROOT/'output/primary-prevention-triples';newg=read(out/'graph.json');newt=read(out/'triples.json')
    mapping=read(out/'id-mapping.json')['old_to_new']
    for key in ('entities','relations','evidence'):
        check(len(oldg[key])==len(newg[key]),'D1 item count changed');lookup={x['id']:x for x in newg[key]}
        for old in oldg[key]:
            expected=replace_references(old,mapping)
            if key=='relations':expected['type']=normalize_relation(expected['type'])
            if key=='entities':expected['type']=normalize_entity_type(expected['type'])
            for k,v in expected.items():check(lookup[expected['id']][k]==v,f'D1 original content changed: {key}/{k}')
    current={t['id']:t for t in newt['triples']}
    for old in oldt['triples']:
        expected=replace_references(old,mapping);actual=current[expected['id']]
        for k,v in expected.items():
            if k=='source':check(actual['source_name']==v,'Source name lost')
            elif k=='target':check(actual['target_name']==v,'Target name lost')
            elif k=='relation':check(actual['type']==normalize_relation(v),'Relation meaning changed')
            elif k in ('source_type','target_type'):check(actual[k]==normalize_entity_type(v),'Endpoint type meaning changed')
            else:check(actual[k]==v,f'D1 triple content changed: {k}')
    return {'result':'passed','backup':str(backup),**{k:len(oldg[k]) for k in ('entities','relations','evidence')},
            'all_existing_names_aliases_semantics_qualifiers_and_evidence_preserved':True}


def verify_type_migration(backup):
    """Allow only ontology-label/metadata changes; all other content is exact."""
    from .normalize import EXPORT_VERSION
    reports=[]
    for prefix, profile in read(ROOT/'config/documents.json').items():
        old=Path(backup)/'output'/profile['output'];current=ROOT/'output'/profile['output']
        for name in ('graph.json','triples.json','pending-review.json','extraction-report.json'):
            expected=translate_entity_fields(read(old/name))
            if name in ('graph.json','triples.json'):
                expected['metadata'].update(export_schema_version=EXPORT_VERSION,entity_language='zh-CN')
            if name=='extraction-report.json':
                expected.update(export_schema_version=EXPORT_VERSION,entity_language='zh-CN')
            check(read(current/name)==expected,f'Unexpected non-type content change: {prefix}/{name}')
        for name in ('id-mapping.json','candidates.json','review-decisions.json','active-run.json'):
            check((old/name).read_bytes()==(current/name).read_bytes(),f'Original identifiers/run record changed: {prefix}/{name}')
        def hashes(directory):
            return {str(p.relative_to(directory)):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in directory.rglob('*') if p.is_file()}
        old_hashes=hashes(old/'runs')
        check(old_hashes==hashes(current/'runs'),f'Original model-run records changed: {prefix}')
        reports.append({'document_id':prefix,'result':'passed','ids_unchanged':True,
                        'all_names_aliases_relations_evidence_and_source_information_preserved':True,
                        'original_model_run_files_unchanged':len(old_hashes),'new_model_calls':0})
    return {'backup':str(backup),'result':'passed','documents':reports}

def main():
    p=argparse.ArgumentParser();p.add_argument('--directory');p.add_argument('--all',action='store_true');p.add_argument('--verify-d1-backup');p.add_argument('--verify-types-backup');args=p.parse_args()
    profiles=read(ROOT/'config/documents.json')
    directories=[ROOT/'output'/v['output'] for v in profiles.values()] if args.all else [Path(args.directory or ROOT/'output/primary-prevention-triples')]
    summaries=[];global_ids=set()
    for directory in directories:
        summary,ids=validate_export(directory);check(not global_ids.intersection(ids),'Cross-document ID collision')
        global_ids.update(ids);summaries.append(summary)
        print(f'{summary["document_id"]}: PASS {summary["entity_count"]} entities, {summary["relation_count"]} relations, {summary["evidence_count"]} evidence')
    report={'checked_at':now(),'documents':summaries,'cross_document_ids_unique':True,'consistent_schema':True}
    if args.verify_d1_backup:report['D1_preservation']=verify_d1_preservation(args.verify_d1_backup)
    if args.verify_types_backup:
        report['entity_type_migration']=verify_type_migration(args.verify_types_backup)
        write(ROOT/'reports/entity-type-migration-validation.json',report['entity_type_migration'])
    write(ROOT/'reports/unified-validation.json',report)

if __name__=='__main__':main()
