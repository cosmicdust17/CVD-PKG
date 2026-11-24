"""Local HTTP entry point for the existing HF-KG project."""
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .health_agent import chat
from .health_evidence import documents
from .health_graph import ROOT, index, ordered
from .health_risk import RiskInput, estimate
from .health_simulator import DETAIL, OPTIONS, evaluate

app = FastAPI(title="HF-KG 健康知识 API")
Term = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GraphQuery(Payload):
    entities: list[Term] = Field(default_factory=list, max_length=12)
    max_depth: int = Field(2, ge=0, le=3)
    relation_types: list[Literal["增加风险", "导致", "相关"]] = Field(default_factory=list, max_length=3)


class ChatContext(Payload):
    previous_question: Question | None = None
    entity_ids: list[Term] = Field(default_factory=list, max_length=8)
    path_edge_ids: list[Term] = Field(default_factory=list, max_length=12)


class ChatInput(Payload):
    conversation_id: UUID | None = None
    message: Question
    context: ChatContext = Field(default_factory=ChatContext)


class Lifestyle(Payload):
    diet: Literal["high", "reduced"] | None = None
    exercise: Literal["inactive", "regular"] | None = None
    sleep: Literal["irregular", "regular"] | None = None
    smoking: Literal["current", "none"] | None = None


class Simulation(Payload):
    lifestyle: Lifestyle
    compare_with: Lifestyle | None = None
    risk_assessment: RiskInput | None = None
    explain: bool = True


class HistoryInput(Payload):
    title: Term
    lifestyle: Lifestyle
    compare_with: Lifestyle | None = None


BrowserID = Annotated[UUID, Header(alias="X-HF-Browser-ID")]


def connect_history():
    path = Path(os.getenv("HF_HISTORY_DB", ROOT / "data/health-history.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    connection.execute("""CREATE TABLE IF NOT EXISTS scenario_history (
        id TEXT PRIMARY KEY, browser_id TEXT NOT NULL, payload TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    )""")
    connection.row_factory = sqlite3.Row
    return connection


def history_item(row):
    return dict(id=row["id"], created_at=row["created_at"], **json.loads(row["payload"]))


@app.post("/api/knowledge-graph/query")
def query(data: GraphQuery):
    return index().subgraph(data.entities, data.max_depth, data.relation_types)


@app.post("/api/agent/chat")
def ask(data: ChatInput):
    context = data.context
    graph = index()
    entities = ordered(node for term in context.entity_ids for node in graph.resolve(term))
    for edge_id in context.path_edge_ids:
        edge = graph.edges.get(edge_id)
        if edge and (edge["source"] in entities or edge["target"] in entities):
            entities.extend(node for node in (edge["source"], edge["target"]) if node not in entities)
    return dict(conversation_id=str(data.conversation_id or uuid4()),
                **chat(data.message, context.previous_question or "", entities[:8]))


@app.get("/api/simulator/options")
def options():
    return {factor: {"choices": choices, "description": DETAIL[factor]} for factor, choices in OPTIONS.items()}


@app.post("/api/simulator/risk-assessment")
def risk_assessment(data: RiskInput):
    try:
        return estimate(data)
    except ModuleNotFoundError as exc:
        raise HTTPException(503, "风险评分组件未安装。") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/simulator/evaluate")
def simulate(data: Simulation):
    baseline = data.lifestyle.model_dump(exclude_none=True)
    modified = data.compare_with.model_dump(exclude_none=True) if data.compare_with else baseline
    if not baseline and not modified:
        raise HTTPException(422, "请至少选择一项生活方式。")
    risk = risk_assessment(data.risk_assessment) if data.risk_assessment else None
    return evaluate(baseline, modified, risk, explain=data.explain)


@app.get("/api/knowledge-evidence/documents/{document_id}")
def open_document(document_id: str):
    document = documents().get(document_id)
    if document and Path(document["path"]).is_file():
        return FileResponse(document["path"], media_type="application/pdf", content_disposition_type="inline",
                            filename=document["name"])
    raise HTTPException(404, "原文 PDF 未配置或本机找不到。")


@app.get("/api/simulator/history")
def list_history(browser_id: BrowserID):
    with closing(connect_history()) as db:
        rows = db.execute("SELECT id, created_at, payload FROM scenario_history WHERE browser_id=? "
                          "ORDER BY created_at DESC, id DESC LIMIT 100", (str(browser_id),))
        return [history_item(row) for row in rows]


@app.post("/api/simulator/history", status_code=201)
def save_history(data: HistoryInput, browser_id: BrowserID):
    if not data.lifestyle.model_dump(exclude_none=True) and not (
        data.compare_with and data.compare_with.model_dump(exclude_none=True)
    ):
        raise HTTPException(422, "请至少选择一项生活方式。")
    with closing(connect_history()) as db, db:
        cursor = db.execute("INSERT INTO scenario_history(id,browser_id,payload) VALUES(?,?,?) "
                            "RETURNING id, created_at, payload",
                            (str(uuid4()), str(browser_id), data.model_dump_json(exclude_none=True)))
        return history_item(cursor.fetchone())


@app.get("/api/simulator/history/{scenario_id}")
def get_history(scenario_id: UUID, browser_id: BrowserID):
    with closing(connect_history()) as db:
        row = db.execute("SELECT id, created_at, payload FROM scenario_history WHERE id=? AND browser_id=?",
                         (str(scenario_id), str(browser_id))).fetchone()
    if row is None:
        raise HTTPException(404, "找不到该场景。")
    return history_item(row)


@app.delete("/api/simulator/history/{scenario_id}", status_code=204)
def delete_history(scenario_id: UUID, browser_id: BrowserID):
    with closing(connect_history()) as db, db:
        cursor = db.execute("DELETE FROM scenario_history WHERE id=? AND browser_id=?",
                            (str(scenario_id), str(browser_id)))
        if not cursor.rowcount:
            raise HTTPException(404, "找不到该场景。")
