# /home/ubuntu/chatbot_project/tools/web_search.py
import requests
import json
from typing import Optional, Dict, Any, Type
from pydantic import BaseModel, Field, HttpUrl, ValidationError
from langchain.tools import Tool
import functools
import logging


logger = logging.getLogger(__name__)

# --- Pydantic Schemas for WebSearch Tool ---
class WebSearchInput(BaseModel):
    query: str = Field(..., description="The search query.")

    class Config:
        extra = "forbid"
        # Pydantic V2 by default performs type coercion. For strict validation:
        # strict = True # This is a Pydantic V1 config.
        # For Pydantic V2, use specific Strict types (StrictStr, StrictInt) or custom validators if needed.
        # User requested strict=True in dev. For now, standard Pydantic V2 validation is used.
        # The executor should catch ValidationError and handle it.

class WebSearchOutput(BaseModel):
    provider: str = Field(..., description="The search provider used (e.g., DuckDuckGo, SerpAPI).")
    summary: Optional[str] = Field(None, description="The summary of the search result.")
    source: Optional[HttpUrl] = Field(None, description="The source URL of the search result.")
    error: Optional[str] = Field(None, description="Error message if the search failed.")
    details: Optional[str] = Field(None, description="Additional details for errors or results.")

    class Config:
        extra = "forbid"

# --- Core Tool Logic ---
def _run_web_search_logic(inp: WebSearchInput, api_keys: Dict[str, str], config: Any) -> WebSearchOutput:
    """
    Internal logic for performing a web search.
    """
    query = inp.query
    provider = config.WEB_SEARCH_PROVIDER

    if config.DEBUG_MODE:
        print(f"--- tools/web_search.py (_run_web_search_logic) --- Provider: {provider}, Query: {query}")

    try:
        if provider == "duckduckgo":
            ddg_url = f"https://api.duckduckgo.com/?q={requests.utils.quote(query)}&format=json&no_html=1&skip_disambig=1"
            response = requests.get(ddg_url, timeout=10)
            response.raise_for_status()
            data = response.json()

            summary, source_url_str = None, None
            if data.get("AbstractText"):
                summary = data["AbstractText"]
                source_url_str = data.get("AbstractURL")
            elif data.get("Heading") and data.get("Type") == "A":
                summary = data["Heading"]
                source_url_str = data.get("AbstractURL")
            elif data.get("RelatedTopics") and data["RelatedTopics"]:
                first_topic = data["RelatedTopics"][0]
                if first_topic.get("Text"):
                    summary = first_topic["Text"]
                    source_url_str = first_topic.get("FirstURL")
            elif data.get("Results") and data["Results"]:
                first_result = data["Results"][0]
                summary = first_result.get("Text")
                source_url_str = first_result.get("FirstURL")
            
            validated_source_url = None
            if source_url_str:
                try:
                    validated_source_url = HttpUrl(source_url_str) # type: ignore
                except ValidationError:
                    if config.DEBUG_MODE:
                        print(f"Warning: Invalid URL from DuckDuckGo API: {source_url_str}")
            
            if summary:
                return WebSearchOutput(provider="DuckDuckGo", summary=summary, source=validated_source_url)
            else:
                return WebSearchOutput(provider="DuckDuckGo", error="No clear answer found via DuckDuckGo.", details="Try rephrasing or use a different search tool/keyword.")

        elif provider == "serpapi":
            serpapi_key = api_keys.get("SERPAPI_API_KEY")
            if not serpapi_key:
                return WebSearchOutput(provider="SerpAPI", error="SerpAPI key not found in configuration.")
            
            serpapi_url = "https://serpapi.com/search"
            params = {"q": query, "api_key": serpapi_key, "engine": "google"}
            response = requests.get(serpapi_url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            # logger.info(f"SerpAPI response: {data}") # Log the SerpAPI response for debugging

            summaries = []
            source_urls = []

            # Answer box (if present)
            if data.get("answer_box") and data["answer_box"].get("answer"):
                summaries.append(data["answer_box"]["answer"])
                if data["answer_box"].get("link"):
                    source_urls.append(data["answer_box"]["link"])

            # Organic results (all, not just first)
            if data.get("organic_results") and data["organic_results"]:
                for result in data["organic_results"]:
                    snippet = result.get("snippet")
                    link = result.get("link")
                    if snippet:
                        summaries.append(snippet)
                    if link:
                        source_urls.append(link)

            summary = "\n\n".join(summaries) if summaries else None
            logger.info(f"SerpAPI summary: {summary}") # Log the summary for debugging
            # Optionally, join URLs or just use the first as 'source'
            source_url_str = source_urls[0] if source_urls else None

            validated_source_url = None
            if source_url_str:
                try:
                    validated_source_url = HttpUrl(source_url_str) # type: ignore
                except ValidationError:
                    if config.DEBUG_MODE:
                        print(f"Warning: Invalid URL from SerpAPI: {source_url_str}")

            if summary:
                # Optionally, you can add all URLs as details or extend the schema to return all sources
                return WebSearchOutput(
                    provider=f"SerpAPI (All Results)",
                    summary=summary,
                    source=validated_source_url,
                    details="; ".join(source_urls) if len(source_urls) > 1 else None
                )
            else:
                return WebSearchOutput(provider="SerpAPI", error="No clear answer found via SerpAPI.")
        else:
            return WebSearchOutput(provider=provider, error=f"Unsupported web search provider: {provider}")

    except requests.exceptions.Timeout:
        return WebSearchOutput(provider=provider, error=f"Search request timed out for provider: {provider}.")
    except requests.exceptions.RequestException as e:
        return WebSearchOutput(provider=provider, error=f"Failed to fetch search results from {provider}: {str(e)}")
    except json.JSONDecodeError:
        return WebSearchOutput(provider=provider, error=f"Failed to parse JSON response from {provider}.")
    except ValidationError as e: # Should be caught before if input is validated first
        return WebSearchOutput(provider=provider, error="Invalid data format for search input/output.", details=str(e))
    except Exception as e:
        return WebSearchOutput(provider=provider, error=f"An unexpected error occurred in web search tool: {str(e)}")

# --- Langchain Tool Definition ---
# This is the function that the Langchain Tool will wrap.
# It matches the fields in WebSearchInput and returns a JSON string of WebSearchOutput.
def _web_search_langchain_adapter(query: str, api_keys_instance: Dict[str, str], config_instance: Any) -> str:
    try:
        inp = WebSearchInput(query=query)
    except ValidationError as e:
        # This path should ideally be hit by the executor validating before calling the tool func
        error_output = WebSearchOutput(provider="N/A", error="Input validation failed", details=str(e))
        return error_output.model_dump_json()
    
    output = _run_web_search_logic(inp, api_keys_instance, config_instance)
    return output.model_dump_json()

def get_web_search_langchain_tool(api_keys_instance: Dict[str, str], config_instance: Any) -> Tool:
    """Returns a Langchain Tool instance for web search, configured with API keys and app config."""
    # Use functools.partial to bake in api_keys and config for the adapter function
    func_with_context = functools.partial(
        _web_search_langchain_adapter, 
        api_keys_instance=api_keys_instance, 
        config_instance=config_instance
    )
    
    return Tool(
        name="web_search",
        func=func_with_context, # The adapter function with context baked in
        description="Performs a web search using DuckDuckGo or SerpAPI to find information. Input should be a search query. Returns a JSON string with summary, source, and provider, or an error.",
        args_schema=WebSearchInput, # Pydantic model for input validation by Langchain
        # return_direct=False # Default, means output goes to LLM. True means output is final answer.
    )

# --- Original run_web_search_tool for app.py direct call (if needed, or refactor app.py to use the Tool object) ---
# For now, app.py will be updated to use the Langchain Tool definition and its Pydantic schema.
# The function below is kept for direct testing or if a non-Langchain path is still desired.
# It's better to unify, so app.py should ideally use the Langchain Tool's args_schema for validation
# and then call a core logic function like _run_web_search_logic.

def run_web_search_tool_direct(args_dict: dict, api_keys: Dict[str, str], config: Any) -> dict:
    """ 
    Callable by app.py, takes dict args, validates with Pydantic, calls core logic, returns dict.
    This is an alternative to app.py directly using the Langchain Tool object for execution.
    """
    try:
        inp = WebSearchInput(**args_dict)
    except ValidationError as e:
        return WebSearchOutput(provider="N/A", error="Input validation failed", details=str(e)).model_dump()
    
    output = _run_web_search_logic(inp, api_keys, config)
    return output.model_dump()


if __name__ == "__main__":
    # Example usage for direct testing
    class DummyConfig:
        DEBUG_MODE = True
        WEB_SEARCH_PROVIDER = "duckduckgo" # or "serpapi"
        API_KEYS_FILE = "../config.json" # Adjust path if testing directly
        # Add other config attributes if _run_web_search_logic or other parts expect them

    dummy_config_instance = DummyConfig()
    dummy_api_keys_instance = {}
    try:
        # This path might be relative to where you run the script from
        with open("../config.json", "r") as f: # Assuming config.json is in parent directory
            dummy_api_keys_instance = json.load(f)
    except Exception as e:
        print(f"Could not load API keys for direct test: {e}")

    print("--- Testing Web Search Tool (DuckDuckGo) via Langchain Tool Adapter ---")
    # Get the configured Langchain tool
    lc_web_search_tool = get_web_search_langchain_tool(dummy_api_keys_instance, dummy_config_instance)
    
    # Simulate Langchain calling the tool's function (which is func_with_context)
    # Langchain would typically parse arguments based on args_schema and pass them as kwargs
    # Here, we call it directly as the func expects `query` as a named argument.
    try:
        result_json_str = lc_web_search_tool.func(query="What is the capital of France?")
        print(json.dumps(json.loads(result_json_str), indent=2))
    except Exception as e:
        print(f"Error during Langchain tool direct func call: {e}")

    print("\n--- Testing Web Search Tool (DuckDuckGo - complex) via Langchain Tool Adapter ---")
    try:
        result_json_str_complex = lc_web_search_tool.func(query="Python programming language")
        print(json.dumps(json.loads(result_json_str_complex), indent=2))
    except Exception as e:
        print(f"Error during Langchain tool direct func call: {e}")

    print("\n--- Testing Web Search Tool (Invalid Input to Pydantic model directly) ---")
    try:
        invalid_input = WebSearchInput(qwerty="test") # type: ignore
    except ValidationError as e:
        print(f"Caught expected validation error for Pydantic model: {e}")

    print("\n--- Testing run_web_search_tool_direct (for potential app.py use) ---")
    direct_result = run_web_search_tool_direct({"query": "Latest AI news"}, dummy_api_keys_instance, dummy_config_instance)
    print(json.dumps(direct_result, indent=2))

    direct_invalid_result = run_web_search_tool_direct({"qwerty": "test"}, dummy_api_keys_instance, dummy_config_instance)
    print(json.dumps(direct_invalid_result, indent=2))


