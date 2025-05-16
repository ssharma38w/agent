# /home/ubuntu/chatbot_project/tools/cricket_tool.py
"""
Tool for fetching live cricket scores and match status by scraping Cricbuzz.
"""
import requests
from bs4 import BeautifulSoup
from typing import List, Optional, Callable, Any
from pydantic import BaseModel, Field, HttpUrl, ValidationError
from langchain_core.tools import Tool
import json

from .. import config # For debug mode and API key file path

# --- Pydantic Schemas for Input and Output ---
class CricketInput(BaseModel):
    """Input schema for the Cricbuzz / Live Cricket tool."""
    match_type: Optional[str] = Field("all", description="Type of matches to fetch (e.g., \"international\", \"domestic\", \"league\"). Currently supports \"all\".")
    max_results: int = Field(5, description="Maximum number of matches to return.", ge=1, le=15)

class MatchScore(BaseModel):
    """Schema for a single cricket match score entry."""
    match_title: str = Field(..., description="Title of the match, often including series name or type.")
    teams_involved: str = Field(..., description="Teams playing, e.g., \"India vs Australia\".")
    score_summary: str = Field(..., description="Current score summary, e.g., \"IND 150/2 (20.0) | AUS 145/7 (20.0)\".")
    status: str = Field(..., description="Current status of the match, e.g., \"Live\", \"India won by 5 runs\".")
    match_url: Optional[HttpUrl] = Field(None, description="Link to the full match details on Cricbuzz.")

class CricketOutput(BaseModel):
    """Output schema for the Cricbuzz / Live Cricket tool."""
    matches: List[MatchScore] = Field(default_factory=list)
    error: Optional[str] = None
    message: Optional[str] = None

# --- Core Tool Logic ---

# Attempt to load CricAPI key, though scraping is the primary method for now
CRICAPI_KEY = None
try:
    with open(config.API_KEYS_FILE, "r") as f:
        api_keys_content = json.load(f)
        CRICAPI_KEY = api_keys_content.get("CRICAPI_KEY") # User would need to add this if using CricAPI
except FileNotFoundError:
    if config.DEBUG_MODE:
        print(f"--- cricket_tool.py --- API keys file not found at {config.API_KEYS_FILE}. CricAPI will not be available.")
except json.JSONDecodeError:
    if config.DEBUG_MODE:
        print(f"--- cricket_tool.py --- Error decoding API keys file {config.API_KEYS_FILE}. CricAPI may not be available.")
except Exception as e:
    if config.DEBUG_MODE:
        print(f"--- cricket_tool.py --- An unexpected error occurred while loading CricAPI key: {e}")

if not CRICAPI_KEY and config.DEBUG_MODE:
    print("--- cricket_tool.py --- CricAPI key not found or not configured. Will rely on Cricbuzz scraping.")

# Fallback scraping logic for Cricbuzz
CRICBUZZ_LIVE_SCORES_URL = "https://www.cricbuzz.com/cricket-match/live-scores"

def _fetch_from_cricbuzz_scrape(match_type_filter: str, max_results: int) -> CricketOutput:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        if config.DEBUG_MODE:
            print(f"--- cricket_tool.py (_fetch_from_cricbuzz_scrape) --- Fetching from {CRICBUZZ_LIVE_SCORES_URL}")
        response = requests.get(CRICBUZZ_LIVE_SCORES_URL, headers=headers, timeout=15)
        response.raise_for_status() # Raise an exception for HTTP errors

        soup = BeautifulSoup(response.content, "html.parser")
        
        # Cricbuzz structure can change. This is based on a potential structure.
        # Find match containers. This selector needs to be verified and updated by inspecting Cricbuzz.
        # Example: looking for divs with a class that typically wraps a live match item.
        # Common classes might be like 'cb-mtch-lst', 'cb-col-100', 'cb-col', etc.
        # For this example, let's assume a structure like:
        # <div class="cb-lv-main">
        #   <div class="cb-lv-scr-card">
        #     <h3 class="cb-lv-scr-mtch-hdr"><a href="/live-cricket-scores/..." title="...">Match Title (e.g., IND vs AUS, 1st T20I)</a></h3>
        #     <div class="cb-hmscg-bat-txt cb-ovr-flo">...Team1 Score...</div>
        #     <div class="cb-hmscg-bwl-txt cb-ovr-flo">...Team2 Score...</div> (or combined score div)
        #     <div class="cb-text-live">Live</div> or <div class="cb-text-complete">Result</div>
        #   </div>
        # </div>
        
        # Updated selectors based on a more common Cricbuzz structure (needs verification)
        match_cards = soup.select("div.cb-mtch-lst.cb-col.cb-col-100.cb-tms-itm") # A common top-level match item class
        if not match_cards:
            # Fallback to another common structure if the first fails
            match_cards = soup.select("div.cb-col.cb-col-100.cb-lv-main > div[class*='cb-lv-scr-card']")
            if not match_cards:
                 match_cards = soup.select("div.cb-col.cb-col-100.cb-match-list-item") # Yet another possible selector

        if not match_cards and config.DEBUG_MODE:
            print("--- cricket_tool.py --- No match cards found with primary selectors. HTML structure might have changed.")
            # For debugging, save HTML: with open("cricbuzz.html", "w") as f: f.write(soup.prettify())
            return CricketOutput(matches=[], message="Could not find match information on the page. Site structure may have changed.")

        extracted_matches = []
        for card in match_cards:
            if len(extracted_matches) >= max_results:
                break

            title_tag = card.select_one("h3.cb-lv-scr-mtch-hdr a, div.cb-match-list-item-header a") 
            match_title_text = title_tag.get("title") if title_tag else "N/A"
            match_url_path = title_tag["href"] if title_tag and title_tag.has_attr("href") else None
            full_match_url = f"https://www.cricbuzz.com{match_url_path}" if match_url_path else None

            # Teams involved might be part of the title or in separate elements
            # For simplicity, we might take it from the title or a specific element if available
            teams_text = match_title_text # Default to title, can be refined
            # Example: if title is "India vs Australia, 1st T20I", teams_text is that.
            # More specific parsing might be needed if teams are in separate divs.

            # Score summary is tricky and highly variable
            score_divs = card.select("div[class*='cb-hmscg-bat-txt'], div[class*='cb-hmscg-bwl-txt'], div.cb-lv-scrs-well-live, div.cb-lv-scrs-well-complete")
            score_summary_text = " | ".join([div.get_text(strip=True) for div in score_divs if div.get_text(strip=True)])
            if not score_summary_text:
                score_summary_text = "Score not available"
            
            status_tag = card.select_one("div.cb-text-live, div.cb-text-complete, div.cb-text-preview, div.cb-mtch-crd-state")
            status_text = status_tag.get_text(strip=True) if status_tag else "Status N/A"

            try:
                match_data = MatchScore(
                    match_title=match_title_text,
                    teams_involved=teams_text, # This might need refinement
                    score_summary=score_summary_text,
                    status=status_text,
                    match_url=full_match_url
                )
                extracted_matches.append(match_data)
            except ValidationError as ve_item:
                if config.DEBUG_MODE:
                    print(f"--- cricket_tool.py --- Validation error for scraped match: {ve_item}. Card HTML: {card.prettify()[:300]}...")
        
        if not extracted_matches:
            return CricketOutput(matches=[], message=f"No matches found or parsable with current selectors for type {match_type_filter} on Cricbuzz.")
        return CricketOutput(matches=extracted_matches, message=f"Successfully fetched {len(extracted_matches)} matches from Cricbuzz.")

    except requests.exceptions.RequestException as e:
        if config.DEBUG_MODE:
            print(f"--- cricket_tool.py --- Request error: {e}")
        return CricketOutput(matches=[], error=f"Network error fetching scores: {str(e)}")
    except Exception as e:
        if config.DEBUG_MODE:
            import traceback
            print(f"--- cricket_tool.py (_fetch_from_cricbuzz_scrape) --- Error: {e}")
            traceback.print_exc()
        return CricketOutput(matches=[], error=f"An error occurred while scraping Cricbuzz: {str(e)}")

def _run_cricket_search(match_type: str, max_results: int) -> CricketOutput:
    # Prioritize CricAPI if key is available and implemented
    # if CRICAPI_KEY:
    #     # Placeholder for CricAPI logic
    #     # cricapi_result = _fetch_from_cricapi(match_type, max_results)
    #     # if cricapi_result.matches or cricapi_result.error:
    #     #     return cricapi_result
    #     pass 

    # Fallback to scraping Cricbuzz
    if config.DEBUG_MODE:
        print(f"--- cricket_tool.py --- Using Cricbuzz scraping for match_type: {match_type}")
    return _fetch_from_cricbuzz_scrape(match_type, max_results)

# --- Langchain Tool Integration ---
def cricket_tool_adapter(tool_input: dict) -> str:
    try:
        if isinstance(tool_input, str):
            # If planner sends a simple string, assume it\s match_type or a general query
            # For now, we only use match_type from CricketInput, so a string query is ambiguous.
            # Defaulting to match_type="all" if only a string is passed.
            validated_input = CricketInput(match_type=tool_input if tool_input else "all")
        elif isinstance(tool_input, dict):
            validated_input = CricketInput(**tool_input)
        else:
            return CricketOutput(error="Invalid input type for Cricket tool. Expected dict or string.").model_dump_json()
        
        result = _run_cricket_search(match_type=validated_input.match_type, max_results=validated_input.max_results)
        return result.model_dump_json()
    except ValidationError as ve:
        return CricketOutput(error=f"Input validation error: {str(ve)}").model_dump_json()
    except Exception as e:
        if config.DEBUG_MODE:
            print(f"--- cricket_tool.py (adapter) --- Unexpected error: {e}")
        return CricketOutput(error=f"An unexpected error occurred in Cricket tool adapter: {str(e)}").model_dump_json()

CRICKET_TOOL_DESCRIPTION = (
    "Fetches live cricket scores and match status from Cricbuzz.com. "
    "Input should be a JSON object with \'match_type\' (string, optional, e.g., \"all\", \"international\"; default \"all\") "
    "and \'max_results\' (integer, optional, default 5)."
)

cricket_langchain_tool = Tool(
    name="cricket_scores_search",
    func=cricket_tool_adapter,
    description=CRICKET_TOOL_DESCRIPTION,
    args_schema=CricketInput
)

def get_cricket_langchain_tool(api_keys: Optional[dict] = None, cfg: Optional[Any] = None) -> Tool:
    # api_keys (for CricAPI) could be used here if that path is fully implemented.
    return cricket_langchain_tool

# --- Direct Test (for development) ---
if __name__ == "__main__":
    print("--- Testing Cricket Tool Directly (Scraping Cricbuzz) ---")
    
    # Test Case 1: Default input
    test_input_1 = CricketInput(max_results=3)
    output_1_json_str = cricket_tool_adapter(test_input_1.model_dump())
    output_1 = CricketOutput.model_validate_json(output_1_json_str)
    print(f"Test Case 1 Input: {test_input_1.model_dump_json(indent=2)}")
    print(f"Test Case 1 Output: {output_1.model_dump_json(indent=2)}")
    if output_1.matches:
        for match in output_1.matches:
            print(f"  Match: {match.match_title}")
            print(f"  Teams: {match.teams_involved}")
            print(f"  Score: {match.score_summary}")
            print(f"  Status: {match.status}")
            print(f"  URL: {match.match_url}")
    elif output_1.error:
        print(f"  Error: {output_1.error}")
    else:
        print(f"  Message: {output_1.message}")

    print("\n--- Cricket Tool direct test complete. ---")
    print("Note: Cricbuzz website structure can change, which may break the scraper.")
    print("Consider adding a CricAPI integration with an API key for more stability if available.")

