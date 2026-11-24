"""RAGFlow document retrieval and the existing local PDF audit corpus."""
import json
import logging
import os
import re
from functools import lru_cache
from time import monotonic
from urllib.parse import urlsplit

import requests

from .health_graph import ROOT, index, normalize, ordered

LOG = logging.getLogger(__name__)


def setting(name, default=""):
    return os.getenv(name, default).strip()


def local_api(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("本地服务地址必须使用回环接口")
    return url.rstrip("/")


@lru_cache(maxsize=1)
def documents():
    return json.loads((ROOT / "config/documents.json").read_text(encoding="utf-8-sig"))


def evidence_terms(question, entities):
    terms, _ = index().match(question)
    names = [index().nodes[node]["name"] for term in entities for node in index().resolve(term)]
    extra = re.findall(r"减盐|限盐|钠盐|低盐|血压|规律运动|有氧运动|运动|身体活动|体力活动|久坐|规律睡眠|睡眠|作息|戒烟|吸烟|烟草|一级预防|生活方式", question)
    return ordered(normalize(term) for term in [*terms, *extra, *names])[:16]


def title_for(quote, terms):
    first = next((term for term in terms if 2 <= len(term) <= 8 and term in normalize(quote)), None)
    if first:
        return first
    match = re.search(r"[\u3400-\u9fff]{2,8}", quote)
    return match.group() if match else "文献摘录"


@lru_cache(maxsize=128)
def rag_chunks(question, time_bucket):
    del time_bucket
    ids = [value.strip() for value in setting("RAGFLOW_DATASET_IDS").split(",") if value.strip()]
    token = setting("RAGFLOW_API_KEY")
    if not ids or not token:
        return [], "未配置 RAGFlow 知识库或访问令牌"
    started = monotonic()
    try:
        with requests.Session() as session:
            session.trust_env = False
            response = session.post(
                local_api(setting("RAGFLOW_BASE_URL", "http://127.0.0.1:19380")) + "/api/v1/retrieval",
                headers={"Authorization": "Bearer " + token},
                json={"question": question, "dataset_ids": ids, "page_size": 6,
                      "similarity_threshold": 0.25, "highlight": False,
                      "include_knowledge_compilation": False},
                timeout=(3, float(setting("RAGFLOW_TIMEOUT", "12"))), allow_redirects=False,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("code") != 0:
                raise ValueError("RAGFlow rejected retrieval")
            chunks = data["data"]["chunks"]
            if not isinstance(chunks, list):
                raise ValueError("Unexpected chunk data")
        return chunks, "RAGFlow 检索完成" if chunks else "RAGFlow 未检索到相关证据"
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as exc:
        LOG.warning("RAGFlow retrieval failed (%s)", type(exc).__name__)
        return [], "RAGFlow 暂不可用"
    finally:
        LOG.info("RAGFlow retrieval %.1f ms", (monotonic() - started) * 1000)


@lru_cache(maxsize=1)
def local_passages():
    rows = []
    for document_id, document in documents().items():
        base = ROOT / "data/pdf-audit" / ("DOC_" + document["sha256"].upper())
        source = ROOT / "output" / document["output"] / "triples.json"
        try:
            pages = json.loads((base / "pages.json").read_text(encoding="utf-8-sig"))
            included = set(json.loads(source.read_text(encoding="utf-8-sig"))["metadata"]["processed_body_pages"])
        except (OSError, ValueError, KeyError):
            LOG.warning("Local PDF audit unavailable for %s", document_id)
            continue
        for page in pages:
            if page["page"] not in included:
                continue
            for number, clause in enumerate(re.finditer(r"[^。！？]{15,700}[。！？]?", page["text"]), start=1):
                text = clause.group().strip()
                if len(text) >= 24:
                    rows.append((document_id, page["page"], number, text, normalize(text)))
    return rows


CONCEPTS = {
    "salt": ("减盐", "限盐", "低盐", "高盐", "高钠", "钠盐", "食盐", "烹调用盐", "盐摄入", "钠摄入"),
    "pressure": ("高血压", "血压", "收缩压", "舒张压"),
    "exercise": ("身体活动", "体力活动", "有氧运动", "运动", "久坐"),
    "sleep": ("规律作息", "睡眠时间", "睡眠时长", "入睡", "睡眠", "作息"),
    "smoking": ("吸烟", "戒烟", "烟草", "二手烟"),
    "cvd": ("心血管病", "心血管疾病", "ascvd", "心脏代谢"),
}
ACTION = ("有助", "推荐", "建议", "选择", "应当", "可降低", "能够降低", "可减少", "保持")
DEFINITION = re.compile(r"高血压[的]?定义|高血压是指|诊室血压.{0,30}(诊断|界值)|高血压.{0,12}诊断标准")


@lru_cache(maxsize=128)
def local_search(terms, question):
    question = normalize(question)
    definition = bool(re.search(r"^什么是|是什么[?。]?$|^定义", question))
    prevention = any(word in question for word in ("预防", "改善", "减少", "规律", "戒烟"))
    groups = [values for values in CONCEPTS.values()
              if any(term in question for term in values)]
    covered = {term for values in groups for term in values}
    groups.extend((term,) for term in terms if len(term) >= 2 and term not in covered
                  and not any(word in term for word in covered) and term != "生活方式")
    if not groups:
        return []

    def score(text):
        hits = [group for group in groups if any(term in text for term in group)]
        if not hits or (groups[0] not in hits and len(groups) > 1):
            return 0
        weight = 5 * len(hits)
        if definition:
            if not DEFINITION.search(text) or re.search(r"随机抽样|未考虑2周|调查年份", text):
                return 0
            weight += 8
        if prevention and any(word in text for word in ACTION):
            weight += 3
        if "生活方式" in question and "生活方式" in text and any(word in text for word in ACTION):
            weight += 6
        if "【关键词】" in text or "制定的方法学" in text or len(text) > 480:
            weight -= 4
        return weight

    ranked = []
    for row in index().evidence.values():
        quote = row["quote"] or ""
        weight = score(normalize(quote))
        if weight >= 2:
            ranked.append((weight + 2, len(quote), dict(
                id=row["id"], document_id=row["documentId"], document_name=row["documentName"],
                page=row["page"], quote=quote, chunk_id=row["originalEvidenceId"],
                source="图谱已核验引文", relevance=None,
            )))
    for document_id, page, number, quote, normalized in local_passages():
        weight = score(normalized)
        if weight >= 2:
            identifier = f"{document_id}:p{page}:s{number}"
            ranked.append((weight, len(quote), dict(
                id=identifier, document_id=document_id, document_name=documents()[document_id]["name"],
                page=page, quote=quote, chunk_id=identifier, source="本地 PDF 原文", relevance=None,
            )))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    results = []
    seen = set()
    per_page = {}
    for _, _, row in ranked:
        normalized = normalize(row["quote"]).strip("。！？.!?")
        key = (row["document_id"], row["page"])
        if normalized in seen or per_page.get(key, 0) >= 2:
            continue
        seen.add(normalized)
        per_page[key] = per_page.get(key, 0) + 1
        results.append(row)
        if len(results) == 6:
            break
    return results


def retrieve(question, entities=()):
    terms = evidence_terms(question, entities)
    canonical = [index().nodes[node]["name"] for term in entities for node in index().resolve(term)]
    query = " ".join(ordered([question, *canonical]))
    chunks, status = rag_chunks(query, int(monotonic() // 120))
    items = []
    sources = {row["name"]: ident for ident, row in documents().items()}
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        text, chunk_id = chunk.get("content"), chunk.get("id")
        if not isinstance(text, str) or not text.strip() or not isinstance(chunk_id, str) or not chunk_id:
            continue
        name = chunk.get("document_keyword") or chunk.get("docnm_kwd") or None
        if not isinstance(name, str):
            name = None
        positions = chunk.get("positions")
        # RAGFlow rc2 stores PDF positions as [one-based page, x0, x1, top, bottom].
        pdf_pages = [p[0] for p in positions if isinstance(p, list) and len(p) == 5
                     and type(p[0]) is int and p[0] > 0] if (
            isinstance(positions, list) and name and name.lower().endswith(".pdf")
        ) else []
        page = chunk.get("page") or min(pdf_pages, default=None)
        items.append(dict(id=f"rag:{chunk_id}", document_id=sources.get(name),
                          ragflow_document_id=chunk.get("document_id"), dataset_id=chunk.get("dataset_id"),
                          document_name=name, page=page if type(page) is int and page > 0 else None,
                          quote=text, chunk_id=chunk_id, source="RAGFlow", relevance=chunk["similarity"] if type(chunk.get("similarity")) in (int, float) else None))
    if not items and chunks:
        status = "RAGFlow 未返回可追溯的原文片段"
    if not items and terms and setting("HF_LOCAL_EVIDENCE", "1") == "1":
        items = local_search(tuple(terms), question)
        if items:
            status += "，已展示本地文献证据"
    return [dict(item, title=title_for(item["quote"], terms)) for item in items], status


def link_evidence(items, graph):
    linked = []
    for item in items:
        quote = normalize(item["quote"])
        nodes = [node for node in graph["nodes"] if item["id"] in node["evidenceIds"]
                 or normalize(node["name"]) in quote]
        matched_evidence = {item["id"]}
        if item.get("document_id"):
            matched_evidence.update(row["id"] for row in index().evidence.values()
                                    if row["documentId"] == item["document_id"] and row["quote"]
                                    and normalize(row["quote"]) in quote)
        edges = [edge for edge in graph["edges"] if matched_evidence.intersection(edge["evidenceIds"])]
        linked.append(dict(item, node_ids=[node["id"] for node in nodes],
                           edge_ids=[edge["id"] for edge in edges]))
    return linked
