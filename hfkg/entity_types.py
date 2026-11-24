"""Chinese output vocabulary; English identifiers are legacy input aliases."""
import json
from pathlib import Path

CONFIG = json.loads((Path(__file__).resolve().parents[1] / 'config/entity-types.json').read_text(encoding='utf-8-sig'))
ENTITY_MAP = {row['internal']: row['name'] for row in CONFIG['types']}
ENTITY_TYPES = tuple(row['name'] for row in CONFIG['types'])


def normalize_entity_type(value):
    return ENTITY_MAP.get(value, value) if isinstance(value, str) else value


def normalize_alias_map(aliases):
    result = {}
    for typ, mapping in aliases.items():
        target = result.setdefault(normalize_entity_type(typ), {})
        for alias, name in mapping.items():
            if alias in target and target[alias] != name:
                raise ValueError('Conflicting bilingual entity alias definitions')
            target[alias] = name
    return result


def translate_entity_fields(value):
    """Translate type fields/count keys only; never touch names or evidence text."""
    if isinstance(value, list):
        return [translate_entity_fields(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key in ('type', 'source_type', 'target_type', 'entity_type') and isinstance(item, str):
            result[key] = normalize_entity_type(item)
        elif key == 'entity_type_counts' and isinstance(item, dict):
            counts = {}
            for typ, count in item.items():
                name = normalize_entity_type(typ)
                counts[name] = counts.get(name, 0) + count
            result[key] = counts
        elif key == 'aliases' and isinstance(item, dict):
            result[key] = normalize_alias_map(item)
        else:
            result[key] = translate_entity_fields(item)
    return result
