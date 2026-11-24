"""Keep chapter body text while excluding reference lists without losing chapters."""
import re

REF = re.compile(r'^\s*参\s*考\s*文\s*献\s*$')
HEADING = re.compile(r'^\s*[1-5]\.\d{1,2}(?:\.\d{1,2}){0,3}\s*[\u4e00-\u9fff]')

def select_body_pages(pages, profile):
    body, skipped, in_references = [], [], False
    for page in pages:
        excluded = next((r[2] for r in profile.get('exclude_ranges', []) if r[0] <= page['page'] <= r[1]), None)
        if excluded:
            skipped.append({'page': page['page'], 'reason': excluded})
            continue
        kept = []
        for line in page['text'].splitlines(keepends=True):
            if REF.fullmatch(line.strip()):
                in_references = True
                continue
            if in_references and profile['reference_mode'] == 'chapters' and HEADING.match(line):
                in_references = False
            if not in_references:
                kept.append(line)
        text = ''.join(kept)
        # Running headers on an otherwise reference-only page are not content.
        meaningful = re.sub(r'中国协和医科大学出版社|中国心血管健康与疾病报告\s*2024|\s|\d', '', text)
        if len(meaningful) < 20:
            skipped.append({'page': page['page'], 'reason': '参考文献页或无实质正文（源文本保留在页码索引）'})
        else:
            body.append({'page': page['page'], 'text': text})
    return body, skipped
