# /home/ubuntu/chatbot_project/tools/magnet.py
import requests # Will be used when actual scraping is implemented
import json 
from typing import Optional, Dict, Any, List, Type
from pydantic import BaseModel, Field, HttpUrl, ValidationError, constr, field_validator
from langchain.tools import Tool
import functools

# --- Pydantic Schemas for Magnet Fetcher Tool ---
class MagnetInput(BaseModel):
    query: str = Field(..., description="The name of the movie or show to search for a magnet link.")

    class Config:
        extra = "forbid"

class MagnetResultItem(BaseModel):
    title: str = Field(..., description="Title of the torrent.")
    magnet_link: str = Field(..., description="The magnet URI.")
    seeders: Optional[int] = Field(None, ge=0, description="Number of seeders.")
    leechers: Optional[int] = Field(None, ge=0, description="Number of leechers.")
    size: Optional[str] = Field(None, description="Size of the torrent (e.g., 1.2 GB).")
    source_site: Optional[str] = Field(None, description="Website from which the torrent was fetched (e.g., 1337x.to).")

    @field_validator("magnet_link")
    def validate_magnet_link(cls, v):
        import re
        pattern = r"^magnet:\?xt=urn:(btih|sha1):[a-zA-Z0-9]{32,}"
        if not re.match(pattern, v):
            raise ValueError("Invalid magnet link format")
        return v

class MagnetOutput(BaseModel):
    query: str = Field(..., description="The original search query.")
    results: Optional[List[MagnetResultItem]] = Field(None, description="A list of found magnet links and their details, ordered by relevance (e.g., most seeders).")
    best_match: Optional[MagnetResultItem] = Field(None, description="The best matching magnet link based on criteria (e.g., most seeders, then quality).")
    error: Optional[str] = Field(None, description="Error message if fetching magnet links failed.")
    details: Optional[str] = Field(None, description="Additional details for errors.")

    class Config:
        extra = "forbid"

# --- Core Tool Logic (Placeholder - to be fully implemented later) ---
def _run_magnet_logic(inp: MagnetInput, api_keys: Dict[str, str], config: Any) -> MagnetOutput:
    """
    Internal logic for fetching torrent magnet links for a given movie/show name.
    Actual scraping logic will be implemented in Phase 4.
    """
    query = inp.query

    if config.DEBUG_MODE:
        print(f"--- tools/magnet.py (_run_magnet_logic) --- Fetching magnet links for query: {query}")

    # Placeholder logic - actual scraping from 1337x.to or YTS.mx using requests and BeautifulSoup will be in a later step.
    if query.lower() == "the matrix": # Example success case
        example_result_item = MagnetResultItem(
            title="The Matrix 1999 1080p BluRay x264",
            magnet_link="magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567",
            seeders=1200,
            leechers=300,
            size="2.2 GB",
            source_site="example.com"
        )
        return MagnetOutput(query=query, results=[example_result_item], best_match=example_result_item)
    elif "nonexistent movie 123xyz" in query.lower(): # Example no results case
        return MagnetOutput(query=query, results=[], error="No magnet links found for this query (placeholder).", details="Scraping might not have found any matches or the title is incorrect.")
    elif "error scrape movie" in query.lower(): # Example scraping error case
        return MagnetOutput(query=query, error="Simulated error during scraping process (placeholder).")
    else:
        # Generic placeholder for other queries
        return MagnetOutput(query=query, results=[], error="Magnet link fetching is not fully implemented yet for this query (placeholder).", details="The actual scraping logic for this title has not been run.")

# --- Langchain Tool Definition ---
def _magnet_langchain_adapter(query: str, api_keys_instance: Dict[str, str], config_instance: Any) -> str:
    try:
        inp = MagnetInput(query=query)
    except ValidationError as e:
        error_output = MagnetOutput(query=query, error="Input validation failed", details=str(e))
        return error_output.model_dump_json()
    
    output = _run_magnet_logic(inp, api_keys_instance, config_instance)
    return output.model_dump_json()

def get_magnet_fetcher_langchain_tool(api_keys_instance: Dict[str, str], config_instance: Any) -> Tool:
    """Returns a Langchain Tool instance for fetching magnet links."""
    func_with_context = functools.partial(
        _magnet_langchain_adapter, 
        api_keys_instance=api_keys_instance, 
        config_instance=config_instance
    )
    
    return Tool(
        name="magnet_link_fetcher",
        func=func_with_context,
        description="Fetches torrent magnet links for a given movie or show name. Input should be the name of the content. Returns a JSON string with magnet link details or an error.",
        args_schema=MagnetInput,
    )

# --- Direct callable function for app.py (if needed) ---
def run_magnet_tool_direct(args_dict: dict, api_keys: Dict[str, str], config: Any) -> dict:
    try:
        inp = MagnetInput(**args_dict)
    except ValidationError as e:
        return MagnetOutput(query=args_dict.get("query", "N/A"), error="Input validation failed", details=str(e)).model_dump()
    
    output = _run_magnet_logic(inp, api_keys, config)
    return output.model_dump()

if __name__ == "__main__":
    class DummyConfig:
        DEBUG_MODE = True
        # Add other config attributes if _run_magnet_logic expects them

    dummy_config_instance = DummyConfig()
    dummy_api_keys_instance = {} # Not typically used by this tool unless a specific API is involved

    print("--- Testing Magnet Fetcher Tool (Success Example) via Langchain Tool Adapter ---")
    lc_magnet_tool = get_magnet_fetcher_langchain_tool(dummy_api_keys_instance, dummy_config_instance)
    try:
        result_json_str = lc_magnet_tool.func(query="The Matrix")
        print(json.dumps(json.loads(result_json_str), indent=2))
    except Exception as e:
        print(f"Error during Langchain tool direct func call: {e}")

    print("\n--- Testing Magnet Fetcher Tool (No Results Example) via Langchain Tool Adapter ---")
    try:
        result_json_str_nonexistent = lc_magnet_tool.func(query="nonexistent movie 123xyz")
        print(json.dumps(json.loads(result_json_str_nonexistent), indent=2))
    except Exception as e:
        print(f"Error during Langchain tool direct func call: {e}")

    print("\n--- Testing Magnet Fetcher Tool (Invalid Input to Pydantic model directly) ---")
    try:
        invalid_input = MagnetInput(search_term="test") # type: ignore
    except ValidationError as e:
        print(f"Caught expected validation error for Pydantic model: {e}")

    print("\n--- Testing run_magnet_tool_direct (Example: The Matrix) ---")
    direct_result_matrix = run_magnet_tool_direct({"query": "The Matrix"}, dummy_api_keys_instance, dummy_config_instance)
    print(json.dumps(direct_result_matrix, indent=2))

    print("\n--- Testing run_magnet_tool_direct (Invalid Input) ---")
    direct_invalid_result = run_magnet_tool_direct({"search_term": "test"}, dummy_api_keys_instance, dummy_config_instance)
    print(json.dumps(direct_invalid_result, indent=2))

