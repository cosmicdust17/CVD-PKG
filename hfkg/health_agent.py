"""Finite LangGraph workflow with one shared local Qwen service."""
import json
import logging
import re
from threading import Lock
from time import monotonic
from typing import TypedDict

import requests
from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context

from .health_evidence import link_evidence, local_api, retrieve, setting
from .health_graph import TOPICS, index, normalize, ordered

LOG = logging.getLogger(__name__)
MODEL_LOCK = Lock()
EMPTY = dict(nodes=[], edges=[], paths=[], matched_entities=[], missing_entities=[])
URGENT = re.compile(r"胸痛|胸口痛|胸部疼痛|胸闷|呼吸困难|喘不上气|晕厥")
EDUCATIONAL = re.compile(r"什么是|是什么|有哪些原因|为什么会|机制|科普")
PERSONAL = re.compile(r"我|家人|现在|突然|持续|刚刚|怎么办")
CLINICAL = re.compile(r"停药|换药|加药|减药|药量|剂量|确诊|诊断|处方|用药|吃什么药|吃多少|几片|加量|减量|药.{0,8}停")
TREATMENT_DECISION = re.compile(r"多少|几片|能否|能不能|能.{0,5}吗|可不可以|要不要|该不该|应该|怎么|如何|给我")
PERCENT = re.compile(r"[%％]|百分之")
NOTICE = "健康科普仅供参考，具体诊疗请咨询医务人员。"


class State(TypedDict, total=False):
    message: str
    previous: str
    context_entities: list[str]
    entities: list[str]
    topics: list[str]
    route: str
    question: str
    graph_result: dict
    evidence_result: tuple
    evidence: list[dict]
    evidence_status: str
    model_status: str
    answer: str


CITATION_LIMIT = 6
SUPPORT_LENGTH = 480
CAUSAL_TERMS = ("导致", "引起", "造成", "因果关系", "作用机制")
TREATMENT_ADVICE = re.compile(r"停药|换药|加药|减药|加量|减量|处方")


def cited_markdown(sections, evidence, *, qualitative=False):
    blocks = []
    for section in sections[:2]:
        title = section.get("title", "").strip()
        body_markdown = section.get("markdown", "").strip()
        text = f"## {title}\n\n{body_markdown}"
        if not 2 <= len(title) <= 35 or "\n" in title or not 15 <= len(body_markdown) <= 360:
            continue
        references = section.get("references", [])
        if (not 10 <= len(text) <= 440 or not 1 <= len(references) <= 3
                or re.search(r"\[\d+\]", normalize(text)) or TREATMENT_ADVICE.search(text)
                or (qualitative and PERCENT.search(text))):
            continue
        numbers = []
        supports = []
        source_texts = []
        for ref in references:
            number, support = ref.get("number"), normalize(ref.get("support", ""))
            if type(number) is not int or not 1 <= number <= min(len(evidence), CITATION_LIMIT):
                break
            quote = evidence[number - 1]["quote"]
            source_text = normalize(quote[:SUPPORT_LENGTH])
            if (not 10 <= len(support) <= 180 or support not in source_text
                    or (qualitative and PERCENT.search(quote))):
                break
            numbers.append(number)
            supports.append(support)
            source_texts.append(source_text)
        else:
            body = normalize(re.sub(r"(?m)^#{1,6}[ \t]+[^\n]*", "", text))
            combined = " ".join(supports)
            if not body or any(term in normalize(text) and term not in combined for term in CAUSAL_TERMS):
                continue
            claims = re.sub(r"(?m)^\s*\d+[.)][ \t]+", "", text)
            if not set(re.findall(r"\d+(?:\.\d+)?", claims)) <= set(re.findall(r"\d+(?:\.\d+)?", combined)):
                continue
            compact = re.sub(r"[*_]", "", body)
            if any(compact[i:i + 45] in quote for quote in source_texts for i in range(len(compact) - 44)):
                continue
            blocks.append(text + " " + "".join(f"[{number}]" for number in ordered(numbers)))
    return "\n\n".join(blocks)


def numbered_evidence(evidence):
    return [dict(item, citation_number=number) for number, item in enumerate(evidence, start=1)]


def plain_answer(markdown):
    return re.sub(r"(?m)^#{1,6}\s+|\*\*|\x60", "", markdown)


def evidence_summary(evidence, status):
    if not evidence:
        return "## 证据不足\n\n当前没有检索到足以支持回答的文献证据。"
    citations = " ".join(f"[{i}]" for i in range(1, min(len(evidence), 3) + 1))
    return f"## 相关文献\n\n{status}。找到 **{len(evidence)} 条文献依据**，可展开核对原文。 {citations}"


def ollama(prompt, evidence, *, qualitative=False):
    if setting("LLM_ENABLED", "1") == "0":
        return None, "Qwen 模型已停用"
    started = monotonic()
    timeout = float(setting("LLM_TIMEOUT", "120"))
    if not MODEL_LOCK.acquire(timeout=timeout):
        return None, "Qwen 模型繁忙"
    reference = {"type": "object", "properties": {"number": {"type": "integer"}, "support": {"type": "string"}},
                 "required": ["number", "support"]}
    section = {"type": "object", "properties": {
        "references": {"type": "array", "minItems": 1, "maxItems": 1, "items": reference},
        "title": {"type": "string"}, "markdown": {"type": "string", "minLength": 15, "maxLength": 90}},
        "required": ["references", "title", "markdown"]}
    schema = {"type": "object", "properties": {
        "sections": {"type": "array", "maxItems": 2, "items": section}}, "required": ["sections"]}
    instructions = (
        "你负责中文心血管健康科普。每段按以下顺序："
        "先从一条证据照抄能直接回答问题的连续原文到 support（约15到45字），并填写它的编号 number。"
        "再写简短标题 title。markdown 只写一句或两句对该原文的换述，约20到60字，用 ** 加粗一处重点。"
        "必须保留原文的相关性或适用条件。只说明这段 support 已明确支持的事实。"
        "不要补充机制、因果、数字、诊断、剂量或用药内容，不写引用编号、链接、HTML，也不复制整段原文。"
        "没有直接的原文支持时返回空数组。"
    )
    if qualitative:
        instructions += "这是定性场景模拟。解释相关路径与预防方向，避免百分比和疗效量化。"
    try:
        if setting("LLM_PROVIDER", "ollama") != "ollama":
            raise ValueError("unsupported LLM provider")
        with requests.Session() as session:
            session.trust_env = False
            response = session.post(
                local_api(setting("LLM_BASE_URL", "http://127.0.0.1:11434")) + "/api/chat",
                json={
                    "model": setting("LLM_MODEL", "qwen3:4b"), "stream": False, "think": False,
                    "keep_alive": setting("LLM_KEEP_ALIVE", "5m"),
                    "options": {"temperature": float(setting("LLM_TEMPERATURE", "0.2")),
                                "num_ctx": int(setting("LLM_CONTEXT", "4096")), "num_predict": 850},
                    "format": schema,
                    "messages": [
                        {"role": "system", "content": instructions},
                        {"role": "user", "content": json.dumps({"task": prompt, "evidence": [
                            {"citation": n, "quote": item["quote"][:SUPPORT_LENGTH]}
                            for n, item in enumerate(evidence[:CITATION_LIMIT], start=1)
                            if not qualitative or not PERCENT.search(item["quote"])
                        ]}, ensure_ascii=False)},
                    ],
                }, timeout=(1, timeout), allow_redirects=False,
            )
            response.raise_for_status()
            envelope = response.json()
            if type(envelope.get("load_duration")) in (int, float):
                LOG.info("Ollama model load %.1f ms", envelope["load_duration"] / 1_000_000)
            payload = json.loads(envelope["message"]["content"])
        markdown = cited_markdown(payload["sections"], evidence, qualitative=qualitative)
        if markdown:
            return markdown, "Qwen 已归纳证据并通过引用核对"
        return None, "本次未生成通过引用核对的分析"
    except (requests.RequestException, ValueError, TypeError, KeyError, AttributeError) as exc:
        LOG.warning("Qwen request failed (%s)", type(exc).__name__)
        return None, "Qwen 模型暂不可用"
    finally:
        MODEL_LOCK.release()
        LOG.info("Qwen request including queue %.1f ms", (monotonic() - started) * 1000)


def plan(state):
    message = state["message"]
    if URGENT.search(message) and (PERSONAL.search(message) or not EDUCATIONAL.search(message)):
        return {"route": "urgent", "answer": "如正在出现胸痛、呼吸困难、晕厥等症状，请立即联系当地急救服务。"
                "在中国大陆可拨打 120。请尽快就医，由医务人员判断下一步。"}
    if CLINICAL.search(message) and (PERSONAL.search(message) or TREATMENT_DECISION.search(message)):
        return {"route": "clinical", "answer": "请由医务人员结合病史、检查和用药情况评估。"
                "如已接受治疗，调整用药前请联系开具处方的医生。"}
    entities, topics = index().match(message)
    follow_up = bool(re.search(r"^(那|这|它|还有|如何改善|有哪些可以)", message))
    if follow_up and state.get("previous"):
        inherited, previous_topics = index().match(state["previous"])
        entities = ordered([*entities, *inherited[:3]])
        topics = ordered([*topics, *previous_topics])
    entities = ordered([*state.get("context_entities", []), *entities])[:8]
    if not topics and "生活方式" in message and "预防" in message:
        topics = list(TOPICS)
    topics = ordered([*topics, *(key for key, (_, names) in TOPICS.items() if any(n in entities for n in names))])
    definition = re.search(r"^什么是|是什么[？?。]?$|^定义", message)
    explicit_graph = re.search(r"^图谱|^显示.*(节点|关系)|^查找.*节点", message)
    question = (state["previous"] + "；追问：" + message) if follow_up and state.get("previous") else message
    return dict(route="graph" if explicit_graph else "evidence" if definition or not entities else "combined",
                entities=entities, topics=topics, question=question)


def graph_agent(state):
    started = monotonic()
    result = index().subgraph(state["entities"], 2)
    LOG.info("Graph query %.1f ms", (monotonic() - started) * 1000)
    return {"graph_result": result}


def evidence_agent(state):
    return {"evidence_result": retrieve(state["question"], state["entities"])}


def supported_answer(state):
    result, evidence_status = state.get("evidence_result", ([], ""))
    evidence = link_evidence(result, state.get("graph_result", EMPTY))
    task = f"问题：{state['question']}。归纳下列证据直接支持的联系和适用条件。"
    answer, model_status = ollama(task, evidence) if evidence else (None, "证据不足")
    return dict(evidence=evidence, evidence_status=evidence_status, model_status=model_status,
                answer=answer or evidence_summary(evidence, model_status))


def medical_agent(state):
    return supported_answer(state)


def summarize(state):
    if state["route"] == "graph":
        graph = state.get("graph_result", EMPTY)
        answer = (f"图谱找到 {len(graph['matched_entities'])} 个匹配实体及 "
                  f"{len(graph['edges'])} 条可探索关系。点击图谱查看文献出处与限定条件。")
        if not graph["matched_entities"]:
            answer = "图谱未找到对应实体。请尝试使用具体名称。"
        return {"answer": answer}
    if state["route"] in ("urgent", "clinical"):
        return {}
    if state["route"] == "evidence":
        result = supported_answer(state)
        return dict(result, answer=result["answer"] + "\n\n" + NOTICE)
    return {"answer": state["answer"] + "\n\n" + NOTICE}


def after_plan(state):
    return {"graph": ["graph_agent"], "evidence": ["evidence_agent"], "combined": ["graph_agent", "evidence_agent"],
            "urgent": ["summarize"], "clinical": ["summarize"]}[state["route"]]


workflow = StateGraph(State)
for name, fn in (("plan", plan), ("graph_agent", graph_agent), ("evidence_agent", evidence_agent),
                 ("medical_agent", medical_agent), ("summarize", summarize)):
    workflow.add_node(name, fn)
workflow.add_edge(START, "plan")
workflow.add_conditional_edges("plan", after_plan, ["graph_agent", "evidence_agent", "summarize"])
workflow.add_conditional_edges("graph_agent", lambda state: "summarize" if state["route"] == "graph" else "medical_agent",
                               ["summarize", "medical_agent"])
workflow.add_conditional_edges("evidence_agent", lambda state: "summarize" if state["route"] == "evidence" else "medical_agent",
                               ["summarize", "medical_agent"])
workflow.add_edge("medical_agent", "summarize")
workflow.add_edge("summarize", END)
WORKFLOW = workflow.compile()


def chat(message, previous="", context_entities=()):
    with tracing_context(enabled=False):
        result = WORKFLOW.invoke(dict(message=message, previous=previous,
                                      context_entities=list(context_entities)), {"recursion_limit": 8})
    steps = [dict(agent="主控 Agent", status="completed")]
    for key, name in (("graph_result", "图谱探索 Agent"), ("evidence_result", "证据检索 Agent"),
                      ("model_status", "医学分析 Agent")):
        if key in result and (key != "model_status" or result["route"] == "combined"):
            steps.append(dict(agent=name, status="completed",
                              detail=result.get("model_status") if key == "model_status" else
                              result.get("evidence_status") if key == "evidence_result" else None))
    return dict(answer=plain_answer(result["answer"]), answer_markdown=result["answer"], graph=result.get("graph_result", EMPTY),
                evidence=numbered_evidence(result.get("evidence", [])), agent_trace=steps,
                evidence_status=result.get("evidence_status", ""), topics=result.get("topics", []),
                suggested_questions=["有哪些生活方式有助于预防心血管疾病？", "图谱中高血压与冠心病有什么联系？"]
                if result["route"] not in ("urgent", "clinical") else [])
