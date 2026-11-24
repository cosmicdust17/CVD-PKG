"""Pinned v1.0.0-rc2 HTTP workflow; credentials are environment-only.

Routes/fields are traced in docs/API-AUDIT.md. Calls not live-tested until a
local RAGFlow account and models are configured are reported as such.
"""
import argparse
import copy
import logging
import os
import re
import time
from pathlib import Path
from urllib.parse import quote
import requests
from .core import ROOT, convert, file_identity, g6, read, write
from .pdf_audit import audit

LOG = logging.getLogger('hfkg.ragflow')

class Client:
    def __init__(self, base, key):
        self.base = base.rstrip('/')
        if not re.match(r'^https?://(localhost|127\.0\.0\.1)(:\d+)?$', self.base):
            raise ValueError('This project only sends source PDFs to local RAGFlow')
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers['Authorization'] = 'Bearer ' + key

    def call(self, method, path, **kwargs):
        started = time.monotonic()
        response = self.session.request(method, self.base + '/api/v1' + path, timeout=(10, 180), **kwargs)
        LOG.info('%s %s HTTP=%s seconds=%.2f', method, path, response.status_code, time.monotonic() - started)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get('code') != 0:
            # Do not dump full model/provider payloads or credentials into logs.
            raise RuntimeError(f'RAGFlow rejected {method} {path}; code={payload.get("code") if isinstance(payload,dict) else "invalid-envelope"}; message={str(payload.get("message", ""))[:600] if isinstance(payload,dict) else ""}')
        return payload.get('data')

def build_pipeline(template_id, chat_model, embedding_model, pdf_method='Plain Text'):
    base = read(ROOT / 'vendor' / 'ragflow' / 'internal' / 'ingestion' / 'pipeline' / 'template' / 'ingestion_pipeline_general.json')
    dsl = copy.deepcopy(base['dsl'])
    components = dsl['components']
    extractor = next(k for k, v in components.items() if v['obj']['component_name'] == 'Extractor')
    compiler = 'Compiler:HFCardioGraph'
    components[compiler] = components.pop(extractor)
    components[compiler]['obj'] = {'component_name': 'Compiler', 'params': {
        'compilation_template_id': template_id, 'llm_id': chat_model,
        'embedding_model': embedding_model, 'language': 'Chinese',
        'max_workers': 1, 'enable_historical_dedup': False,
    }}
    for component in components.values():
        for key in ('upstream', 'downstream'):
            component[key] = [compiler if v == extractor else v for v in component[key]]
        if component['obj']['component_name'] == 'Parser':
            component['obj']['params']['pdf']['parse_method'] = pdf_method
    # The server normalizes components to the React graph. The old graph would
    # otherwise still show the replaced Extractor instead of Compiler.
    dsl.pop('graph', None)
    dsl.pop('path', None)
    return {'title': 'HF-KG cardiovascular Graph', 'permission': 'me',
            'canvas_type': 'Ingestion Pipeline', 'canvas_category': 'dataflow_canvas', 'dsl': dsl}

def create_setup(client, state, state_path, chat_model, embedding_model, pdf_method):
    if not state.get('template_id'):
        template = client.call('POST', '/compilation-template-groups', json=read(ROOT / 'config' / 'graph-template.json'))
        state['group_id'] = template['id']
        state['template_id'] = template['templates'][0]['id']
        write(state_path, state)
    if not state.get('pipeline_id'):
        pipeline = build_pipeline(state['template_id'], chat_model, embedding_model, pdf_method)
        write(ROOT / 'data' / 'pipeline-request.json', pipeline)
        result = client.call('POST', '/agents', json=pipeline)
        state['pipeline_id'] = result['id']
        write(state_path, state)
    if not state.get('dataset_id'):
        result = client.call('POST', '/datasets', json={
            'name': 'HF-KG cardiovascular prevention', 'embedding_model': embedding_model,
            'language': 'Chinese', 'permission': 'me', 'parse_type': 2, 'pipeline_id': state['pipeline_id'],
        })
        state['dataset_id'] = result['id']
        state['tenant_id'] = result.get('tenant_id')
        write(state_path, state)
    if not state.get('tenant_id'):
        # GetDataset returns the persisted dataset including tenant_id.
        dataset = client.call('GET', f'/datasets/{quote(state["dataset_id"], safe="")}')
        state['tenant_id'] = dataset.get('tenant_id')
        write(state_path, state)

def list_documents(client, dataset_id):
    docs, page = [], 1
    while True:
        result = client.call('GET', f'/datasets/{dataset_id}/documents', params={'page': page, 'page_size': 100})
        if not isinstance(result, dict) or not isinstance(result.get('docs'), list):
            raise RuntimeError('Unexpected document-list shape. Inspect actual response before proceeding.')
        batch = result['docs']
        docs.extend(batch)
        if not batch or len(docs) >= result.get('total', len(docs)):
            return docs
        page += 1

def poll_document(client, dataset_id, document_id, timeout, out):
    deadline = time.monotonic() + timeout
    history = []
    while time.monotonic() < deadline:
        docs = list_documents(client, dataset_id)
        doc = next((d for d in docs if d['id'] == document_id), None)
        if not doc:
            raise RuntimeError('Uploaded document missing from dataset listing')
        history.append({'time': time.time(), 'document': doc})
        write(out / 'parse-history.json', history)
        status = str(doc.get('ingestion_status', '')).upper()
        progress = doc.get('progress', 0)
        LOG.info('document=%s status=%s progress=%s', document_id, status, progress)
        if status in ('FAIL', 'FAILED', 'ERROR', 'STOPPED', 'CANCEL', 'CANCELED', 'CANCELLED') or progress < 0:
            raise RuntimeError(f'Ingestion failed: {status}; inspect parse-history.json')
        if status in ('DONE', 'SUCCESS', 'SUCCEEDED', 'COMPLETED'):
            return doc
        time.sleep(5)
    raise TimeoutError('Ingestion did not finish within the requested timeout; remote task was not cancelled')

def export_rows(dataset_id, document_id, tenant_id, template_id):
    """Read exact persisted rows through Elasticsearch's supported REST API.

    RAGFlow graph GET projects away relation evidence; chunk GET explicitly
    hides compile_kwd. This local ES-only adapter does not modify the index.
    """
    if not tenant_id or not re.fullmatch(r'[A-Za-z0-9_-]+', tenant_id):
        raise ValueError('Verified dataset tenant_id is needed for raw evidence export')
    env = {}
    for line in (ROOT / 'deployment' / 'runtime' / '.env').read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k, v = line.split('=', 1)
            env[k] = v
    session = requests.Session()
    session.trust_env = False
    session.auth = ('elastic', os.environ.get('ELASTIC_PASSWORD', env.get('ELASTIC_PASSWORD', '')))
    base = 'http://127.0.0.1:' + env.get('ES_PORT', '19200')
    query = {'size': 500, 'sort': ['_doc'], '_source': [
        'id', 'doc_id', 'kb_id', 'content_with_weight', 'knowledge_graph_kwd',
        'source_chunk_ids', 'compilation_template_ids', 'compile_kwd', 'compilation_template_kind_kwd'],
        'query': {'bool': {'filter': [
            {'term': {'doc_id': document_id}}, {'term': {'kb_id': dataset_id}},
            {'terms': {'knowledge_graph_kwd': ['entity', 'relation']}},
            {'term': {'compilation_template_ids': template_id}},
        ]}}}
    response = session.post(base + '/ragflow_' + tenant_id + '/_search?scroll=2m', json=query, timeout=60)
    response.raise_for_status()
    result, rows, scroll_id = response.json(), [], None
    try:
        while True:
            scroll_id = result.get('_scroll_id', scroll_id)
            batch = result.get('hits', {}).get('hits', [])
            if not batch:
                break
            for hit in batch:
                row = hit['_source']
                row.setdefault('id', hit['_id'])
                rows.append(row)
            if not scroll_id:
                raise RuntimeError('ES did not return the requested scroll cursor')
            response = session.post(base + '/_search/scroll', json={'scroll': '2m', 'scroll_id': scroll_id}, timeout=60)
            response.raise_for_status()
            result = response.json()
    finally:
        if scroll_id:
            session.delete(base + '/_search/scroll', json={'scroll_id': [scroll_id]}, timeout=30)
    return rows

def main():
    parser = argparse.ArgumentParser(description='Actual local RAGFlow upload → Compiler Graph → evidence export')
    parser.add_argument('input', help='PDF or folder; files processed sequentially')
    parser.add_argument('--base-url', default='http://127.0.0.1:19380')
    parser.add_argument('--timeout', type=int, default=3600)
    parser.add_argument('--pdf-method', default='Plain Text', choices=['Plain Text', 'DeepDOC'])
    args = parser.parse_args()
    (ROOT / 'logs').mkdir(exist_ok=True)
    logging.basicConfig(filename=ROOT / 'logs' / 'ragflow-pipeline.log', level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    key, chat, embedding = [os.environ.get(k, '') for k in ('RAGFLOW_API_KEY', 'RAGFLOW_CHAT_MODEL', 'RAGFLOW_EMBEDDING_MODEL')]
    if not all((key, chat, embedding)):
        raise SystemExit('NOT RUN: Configure local RAGFlow models and set RAGFLOW_API_KEY, RAGFLOW_CHAT_MODEL, RAGFLOW_EMBEDDING_MODEL. No document was submitted.')
    state_path, lock = ROOT / 'data' / 'run-state.json', ROOT / 'data' / '.pipeline-lock'
    state_path.parent.mkdir(exist_ok=True)
    try:
        lock.mkdir()
    except FileExistsError:
        raise SystemExit('Another pipeline holds data/.pipeline-lock; verify it has stopped before removing this project lock.')
    try:
        client = Client(args.base_url, key)
        client.call('GET', '/compilation-templates/builtins')
        state = read(state_path) if state_path.exists() else {'documents': {}, 'chat_model': chat, 'embedding_model': embedding, 'pdf_method': args.pdf_method}
        if (state.get('chat_model'), state.get('embedding_model'), state.get('pdf_method')) != (chat, embedding, args.pdf_method):
            raise ValueError('Model or PDF parser settings changed; use a separate project run-state to preserve provenance')
        create_setup(client, state, state_path, chat, embedding, args.pdf_method)
        source = Path(args.input)
        files = sorted(source.rglob('*.pdf')) if source.is_dir() else [source]
        if not files:
            raise ValueError('No PDFs found')
        for pdf in files:
            doc_id, sha = file_identity(pdf)
            out = ROOT / 'output' / doc_id
            audit_dir = ROOT / 'data' / 'pdf-audit' / doc_id
            record = audit(pdf, audit_dir)
            existing = state['documents'].get(doc_id, {})
            if existing.get('upload_status') == 'unknown':
                raise RuntimeError('Previous upload outcome unknown; reconcile against dataset before retrying')
            if not existing.get('ragflow_document_id'):
                state['documents'][doc_id] = {'sha256': sha, 'upload_status': 'unknown'}
                write(state_path, state)
                with open(pdf, 'rb') as stream:
                    result = client.call('POST', f'/datasets/{state["dataset_id"]}/documents', files={'file': (pdf.name, stream, 'application/pdf')})
                write(out / 'upload-response.json', result)
                if not isinstance(result, list) or len(result) != 1 or 'id' not in result[0]:
                    raise RuntimeError('Unexpected upload response; saved response; no parse request was sent')
                existing = {'sha256': sha, 'ragflow_document_id': result[0]['id'], 'upload_status': 'complete'}
                state['documents'][doc_id] = existing
                write(state_path, state)
            remote_id = existing['ragflow_document_id']
            prefix = f'/datasets/{state["dataset_id"]}'
            if not existing.get('parse_requested'):
                client.call('PATCH', prefix + f'/documents/{remote_id}', json={'parse_type': 2, 'pipeline_id': state['pipeline_id']})
                result = client.call('POST', prefix + '/documents/parse', json={'document_ids': [remote_id]})
                if not isinstance(result, dict) or result.get('success_count') != 1:
                    raise RuntimeError('Parse request was not accepted for this document')
                existing['parse_requested'] = True
                write(state_path, state)
            poll_document(client, state['dataset_id'], remote_id, args.timeout, out)
            graph_view = client.call('GET', prefix + f'/documents/{remote_id}/structure/graph')
            write(out / 'ragflow-graph-view.json', graph_view)
            rows = export_rows(state['dataset_id'], remote_id, state.get('tenant_id'), state['template_id'])
            write(out / 'ragflow-raw-rows.json', rows)
            if not rows:
                raise RuntimeError('No actual Compiler entity/relation rows found; knowledge extraction is NOT verified')
            decisions_path = out / 'decisions.json'
            graph, review = convert(rows, read(audit_dir / 'pages.json'), record,
                                    read(decisions_path) if decisions_path.exists() else {}, read(ROOT / 'config' / 'aliases.json'))
            write(out / 'review.json', review)
            if graph['entities']:
                write(out / 'graph.json', graph)
                write(out / 'g6-data.json', g6(graph))
            print(f'RAGFlow rows={len(rows)} verified entities={len(graph["entities"])} reviewed relations={len(graph["relations"])}; {out}')
    except Exception:
        LOG.exception('Workflow failed; no success is claimed')
        raise
    finally:
        lock.rmdir()

if __name__ == '__main__':
    main()
