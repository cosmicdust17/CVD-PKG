"""Query the existing G6 export without changing its display or source IDs."""
import json
import os
import re
import unicodedata
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import Path

ROOT = Path(os.getenv("HF_KG_ROOT", Path(__file__).resolve().parents[1]))
DATA = ROOT / "kg-visualization/public/data/graph-data.json"

TOPICS = {
    "diet": (("盐", "钠"), ("高盐饮食", "高钠膳食", "高钠饮食")),
    "exercise": (("运动", "久坐", "体力活动", "身体活动"), ("久坐行为",)),
    "sleep": (("睡眠", "作息", "入睡"), ("睡眠不足或睡眠模式紊乱", "0点后入睡")),
    "smoking": (("吸烟", "抽烟", "戒烟", "烟草"), ("吸烟",)),
}


def normalize(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).casefold()


def ordered(values):
    return list(dict.fromkeys(values))


class KnowledgeIndex:
    def __init__(self, path):
        self.data = json.loads(path.read_text(encoding="utf-8-sig"))
        self.nodes = {row["id"]: row for row in self.data["nodes"]}
        self.edges = {row["id"]: row for row in self.data["edges"]}
        self.evidence = {row["id"]: row for row in self.data["evidence"]}
        self.names = defaultdict(list)
        self.adjacent = defaultdict(list)
        self.ids = {}
        for row in self.nodes.values():
            for name in [row["name"], *row["aliases"]]:
                self.names[normalize(name)].append(row["id"])
            for original in row["sourceEntityIds"]:
                self.ids[original.upper()] = row["id"]
        for row in self.edges.values():
            for endpoint in ordered([row["source"], row["target"]]):
                self.adjacent[endpoint].append(row["id"])

    def resolve(self, term):
        key = term.strip().upper()
        if key in self.nodes:
            return [key]
        if key in self.ids:
            return [self.ids[key]]
        return self.names.get(normalize(term), [])

    def match(self, message):
        normalized = normalize(message)
        names = sorted((name for name in self.names if len(name) >= 2 and name in normalized),
                       key=lambda name: (normalized.index(name), -len(name)))
        selected = []
        for name in names:
            if not any(name in longer for longer in selected):
                selected.append(name)
        topics = [key for key, (terms, _) in TOPICS.items() if any(t in normalized for t in terms)]
        aliases = []
        if not any("血压" in name for name in selected) and "血压" in normalized:
            aliases.append("高血压")
        for topic in topics:
            if not any(term in name for term in TOPICS[topic][0] for name in selected):
                aliases.extend(TOPICS[topic][1][:1])
        return ordered([*selected, *aliases])[:7], topics

    def subgraph(self, entities, depth=2, types=(), outgoing=False):
        return self._subgraph(tuple(entities), depth, tuple(types), outgoing)

    @lru_cache(maxsize=256)
    def _subgraph(self, entities, depth, types, outgoing):
        roots = ordered(node for term in entities for node in self.resolve(term))[:12]
        paths = []
        for root in roots:
            queue = deque([([root], [])])
            visited = {root}
            while queue and len(visited) < 22:
                nodes, edges = queue.popleft()
                head = nodes[-1]
                if len(edges) >= depth:
                    continue
                candidates = []
                for edge_id in self.adjacent[head]:
                    edge = self.edges[edge_id]
                    if types and edge["relationType"] not in types:
                        continue
                    if outgoing and edge["directed"] and edge["source"] != head:
                        continue
                    other = edge["target"] if edge["source"] == head else edge["source"]
                    candidates.append((other not in roots, edge_id, other))
                for _, edge_id, other in sorted(candidates)[:8]:
                    if other in nodes:
                        continue
                    path = dict(nodes=[*nodes, other], edges=[*edges, edge_id])
                    if other not in visited or len(nodes) == 1:
                        paths.append(path)
                    if other not in visited:
                        visited.add(other)
                        queue.append((path["nodes"], path["edges"]))
        paths.sort(key=lambda p: (p["nodes"][-1] not in roots, len(p["edges"])))
        unique_paths = {}
        for path in paths:
            key = tuple(path["edges"])
            if key[::-1] not in unique_paths:
                unique_paths.setdefault(key, path)
        paths = list(unique_paths.values())[:35]
        node_ids = ordered([*roots, *(n for path in paths for n in path["nodes"])])
        edge_ids = ordered(e for path in paths for e in path["edges"])
        return dict(nodes=[self.nodes[n] for n in node_ids], edges=[self.edges[e] for e in edge_ids],
                    paths=paths, matched_entities=roots,
                    missing_entities=[name for name in entities if not self.resolve(name)])


@lru_cache(maxsize=1)
def index():
    return KnowledgeIndex(DATA)
