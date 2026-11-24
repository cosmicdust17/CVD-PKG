"""Health API regression checks against the existing three-document graph."""
import os
import re
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from hfkg.health_agent import cited_markdown
from hfkg.health_api import app
from hfkg.health_evidence import local_passages
from hfkg.health_graph import index


QUESTION_SET = (
    "什么是高血压？",
    "高盐饮食为什么会影响血压？",
    "长期缺乏运动可能带来哪些健康影响？",
    "吸烟与心血管疾病有什么关系？",
    "高血压与冠心病之间有什么联系？",
    "有哪些生活方式有助于预防心血管疾病？",
)
RISK = dict(age=55, sex="male", sbp=140, total_chol=5.5, smoker=False,
            diabetes=False, prior_cvd=False, region="china_mainland")
BEFORE = dict(diet="high", exercise="inactive", sleep="irregular", smoking="current")
AFTER = dict(diet="reduced", exercise="regular", sleep="regular", smoking="none")


class HealthAPITest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        env = patch.dict(os.environ, {"HF_HISTORY_DB": str(Path(directory.name) / "history.sqlite3"),
                                      "RAGFLOW_DATASET_IDS": "", "HF_LOCAL_EVIDENCE": "1", "LLM_ENABLED": "0"})
        env.start()
        self.addCleanup(env.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_graph_original_ids_and_path_references(self):
        response = self.client.post("/api/knowledge-graph/query", json={
            "entities": ["D1_E048", "xyz-unmapped"], "max_depth": 2, "relation_types": ["增加风险"],
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["missing_entities"], ["xyz-unmapped"])
        nodes = {n["id"]: n for n in body["nodes"]}
        edges = {e["id"]: e for e in body["edges"]}
        self.assertTrue(any("D1_E048" in n["sourceEntityIds"] for n in nodes.values()))
        self.assertTrue(edges)
        for path in body["paths"]:
            self.assertTrue(set(path["nodes"]) <= nodes.keys())
            for src, dst, edge_id in zip(path["nodes"][:-1], path["nodes"][1:], path["edges"], strict=True):
                self.assertEqual({src, dst}, {edges[edge_id]["source"], edges[edge_id]["target"]})
                self.assertTrue(edges[edge_id]["sourceRelationIds"])

    def test_six_questions_followup_and_urgent(self):
        has_fulltext = bool(local_passages())
        replies = []
        for position, question in enumerate(QUESTION_SET):
            with self.subTest(question=question):
                response = self.client.post("/api/agent/chat", json={"message": question})
                self.assertEqual(response.status_code, 200)
                body = response.json()
                replies.append(body)
                self.assertTrue(body["answer"])
                if position or has_fulltext:
                    self.assert_document_references(body)
                    self.assertTrue(body["evidence"])
                else:
                    self.assertFalse(body["evidence"])
                    self.assertIn("证据不足", body["answer_markdown"])
                self.assertTrue(all(item["document_name"] and item["page"] and item["chunk_id"]
                                    for item in body["evidence"]))
                self.assertTrue(all(item["source"] != "RAGFlow" for item in body["evidence"]))
                self.assertEqual(len(body["agent_trace"]), 2 if position == 0 else 4)
                if position:
                    self.assertTrue(body["graph"]["edges"])
        if has_fulltext:
            self.assertTrue(any("盐" in row["quote"] and "血压" in row["quote"] for row in replies[1]["evidence"]))
        response = self.client.post("/api/agent/chat", json=dict(
            conversation_id=replies[1]["conversation_id"], message="那它和高血压之间有什么联系？",
            context={"previous_question": QUESTION_SET[1]},
        )).json()
        self.assertEqual(response["conversation_id"], replies[1]["conversation_id"])
        self.assertIn("diet", response["topics"])
        urgent = self.client.post("/api/agent/chat", json={"message": "我现在胸痛，呼吸困难"}).json()
        self.assertIn("120", urgent["answer"])
        self.assertFalse(urgent["evidence"])
        self.assertEqual(len(urgent["agent_trace"]), 1)
        treatment = self.client.post("/api/agent/chat", json={"message": "降压药能停吗？"}).json()
        self.assertIn("医生", treatment["answer"])
        self.assertEqual(len(treatment["agent_trace"]), 1)
        absent = self.client.post("/api/agent/chat", json={"message": "月球上的彩虹是什么？"}).json()
        self.assertFalse(absent["evidence"])

    def test_lifestyle_and_browser_scoped_history(self):
        for factor in (*BEFORE, "all"):
            before = BEFORE if factor == "all" else {factor: BEFORE[factor]}
            after = AFTER if factor == "all" else {factor: AFTER[factor]}
            data = dict(lifestyle=before, compare_with=after)
            with self.subTest(factor=factor):
                response = self.client.post("/api/simulator/evaluate", json=data)
                self.assertEqual(response.status_code, 200)
                result = response.json()
                self.assertEqual(result["modified"]["lifestyle"], after)
                self.assertTrue(result["removed_edge_ids"])
                self.assertFalse(result["modified"]["graph"]["edges"])
                self.assertTrue(result["explanation"])
                self.assert_document_references(result)
                self.assertTrue(result["evidence"])
                self.assertIsNone(result["risk_assessment"])
        browser = {"X-HF-Browser-ID": str(uuid4())}
        saved = self.client.post("/api/simulator/history", json={**data, "title": "场景一"}, headers=browser)
        self.assertEqual(saved.status_code, 201)
        path = "/api/simulator/history/" + saved.json()["id"]
        self.assertEqual(self.client.get(path, headers=browser).json()["compare_with"], after)
        self.assertEqual(self.client.get(path, headers={"X-HF-Browser-ID": str(uuid4())}).status_code, 404)
        self.assertEqual(self.client.get("/api/simulator/history", headers=browser).json(), [saved.json()])
        self.assertEqual(self.client.delete(path, headers=browser).status_code, 204)
        self.assertEqual(self.client.get(path, headers=browser).status_code, 404)

    def test_risk_missing_boundaries_and_region(self):
        path = "/api/simulator/risk-assessment"
        for age in (40, 79):
            response = self.client.post(path, json={**RISK, "age": age})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(0 < response.json()["result_percent"] < 100)
        for invalid in ({"age": 39}, {"age": 80}, {"prior_cvd": True}, {"region": "any"},
                        {"smoker": "false"}, {"total_chol": 200}):
            self.assertEqual(self.client.post(path, json={**RISK, **invalid}).status_code, 422)
        self.assertEqual(self.client.post(path, json={k: v for k, v in RISK.items() if k != "sbp"}).status_code, 422)
        result = self.client.post(path, json=RISK).json()
        self.assertEqual(result["result_percent"], 7.5)
        self.assertEqual(result["unit"], "%")
        self.assertEqual(result["package_version"], "2.0.0")
        # WHO East Asia chart, PDF p. 13, 55–59, 140–159, 5–5.9, male nonsmoker, no diabetes.
        reference = self.client.post(path, json={**RISK, "age": 57, "sbp": 150}).json()
        self.assertEqual(reference["result_percent"], 10.0)

    def assert_document_references(self, reply):
        evidence = reply["evidence"]
        self.assertEqual([item["citation_number"] for item in evidence], list(range(1, len(evidence) + 1)))
        body = reply["answer_markdown"]
        self.assertTrue(body.startswith("## "))
        citations = re.findall(r"\[(\d+)\]", body)
        self.assertTrue(citations)
        self.assertTrue(set(map(int, citations)) <= {item["citation_number"] for item in evidence})
        self.assertFalse(any(item["quote"] in body for item in evidence))

    def test_model_markdown_requires_real_support_and_numbers(self):
        quote = "高钠膳食与高血压发病风险升高相关。"
        valid = "现有证据提示，**盐分摄入偏高**与高血压的发生风险有关。"
        title = "关联结论"
        items = [{"quote": quote}]
        ref = {"number": 1, "support": quote}
        invalid = [
            {"markdown": valid, "references": [{**ref, "number": 5}]},
            {"markdown": valid, "references": [{**ref, "support": "血容量扩张会导致高血压风险升高。"}]},
            {"markdown": "## 分析\n\n长期高盐饮食会导致高血压。", "references": [ref]},
            {"markdown": valid + " 风险增加 30%。", "references": [ref]},
            {"markdown": valid + " [77]", "references": [ref]},
        ]
        for section in invalid:
            with self.subTest(section=section):
                self.assertEqual(cited_markdown([{**section, "title": title}], items), "")
        self.assertEqual(cited_markdown([{"title": title, "markdown": valid, "references": [ref]}], items),
                         f"## {title}\n\n{valid} [1]")

    def test_parallel_graph_requests(self):
        payload = {"entities": ["吸烟", "高血压"], "max_depth": 2}
        with ThreadPoolExecutor(max_workers=4) as pool:
            replies = list(pool.map(lambda _: self.client.post("/api/knowledge-graph/query", json=payload).json(), range(8)))
        self.assertTrue(all(reply == replies[0] for reply in replies))
        self.assertTrue(index().edges)


if __name__ == "__main__":
    unittest.main()
