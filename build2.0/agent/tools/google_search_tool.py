# /home/ubuntu/chatbot_project/tools/google_search_tool.py
"""
Tool for performing advanced Google searches using Google Custom Search API or DuckDuckGo.
"""
import requests
import json
from typing import List, Optional, Callable, Any
from pydantic import BaseModel, HttpUrl, Field, ValidationError
from langchain_core.tools import Tool
from googleapiclient.discovery import build # For Google Custom Search API
from duckduckgo_search import DDGS # For DuckDuckGo fallback

from .. import config # For debug mode and API key file path

# --- Pydantic Schemas for Input and Output ---
class GoogleSearchInput(BaseModel):
    """Input schema for the Advanced Google Search tool."""
    query: str = Field(..., description="The search query.")
    num_results: int = Field(3, description="Number of results to return.", ge=1, le=10) # Google CSE max is 10 per query

class SearchResult(BaseModel):
    """Schema for a single search result entry."""
    title: str
    url: HttpUrl # Ensures link is a valid URL
    snippet: Optional[str] = None

class GoogleSearchOutput(BaseModel):
    """Output schema for the Advanced Google Search tool."""
    results: List[SearchResult] = Field(default_factory=list)
    error: Optional[str] = None
    message: Optional[str] = None
    search_engine_used: Optional[str] = None # To indicate which engine was used

# --- Core Tool Logic ---

GOOGLE_API_KEY = "AIzaSyBbEbHZdvIq14KRCRxi4GkpHYwj4Tsbx-g"
GOOGLE_CSE_ID = "Project-1:0b8f2c3a4d5e4c7a" # Example CSE ID, replace with your own

try:
    with open(config.API_KEYS_FILE, "r") as f:
        api_keys_content = json.load(f)
        GOOGLE_API_KEY = api_keys_content.get("GOOGLE_API_KEY")
        GOOGLE_CSE_ID = api_keys_content.get("GOOGLE_CSE_ID")
except FileNotFoundError:
    if config.DEBUG_MODE:
        print(f"--- google_search_tool.py --- API keys file not found at {config.API_KEYS_FILE}. Google CSE will not be available.")
except json.JSONDecodeError:
    if config.DEBUG_MODE:
        print(f"--- google_search_tool.py --- Error decoding API keys file {config.API_KEYS_FILE}. Google CSE may not be available.")
except Exception as e:
    if config.DEBUG_MODE:
        print(f"--- google_search_tool.py --- An unexpected error occurred while loading Google CSE keys: {e}")

if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
    if config.DEBUG_MODE:
        print("--- google_search_tool.py --- Google API Key or CSE ID not found/configured. Will rely on DuckDuckGo fallback.")

def _fetch_from_google_cse(query: str, num_results: int) -> GoogleSearchOutput:
    if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
        return GoogleSearchOutput(results=[], error="Google Custom Search API key or CSE ID not configured.", search_engine_used="None")
    try:
        if config.DEBUG_MODE:
            print(f"--- google_search_tool.py (_fetch_from_google_cse) --- Query: {query}, Num Results: {num_results}")
        
        service = build("customsearch", "v1", developerKey=GOOGLE_API_KEY)
        raw_results = service.cse().list(
            q=query,
            cx=GOOGLE_CSE_ID,
            num=num_results # Number of search results to return (1-10)
        ).execute()

        search_items = raw_results.get("items", [])
        output_results = []
        for item in search_items:
            try:
                result = SearchResult(
                    title=item.get("title"),
                    url=item.get("link"),
                    snippet=item.get("snippet")
                )
                output_results.append(result)
            except ValidationError as ve_item:
                 if config.DEBUG_MODE:
                    print(f"--- google_search_tool.py --- Validation error for Google CSE item: {ve_item}. Item: {item}")
        
        if not output_results and not search_items:
             return GoogleSearchOutput(results=[], message=f"No results found for query: {query} via Google CSE.", search_engine_used="Google Custom Search")
        return GoogleSearchOutput(results=output_results, message=f"Successfully fetched {len(output_results)} results via Google Custom Search.", search_engine_used="Google Custom Search")

    except Exception as e:
        if config.DEBUG_MODE:
            import traceback
            print(f"--- google_search_tool.py (_fetch_from_google_cse) --- Error: {e}")
            traceback.print_exc()
        return GoogleSearchOutput(results=[], error=f"An error occurred with Google Custom Search API: {str(e)}", search_engine_used="Google Custom Search")

def _fetch_from_duckduckgo(query: str, num_results: int) -> GoogleSearchOutput:
    try:
        if config.DEBUG_MODE:
            print(f"--- google_search_tool.py (_fetch_from_duckduckgo) --- Query: {query}, Num Results: {num_results}")
        
        results_list = []
        with DDGS() as ddgs:
            ddgs_results = ddgs.text(query, max_results=num_results)
            for r in ddgs_results:
                try:
                    result = SearchResult(
                        title=r.get("title"),
                        url=r.get("href"),
                        snippet=r.get("body")
                    )
                    results_list.append(result)
                except ValidationError as ve_item:
                    if config.DEBUG_MODE:
                        print(f"--- google_search_tool.py --- Validation error for DDG item: {ve_item}. Item: {r}")
        
        if not results_list:
            return GoogleSearchOutput(results=[], message=f"No results found for query: {query} via DuckDuckGo.", search_engine_used="DuckDuckGo")
        return GoogleSearchOutput(results=results_list, message=f"Successfully fetched {len(results_list)} results via DuckDuckGo.", search_engine_used="DuckDuckGo")

    except Exception as e:
        if config.DEBUG_MODE:
            import traceback
            print(f"--- google_search_tool.py (_fetch_from_duckduckgo) --- Error: {e}")
            traceback.print_exc()
        return GoogleSearchOutput(results=[], error=f"An error occurred with DuckDuckGo search: {str(e)}", search_engine_used="DuckDuckGo")

def _run_google_search(query: str, num_results: int = 3) -> GoogleSearchOutput:
    if GOOGLE_API_KEY and GOOGLE_CSE_ID:
        if config.DEBUG_MODE:
            print("--- google_search_tool.py --- Attempting Google Custom Search API first.")
        gcs_result = _fetch_from_google_cse(query, num_results)
        # If GCS has results or a definitive error (not just config error), return it.
        if gcs_result.results or (gcs_result.error and "configured" not in gcs_result.error.lower()):
            return gcs_result
        if config.DEBUG_MODE and gcs_result.error:
             print(f"--- google_search_tool.py --- Google CSE failed or not configured, error: {gcs_result.error}. Falling back to DuckDuckGo.")
    
    if config.DEBUG_MODE:
        print("--- google_search_tool.py --- Using DuckDuckGo fallback for Google Search.")
    return _fetch_from_duckduckgo(query, num_results)

# --- Langchain Tool Integration ---
def google_search_tool_adapter(tool_input: dict) -> str:
    try:
        if isinstance(tool_input, str):
            validated_input = GoogleSearchInput(query=tool_input)
        elif isinstance(tool_input, dict):
            validated_input = GoogleSearchInput(**tool_input)
        else:
            return GoogleSearchOutput(error="Invalid input type for Google Search tool. Expected dict or string.").model_dump_json()
        
        result = _run_google_search(query=validated_input.query, num_results=validated_input.num_results)
        return result.model_dump_json()
    except ValidationError as ve:
        return GoogleSearchOutput(error=f"Input validation error: {str(ve)}").model_dump_json()
    except Exception as e:
        if config.DEBUG_MODE:
            print(f"--- google_search_tool.py (adapter) --- Unexpected error: {e}")
        return GoogleSearchOutput(error=f"An unexpected error occurred in Google Search tool adapter: {str(e)}").model_dump_json()

GOOGLE_SEARCH_TOOL_DESCRIPTION = (
    "Performs a web search using Google Custom Search API if configured, otherwise falls back to DuckDuckGo. "
    "Useful for finding general information, websites, or answers to questions. "
    "Input should be a JSON object with \'query\' (string, required) and \'num_results\' (integer, optional, default 3, max 10)."
)

google_search_langchain_tool = Tool(
    name="google_search",
    func=google_search_tool_adapter,
    description=GOOGLE_SEARCH_TOOL_DESCRIPTION,
    args_schema=GoogleSearchInput
)

def get_google_search_langchain_tool(api_keys: Optional[dict] = None, cfg: Optional[Any] = None) -> Tool:
    # This tool now loads its own API keys from config.json
    return google_search_langchain_tool

# --- Direct Test (for development) ---
if __name__ == "__main__":
    print("--- Testing Google Search Tool Directly ---")
    # To test Google CSE, ensure GOOGLE_API_KEY and GOOGLE_CSE_ID are in your config.json
    # Otherwise, it will use DuckDuckGo.

    test_queries = ["latest AI research papers", "weather in London today"]
    
    for t_query in test_queries:
        print(f"\n--- Query: {t_query} ---")
        test_input = GoogleSearchInput(query=t_query, num_results=2)
        output_json_str = google_search_tool_adapter(test_input.model_dump())
        output = GoogleSearchOutput.model_validate_json(output_json_str)
        
        print(f"Input: {test_input.model_dump_json(indent=2)}")
        print(f"Output: {output.model_dump_json(indent=2)}")
        print(f"Search Engine Used: {output.search_engine_used}")

        if output.results:
            for res in output.results:
                print(f"  Title: {res.title}")
                print(f"  URL: {res.url}")
                print(f"  Snippet: {res.snippet}")
        elif output.error:
            print(f"  Error: {output.error}")
        else:
            print(f"  Message: {output.message}")

    print("\n--- Google Search Tool direct test complete. ---")

