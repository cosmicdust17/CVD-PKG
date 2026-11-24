"""Build the local G6 dataset from the three accepted RAGFlow exports."""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
import unicodedata


PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES = [
    PROJECT.parent / "output" / directory / "triples.json"
    for directory in (
        "primary-prevention-triples",
        "cardiovascular-report-2024-triples",
        "healthy-lifestyle-triples",
    )
]


def normalize(value):
    if not isinstance(value, str):
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).split())


def extend_unique(values, additions):
    values.extend(value for value in additions if value not in values)


def build(paths):
    documents, evidence = {}, {}
    nodes, edges = {}, {}
    raw_ids = {key: Counter() for key in ("entities", "relations", "evidence")}
    document_reports = []
    raw_counts = Counter()

    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict) or not isinstance(data.get("metadata"), dict):
            raise ValueError(f"{path}: 缺少 metadata 对象")
        metadata = data["metadata"]
        document_id = normalize(metadata.get("document_id"))
        if not document_id or document_id in documents or ":" in document_id:
            raise ValueError(f"{path}: 文献 ID 缺失、重复或含保留字符")

        descriptions = metadata.get("documents", [])
        description = next(
            (d for d in descriptions if isinstance(d, dict) and d.get("document_id") == document_id),
            {},
        ) if isinstance(descriptions, list) else {}
        document_name = description.get("name")
        if not isinstance(document_name, str) or not document_name.strip():
            document_name = None
        documents[document_id] = {"id": document_id, "name": document_name}

        anomalies = Counter()
        counts = {}
        rows_by_kind = {}
        for kind in raw_ids:
            rows = data.get(kind)
            if not isinstance(rows, list):
                raise ValueError(f"{path}: {kind} 必须是数组")
            counts[kind] = len(rows)
            rows_by_kind[kind] = {}
            for row in rows:
                oid = row.get("id") if isinstance(row, dict) else None
                if not isinstance(oid, str) or not oid.strip():
                    anomalies[f"invalid_{kind}_row_or_id"] += 1
                    continue
                if oid in rows_by_kind[kind]:
                    raise ValueError(f"{path}: {kind} 重复 ID {oid}，无法确定引用目标")
                rows_by_kind[kind][oid] = row
                raw_ids[kind][oid] += 1
        raw_counts.update(counts)

        evidence_map = {}
        for oid, row in rows_by_kind["evidence"].items():
            if row.get("document_id", document_id) != document_id:
                raise ValueError(f"{path}: 证据 {oid} 声明的文献 ID 与当前文献不一致")
            evidence_id = f"{document_id}:{oid}"
            evidence_map[oid] = evidence_id
            page, quote = row.get("page"), row.get("quote")
            if type(page) is not int or page < 1:
                page = None
                anomalies["missing_or_invalid_page"] += 1
            if not isinstance(quote, str) or not quote.strip():
                quote = None
                anomalies["missing_or_invalid_quote"] += 1
            evidence[evidence_id] = dict(
                id=evidence_id, documentId=document_id, documentName=document_name,
                page=page, quote=quote, originalEvidenceId=oid,
            )

        def resolve_evidence(ids):
            if not isinstance(ids, list):
                anomalies["invalid_evidence_reference_list"] += 1
                return []
            valid = []
            for oid in ids:
                if isinstance(oid, str) and oid in evidence_map:
                    extend_unique(valid, [evidence_map[oid]])
                else:
                    anomalies["unresolved_evidence_reference"] += 1
            return valid

        entity_map = {}
        for oid, row in rows_by_kind["entities"].items():
            original_name = row.get("name")
            name = normalize(original_name)
            entity_type = normalize(row.get("type"))
            if not name or not re.search(r"[\u3400-\u9fff]", entity_type):
                anomalies["invalid_entity_name_or_type"] += 1
                continue
            key = name, entity_type
            if key not in nodes:
                nodes[key] = dict(
                    id=f"N{len(nodes) + 1:04}", name=name, entityType=entity_type,
                    aliases=[], sourceEntityIds=[], sourceDocumentIds=[], evidenceIds=[],
                    sourceEntities=[],
                )
            node = nodes[key]
            entity_map[oid] = node["id"]
            aliases = row.get("aliases", [])
            if not isinstance(aliases, list):
                anomalies["invalid_alias_list"] += 1
                aliases = []
            extend_unique(node["aliases"], [
                alias.strip() for alias in aliases
                if isinstance(alias, str) and normalize(alias) and normalize(alias) != name
            ])
            ids = resolve_evidence(row.get("evidence_ids", []))
            extend_unique(node["sourceEntityIds"], [oid])
            extend_unique(node["sourceDocumentIds"], [document_id])
            extend_unique(node["evidenceIds"], ids)
            node["sourceEntities"].append(dict(
                id=oid, documentId=document_id, name=original_name, evidenceIds=ids,
            ))

        for oid, row in rows_by_kind["relations"].items():
            src, dst = row.get("source"), row.get("target")
            if not all(isinstance(ref, str) and ref in entity_map for ref in (src, dst)):
                anomalies["unresolved_relation_endpoint"] += 1
                continue
            source, target = entity_map[src], entity_map[dst]
            relation_type = normalize(row.get("type"))
            directed = row.get("directed")
            if not re.search(r"[\u3400-\u9fff]", relation_type) or type(directed) is not bool:
                anomalies["invalid_relation_type_or_direction"] += 1
                continue
            key = source, target, relation_type, directed
            if key not in edges:
                edges[key] = dict(
                    id=f"R{len(edges) + 1:04}", source=source, target=target,
                    relationType=relation_type, label=relation_type, directed=directed,
                    sourceRelationIds=[], sourceDocumentIds=[], evidenceIds=[], sourceRelations=[],
                )
            edge = edges[key]
            ids = resolve_evidence(row.get("evidence_ids", []))
            contexts = []
            raw_contexts = row.get("evidence_contexts", [])
            if not isinstance(raw_contexts, list):
                anomalies["invalid_evidence_context"] += 1
                raw_contexts = []
            for context in raw_contexts:
                if not isinstance(context, dict):
                    anomalies["invalid_evidence_context"] += 1
                    continue
                context_ids = resolve_evidence(context.get("evidence_ids", []))
                extend_unique(ids, context_ids)
                qualifier = context.get("qualifiers")
                contexts.append(dict(
                    evidenceIds=context_ids,
                    qualifier=qualifier if isinstance(qualifier, str) and qualifier.strip() else None,
                ))
            extend_unique(edge["sourceRelationIds"], [oid])
            extend_unique(edge["sourceDocumentIds"], [document_id])
            extend_unique(edge["evidenceIds"], ids)
            qualifiers = row.get("qualifiers")
            edge["sourceRelations"].append(dict(
                id=oid, documentId=document_id, evidenceIds=ids, evidenceContexts=contexts,
                qualifiers=[q for q in qualifiers if isinstance(q, str) and q.strip()]
                if isinstance(qualifiers, list) else [],
            ))

        document_reports.append(dict(
            documentId=document_id, documentName=document_name, path=str(path.resolve()),
            original=counts, anomalies=dict(anomalies), anomalyCount=sum(anomalies.values()),
        ))

    graph = dict(
        metadata=dict(
            name="心血管疾病预防知识图谱", documentCount=len(documents),
            entityCount=len(nodes), relationCount=len(edges),
        ),
        documents=list(documents.values()), nodes=list(nodes.values()),
        edges=list(edges.values()), evidence=list(evidence.values()),
    )
    node_ids = {node["id"] for node in nodes.values()}
    all_ids = [item["id"] for kind in ("nodes", "edges", "evidence") for item in graph[kind]]
    items = [*graph["nodes"], *graph["edges"]]
    validation = dict(
        duplicateGlobalIds=len(all_ids) - len(set(all_ids)),
        duplicateNodeKeys=len(graph["nodes"]) - len(nodes),
        duplicateEdgeKeys=len(graph["edges"]) - len(edges),
        danglingEdges=sum(edge["source"] not in node_ids or edge["target"] not in node_ids
                          for edge in edges.values()),
        danglingEvidenceReferences=sum(ev_id not in evidence for item in items
                                       for ev_id in item["evidenceIds"]),
    )
    if any(validation.values()):
        raise ValueError(f"生成数据存在无效引用或重复项: {validation}")
    merged = dict(entities=len(nodes), relations=len(edges), evidence=len(evidence))
    report = dict(
        documents=document_reports, original=dict(raw_counts), merged=merged,
        mergedEntityRecords=sum(len(n["sourceEntities"]) - 1 for n in nodes.values()),
        mergedRelationRecords=sum(len(e["sourceRelations"]) - 1 for e in edges.values()),
        crossDocumentEntityCount=sum(len(n["sourceDocumentIds"]) > 1 for n in nodes.values()),
        crossDocumentRelationCount=sum(len(e["sourceDocumentIds"]) > 1 for e in edges.values()),
        crossDocumentOriginalIdCollisions={
            kind: sorted(oid for oid, count in ids.items() if count > 1)
            for kind, ids in raw_ids.items()
        },
        entityTypeCounts=dict(Counter(n["entityType"] for n in nodes.values())),
        relationTypeCounts=dict(Counter(e["relationType"] for e in edges.values())),
        anomalyCount=sum(d["anomalyCount"] for d in document_reports),
        validation=validation,
    )
    return graph, report


def write_json(path, value):
    with NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
    ) as output:
        temporary_path = Path(output.name)
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write("\n")
    temporary_path.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path, nargs="*", help="按顺序指定三份正式 triples.json")
    parser.add_argument("--output-dir", type=Path, default=PROJECT / "public" / "data")
    args = parser.parse_args()
    sources = args.inputs or DEFAULT_SOURCES
    if len(sources) != 3:
        parser.error("需要三份 triples.json")
    try:
        graph, report = build(sources)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        write_json(args.output_dir / "graph-data.json", graph)
        write_json(args.output_dir / "build-report.json", report)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(f"{graph['metadata']}  evidence={len(graph['evidence'])}  anomalies={report['anomalyCount']}")


if __name__ == "__main__":
    main()
