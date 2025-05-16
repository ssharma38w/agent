# /home/ubuntu/chatbot_project/tools/imdb_tool.py
"""
Tool for fetching movie/show information from IMDB using cinemagoer (IMDbPY).
OMDb API can be an alternative if an API key is provided.
"""
import json
from typing import List, Optional, Callable, Any
from pydantic import BaseModel, HttpUrl, Field, ValidationError
from langchain_core.tools import Tool

# IMDbPY uses cinemagoer
from imdb import Cinemagoer

from .. import config # For debug mode and API key file path

# --- Pydantic Schemas for Input and Output ---
class IMDBInput(BaseModel):
    """Input schema for the IMDB + Live Data tool."""
    query: Optional[str] = Field(None, description="The movie or show title to search for. If None, fetches top/trending movies.")
    max_results: int = Field(5, description="Maximum number of results to return for searches or top lists.", ge=1, le=25)
    # type: Optional[str] = Field("movie", description="Type of media: movie, series, episode. Not fully implemented yet.")

class IMDBEntry(BaseModel):
    """Schema for a single IMDB entry (movie, show, etc.)."""
    title: str
    year: Optional[str] = None
    rating: Optional[str] = None # e.g., "8.5/10"
    kind: Optional[str] = None # e.g., "movie", "tv series"
    imdb_id: Optional[str] = None
    link: Optional[HttpUrl] = None # Link to the IMDB page
    # plot: Optional[str] = None
    # poster_url: Optional[HttpUrl] = None

class IMDBOutput(BaseModel):
    """Output schema for the IMDB + Live Data tool."""
    results: List[IMDBEntry] = Field(default_factory=list)
    error: Optional[str] = None
    message: Optional[str] = None

# --- Core Tool Logic ---

OMDB_API_KEY = None
try:
    with open(config.API_KEYS_FILE, "r") as f:
        api_keys_content = json.load(f)
        OMDB_API_KEY = api_keys_content.get("OMDB_API_KEY")
except FileNotFoundError:
    if config.DEBUG_MODE:
        print(f"--- imdb_tool.py --- API keys file not found at {config.API_KEYS_FILE}. OMDb API will not be available.")
except json.JSONDecodeError:
    if config.DEBUG_MODE:
        print(f"--- imdb_tool.py --- Error decoding API keys file {config.API_KEYS_FILE}. OMDb API may not be available.")
except Exception as e:
    if config.DEBUG_MODE:
        print(f"--- imdb_tool.py --- An unexpected error occurred while loading OMDb API key: {e}")

if not OMDB_API_KEY and config.DEBUG_MODE:
    print("--- imdb_tool.py --- OMDb API key not found or not configured. Will primarily use cinemagoer (IMDbPY).")

# Initialize Cinemagoer (IMDbPY)
ia = Cinemagoer()

def _fetch_from_imdbpy(query: Optional[str], max_results: int) -> IMDBOutput:
    try:
        if config.DEBUG_MODE:
            print(f"--- imdb_tool.py (_fetch_from_imdbpy) --- Query: {query}, Max Results: {max_results}")
        
        results_list = []
        if query:
            # Search for a specific movie/show
            search_results = ia.search_movie(query)
            movies_to_process = search_results[:max_results]
        else:
            # Fetch top movies (e.g., top 250)
            # Note: get_top250_movies() returns a list of Movie objects directly
            top_movies = ia.get_top250_movies() # This can be slow as it fetches details for all 250
            if not top_movies:
                 # Fallback or alternative if top250 is too slow or fails
                 # For example, search for popular movies, though this is less defined by imdbpy directly
                 # For now, if top_movies fails, we return an empty list or error.
                 return IMDBOutput(results=[], message="Could not fetch top movies list from IMDbPY.")
            movies_to_process = top_movies[:max_results]

        for movie_obj in movies_to_process:
            # For search_results, we might need to fetch more details if not already present
            # For top_movies, details are usually fetched by the get_top250_movies call.
            # However, to be safe and consistent, let's try to update the movie object to get more details.
            # This can be slow if done for many items.
            try:
                # ia.update(movie_obj) # This fetches more details. Can be slow.
                # For performance, let's try to use what's available first.
                # If essential details are missing, then consider ia.update().
                # For now, we assume basic details are available or ia.update() is implicitly handled for top lists.
                
                title = movie_obj.get(\"title\")
                year = str(movie_obj.get(\"year\")) if movie_obj.get(\"year\") else None
                rating_val = movie_obj.get(\"rating\")
                rating_str = f"{rating_val}/10" if rating_val else None
                kind = movie_obj.get(\"kind\")
                imdb_id = movie_obj.movieID
                imdb_url = f"https://www.imdb.com/title/tt{imdb_id}/" if imdb_id else None

                entry = IMDBEntry(
                    title=title if title else "N/A",
                    year=year,
                    rating=rating_str,
                    kind=kind,
                    imdb_id=imdb_id,
                    link=imdb_url
                )
                results_list.append(entry)
            except Exception as item_e:
                if config.DEBUG_MODE:
                    print(f"--- imdb_tool.py --- Error processing IMDbPY movie object {movie_obj.get('title', 'Unknown')}: {item_e}")
                continue # Skip this item
        
        if not results_list:
            return IMDBOutput(results=[], message=f"No results found for query: 
Query: 
{query} via IMDbPY (cinemagoer)." if query else "No top movies found via IMDbPY.")
        return IMDBOutput(results=results_list, message=f"Successfully fetched {len(results_list)} results via IMDbPY (cinemagoer).")

    except Exception as e:
        if config.DEBUG_MODE:
            import traceback
            print(f"--- imdb_tool.py (_fetch_from_imdbpy) --- Error: {e}")
            traceback.print_exc()
        return IMDBOutput(results=[], error=f"An error occurred with IMDbPY (cinemagoer): {str(e)}")

# Placeholder for OMDb API logic (if to be implemented as primary or fallback)
# def _fetch_from_omdb(query: str, max_results: int) -> IMDBOutput:
#     if not OMDB_API_KEY:
#         return IMDBOutput(results=[], error="OMDb API key not configured.")
#     # ... implementation using requests to OMDb API ...
#     return IMDBOutput(results=[], message="OMDb logic not yet implemented.")


def _run_imdb_search(query: Optional[str], max_results: int) -> IMDBOutput:
    # Prioritize IMDbPY (cinemagoer) as it doesn't require an API key from the user by default
    if config.DEBUG_MODE:
        print("--- imdb_tool.py --- Using IMDbPY (cinemagoer).")
    imdbpy_result = _fetch_from_imdbpy(query, max_results)
    
    # If OMDb was a primary option and IMDbPY failed, could call it here.
    # if not imdbpy_result.results and OMDB_API_KEY:
    #     if config.DEBUG_MODE:
    #         print("--- imdb_tool.py --- IMDbPY failed, trying OMDb API.")
    #     return _fetch_from_omdb(query, max_results)
        
    return imdbpy_result

# --- Langchain Tool Integration ---
def imdb_tool_adapter(tool_input: dict) -> str:
    try:
        if isinstance(tool_input, str):
            # If planner sends a simple string, assume it's the query
            validated_input = IMDBInput(query=tool_input)
        elif isinstance(tool_input, dict):
            validated_input = IMDBInput(**tool_input)
        else:
            return IMDBOutput(error="Invalid input type for IMDB tool. Expected dict or string.").model_dump_json()
        
        result = _run_imdb_search(query=validated_input.query, max_results=validated_input.max_results)
        return result.model_dump_json()
    except ValidationError as ve:
        return IMDBOutput(error=f"Input validation error: {str(ve)}").model_dump_json()
    except Exception as e:
        if config.DEBUG_MODE:
            print(f"--- imdb_tool.py (adapter) --- Unexpected error: {e}")
        return IMDBOutput(error=f"An unexpected error occurred in IMDB tool adapter: {str(e)}").model_dump_json()

IMDB_TOOL_DESCRIPTION = (
    "Fetches movie or TV show information from IMDb. "
    "If a query (title) is provided, it searches for that title. "
    "If no query is provided, it attempts to fetch a list of top/trending movies. "
    "Input should be a JSON object with an optional \'query\' (string) and an optional \'max_results\' (integer, default 5)."
)

imdb_langchain_tool = Tool(
    name="imdb_search",
    func=imdb_tool_adapter,
    description=IMDB_TOOL_DESCRIPTION,
    args_schema=IMDBInput
)

def get_imdb_langchain_tool(api_keys: Optional[dict] = None, cfg: Optional[Any] = None) -> Tool:
    # OMDb API key could be passed via api_keys if that integration is activated
    return imdb_langchain_tool

# --- Direct Test (for development) ---
if __name__ == "__main__":
    print("--- Testing IMDB Tool Directly (using IMDbPY/cinemagoer) ---")
    
    # Test Case 1: Search for a specific movie
    print("\n--- Test Case 1: Specific Movie Query ---")
    test_input_1 = IMDBInput(query="The Matrix", max_results=2)
    output_1_json_str = imdb_tool_adapter(test_input_1.model_dump())
    output_1 = IMDBOutput.model_validate_json(output_1_json_str)
    print(f"Input: {test_input_1.model_dump_json(indent=2)}")
    print(f"Output: {output_1.model_dump_json(indent=2)}")
    if output_1.results:
        for item in output_1.results:
            print(f"  Title: {item.title} ({item.year}), Rating: {item.rating}, Kind: {item.kind}, Link: {item.link}")
    else:
        print(f"  Message: {output_1.message}")
        print(f"  Error: {output_1.error}")

    # Test Case 2: Fetch top/trending movies (query=None)
    # This can be slow as get_top250_movies() fetches a lot of data.
    print("\n--- Test Case 2: Top/Trending Movies (Query is None) - This might take a moment ---")
    test_input_2 = IMDBInput(query=None, max_results=3)
    output_2_json_str = imdb_tool_adapter(test_input_2.model_dump())
    output_2 = IMDBOutput.model_validate_json(output_2_json_str)
    print(f"Input: {test_input_2.model_dump_json(indent=2)}")
    print(f"Output: {output_2.model_dump_json(indent=2)}")
    if output_2.results:
        for item in output_2.results:
            print(f"  Title: {item.title} ({item.year}), Rating: {item.rating}, Kind: {item.kind}, Link: {item.link}")
    else:
        print(f"  Message: {output_2.message}")
        print(f"  Error: {output_2.error}")

    # Test Case 3: Query that might not yield results
    print("\n--- Test Case 3: Non-existent Movie Query ---")
    test_input_3 = IMDBInput(query="ThisMovieDoesNotExistXYZ123", max_results=2)
    output_3_json_str = imdb_tool_adapter(test_input_3.model_dump())
    output_3 = IMDBOutput.model_validate_json(output_3_json_str)
    print(f"Input: {test_input_3.model_dump_json(indent=2)}")
    print(f"Output: {output_3.model_dump_json(indent=2)}")
    if not output_3.results:
        print(f"  Message: {output_3.message}")
        print(f"  Error: {output_3.error}")

    print("\n--- IMDB Tool direct test complete. ---")

