from typing import Any, Literal

from pydantic import BaseModel


class CytoscapeNodeData(BaseModel):
    id: str
    label: str
    type: Literal["object", "column"]
    object_type: str | None = None
    database_name: str | None = None
    parent: str | None = None


class CytoscapeEdgeData(BaseModel):
    id: str
    source: str
    target: str
    label: str | None = None
    transformation_type: str | None = None
    confidence: float | None = None


class CytoscapeElement(BaseModel):
    group: Literal["nodes", "edges"]
    data: dict[str, Any]


class DiagramResponse(BaseModel):
    elements: list[CytoscapeElement]
    node_count: int
    edge_count: int
    truncated: bool = False
