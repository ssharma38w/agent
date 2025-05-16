# /home/ubuntu/chatbot_project/tools/twitter_tool.py
"""
Tool for interacting with Twitter API (search tweets, get user profiles) using Datasource APIs.
"""
import json
from typing import List, Optional, Any, Dict, Callable
from pydantic import BaseModel, Field, ValidationError, HttpUrl
from langchain_core.tools import Tool

# To use Datasource APIs
import sys
sys.path.append("/opt/.manus/.sandbox-runtime")
from data_api import ApiClient

from .. import config # For debug mode

# --- Pydantic Schemas for Input and Output ---

# --- Schemas for search_twitter ---
class TwitterSearchInput(BaseModel):
    query: str = Field(..., description="The query to search for on Twitter.")
    count: int = Field(10, description="The number of tweets to return.", ge=1, le=50) # API might have its own limits
    type: str = Field("Top", description="Type of search: Top, Photos, Videos, People, Latest")
    # cursor: Optional[str] = None # For pagination, if needed later

# Simplified Tweet Structures - API is very complex
class TweetUser(BaseModel):
    screen_name: Optional[str] = None
    name: Optional[str] = None
    verified: Optional[bool] = False
    profile_image_url_https: Optional[HttpUrl] = None

class TweetData(BaseModel):
    rest_id: Optional[str] = None # Tweet ID
    created_at: Optional[str] = None
    full_text: Optional[str] = None
    favorite_count: Optional[int] = None
    retweet_count: Optional[int] = None
    user: Optional[TweetUser] = None
    # Add other fields like media URLs if parsed

class TwitterSearchOutput(BaseModel):
    tweets: List[TweetData] = Field(default_factory=list)
    error: Optional[str] = None
    message: Optional[str] = None
    # cursor_top: Optional[str] = None
    # cursor_bottom: Optional[str] = None

# --- Schemas for get_user_profile_by_username ---
class TwitterUserProfileInput(BaseModel):
    username: str = Field(..., description="The Twitter username (screen name) to fetch profile for.")

class UserProfileLegacy(BaseModel):
    name: Optional[str] = None
    screen_name: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    url: Optional[HttpUrl] = None
    followers_count: Optional[int] = None
    friends_count: Optional[int] = None
    statuses_count: Optional[int] = None
    verified: Optional[bool] = None
    is_blue_verified: Optional[bool] = None # From top level user.result
    profile_image_url_https: Optional[HttpUrl] = None
    profile_banner_url: Optional[HttpUrl] = None
    created_at: Optional[str] = None

class UserProfileData(BaseModel):
    rest_id: Optional[str] = None # User ID
    legacy: Optional[UserProfileLegacy] = None
    # professional: Optional[Dict[str, Any]] = None # Can be added if needed

class TwitterUserProfileOutput(BaseModel):
    profile: Optional[UserProfileData] = None
    error: Optional[str] = None
    message: Optional[str] = None

# --- General Input to select the type of Twitter action ---
class TwitterActionInput(BaseModel):
    action: str = Field(..., description="Action to perform: search_twitter, get_user_profile")
    parameters: Dict[str, Any]

# --- Core Tool Logic ---
api_client = ApiClient()

def _call_twitter_api(api_name: str, query_params: dict) -> Any:
    if config.DEBUG_MODE:
        print(f"--- twitter_tool.py (_call_twitter_api) --- Calling API: {api_name}, Params: {query_params}")
    try:
        response = api_client.call_api(api_name, query=query_params)
        if config.DEBUG_MODE:
            print(f"--- twitter_tool.py (_call_twitter_api) --- Raw Response: {json.dumps(response)[:500]}...") # Log snippet of response
        
        # Check for common error patterns in the response itself if API doesn\t raise exceptions for app-level errors
        if isinstance(response, dict) and response.get("errors"):
            return {"error_message": str(response["errors"]) }
        if isinstance(response, dict) and response.get("result") is None and not response.get("data") : # common for twitter if no data
             if "timeline" in str(response).lower() and "instructions" in str(response).lower(): # search might return empty timeline
                 pass # let specific parser handle empty timeline
             else:
                return {"error_message": "API returned no result or data."}

        return response
    except Exception as e:
        if config.DEBUG_MODE:
            import traceback
            print(f"--- twitter_tool.py (_call_twitter_api) --- API Call Error: {e}")
            traceback.print_exc()
        return {"error_message": f"API call failed: {str(e)}"}

def _parse_tweet_entry(entry: Dict[str, Any]) -> Optional[TweetData]:
    """Helper to parse a single tweet entry from the complex API response."""
    try:
        # The structure can vary. Common path: entry.content.itemContent.tweet_results.result
        # or entry.content.tweet_results.result (if entryType is Tweet)
        tweet_content_data = entry.get("content", {}).get("itemContent", {}).get("tweet_results", {}).get("result")
        if not tweet_content_data:
            # Sometimes it is directly under content if entryType is Tweet
            if entry.get("content", {}).get("entryType") == "Tweet":
                 tweet_content_data = entry.get("content", {}).get("tweet_results", {}).get("result") # Check this path
            if not tweet_content_data:
                # Check another common path for promoted tweets or other types
                if entry.get("content", {}).get("tweetDisplayType") == "Tweet":
                    tweet_content_data = entry.get("content", {}).get("tweet_results", {}).get("result")
                if not tweet_content_data:
                    # One more attempt for a slightly different structure
                    if entry.get("content", {}).get("itemContent", {}).get("itemType") == "Tweet":
                        tweet_content_data = entry.get("content", {}).get("itemContent", {}).get("tweet_results", {}).get("result")
                    if not tweet_content_data:
                        if config.DEBUG_MODE:
                            print(f"--- twitter_tool.py --- Could not find tweet_results.result in entry: {json.dumps(entry)[:200]}")
                        return None

        legacy_tweet_data = tweet_content_data.get("legacy")
        if not legacy_tweet_data:
            # Check for note_tweet structure
            note_tweet_results = tweet_content_data.get("note_tweet", {}).get("note_tweet_results", {}).get("result")
            if note_tweet_results:
                legacy_tweet_data = note_tweet_results.get("legacy")
                if not legacy_tweet_data:
                    if config.DEBUG_MODE:
                        print(f"--- twitter_tool.py --- Could not find legacy tweet data in note_tweet: {json.dumps(tweet_content_data)[:200]}")
                    return None
            else:
                if config.DEBUG_MODE:
                    print(f"--- twitter_tool.py --- Could not find legacy tweet data: {json.dumps(tweet_content_data)[:200]}")
                return None

        user_results_data = tweet_content_data.get("core", {}).get("user_results", {}).get("result", {}).get("legacy")
        if not user_results_data:
             user_results_data = tweet_content_data.get("core", {}).get("user_results", {}).get("result", {}).get("user",{}).get("legacy") # another possible path
             if not user_results_data: # One more common path
                user_results_data = tweet_content_data.get("core", {}).get("user_results", {}).get("result", {}).get("legacy")
                if not user_results_data:
                    if config.DEBUG_MODE:
                        print(f"--- twitter_tool.py --- Could not find user_results.result.legacy: {json.dumps(tweet_content_data.get(\"core\"))[:200]}")
                    # User data might be missing for some tweet types, proceed without it if so
                    user_obj = None
                else:
                    user_obj = TweetUser(**user_results_data)
             else:
                user_obj = TweetUser(**user_results_data)
        else:
            user_obj = TweetUser(**user_results_data)

        return TweetData(
            rest_id=tweet_content_data.get("rest_id"),
            created_at=legacy_tweet_data.get("created_at"),
            full_text=legacy_tweet_data.get("full_text"),
            favorite_count=legacy_tweet_data.get("favorite_count"),
            retweet_count=legacy_tweet_data.get("retweet_count"),
            user=user_obj
        )
    except Exception as e:
        if config.DEBUG_MODE:
            print(f"--- twitter_tool.py --- Error parsing individual tweet entry: {e}. Entry: {json.dumps(entry)[:200]}...")
        return None

def _search_twitter(params: TwitterSearchInput) -> TwitterSearchOutput:
    api_response = _call_twitter_api("Twitter/search_twitter", params.model_dump())
    if isinstance(api_response, dict) and api_response.get("error_message"):
        return TwitterSearchOutput(error=api_response["error_message"])
    
    tweets_list = []
    try:
        # Expected structure: response.result.timeline.instructions[...].entries
        # The relevant instruction type is often "TimelineAddEntries" or similar
        instructions = api_response.get("result", {}).get("timeline", {}).get("instructions", [])
        entries_to_parse = []
        for instruction in instructions:
            # Look for instructions that contain tweet entries
            # Common types: "TimelineAddEntries", "TimelineReplaceEntry"
            # The actual type string might vary, check for presence of 'entries'
            if instruction.get("entries") and isinstance(instruction.get("entries"), list):
                entries_to_parse.extend(instruction.get("entries"))
            elif instruction.get("entry") and isinstance(instruction.get("entry"), dict): # For single entry instructions
                entries_to_parse.append(instruction.get("entry"))

        if not entries_to_parse and config.DEBUG_MODE:
            print(f"--- twitter_tool.py --- No entries found in timeline instructions. API Response: {json.dumps(api_response)[:300]}")

        for entry in entries_to_parse:
            # Tweets are usually identified by entryId starting with "tweet-" or content having tweet_results
            entry_id = entry.get("entryId", "")
            if "tweet-" in entry_id or ("tweet_results" in str(entry.get("content"))):
                parsed_tweet = _parse_tweet_entry(entry)
                if parsed_tweet:
                    tweets_list.append(parsed_tweet)
            # Also check for cursor entries if pagination is needed later
            # elif "cursor-top-" in entry_id: cursors["top"] = entry.get("content", {}).get("value")
            # elif "cursor-bottom-" in entry_id: cursors["bottom"] = entry.get("content", {}).get("value")

        if not tweets_list:
            return TwitterSearchOutput(message="No tweets found matching the criteria or parsable from response.")
        return TwitterSearchOutput(tweets=tweets_list, message=f"Successfully fetched {len(tweets_list)} tweets.")

    except Exception as e:
        if config.DEBUG_MODE:
            import traceback
            print(f"--- twitter_tool.py (_search_twitter) --- Error parsing search results: {e}")
            traceback.print_exc()
        return TwitterSearchOutput(error=f"Error processing Twitter search results: {str(e)}")

def _get_user_profile(params: TwitterUserProfileInput) -> TwitterUserProfileOutput:
    api_response = _call_twitter_api("Twitter/get_user_profile_by_username", params.model_dump())
    if isinstance(api_response, dict) and api_response.get("error_message"):
        return TwitterUserProfileOutput(error=api_response["error_message"])
    
    try:
        # Expected structure: response.result.data.user.result
        user_data_raw = api_response.get("result", {}).get("data", {}).get("user", {}).get("result")
        if not user_data_raw:
            return TwitterUserProfileOutput(error="User profile data not found in API response or unexpected structure.")
        
        # Extract legacy profile data
        legacy_data_raw = user_data_raw.get("legacy")
        if not legacy_data_raw:
            return TwitterUserProfileOutput(error="Legacy user profile data not found.")
        
        # Create UserProfileLegacy object, handling potential missing fields
        legacy_profile = UserProfileLegacy(
            name=legacy_data_raw.get("name"),
            screen_name=legacy_data_raw.get("screen_name"),
            description=legacy_data_raw.get("description"),
            location=legacy_data_raw.get("location"),
            url=legacy_data_raw.get("url"), # Will be validated by HttpUrl
            followers_count=legacy_data_raw.get("followers_count"),
            friends_count=legacy_data_raw.get("friends_count"),
            statuses_count=legacy_data_raw.get("statuses_count"),
            verified=legacy_data_raw.get("verified"),
            is_blue_verified=user_data_raw.get("is_blue_verified"), # From parent
            profile_image_url_https=legacy_data_raw.get("profile_image_url_https"),
            profile_banner_url=legacy_data_raw.get("profile_banner_url"),
            created_at=legacy_data_raw.get("created_at")
        )

        profile_data = UserProfileData(
            rest_id=user_data_raw.get("rest_id"),
            legacy=legacy_profile
            # professional data can be added here if needed
        )
        return TwitterUserProfileOutput(profile=profile_data, message="User profile fetched successfully.")

    except ValidationError as ve:
        return TwitterUserProfileOutput(error=f"Data validation error for user profile: {str(ve)}")
    except Exception as e:
        if config.DEBUG_MODE:
            import traceback
            print(f"--- twitter_tool.py (_get_user_profile) --- Error parsing profile: {e}")
            traceback.print_exc()
        return TwitterUserProfileOutput(error=f"Error processing user profile data: {str(e)}")

ACTION_MAP: Dict[str, Callable[[Any], Any]] = {
    "search_twitter": _search_twitter,
    "get_user_profile": _get_user_profile,
}

INPUT_MODEL_MAP: Dict[str, Any] = {
    "search_twitter": TwitterSearchInput,
    "get_user_profile": TwitterUserProfileInput,
}

def _run_twitter_action(action_input: TwitterActionInput) -> Any:
    action_name = action_input.action
    params_dict = action_input.parameters

    if action_name not in ACTION_MAP or action_name not in INPUT_MODEL_MAP:
        return {"error": f"Invalid Twitter action: {action_name}"} 
    
    action_function = ACTION_MAP[action_name]
    pydantic_input_model = INPUT_MODEL_MAP[action_name]
    
    try:
        validated_params = pydantic_input_model(**params_dict)
    except ValidationError as ve:
        return {"error": f"Input validation error for action {action_name}: {str(ve)}"} 

    return action_function(validated_params)

# --- Langchain Tool Integration ---
def twitter_tool_adapter(tool_input: dict) -> str:
    try:
        if not isinstance(tool_input, dict):
            # Fallback for simple string query, assuming it\s a search query
            if isinstance(tool_input, str):
                action_input = TwitterActionInput(action="search_twitter", parameters={"query": tool_input})
            else:
                return TwitterSearchOutput(error="Invalid input type for Twitter tool. Expected dict or string.").model_dump_json()
        else:
            action_input = TwitterActionInput(**tool_input)
        
        result_obj = _run_twitter_action(action_input)
        
        if hasattr(result_obj, "model_dump_json"):
            return result_obj.model_dump_json()
        elif isinstance(result_obj, dict) and "error" in result_obj:
            return json.dumps(result_obj)
        else:
            return TwitterSearchOutput(error="Unexpected result type from Twitter acti
(Content truncated due to size limit. Use line ranges to read in chunks)