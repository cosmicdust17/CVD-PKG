import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.build_graph_data import DEFAULT_SOURCES, PROJECT, build, normalize


class BuildGraphTests(unittest.TestCase):
    def test_published_data_matches_all_three_source_exports(self):
        graph, report = build(DEFAULT_SOURCES)
        output = PROJECT / "public" / "data"
        self.assertEqual(graph, json.loads((output / "graph-data.json").read_text(encoding="utf8")))
        self.assertEqual(report["anomalyCount"], 0)
        self.assertTrue(all(value == 0 for value in report["validation"].values()))
        self.assertTrue(all(not ids for ids in report["crossDocumentOriginalIdCollisions"].values()))
        self.assertEqual(report["original"]["evidence"], report["merged"]["evidence"])
        self.assertGreater(report["crossDocumentEntityCount"], 0)
        self.assertGreater(report["crossDocumentRelationCount"], 0)

        node_sources = {(s["documentId"], s["id"]): node for node in graph["nodes"] for s in node["sourceEntities"]}
        edge_sources = {(s["documentId"], s["id"]): edge for edge in graph["edges"] for s in edge["sourceRelations"]}
        evidence = {(e["documentId"], e["originalEvidenceId"]): e for e in graph["evidence"]}
        for path in DEFAULT_SOURCES:
            raw = json.loads(path.read_text(encoding="utf8"))
            doc = raw["metadata"]["document_id"]
            for row in raw["entities"]:
                node = node_sources[doc, row["id"]]
                self.assertEqual((node["name"], node["entityType"]), (normalize(row["name"]), row["type"]))
                self.assertTrue({evidence[doc, ev]["id"] for ev in row["evidence_ids"]} <= set(node["evidenceIds"]))
            for row in raw["relations"]:
                edge = edge_sources[doc, row["id"]]
                self.assertEqual(edge["source"], node_sources[doc, row["source"]]["id"])
                self.assertEqual(edge["target"], node_sources[doc, row["target"]]["id"])
                self.assertEqual((edge["relationType"], edge["directed"]), (row["type"], row["directed"]))
                source = next(s for s in edge["sourceRelations"] if (s["documentId"], s["id"]) == (doc, row["id"]))
                self.assertEqual(source["qualifiers"], row["qualifiers"])
                self.assertTrue({evidence[doc, ev]["id"] for ev in row["evidence_ids"]} <= set(source["evidenceIds"]))
                self.assertTrue(set(source["evidenceIds"]) <= set(edge["evidenceIds"]))
            for row in raw["evidence"]:
                self.assertEqual(evidence[doc, row["id"]]["quote"], row["quote"])
                self.assertEqual(evidence[doc, row["id"]]["page"], row["page"])

    def test_normalization_and_local_references(self):
        with TemporaryDirectory() as folder:
            def document(doc):
                return {
                    "metadata": {"document_id": doc},
                    "entities": [
                        {"id": "E1", "name": " Ａ　 Β ", "type": "危险因素", "aliases": ["别名"], "evidence_ids": ["V1"]},
                        {"id": "E2", "name": "同名", "type": "心血管疾病", "evidence_ids": []},
                        {"id": "E3", "name": "同名", "type": "健康指标", "evidence_ids": []},
                    ],
                    "relations": [{"id": "R1", "source": "E1", "target": "E2", "type": "相关",
                                   "directed": True, "evidence_ids": ["V1", "unknown"]}],
                    "evidence": [{"id": "V1", "document_id": doc}],
                }

            first, second = document("D1"), document("D2")
            second["entities"][0]["name"] = "A   Β"
            second["relations"] += [
                dict(second["relations"][0], id="R2", source="E2", target="E1"),
                dict(second["relations"][0], id="R3", type="导致"),
                dict(second["relations"][0], id="R4", target="unknown"),
            ]
            paths = [Path(folder) / name for name in ("a.json", "b.json")]
            for path, data in zip(paths, (first, second)):
                path.write_text(json.dumps(data), encoding="utf8")
            graph, report = build(paths)
            self.assertEqual(len(graph["nodes"]), 3)
            self.assertEqual(len(graph["edges"]), 3)
            self.assertEqual(graph["nodes"][0]["name"], "A Β")
            self.assertEqual(graph["edges"][0]["evidenceIds"], ["D1:V1", "D2:V1"])
            self.assertIsNone(graph["evidence"][0]["page"])
            self.assertIsNone(graph["evidence"][0]["quote"])
            self.assertEqual(report["documents"][1]["anomalies"]["unresolved_relation_endpoint"], 1)

            second["entities"].append(copy.copy(second["entities"][0]))
            paths[1].write_text(json.dumps(second), encoding="utf8")
            with self.assertRaisesRegex(ValueError, "重复 ID"):
                build(paths)


if __name__ == "__main__":
    unittest.main()
