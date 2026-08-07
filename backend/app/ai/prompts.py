"""Prompt templates for the AI column-lineage fallback."""

from __future__ import annotations

import json

SYSTEM_PROMPT = """\
You are a precise SQL data-lineage analyst embedded in an automated pipeline.

Your job is to look at the SQL definition of a database view and propose \
column-level lineage: for each requested target column, which upstream \
table.column(s) it is derived from, and how.

Hard rules:
- Only ever reference tables and columns that appear in the `available_tables` \
schema you are given. Never invent a table name, column name, or table alias \
that was not given to you. If a column genuinely has no discoverable source \
among the tables you were given, omit it rather than guessing an identifier \
that doesn't exist.
- Base your answer strictly on the SQL text provided. Do not assume the \
existence of columns or tables that aren't shown to you, even if they seem \
plausible for the domain.
- You must call the `report_column_lineage` tool exactly once with your \
complete findings. Do not respond with plain text instead of (or in addition \
to) the tool call.
- Include an edge for every plausible source of every target column you were \
asked about, even when you are not fully sure it's correct. Low-confidence \
guesses should be reported with a low `confidence` value (e.g. 0.1-0.3) \
rather than being left out entirely — a downstream validator will filter and \
weigh your findings, so completeness matters more than precision here.
- `confidence` must reflect your actual certainty: 1.0 only for an \
unambiguous, directly traceable relationship; lower values for anything \
inferred, indirect, or based on dynamic/generated SQL you can't fully \
resolve.
"""


def build_user_prompt(sql: str, target_columns: list[str], available_tables: dict) -> str:
    """Render the view SQL, target columns, and available schema for Claude.

    Args:
        sql: The full SQL text of the view whose lineage couldn't be resolved
            deterministically.
        target_columns: The specific output column(s) of the view that need
            lineage resolved.
        available_tables: ``{table_name: {column_name: data_type}}`` — the
            complete set of tables/columns Claude is allowed to reference as
            lineage sources.

    Returns:
        A single string, ready to use as the ``content`` of a user message.
    """
    tables_json = json.dumps(available_tables, indent=2, sort_keys=True)
    targets_json = json.dumps(target_columns, indent=2)

    return f"""\
Below is the SQL definition of a view that a deterministic SQL parser could \
not confidently resolve column-level lineage for. Analyze it and report \
lineage for the requested target column(s) only.

<view_sql>
{sql}
</view_sql>

<target_columns>
{targets_json}
</target_columns>

<available_tables>
The keys are table names; each value maps column name -> data type. These \
are the ONLY valid values for `source_table` / `source_column` in your \
answer — do not reference anything not listed here.
{tables_json}
</available_tables>

Call `report_column_lineage` with your complete findings for the target \
column(s) listed above.
"""
