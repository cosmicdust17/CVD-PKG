"""Synthetic nonmedical fixtures: migration and bibliography regressions."""
import copy
import unittest
from hfkg.core import ROOT, read, validate
from hfkg.relations import RELATION_TYPES
from hfkg.normalize import normalize_bundle
from hfkg.sections import select_body_pages


def fixture():
    evidence = {'id':'long-ev', 'document_id':'long-doc', 'page':1, 'quote':'甲与乙相关。'}
    entities = [
        {'id':'long-e1','name':'甲','type':'risk_factor','aliases':['甲别名'],'evidence_ids':['long-ev']},
        {'id':'long-e2','name':'乙','type':'cardiovascular_disease','aliases':[],'evidence_ids':['long-ev']},
    ]
    relation = {'id':'long-r','source':'long-e1','target':'long-e2','type':'associated_with',
                'directed':False,'evidence_ids':['long-ev']}
    graph = {'metadata':{'schema_version':'1.0','extractor':'RAGFlow','document_id':'long-doc'},
             'entities':entities,'relations':[relation],'evidence':[evidence]}
    detail = {'id':'long-r','source':'甲','source_id':'long-e1','source_type':'risk_factor',
              'target':'乙','target_id':'long-e2','target_type':'cardiovascular_disease',
              'relation':'associated_with','directed':False,'qualifiers':['仅甲类人群'],
              'evidence':[copy.deepcopy(evidence)],'source_candidate_ids':['long-candidate'],
              'evidence_contexts':[{'evidence_ids':['long-ev'],'qualifiers':'仅甲类人群','review_reason':'合成测试'}]}
    return graph, {'metadata':{'relation_type_counts':{'associated_with':1}},'triples':[detail]}


class ShortExportTests(unittest.TestCase):
    def test_relation_vocabulary_matches_both_schemas_and_graph_template(self):
        expected=set(RELATION_TYPES)
        self.assertEqual(expected,{'增加风险','导致','相关'})
        for name in ('graph.schema.json','triples.schema.json'):
            schema=read(ROOT/'schema'/name)
            self.assertEqual(set(schema['$defs']['relation']['properties']['type']['enum']),expected)
        template=read(ROOT/'config/graph-template.json')['templates'][0]['config']
        self.assertEqual({field['type'] for field in template['relation']['fields']},expected)

    def test_migration_preserves_content_and_updates_nested_references(self):
        original, details = fixture()
        untouched = copy.deepcopy((original,details))
        graph,bundle,trace=normalize_bundle(original,details,'D1')
        validate(graph,formal=True)
        self.assertEqual((original,details),untouched)
        self.assertEqual(graph['entities'][0]['aliases'],['甲别名'])
        self.assertEqual(graph['evidence'][0],dict(untouched[0]['evidence'][0],id='D1_EV001',document_id='D1'))
        t=bundle['triples'][0]
        self.assertEqual((t['source'],t['target'],t['id']),('D1_E001','D1_E002','D1_R001'))
        self.assertEqual((t['source_name'],t['target_name'],t['type']),('甲','乙','相关'))
        self.assertEqual(t['source_candidate_ids'],['D1_C001'])
        self.assertEqual(t['evidence_contexts'][0]['evidence_ids'],['D1_EV001'])
        self.assertEqual(t['qualifiers'],['仅甲类人群'])
        self.assertEqual(bundle['metadata']['relation_type_counts'],{'相关':1})
        self.assertEqual(trace['old_to_new']['long-ev'],'D1_EV001')

    def test_documents_have_disjoint_identifiers(self):
        ids=[]
        for prefix in ('D1','D2','D3'):
            graph,_,_=normalize_bundle(*fixture(),prefix)
            ids.extend(x['id'] for k in ('entities','relations','evidence') for x in graph[k])
        self.assertEqual(len(ids),len(set(ids)))

    def test_unknown_relation_rejected_in_formal_export(self):
        graph,details=fixture()
        graph['relations'][0]['type']=details['triples'][0]['relation']='undeclared'
        normalized,_,_=normalize_bundle(graph,details,'D2')
        with self.assertRaises(ValueError):validate(normalized,formal=True)

    def test_bibliography_running_header_does_not_resume_body(self):
        pages=[{'page':1,'text':'2.1 第一章正文\n'+'正文资料。'*10+'\n参考文献\n第一条参考资料。'},
               {'page':2,'text':'第二部分 心血管健康\n参考资料甲。'*10},
               {'page':3,'text':'10.1001/参考DOI\n2.2 下一章正文\n'+'后续章节实质正文。'*10}]
        body,skipped=select_body_pages(pages,{'reference_mode':'chapters'})
        self.assertEqual([p['page'] for p in body],[1,3])
        self.assertNotIn('第一条参考',body[0]['text'])
        self.assertNotIn('参考DOI',body[1]['text'])
        self.assertEqual(skipped[0]['page'],2)


if __name__=='__main__':unittest.main()
