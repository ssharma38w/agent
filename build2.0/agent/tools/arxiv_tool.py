# /home/ubuntu/chatbot_project/tools/arxiv_tool.py
"""
Tool for fetching academic papers from ArXiv.
"""
import arxiv
from typing import List, Optional, Callable, Any
from pydantic import BaseModel, HttpUrl, Field, ValidationError
from langchain_core.tools import Tool

try:
    from .. import config  # For package usage
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import config  # For direct script usage

# --- Pydantic Schemas for Input and Output ---
class ArxivInput(BaseModel):
    """Input schema for the ArXiv tool."""
    query: str = Field(..., description="The search query for ArXiv.")
    max_results: int = Field(3, description="Maximum number of papers to return.", ge=1, le=20) # Sensible limits

class ArxivPaper(BaseModel):
    """Schema for a single ArXiv paper entry."""
    title: str
    summary: str
    link: HttpUrl # Ensures link is a valid URL
    # authors: List[str] = Field(default_factory=list)
    # published_date: Optional[str] = None

class ArxivOutput(BaseModel):
    """Output schema for the ArXiv tool."""
    papers: List[ArxivPaper] = Field(default_factory=list)
    error: Optional[str] = None
    message: Optional[str] = None

# --- Core Tool Logic ---
def _run_arxiv_search(query: str, max_results: int = 3) -> ArxivOutput:
    """Performs a search on ArXiv and returns formatted results."""
    if config.DEBUG_MODE:
        print(f"--- arxiv_tool.py (_run_arxiv_search) --- Query: {query}, Max Results: {max_results}")
    try:
        # Using the arxiv library
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance # Or SortCriterion.SubmittedDate for most recent
        )
        
        results = list(search.results()) # Execute the search and get results
        
        if not results:
            return ArxivOutput(papers=[], message=f"No papers found for query: {query}")

        papers_list = []
        for result in results:
            # Ensure summary is not excessively long
            summary = result.summary
            if len(summary) > 1000: # Truncate long summaries
                summary = summary[:1000] + "..."
            
            paper_data = ArxivPaper(
                title=result.title,
                summary=summary,
                link=str(result.entry_id) # entry_id is the link to the abstract page
                # authors=[author.name for author in result.authors],
                # published_date=str(result.published.date())
            )
            papers_list.append(paper_data)
        
        return ArxivOutput(papers=papers_list, message=f"Successfully fetched {len(papers_list)} papers.")

    except Exception as e:
        if config.DEBUG_MODE:
            import traceback
            print(f"--- arxiv_tool.py (_run_arxiv_search) --- Error: {e}")
            traceback.print_exc()
        return ArxivOutput(papers=[], error=f"An error occurred while searching ArXiv: {str(e)}")

# --- Langchain Tool Integration ---

# Adapter function for Langchain Tool
def arxiv_tool_adapter(tool_input: dict) -> str:
    """Adapter to connect Pydantic model with Langchain Tool string input/output."""
    try:
        if isinstance(tool_input, str):
            # If planner sends a simple string, assume it's the query and use default max_results
            # This is less ideal as it bypasses Pydantic validation for max_results at input.
            # The planner should ideally send a dict matching ArxivInput.
            if config.DEBUG_MODE:
                print(f"--- arxiv_tool.py (adapter) --- Received string input: {tool_input}. Using default max_results.")
            validated_input = ArxivInput(query=tool_input) 
        elif isinstance(tool_input, dict):
            validated_input = ArxivInput(**tool_input)
        else:
            return ArxivOutput(error="Invalid input type for ArXiv tool. Expected dict or string.").model_dump_json()

        result = _run_arxiv_search(query=validated_input.query, max_results=validated_input.max_results)
        return result.model_dump_json()
    except ValidationError as ve:
        return ArxivOutput(error=f"Input validation error: {str(ve)}").model_dump_json()
    except Exception as e:
        if config.DEBUG_MODE:
            print(f"--- arxiv_tool.py (adapter) --- Unexpected error: {e}")
        return ArxivOutput(error=f"An unexpected error occurred in ArXiv tool adapter: {str(e)}").model_dump_json()

ARXIV_TOOL_DESCRIPTION = (
    "Fetches academic paper summaries from ArXiv.org. "
    "Input should be a JSON object with 'query' (string, required) and 'max_results' (integer, optional, default 3)."
)

# Create the Langchain Tool instance
# Note: The `name` here is what the LLM Planner will use to call the tool.
arxiv_langchain_tool = Tool(
    name="arxiv_search", # Name for the LLM planner
    func=arxiv_tool_adapter, # The adapter function
    description=ARXIV_TOOL_DESCRIPTION,
    args_schema=ArxivInput # Pydantic schema for input validation by Langchain (if its agent framework is used)
)

# Helper function for other modules to get the tool instance
def get_arxiv_langchain_tool(api_keys: Optional[dict] = None, cfg: Optional[Any] = None) -> Tool:
    # api_keys and cfg are not used by this tool but kept for consistency with other tool getters
    return arxiv_langchain_tool

# --- Direct Test (for development) ---
if __name__ == "__main__":
    print("--- Testing ArXiv Tool Directly ---")
    
    # Test Case 1: Valid query
    test_input_1 = ArxivInput(query="quantum computing", max_results=2)
    output_1_json_str = arxiv_tool_adapter(test_input_1.model_dump())
    output_1 = ArxivOutput.model_validate_json(output_1_json_str)
    print(f"Test Case 1 Input: {test_input_1.model_dump_json(indent=2)}")
    print(f"Test Case 1 Output: {output_1.model_dump_json(indent=2)}")
    if output_1.papers:
        for paper in output_1.papers:
            print(f"  Title: {paper.title}")
            print(f"  Link: {paper.link}")
            print(f"  Summary: {paper.summary[:100]}...")
    else:
        print(f"  Message: {output_1.message}")
        print(f"  Error: {output_1.error}")

    print("\n--- Test Case 2: Query that might yield no results ---")
    test_input_2 = ArxivInput(query="nonexistenttopicxyz123abc", max_results=1)
    output_2_json_str = arxiv_tool_adapter(test_input_2.model_dump())
    output_2 = ArxivOutput.model_validate_json(output_2_json_str)
    print(f"Test Case 2 Input: {test_input_2.model_dump_json(indent=2)}")
    print(f"Test Case 2 Output: {output_2.model_dump_json(indent=2)}")
    if output_2.papers:
        print("  Found papers unexpectedly.")
    else:
        print(f"  Message: {output_2.message}")
        print(f"  Error: {output_2.error}")

    print("\n--- Test Case 3: Invalid input (handled by adapter) ---")
    # This test is for the adapter; Pydantic in ArxivInput would catch it earlier if directly used.
    invalid_input_dict = {"quer": "missing y", "max_results": "not_an_int"} 
    output_3_json_str = arxiv_tool_adapter(invalid_input_dict)
    output_3 = ArxivOutput.model_validate_json(output_3_json_str)
    print(f"Test Case 3 Input: {invalid_input_dict}")
    print(f"Test Case 3 Output: {output_3.model_dump_json(indent=2)}")
    assert output_3.error is not None, "Error should be present for invalid input"
    print(f"  Error reported: {output_3.error}")

    print("\n--- ArXiv Tool direct test complete. ---")

