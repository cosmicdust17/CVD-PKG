"""Canonical Chinese exports; legacy English identifiers are input aliases only."""
import json
from pathlib import Path

CONFIG = json.loads((Path(__file__).resolve().parents[1] / 'config' / 'relations.json').read_text(encoding='utf-8-sig'))
RELATION_MAP = {row['internal']: row['name'] for row in CONFIG['relations']}
RELATION_TYPES = tuple(row['name'] for row in CONFIG['relations'])

def normalize_relation(value):
    if value in RELATION_TYPES:
        return value
    return RELATION_MAP.get(value, value)

def is_directed(value):
    value = normalize_relation(value)
    if value not in RELATION_TYPES:
        raise ValueError(f'Undefined relation type: {value}')
    return value != '相关'
