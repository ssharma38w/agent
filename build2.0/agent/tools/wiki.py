# /home/ubuntu/chatbot_project/tools/wiki.py
import requests
import json
from typing import Optional, Dict, Any, Type
from pydantic import BaseModel, Field, HttpUrl, ValidationError
from langchain.tools import Tool
import functools

# --- Pydantic Schemas for Wikipedia Tool ---
class WikiInput(BaseModel):
    topic: str = Field(..., description="The topic to search for on Wikipedia.")

    class Config:
        extra = "forbid"

class WikiOutput(BaseModel):
    title: Optional[str] = Field(None, description="The title of the Wikipedia page found.")
    summary: Optional[str] = Field(None, description="A brief summary of the topic from Wikipedia.")
    source_url: Optional[HttpUrl] = Field(None, description="The URL of the Wikipedia page.")
    error: Optional[str] = Field(None, description="Error message if the search failed.")
    details: Optional[str] = Field(None, description="Additional details for errors.")

    class Config:
        extra = "forbid"

# --- Core Tool Logic ---
def _run_wiki_logic(inp: WikiInput, api_keys: Dict[str, str], config: Any) -> WikiOutput:
    """
    Internal logic for fetching a summary of a topic from Wikipedia.
    """
    topic = inp.topic

    if config.DEBUG_MODE:
        print(f"--- tools/wiki.py (_run_wiki_logic) --- Searching Wikipedia for topic: {topic}")

    api_url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "prop": "extracts|info",
        "exintro": True,
        "explaintext": True,
        "redirects": 1,
        "inprop": "url",
        "titles": topic
    }

    try:
        response = requests.get(api_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        query_data = data.get("query", {})
        pages = query_data.get("pages", {})

        if not pages:
            return WikiOutput(error=f"No data returned from Wikipedia API for topic: {topic}")

        page_id = next(iter(pages))
        if page_id == "-1":
            return WikiOutput(error=f"Could not find a Wikipedia page for topic: {topic}", details="It may not exist or is spelled incorrectly.")

        page_content = pages[page_id]
        title = page_content.get("title")
        extract = page_content.get("extract")
        source_url_str = page_content.get("fullurl")

        if title and extract:
            summary_limit = 1000  # characters
            if len(extract) > summary_limit:
                extract = extract[:summary_limit] + "... (summary truncated)"
            
            validated_source_url = None
            if source_url_str:
                try:
                    validated_source_url = HttpUrl(source_url_str) # type: ignore
                except ValidationError:
                    if config.DEBUG_MODE:
                        print(f"Warning: Invalid URL from Wikipedia API: {source_url_str}")

            return WikiOutput(
                title=title,
                summary=extract.strip(),
                source_url=validated_source_url
            )
        else:
            return WikiOutput(error=f"Could not extract a summary for topic: {topic}", details="The page might be structured differently or be a disambiguation page.")

    except requests.exceptions.Timeout:
        return WikiOutput(error=f"Wikipedia search request timed out for topic: {topic}.")
    except requests.exceptions.RequestException as e:
        return WikiOutput(error=f"Failed to fetch data from Wikipedia for topic {topic}: {str(e)}")
    except json.JSONDecodeError:
        return WikiOutput(error=f"Failed to parse JSON response from Wikipedia for topic: {topic}.")
    except ValidationError as e:
        return WikiOutput(error="Invalid data format for Wikipedia output.", details=str(e))
    except Exception as e:
        return WikiOutput(error=f"An unexpected error occurred in Wikipedia tool for topic {topic}: {str(e)}")

# --- Langchain Tool Definition ---
def _wiki_langchain_adapter(topic: str, api_keys_instance: Dict[str, str], config_instance: Any) -> str:
    try:
        inp = WikiInput(topic=topic)
    except ValidationError as e:
        error_output = WikiOutput(error="Input validation failed", details=str(e))
        return error_output.model_dump_json()
    
    output = _run_wiki_logic(inp, api_keys_instance, config_instance)
    return output.model_dump_json()

def get_wiki_langchain_tool(api_keys_instance: Dict[str, str], config_instance: Any) -> Tool:
    """Returns a Langchain Tool instance for Wikipedia search."""
    func_with_context = functools.partial(
        _wiki_langchain_adapter, 
        api_keys_instance=api_keys_instance, 
        config_instance=config_instance
    )
    
    return Tool(
        name="wikipedia_search", # Changed name to be more specific
        func=func_with_context,
        description="Fetches a summary of a topic from Wikipedia. Input should be the topic name. Returns a JSON string with title, summary, and source URL, or an error.",
        args_schema=WikiInput,
    )

# --- Original run_wiki_tool for app.py direct call (renamed) ---
def run_wiki_tool_direct(args_dict: dict, api_keys: Dict[str, str], config: Any) -> dict:
    """ 
    Callable by app.py, takes dict args, validates with Pydantic, calls core logic, returns dict.
    """
    try:
        inp = WikiInput(**args_dict)
    except ValidationError as e:
        return WikiOutput(error="Input validation failed", details=str(e)).model_dump()
    
    output = _run_wiki_logic(inp, api_keys, config)
    return output.model_dump()

if __name__ == "__main__":
    class DummyConfig:
        DEBUG_MODE = True
        # Add other config attributes if _run_wiki_logic expects them

    dummy_config_instance = DummyConfig()
    dummy_api_keys_instance = {} # Not used by this tool

    print("--- Testing Wikipedia Tool via Langchain Tool Adapter ---")
    lc_wiki_tool = get_wiki_langchain_tool(dummy_api_keys_instance, dummy_config_instance)
    try:
        result_json_str = lc_wiki_tool.func(topic="Artificial Intelligence")
        print(json.dumps(json.loads(result_json_str), indent=2))
    except Exception as e:
        print(f"Error during Langchain tool direct func call: {e}")

    print("\n--- Testing Wikipedia Tool (Non-existent topic) via Langchain Tool Adapter ---")
    try:
        result_json_str_nonexistent = lc_wiki_tool.func(topic="ThisPageShouldHopefullyNotExistOnWikipedia12345")
        print(json.dumps(json.loads(result_json_str_nonexistent), indent=2))
    except Exception as e:
        print(f"Error during Langchain tool direct func call: {e}")

    print("\n--- Testing run_wiki_tool_direct (for potential app.py use) ---")
    direct_result = run_wiki_tool_direct({"topic": "World Wide Web"}, dummy_api_keys_instance, dummy_config_instance)
    print(WikiOutput(**direct_result).model_dump_json(indent=2))

    direct_invalid_result = run_wiki_tool_direct({"topic_name": "test"}, dummy_api_keys_instance, dummy_config_instance)
    print(WikiOutput(**direct_invalid_result).model_dump_json(indent=2))

