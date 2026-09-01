"""
Custom SQLite query execution tool.
"""
from typing import Dict, Any
from core.database import execute_user_sql_query

def handle_sqlite_query_executor(params: Dict[str, Any], action_id: str = "act_1") -> Dict[str, Any]:
    query = params["query"]
    sql_results = execute_user_sql_query(query)
    return {"id": action_id, "tool": "sqlite_query_executor", "status": "success", "result": sql_results}
