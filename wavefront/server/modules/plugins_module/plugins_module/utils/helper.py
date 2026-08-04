from typing import List, Dict, Any
from pydantic import BaseModel
import json
import hashlib


class AddDatasourcePayload(BaseModel):
    name: str
    type: str
    config: str
    description: str | None = None


class UpdateDatasourcePayload(BaseModel):
    name: str | None = None
    type: str | None = None
    config: str | None = None
    description: str | None = None


class InsertRowsJsonPayload(BaseModel):
    data: List[Dict[str, Any]]


class UpdateRowsJsonPayload(BaseModel):
    # OData filter naming the rows to update, e.g. "id eq 'a0468a96-...'".
    # Required: an UPDATE with no WHERE rewrites the whole table, so omitting it
    # is a schema violation rather than a check the controller has to remember.
    filter: str
    # Column -> new value.
    data: Dict[str, Any]


class TableUpdate(BaseModel):
    table_name: str
    # OData filter naming the rows to update in THIS table. Per-entry rather than
    # shared: the tables are related, not identical, so one predicate could not
    # address them all.
    filter: str
    data: Dict[str, Any]


class UpdateRowsJsonMultiPayload(BaseModel):
    updates: List[TableUpdate]
    # Abort the whole transaction if any entry's filter matches nothing. The
    # premise of an atomic multi-table update is that these rows move together,
    # so a target that does not exist means the premise is false — committing the
    # rest would leave the inconsistency the transaction was meant to prevent.
    require_all_matched: bool = True


class TableInsert(BaseModel):
    table_name: str
    # A single row dict if single_row=True, otherwise a list of row dicts.
    data: Any
    single_row: bool = False


class InsertRowsJsonMultiPayload(BaseModel):
    inserts: List[TableInsert]


class DynamicQueryRequest(BaseModel):
    dynamic_query: str


class DynamicQueryExecuteRequest(BaseModel):
    params: dict[str, str]


def generate_cache_key(
    query_id: str,
    filter: str = None,
    rls_filter_str: str = None,
    limit: int = None,
    offset: int = None,
    params: dict[str, str] = None,
) -> str:
    """Generate a unique cache key based on query parameters."""
    key_dict = {
        'query_id': query_id,
        'filter': filter,
        'rls_filter': rls_filter_str,
        'limit': limit,
        'offset': offset,
        'params': params,
    }

    key_json = json.dumps(key_dict, sort_keys=True, separators=(',', ':'))
    hash_digest = hashlib.md5(key_json.encode()).hexdigest()
    return f'dynamic_query:{hash_digest}'


def generate_export_filename_hash(
    filter: str = None,
    limit: int = None,
    offset: int = None,
    params: dict[str, str] = None,
    rls_filter_str: str = None,
) -> str:
    """Generate a short hash for export filename from $filter, limit, offset, dynamic_query params, and RLS scope."""
    key_dict = {
        'filter': filter,
        'limit': limit,
        'offset': offset,
        'params': params or {},
        'rls': rls_filter_str,
    }
    key_json = json.dumps(key_dict, sort_keys=True, separators=(',', ':'))
    return hashlib.md5(key_json.encode()).hexdigest()


def validate_yaml_query(yaml_query: dict) -> bool:
    """
    Validate the structure of a dynamic query YAML file.

    Args:
        yaml_query: Dictionary containing the parsed YAML query

    Returns:
        bool: True if valid, False otherwise
    """
    # Check top-level required fields
    required_fields = ['id', 'queries', 'name']
    for field in required_fields:
        if field not in yaml_query:
            return False

    # Validate queries is a list
    if not isinstance(yaml_query['queries'], list):
        return False

    # Check that we have at least one query
    if len(yaml_query['queries']) == 0:
        return False

    # Track query IDs to ensure uniqueness
    query_ids = set()

    # Validate each query in the queries list
    queries_required_fields = ['id', 'description', 'query']
    for query in yaml_query['queries']:
        # Check required fields for each query
        for field in queries_required_fields:
            if field not in query:
                return False

        # Check for duplicate query IDs
        query_id = query['id']
        if query_id in query_ids:
            return False
        query_ids.add(query_id)

        # Validate parameters if present (optional field)
        if 'parameters' in query:
            parameters = query['parameters']
            if not isinstance(parameters, list):
                return False

            # Validate each parameter has required fields
            for param in parameters:
                if not isinstance(param, dict):
                    return False
                # Parameters should have at least a name and type
                if 'name' not in param or 'type' not in param:
                    return False

    return True
