from pydantic import BaseModel


class DrColumn(BaseModel):
    name: str
    type: str
    is_key: bool
    description: str = ""


class DrTable(BaseModel):
    name: str
    object_type: str = "TABLE"
    columns: list[DrColumn]


class DrRelationship(BaseModel):
    from_table: str
    from_col: str
    to_table: str
    to_col: str
    via_view: str
    # "JOIN" (equi-join between two tables, parsed from a view's SQL) or
    # "VIEW_SOURCE" (the view reads from this object at all, regardless of
    # whether any JOIN condition involving it could be parsed).
    relationship_type: str = "JOIN"


class DrDiagramResponse(BaseModel):
    database: str
    tables: dict[str, DrTable]
    relationships: list[DrRelationship]
    table_count: int
    view_count: int
    relationship_count: int


class ObjectIdsRequest(BaseModel):
    object_ids: list[str]
