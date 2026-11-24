"""Qualitative scenario comparison using only existing graph paths."""
from uuid import uuid4

from .health_agent import evidence_summary, numbered_evidence, ollama, plain_answer
from .health_evidence import link_evidence, retrieve
from .health_graph import TOPICS, index, normalize, ordered

OPTIONS = {
    "diet": {"high": "高盐饮食", "reduced": "尝试减少盐摄入"},
    "exercise": {"inactive": "日常少动且久坐", "regular": "增加活动并减少久坐"},
    "sleep": {"irregular": "睡眠不足或作息不规律", "regular": "尝试建立规律作息"},
    "smoking": {"current": "当前吸烟", "none": "当前不吸烟"},
}
ACTIVE_ENTITIES = {
    ("diet", "high"): TOPICS["diet"][1],
    ("exercise", "inactive"): TOPICS["exercise"][1],
    ("sleep", "irregular"): TOPICS["sleep"][1][:1],
    ("smoking", "current"): TOPICS["smoking"][1],
}
DETAIL = {
    "diet": "选择与盐摄入相关的场景。",
    "exercise": "图谱中的久坐行为用于探索少动场景中的一个因素。",
    "sleep": "选择与睡眠模式相关的场景。",
    "smoking": "按当前场景中的吸烟状态选择。",
}
DEFAULT_TOPICS = {
    "diet": ("high", "reduced", "为什么减少盐摄入有助于血压管理？"),
    "exercise": ("inactive", "regular", "日常少动和久坐与心血管健康有什么联系？"),
    "sleep": ("irregular", "regular", "睡眠不足和作息不规律与心血管健康有什么联系？"),
    "smoking": ("current", "none", "减少吸烟暴露与心血管预防有什么联系？"),
}
INTERVENTIONS = {
    "diet": ("减盐、限盐或低盐", ("减少钠", "减少盐", "减少烹调用盐", "限制钠", "限制盐", "限盐", "低盐", "减盐")),
    "exercise": ("增加活动并减少久坐", ("减少久坐", "增加身体活动", "规律的身体活动", "定期适量进行身体活动", "增加运动")),
    "sleep": ("改善睡眠习惯", ("规律睡眠", "睡眠规律", "规律作息", "睡眠时间", "睡眠时长")),
    "smoking": ("获取戒烟支持", ("戒烟",)),
}


def scenario(lifestyle):
    active = [name for factor, value in lifestyle.items() for name in ACTIVE_ENTITIES.get((factor, value), ())]
    graph = index().subgraph(active, 2, outgoing=True)
    diseases = [node["name"] for node in graph["nodes"] if node["entityType"] == "心血管疾病"]
    risks = [node["name"] for node in graph["nodes"] if node["entityType"] == "危险因素"]
    return dict(lifestyle=lifestyle, graph=graph, related_diseases=diseases, risk_factors=risks,
                labels={factor: OPTIONS[factor][value] for factor, value in lifestyle.items()})


def evaluate(baseline, modified, risk=None, explain=True):
    before, after = scenario(baseline), scenario(modified)
    old, new = before["graph"], after["graph"]
    old_ids, new_ids = ({edge["id"] for edge in graph["edges"]} for graph in (old, new))
    paths = list({(tuple(path["nodes"]), tuple(path["edges"])): path
                  for path in [*old["paths"], *new["paths"]]}.values())
    graph = dict(nodes=list({n["id"]: n for n in [*old["nodes"], *new["nodes"]]}.values()),
                 edges=list({e["id"]: e for e in [*old["edges"], *new["edges"]]}.values()), paths=paths,
                 matched_entities=ordered([*old["matched_entities"], *new["matched_entities"]]),
                 missing_entities=ordered([*old["missing_entities"], *new["missing_entities"]]))
    changes = [dict(factor=factor, before=baseline.get(factor), after=modified.get(factor))
               for factor in OPTIONS if baseline.get(factor) != modified.get(factor)]
    focused = [change["factor"] for change in changes] or list(modified)
    evidence = []
    statuses = []
    results = {}
    for factor in focused:
        items, status = retrieve(DEFAULT_TOPICS[factor][2] + " " + INTERVENTIONS[factor][0], TOPICS[factor][1])
        results[factor] = items
        statuses.append(status)
    for offset in range(6):
        for rows in results.values():
            if offset < len(rows) and all(row["id"] != rows[offset]["id"] for row in evidence):
                evidence.append(rows[offset])
    evidence = link_evidence(evidence[:12], graph)
    recommendations = []
    for factor in focused:
        title, terms = INTERVENTIONS[factor]
        candidates = {row["id"] for row in results[factor]}
        source = next((row for row in evidence if row["id"] in candidates
                       and any(term in normalize(row["quote"]) for term in terms)
                       and any(word in row["quote"] for word in ("推荐", "建议", "应", "有助", "有益", "减少", "改善", "降低", "保持"))), None)
        if source:
            recommendations.append(dict(factor=factor, title=title, evidence_id=source["id"]))
    explanation = ""
    if explain:
        preferred = {item["evidence_id"] for item in recommendations}
        evidence.sort(key=lambda row: row["id"] not in preferred)
        task = (f"原始场景：{before['labels']}；调整场景：{after['labels']}。"
                "概括这些因素在文献中的联系和预防方向。")
        answer, status = ollama(task, evidence, qualitative=True) if evidence else (None, "证据不足")
        changes_text = "；".join(
            f"{OPTIONS[change['factor']].get(change['before'], '未设置')} → "
            f"{OPTIONS[change['factor']].get(change['after'], '未设置')}" for change in changes
        )
        change_line = f"所选变化为 {changes_text}。" if changes_text else "两次场景使用相同条件。"
        graph_line = (f"**{len(old_ids - new_ids)} 条**图谱关系仅出现在原始场景，"
                      f"**{len(new_ids - old_ids)} 条**仅出现在调整场景。")
        explanation = f"## 场景对比\n\n{change_line}\n\n{graph_line}\n\n" + (
            answer or evidence_summary(evidence, status)
        )
    focus = [{"factor": factor, "question": DEFAULT_TOPICS[factor][2],
              "entity_ids": ordered(n for name in TOPICS[factor][1] for n in index().resolve(name))}
             for factor in focused]
    return dict(scenario_id=str(uuid4()), baseline=before, modified=after, changes=changes, graph=graph,
                removed_edge_ids=sorted(old_ids - new_ids), added_edge_ids=sorted(new_ids - old_ids),
                recommendations=recommendations, evidence=numbered_evidence(evidence), evidence_status="；".join(ordered(statuses)),
                risk_assessment=risk, explanation=plain_answer(explanation), answer_markdown=explanation, focus=focus,
                limitations=["场景路径反映文献知识关系及适用条件。调整后隐藏的路径仅表示该场景未选择对应暴露。",
                             "图谱尚无已审核的干预关系，预防方向请参阅文献证据。场景比较无法估计个人指标或风险的变化。"])
