"""JSON schema + pydantic models for the AI column-lineage fallback.

The schema in ``LINEAGE_TOOL_SCHEMA`` is passed as the ``input_schema`` of an
Anthropic tool definition (see ``ai_client.py``). Forcing Claude to call this
tool (``tool_choice={"type": "tool", "name": "report_column_lineage"}``) is
what gives us structured JSON back instead of having to parse free-form text.

``AILineageEdge`` / ``AILineageResponse`` mirror the JSON schema exactly, so a
``tool_use`` block's ``input`` dict can be validated straight into
``AILineageResponse`` via ``AILineageResponse.model_validate(...)``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

TransformationType = Literal["DIRECT", "DERIVED", "AGGREGATED", "JOIN", "UNKNOWN"]

_TRANSFORMATION_TYPES: list[str] = ["DIRECT", "DERIVED", "AGGREGATED", "JOIN", "UNKNOWN"]

# JSON Schema (draft-2020-12-ish subset) describing the input to the
# "report_column_lineage" tool. Kept as a plain dict (rather than derived from
# the pydantic models below) because it is wired directly into the Anthropic
# tool definition's `input_schema` field.
LINEAGE_TOOL_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "edges": {
            "type": "array",
            "description": (
                "One entry per inferred column-level lineage edge. Include an "
                "edge for every plausible source column of every target "
                "column, even if you are not fully confident — reflect your "
                "uncertainty in `confidence` rather than omitting the edge."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "source_table": {
                        "type": "string",
                        "description": (
                            "Name of the source table/view this column comes "
                            "from, exactly as given in the available_tables "
                            "schema provided to you."
                        ),
                    },
                    "source_column": {
                        "type": "string",
                        "description": (
                            "Name of the source column, exactly as given in "
                            "the available_tables schema provided to you."
                        ),
                    },
                    "target_column": {
                        "type": "string",
                        "description": (
                            "Name of the target (output) column of the view "
                            "being analyzed."
                        ),
                    },
                    "transformation_type": {
                        "type": "string",
                        "enum": _TRANSFORMATION_TYPES,
                        "description": (
                            "DIRECT: straight column passthrough/alias. "
                            "DERIVED: computed from a scalar expression/"
                            "function of source column(s). AGGREGATED: "
                            "produced by an aggregate function (SUM, COUNT, "
                            "...). JOIN: value taken from a joined table. "
                            "UNKNOWN: relationship suspected but the exact "
                            "transformation could not be determined."
                        ),
                    },
                    "transformation_expr": {
                        "type": "string",
                        "description": (
                            "The SQL expression (as written in the query) "
                            "that produces target_column from this source, "
                            "e.g. 'UPPER(customer_name)' or 'SUM(amount)'. "
                            "Empty string if not applicable."
                        ),
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "description": (
                            "Your confidence that this edge is correct, from "
                            "0.0 (pure guess) to 1.0 (certain)."
                        ),
                    },
                },
                "required": [
                    "source_table",
                    "source_column",
                    "target_column",
                    "transformation_type",
                    "transformation_expr",
                    "confidence",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["edges"],
    "additionalProperties": False,
}


class AILineageEdge(BaseModel):
    """One proposed column-level lineage edge, as returned by Claude."""

    source_table: str
    source_column: str
    target_column: str
    transformation_type: TransformationType
    transformation_expr: str = ""
    # Intentionally unconstrained here (no ge/le) even though the JSON schema
    # above declares 0-1: Claude occasionally returns a slightly out-of-range
    # value, and we want that to survive parsing so result_validator.py can
    # clamp it rather than the whole tool call failing pydantic validation.
    confidence: float = 0.0


class AILineageResponse(BaseModel):
    """Full payload of the ``report_column_lineage`` tool call."""

    edges: list[AILineageEdge] = Field(default_factory=list)
