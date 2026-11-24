"""Verify a local API token and discover enabled default model identities."""
import os
from .core import ROOT, write
from .ragflow import Client

def select_default(models, model_type):
    selected = [m for m in models if m.get('model_type') == model_type and m.get('enable') is True]
    if len(selected) != 1 or not selected[0].get('model_id'):
        raise ValueError(f'RAGFlow must have one enabled default {model_type} with a model_id. Check Model providers and default model settings.')
    return selected[0]

def main():
    token = os.environ.get('RAGFLOW_API_KEY', '').strip()
    if not token:
        raise SystemExit('No token supplied. Run configure.ps1 in your own PowerShell window.')
    client = Client('http://127.0.0.1:19380', token)
    try:
        data = client.call('GET', '/models/default')
    except Exception:
        raise SystemExit('Local RAGFlow token verification failed. Check that the service is running and use a token from this local ordinary account. No token was saved.') from None
    if not isinstance(data, dict) or not isinstance(data.get('models'), list):
        raise SystemExit('Unexpected default-model response; no model identity was guessed.')
    chat = select_default(data['models'], 'chat')
    embedding = select_default(data['models'], 'embedding')
    selection = {
        'base_url': 'http://127.0.0.1:19380',
        'chat_model': chat['model_id'], 'chat_model_name': chat.get('model_name'),
        'embedding_model': embedding['model_id'], 'embedding_model_name': embedding.get('model_name'),
        'source': 'GET /api/v1/models/default; actual enabled default model_id',
    }
    write(ROOT / 'data' / 'model-selection.json', selection)
    print('Local RAGFlow token verified.')
    print(f'Chat model: {chat.get("model_name")}')
    print(f'Embedding model: {embedding.get("model_name")}')
    print('Model identities saved to data/model-selection.json. Model provider keys were not read.')

if __name__ == '__main__':
    main()
