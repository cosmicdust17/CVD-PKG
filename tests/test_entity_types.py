"""Synthetic type-migration checks; no medical model calls or extraction data."""
import copy
import unittest
from hfkg.core import ROOT, read, canonical, validate
from hfkg.entity_types import ENTITY_MAP, ENTITY_TYPES, translate_entity_fields, normalize_alias_map
from hfkg.triples_only import RULES, sanitize_result
from hfkg.review_candidates import REVIEW_PROMPT
from hfkg.normalize import normalize_bundle
from test_short_exports import fixture


class ChineseEntityTypeTests(unittest.TestCase):
    def test_all_four_definitions_match_schema_template_and_prompts(self):
        expected={'危险因素','心血管疾病','健康指标','人群'}
        self.assertEqual(set(ENTITY_TYPES),expected)
        self.assertEqual(len(ENTITY_MAP),4)
        for name in ('graph.schema.json','triples.schema.json'):
            schema=read(ROOT/'schema'/name)
            self.assertEqual(set(schema['$defs']['entity']['properties']['type']['enum']),expected)
        props=read(ROOT/'schema/triples.schema.json')['properties']['triples']['items']['properties']
        for key in ('source_type','target_type'):
            self.assertEqual(set(props[key]['enum']),expected)
        template=read(ROOT/'config/graph-template.json')['templates'][0]['config']
        self.assertEqual({f['type'] for f in template['entity']['fields']},expected)
        for prompt in (RULES,REVIEW_PROMPT):
            for name in expected:self.assertIn(name,prompt)
            for internal in ENTITY_MAP:self.assertNotIn(internal,prompt)

    def test_type_translation_preserves_names_quotes_and_identifiers(self):
        value={'entities':[{'id':'D1_E001','name':'risk_factor','type':'risk_factor','aliases':['risk_factor']}],
               'source_type':'population_group','target_type':'health_indicator',
               'evidence':[{'id':'D1_EV001','page':2,'quote':'risk_factor 只是原文字符。'}],
               'entity_type_counts':{'risk_factor':1}}
        original=copy.deepcopy(value);result=translate_entity_fields(value)
        self.assertEqual(value,original)
        self.assertEqual(result['entities'][0],dict(original['entities'][0],type='危险因素'))
        self.assertEqual(result['evidence'],original['evidence'])
        self.assertEqual((result['source_type'],result['target_type']),('人群','健康指标'))
        self.assertEqual(result['entity_type_counts'],{'危险因素':1})
        self.assertEqual(translate_entity_fields(result),result)

    def test_migration_outputs_chinese_head_tail_types(self):
        graph,bundle,_=normalize_bundle(*fixture(),'D1')
        validate(graph,formal=True)
        self.assertEqual({e['type'] for e in graph['entities']},{'危险因素','心血管疾病'})
        t=bundle['triples'][0]
        self.assertEqual((t['source_type'],t['target_type']),('危险因素','心血管疾病'))

    def test_english_and_unknown_entity_types_rejected_by_formal_schema(self):
        graph,_,_=normalize_bundle(*fixture(),'D1')
        for invalid in ('risk_factor','prevention_measure'):
            bad=copy.deepcopy(graph);bad['entities'][0]['type']=invalid
            with self.assertRaises(ValueError):validate(bad,formal=True)

    def test_legacy_model_input_is_normalized_for_both_endpoints(self):
        ev=[{'page':1,'quote':'甲与乙相关。'}]
        raw={'entities':[{'name':'甲','type':'risk_factor','aliases':[],'evidence':ev}],
             'triples':[{'source':{'name':'甲','type':'risk_factor'},'target':{'name':'乙','type':'cardiovascular_disease'},
                         'relation':'相关','evidence':ev,'qualifiers':'','direction':'undirected'}],'pending_review':[]}
        result=sanitize_result(raw,1,{1:'甲与乙相关。'},{1},'SYNTHETIC_DOC')
        self.assertEqual(result['entities'][0]['type'],'危险因素')
        self.assertEqual(result['triples'][0]['source']['type'],'危险因素')
        self.assertEqual(result['triples'][0]['target']['type'],'心血管疾病')

    def test_legacy_alias_keys_work_without_silent_conflicts(self):
        self.assertEqual(canonical('甲','危险因素',{'risk_factor':{'甲':'乙'}}),'乙')
        with self.assertRaisesRegex(ValueError,'Conflicting'):
            normalize_alias_map({'risk_factor':{'甲':'乙'},'危险因素':{'甲':'丙'}})


if __name__=='__main__':unittest.main()
