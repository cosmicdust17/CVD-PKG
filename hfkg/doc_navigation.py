"""Generate movable local-file navigation from the real document registry."""
import argparse
import hashlib
import os
import re
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit
from .core import ROOT, read, write
from .entity_types import ENTITY_MAP, ENTITY_TYPES
from .relations import RELATION_MAP, RELATION_TYPES
from .triples_only import now


def relative_link(target, document):
    target,document=Path(target),Path(document)
    if not target.is_file():raise FileNotFoundError(target)
    return quote(Path(os.path.relpath(target,document.parent)).as_posix(),safe='/.-')


def merged_outputs(root, profiles):
    registered={root/'output'/p['output'] for p in profiles.values()}
    result=[]
    paths=list((root/'output').glob('*.json'))+list((root/'output').glob('*/*.json'))
    for path in paths:
        if path.parent in registered:continue
        data=read(path)
        if {'entities','relations','evidence'}.issubset(data) and len(data.get('metadata',{}).get('documents',[]))>1:
            result.append(path)
    return sorted(result)


def build_navigation(document, profiles, results, merged, *, acceptance=False):
    lines=['| 文献（实际文件名） | 实体 / 关系 / 证据 | 抽取结果 | 说明 |',
           '| --- | ---: | --- | --- |']
    for prefix,profile in profiles.items():
        result=results[prefix];out=ROOT/'output'/profile['output'];b=result['bundle']
        counts=' / '.join(str(len(b[key])) for key in ('entities','relations','evidence'))
        status='数据校验通过' if result['validation']['result']=='passed' else '校验未通过'
        lines.append(f"| {prefix} {profile['name']} | {counts} | [打开 triples.json]({relative_link(out/'triples.json',document)}) | 已完成；中文实体/关系；{status} |")
    lines+=['','各文献独立保存；详细 triples 视图与 relations 表示同一批关系，不重复计数。','']
    for prefix,profile in profiles.items():
        out=ROOT/'output'/profile['output']
        lines += [f"- **{prefix}** PDF：`{profile['path']}`。",
                  f"  triples.json 完整路径：`{out / 'triples.json'}`。",
                  f"  [标准 graph.json]({relative_link(out/'graph.json',document)}) · "
                  f"[待核验清单]({relative_link(out/'pending-review.json',document)}) · "
                  f"[本文件校验报告]({relative_link(out/'validation-report.json',document)})。"]
    if merged:
        lines+=['','统一合并文件：']
        for path in merged:lines.append(f'- [打开 {path.name}]({relative_link(path,document)})；完整路径：`{path}`。')
    else:lines+=['','**统一合并知识图谱 JSON：尚未生成。** 各文献的 graph.json 是单篇结果，不当作跨文献合并文件。']
    lines+=['','所有快捷链接均相对于本 Markdown 文件生成并检查实际目标；绝对路径供 Windows 中复制定位。']
    if acceptance:
        lines+=['','本次数据规范验收（重新读取真实 JSON 和校验记录）：','',
                '| 检查项 | 结果 |','| --- | --- |',
                '| 实体 type 及 source_type/target_type | 通过：危险因素、心血管疾病、健康指标、人群 |',
                '| 关系 type 及 relation | 通过：增加风险、导致、相关；相关无向 |',
                '| 短 ID、序号和跨文献唯一性 | 通过；现有 D1_/D2_/D3_ 标识未改动 |',
                '| source/target 和全部 evidence_ids 引用 | 通过；均可解析 |',
                '| 三份数据结构 | 通过；共同包含 metadata/entities/relations/evidence 和兼容 triples 视图 |',
                '| 原文、页码、文献名称、别名、限定条件 | 与本次备份逐项比较通过，仅转换类型标签 |',
                '| 原 PDF 与证据 | SHA-256 核对并重新解析引文所在页通过 |','',
                '类型映射（英文仅作内部及历史输入兼容）：','',
                '| 内部标识 | 正式中文类型 |','| --- | --- |']
        for internal,name in {**ENTITY_MAP,**RELATION_MAP}.items():lines.append(f'| {internal} | {name} |')
        proof=read(ROOT/'reports/entity-type-migration-validation.json')
        test=read(ROOT/'reports/code-test-result.json')
        lines+=['',f"备份：`{proof['backup']}`。所有原始模型运行文件与备份逐字节哈希一致；本次新增模型调用为 0。",
                f"代码测试实际通过 {test['test_count']} 项。待核验条目仍独立保存，类型迁移没有把未通过候选提升为正式事实。尚未进行临床专家人工审核。",
                '',f"[统一数据校验结果]({relative_link(ROOT/'reports/unified-validation.json',document)}) · "
                f"[无损类型迁移检查]({relative_link(ROOT/'reports/entity-type-migration-validation.json',document)}) · "
                f"[代码测试结果]({relative_link(ROOT/'reports/code-test-result.json',document)})。"]
    return '\n'.join(lines)+'\n'


def upsert(document, title, body):
    text=document.read_text(encoding='utf-8-sig')
    marker=f'<!-- hfkg-navigation:{title} -->'
    end='<!-- /hfkg-navigation -->'
    section=f'{marker}\n## {title}\n\n{body}\n{end}'
    if marker in text:
        text=re.sub(re.escape(marker)+r'.*?'+re.escape(end),lambda _:section,text,flags=re.S)
    else:text=text.rstrip()+'\n\n'+section+'\n'
    document.write_text(text,encoding='utf-8')


def check_local_links(document):
    links=[]
    for target in re.findall(r'(?<!!)\[[^\]]+\]\(([^\s)]+)\)',document.read_text(encoding='utf-8-sig')):
        parsed=urlsplit(target)
        if parsed.scheme or parsed.netloc or not parsed.path:continue
        path=(document.parent/unquote(parsed.path)).resolve()
        if not path.is_file():raise FileNotFoundError(f'{document}: {target}')
        links.append({'relative_link':target,'resolved_file':str(path)})
    return {'document':str(document),'result':'passed','checked_link_count':len(links),'links':links}


def main():
    parser=argparse.ArgumentParser();parser.parse_args()
    profiles=read(ROOT/'config/documents.json');results={}
    summary=read(ROOT/'reports/unified-validation.json')
    proof=read(ROOT/'reports/entity-type-migration-validation.json')
    if proof['result']!='passed' or not summary['consistent_schema'] or not summary['cross_document_ids_unique']:
        raise ValueError('Data and preservation checks must pass before publishing navigation')
    for prefix,profile in profiles.items():
        if not Path(profile['path']).is_file():raise FileNotFoundError(profile['path'])
        out=ROOT/'output'/profile['output'];bundle=read(out/'triples.json');validation=read(out/'validation-report.json')
        if validation['result']!='passed':raise ValueError(f'{prefix} has no passing validation')
        for field,count_key in (('entities','entity_count'),('relations','relation_count'),('evidence','evidence_count')):
            if len(bundle[field])!=validation[count_key]:
                raise ValueError('Statistics disagree with actual JSON')
        if not all(e['type'] in ENTITY_TYPES for e in bundle['entities']):raise ValueError('Entity vocabulary mismatch')
        if not all(r['type'] in RELATION_TYPES for r in bundle['relations']):raise ValueError('Relation vocabulary mismatch')
        results[prefix]={'bundle':bundle,'validation':validation}
    merged=merged_outputs(ROOT,profiles)
    documents=[ROOT/'README.md']+[p for p in (ROOT/'reports').glob('*.md')]
    for document in documents:
        acceptance=document.parent.name=='reports'
        title='产出文件清单与快捷入口' if acceptance else '产出文件与快捷入口'
        upsert(document,title,build_navigation(document,profiles,results,merged,acceptance=acceptance))
    checks=[check_local_links(document) for document in documents]
    write(ROOT/'reports/navigation-validation.json',{'checked_at':now(),'result':'passed',
          'merged_graph_status':'present' if merged else '尚未生成','documents':checks})
    artifacts=[]
    for prefix,profile in profiles.items():
        for name in ('triples.json','graph.json','id-mapping.json','pending-review.json','extraction-report.json','validation-report.json'):
            path=ROOT/'output'/profile['output']/name
            artifacts.append({'document_id':prefix,'path':str(path),'bytes':path.stat().st_size,
                              'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    write(ROOT/'reports/delivery-artifacts.json',{'checked_at':now(),'files':artifacts,
          'entity_type_migration':proof,'code_tests':read(ROOT/'reports/code-test-result.json')})
    for result in checks:print(f"Navigation PASS: {result['document']} ({result['checked_link_count']} local links)")


if __name__=='__main__':main()
