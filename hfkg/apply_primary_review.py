"""Materialize a review plan bound to this completed, actually inspected run."""
from .core import ROOT, read, write

def main():
    out = ROOT / 'output' / 'primary-prevention-triples'
    candidates = read(out / 'candidates.json')
    plan = read(ROOT / 'config' / 'primary-guideline-review-plan.json')
    if plan['run_fingerprint'] != candidates['metadata']['fingerprint']:
        raise ValueError('The reviewed run fingerprint differs; do not reuse page-index decisions')
    decisions = []
    for page in candidates['pages']:
        for i, candidate in enumerate(page['triples']):
            approved = i in plan['approved_page_indices'].get(str(page['page']), [])
            corrections = plan['corrections'].get(f'{page["page"]}:{i}', {})
            reason = '逐条核对本次真实模型候选与PDF原文，证据支持该关系；保留人群、剂量和条件，不将风险或相关改为因果。'
            if corrections:
                reason += '已按原文修正范围/术语/关系强度，具体变更另行保存。'
            if not approved:
                reason = plan['page_pending_reasons'].get(str(page['page']), '尚未通过语义与范围核验，保留候选待核验。')
            decisions.append({'candidate_id': candidate['candidate_id'], 'approved': approved,
                              'reason': reason, 'corrections': corrections})
    write(out / 'review-decisions.json', {'run_fingerprint': plan['run_fingerprint'],
          'review_method': plan['review_method'], 'aliases': plan['aliases'], 'decisions': decisions})
    print(f'{len(decisions)} content-bound decisions saved; {sum(d["approved"] for d in decisions)} accepted candidates')

if __name__ == '__main__':
    main()
