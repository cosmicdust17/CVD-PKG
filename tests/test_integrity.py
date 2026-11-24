"""Synthetic fixtures only. These tests are never medical extraction results."""
import copy
import unittest
from hfkg.core import canonical, convert, g6, merge, validate

DOC = {'document_id': 'TEST_DOC_A', 'name': 'SYNTHETIC_TEST_ONLY', 'sha256': 'a' * 64}
QUOTE = '甲因素与乙结局相关。'
PAGES = [{'page': 1, 'text': QUOTE}]

def rows(rel_type='associated_with'):
    evidence = [{'quote': QUOTE, 'chunk_id': 'test-chunk'}]
    return [
        {'id': 'test-e1', 'knowledge_graph_kwd': 'entity', 'content_with_weight': {
            'name': '甲因素', 'type': 'risk_factor', 'aliases': [], 'evidence': evidence}},
        {'id': 'test-e2', 'knowledge_graph_kwd': 'entity', 'content_with_weight': {
            'name': '乙结局', 'type': 'cardiovascular_disease', 'aliases': [], 'evidence': evidence}},
        {'id': 'test-r1', 'knowledge_graph_kwd': 'relation', 'content_with_weight': {
            'source': '甲因素', 'target': '乙结局', 'type': rel_type, 'evidence': evidence}},
    ]

def approved(rel_type='associated_with', doc=None, extra=None):
    raw = rows(rel_type)
    _, review = convert(raw, PAGES, doc or DOC)
    decision = {'approved': True, 'reviewer': 'SYNTHETIC TEST', 'rationale': 'Test validator branches only',
                'direction_confirmed': True, 'explicit_causality_confirmed': True}
    decision.update(extra or {})
    return convert(raw, PAGES, doc or DOC, {review['candidates'][0]['candidate_id']: decision})[0]

class IntegrityTests(unittest.TestCase):
    def test_alias_chain_resolves_and_cycle_rejected(self):
        self.assertEqual(canonical('A', 'risk_factor', {'risk_factor': {'A': 'B', 'B': 'C'}}), 'C')
        with self.assertRaisesRegex(ValueError, 'cycle'):
            canonical('A', 'risk_factor', {'risk_factor': {'A': 'B', 'B': 'A'}})

    def test_pending_is_excluded(self):
        graph, review = convert(rows(), PAGES, DOC)
        self.assertEqual(len(graph['entities']), 2)
        self.assertEqual(graph['relations'], [])
        self.assertEqual(len(review['candidates']), 1)

    def test_causality_requires_explicit_review(self):
        graph = approved('causes', extra={'explicit_causality_confirmed': False})
        self.assertEqual(graph['relations'], [])

    def test_risk_direction_requires_confirmation(self):
        self.assertEqual(approved('increases_risk_of', extra={'direction_confirmed': False})['relations'], [])

    def test_unverifiable_quote_is_pending(self):
        graph, review = convert(rows(), [{'page': 1, 'text': '无关原文'}], DOC)
        self.assertFalse(graph['entities'])
        self.assertTrue(all(x['page'] is None and x['quote'] is None for x in review['evidence']))

    def test_repeated_quote_has_no_invented_page(self):
        graph, review = convert(rows(), PAGES + [{'page': 2, 'text': QUOTE}], DOC)
        self.assertFalse(graph['entities'])
        self.assertTrue(all(x['page'] is None for x in review['evidence']))

    def test_unknown_entity_type_quarantined(self):
        raw = rows()
        raw[0]['content_with_weight']['type'] = 'prevention_measure'
        graph, review = convert(raw, PAGES, DOC)
        self.assertEqual(len(graph['entities']), 1)
        self.assertIn('undefined_entity_type_or_name', [x['reason'] for x in review['issues']])

    def test_unknown_relation_type_quarantined(self):
        graph, review = convert(rows('treats'), PAGES, DOC)
        self.assertEqual(graph['relations'], [])
        self.assertEqual(review['candidates'][0]['reason'], 'undefined_relation_type_or_endpoints')

    def test_dangling_endpoint_rejected(self):
        graph = approved()
        graph['relations'][0]['source'] = 'NONEXISTENT'
        with self.assertRaisesRegex(ValueError, 'Dangling entity'):
            validate(graph)

    def test_null_evidence_rejected_from_formal_graph(self):
        graph = approved()
        graph['evidence'][0]['page'] = None
        with self.assertRaisesRegex(ValueError, 'Unverifiable'):
            validate(graph, formal=True)

    def test_null_evidence_requires_pending_label(self):
        graph = approved()
        graph['evidence'][0]['page'] = None
        with self.assertRaisesRegex(ValueError, 'pending_review'):
            validate(graph)
        graph['metadata']['status'] = 'pending_review'
        self.assertTrue(validate(graph))

    def test_page_outside_pdf_rejected(self):
        graph = approved(doc=dict(DOC, page_count=1))
        graph['evidence'][0]['page'] = 2
        with self.assertRaisesRegex(ValueError, 'outside'):
            validate(graph)

    def test_multiple_relation_types_preserved(self):
        merged = merge([approved('associated_with'), approved('increases_risk_of')])
        self.assertEqual(len(merged['relations']), 2)
        self.assertEqual(len(merged['entities']), 2)

    def test_cross_document_evidence_preserved(self):
        other = dict(DOC, document_id='TEST_DOC_B', sha256='b' * 64)
        merged = merge([approved(), approved(doc=other)])
        self.assertEqual(len(merged['entities']), 2)
        self.assertEqual(len(merged['relations']), 1)
        self.assertEqual(len(merged['relations'][0]['evidence_ids']), 2)
        self.assertEqual({x['document_id'] for x in merged['evidence']}, {'TEST_DOC_A', 'TEST_DOC_B'})

    def test_association_is_undirected_in_g6(self):
        edge = g6(approved())['edges'][0]
        self.assertFalse(edge['data']['directed'])
        self.assertFalse(edge['style']['endArrow'])

    def test_duplicate_ids_rejected(self):
        graph = approved()
        graph['entities'].append(copy.deepcopy(graph['entities'][0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate IDs'):
            validate(graph)

    def test_document_collision_rejected(self):
        other = approved(doc=dict(DOC, sha256='b' * 64))
        with self.assertRaisesRegex(ValueError, 'Document ID collision'):
            merge([approved(), other])

    def test_reverse_symmetric_relation_deduplicated(self):
        first = approved()
        second = copy.deepcopy(first)
        rel = second['relations'][0]
        rel['source'], rel['target'] = rel['target'], rel['source']
        self.assertEqual(len(merge([first, second])['relations']), 1)

if __name__ == '__main__':
    unittest.main()
