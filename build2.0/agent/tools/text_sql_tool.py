# /home/ubuntu/chatbot_project/tools/text_sql_tool.py
"""
Tool for converting natural language questions to SQL queries and executing them (Text-to-SQL RAG enhancement).
"""
from typing import Optional, Any, Dict
from pydantic import BaseModel, Field

# --- Pydantic Schemas for Input and Output ---

class TextSQLInput(BaseModel):
    """Input schema for the Text-to-SQL tool."""
    question: str = Field(..., description="The natural language question to be converted to SQL.")
    # schema_description: Optional[str] = None # The user might provide this, or the tool might load a predefined schema.
    # For initial implementation, the tool might use a fixed, known schema for a specific database.
    # If dynamic schemas are needed, this input might change or be handled internally.
    db_identifier: Optional[str] = Field(None, description="Optional identifier for a specific pre-configured database schema to use.")

class TextSQLOutput(BaseModel):
    """Output schema for the Text-to-SQL tool."""
    generated_sql: str = Field(..., description="The SQL query generated from the natural language question.")
    query_result: Optional[Any] = Field(None, description="The result of executing the SQL query. Could be a list of tuples, a stringified table, or a summary.")
    error: Optional[str] = None

# --- General Input to select the type of TextSQL action (if more actions are added later) ---
# For now, a single action (query execution) is assumed for the tool.
# class TextSQLActionInput(BaseModel):
#     action: str = Field(..., description="Action to perform: generate_and_execute_sql")
#     parameters: Dict[str, Any]

# --- Placeholder for Core Tool Logic & Langchain Integration --- 
# Actual implementation will use Langchain Text2SQLChain or similar, 
# and connect to an in-memory SQLite or DuckDB with a predefined schema.
# This will be filled in during the implementation step for this tool.

