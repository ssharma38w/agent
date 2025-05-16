"""
Tool for fetching news articles using NewsAPI.org or Google News RSS.
"""
import requests
import feedparser # For Google News RSS
from newsapi import NewsApiClient # For NewsAPI.org
from typing import List, Optional, Callable, Any
from pydantic import BaseModel, HttpUrl, Field, ValidationError
from langchain_core.tools import Tool
import json # For loading API keys
import logging

logger = logging.getLogger(__name__)

from agent import config # For debug mode and API key file path

# --- Pydantic Schemas for Input and Output ---
class NewsInput(BaseModel):
    """Input schema for the News Feed Search tool."""
    query: str = Field(..., description="The search query for news articles.")
    max_results: int = Field(5, description="Maximum number of articles to return.", ge=1, le=20)
    # source_preference: Optional[str] = Field(None, description="Preferred source: newsapi or rss") # Could add later

class NewsArticle(BaseModel):
    """Schema for a single news article entry."""
    title: str
    source: str  # Name of the news source, e.g., "BBC News", "Reuters"
    url: HttpUrl # Ensures link is a valid URL
    summary: Optional[str] = None # Summary might not always be available
    published_at: Optional[str] = None
    news: Optional[str] = None # Full text of the article, if extracted
    # image_url: Optional[HttpUrl] = None

class NewsOutput(BaseModel):
    """Output schema for the News Feed Search tool."""
    articles: List[NewsArticle] = Field(default_factory=list)
    error: Optional[str] = None
    message: Optional[str] = None

# --- Core Tool Logic ---

NEWSAPI_KEY = '97b231833efd44e9830a7940f3053e48'
try:
    with open('config.json', "r") as f:
        api_keys_content = json.load(f)
        NEWSAPI_KEY = api_keys_content.get("NEWSAPI_ORG_KEY")
except FileNotFoundError:
    if config.DEBUG_MODE:
        print(f"--- news_tool.py --- API keys file not found at {config.API_KEYS_FILE}. NewsAPI will not be available.")
except json.JSONDecodeError:
    if config.DEBUG_MODE:
        print(f"--- news_tool.py --- Error decoding API keys file {config.API_KEYS_FILE}. NewsAPI may not be available.")
except Exception as e:
    if config.DEBUG_MODE:
        print(f"--- news_tool.py --- An unexpected error occurred while loading NewsAPI key: {e}")

newsapi_client = None
if NEWSAPI_KEY:
    try:
        newsapi_client = NewsApiClient(api_key=NEWSAPI_KEY)
    except Exception as e:
        if config.DEBUG_MODE:
            print(f"--- news_tool.py --- Failed to initialize NewsAPI client: {e}")
        newsapi_client = None
else:
    if config.DEBUG_MODE:
        print("--- news_tool.py --- NewsAPI key not found or not configured. Will rely on Google News RSS fallback.")




from newspaper import Article

def extract_article_text(url):
    try:
        article = Article(url)
        article.download()
        article.parse()
        return article.text.strip()
    except Exception as e:
        if config.DEBUG_MODE:
            print(f"Failed to extract article from {url}: {e}")
        return None


def _fetch_from_newsapi(query: str, max_results: int) -> NewsOutput:
    if not newsapi_client:
        return NewsOutput(articles=[], error="NewsAPI client not initialized. API key might be missing or invalid.")
    try:
        if config.DEBUG_MODE:
            print(f"--- news_tool.py (_fetch_from_newsapi) --- Query: {query}, Max Results: {max_results}")
        
        # NewsAPI `page_size` controls number of results per request (max 100 for free tier)
        # `top_headlines` or `everything` endpoint can be used.
        # `everything` is better for general queries.
        all_articles_raw = newsapi_client.get_everything(
            q=query,
            language='en',
            sort_by='relevancy', # or popularity, publishedAt
            page_size=max_results*3 # Request up to max_results
        )
        logger.info(f"--- news_tool.py --- NewsAPI response: {all_articles_raw}")
        articles_list = []
        if all_articles_raw.get('status') == 'ok':
            for article_raw in all_articles_raw.get('articles', [])[:max_results]: # Ensure we don't exceed max_results
                summary = article_raw.get('summary')
                if summary and len(summary) > 500: # Truncate long summaries
                    summary = summary[:500] + "..."
                
                try:
                    news_text = extract_article_text(article_raw.get('url'))
                    article_data = NewsArticle(
                        title=article_raw.get('title', 'N/A'),
                        source=article_raw.get('source', {}).get('name', 'N/A'),
                        url=article_raw.get('url'),
                        summary=summary,
                        published_at=article_raw.get('publishedAt'),
                        news = news_text if news_text else None
                    )
                    articles_list.append(article_data)
                except ValidationError as ve_item:
                    if config.DEBUG_MODE:
                        print(f"--- news_tool.py --- Validation error for NewsAPI article: {ve_item}. Article: {article_raw}")
            return NewsOutput(articles=articles_list, message=f"Successfully fetched {len(articles_list)} articles via NewsAPI.")
        else:
            error_msg = all_articles_raw.get('message', "Unknown error from NewsAPI")
            return NewsOutput(articles=[], error=f"NewsAPI error: {error_msg}")
            
    except Exception as e:
        if config.DEBUG_MODE:
            import traceback
            print(f"--- news_tool.py (_fetch_from_newsapi) --- Error: {e}")
            traceback.print_exc()
        return NewsOutput(articles=[], error=f"An error occurred with NewsAPI: {str(e)}")

def _fetch_from_google_news_rss(query: str, max_results: int) -> NewsOutput:
    try:
        if config.DEBUG_MODE:
            print(f"--- news_tool.py (_fetch_from_google_news_rss) --- Query: {query}, Max Results: {max_results}")
        
        # Construct Google News RSS feed URL
        # Note: Google News RSS is unofficial and can be unreliable or change format.
        rss_url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en-US&gl=US&ceid=US:en"
        
        feed = feedparser.parse(rss_url)
        
        articles_list = []
        if feed.entries:
            for entry in feed.entries[:max_results]:
                summary = entry.get('summary')
                # Feedparser summary often contains HTML, needs cleaning if used directly.
                # For now, we might skip it or take a very short snippet if available.
                # A more robust solution would use BeautifulSoup to parse entry.summary_detail.value
                
                # Try to extract a cleaner summary if possible
                clean_summary = None
                if hasattr(entry, 'summary_detail') and entry.summary_detail and hasattr(entry.summary_detail, 'value'):
                    # Basic cleaning, could be improved with BeautifulSoup
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(entry.summary_detail.value, 'html.parser')
                    text_parts = [p.get_text(separator=' ', strip=True) for p in soup.find_all('p')]
                    if not text_parts:
                        text_parts = [li.get_text(separator=' ', strip=True) for li in soup.find_all('li')]
                    if not text_parts:
                        clean_summary = soup.get_text(separator=' ', strip=True)
                    else:
                        clean_summary = " ".join(text_parts)

                    if clean_summary and len(clean_summary) > 300:
                        clean_summary = clean_summary[:300] + "..."
                elif summary and len(summary) > 300:
                    clean_summary = summary[:300] + "..."
                elif summary:
                    clean_summary = summary

                try:
                    article_data = NewsArticle(
                        title=entry.get('title', 'N/A'),
                        source=entry.get('source', {}).get('title', 'Google News RSS'),
                        url=entry.get('link'),
                        summary=clean_summary,
                        published_at=entry.get('published') # Or entry.published_parsed
                    )
                    articles_list.append(article_data)
                except ValidationError as ve_item:
                    if config.DEBUG_MODE:
                        print(f"--- news_tool.py --- Validation error for RSS article: {ve_item}. Article: {entry}")
            return NewsOutput(articles=articles_list, message=f"Successfully fetched {len(articles_list)} articles via Google News RSS.")
        else:
            return NewsOutput(articles=[], message=f"No articles found for query {query} via Google News RSS.")

    except Exception as e:
        if config.DEBUG_MODE:
            import traceback
            print(f"--- news_tool.py (_fetch_from_google_news_rss) --- Error: {e}")
            traceback.print_exc()
        return NewsOutput(articles=[], error=f"An error occurred with Google News RSS: {str(e)}")

def _run_news_search(query: str, max_results: int = 5) -> NewsOutput:
    if newsapi_client:
        if config.DEBUG_MODE:
            print("--- news_tool.py --- Attempting NewsAPI.org first.")
        newsapi_result = _fetch_from_newsapi(query, max_results)
        # If NewsAPI fails or returns no results, consider falling back, or just return its result.
        # For now, prefer NewsAPI if configured.
        if newsapi_result.articles or newsapi_result.error:
            return newsapi_result 
    
    # Fallback to Google News RSS if NewsAPI is not available or returned nothing without error
    if config.DEBUG_MODE:
        print("--- news_tool.py --- Using Google News RSS fallback.")
    return _fetch_from_google_news_rss(query, max_results)

# --- Langchain Tool Integration ---
def news_tool_adapter(tool_input: dict) -> str:
    try:
        if isinstance(tool_input, str):
            validated_input = NewsInput(query=tool_input)
        elif isinstance(tool_input, dict):
            validated_input = NewsInput(**tool_input)
        else:
            return NewsOutput(error="Invalid input type for News tool. Expected dict or string.").model_dump_json()
        
        result = _run_news_search(query=validated_input.query, max_results=validated_input.max_results)
        return result.model_dump_json()
    except ValidationError as ve:
        return NewsOutput(error=f"Input validation error: {str(ve)}").model_dump_json()
    except Exception as e:
        if config.DEBUG_MODE:
            print(f"--- news_tool.py (adapter) --- Unexpected error: {e}")
        return NewsOutput(error=f"An unexpected error occurred in News tool adapter: {str(e)}").model_dump_json()

NEWS_TOOL_DESCRIPTION = (
    "Fetches recent news articles based on a query. "
    "Uses NewsAPI.org if an API key is provided, otherwise falls back to Google News RSS. "
    "Input should be a JSON object with \'query\' (string, required) and \'max_results\' (integer, optional, default 5)."
)

news_langchain_tool = Tool(
    name="news_search",
    func=news_tool_adapter,
    description=NEWS_TOOL_DESCRIPTION,
    args_schema=NewsInput
)

def get_news_langchain_tool(api_keys: Optional[dict] = None, cfg: Optional[Any] = None) -> Tool:
    # This tool now loads its own API key from config.json via global NEWSAPI_KEY
    # api_keys and cfg params are kept for consistency but not directly used here to re-init client.
    return news_langchain_tool

# --- Direct Test (for development) ---
if __name__ == "__main__":
    print("--- Testing News Tool Directly ---")
    # To test NewsAPI, ensure NEWSAPI_ORG_KEY is in your config.json
    # Otherwise, it will use Google News RSS.

    test_queries = ["artificial intelligence advancements", "latest space exploration news"]
    
    for t_query in test_queries:
        print(f"\n--- Query: {t_query} ---")
        test_input = NewsInput(query=t_query, max_results=3)
        output_json_str = news_tool_adapter(test_input.model_dump())
        output = NewsOutput.model_validate_json(output_json_str)
        
        print(f"Input: {test_input.model_dump_json(indent=2)}")
        print(f"Output: {output.model_dump_json(indent=2)}")

        if output.articles:
            for article in output.articles:
                print(f"  Title: {article.title}")
                print(f"  Source: {article.source}")
                print(f"  URL: {article.url}")
                print(f"  Published: {article.published_at}")
                print(f"  Summary: {article.summary}")
        elif output.error:
            print(f"  Error: {output.error}")
        else:
            print(f"  Message: {output.message}")

    print("\n--- News Tool direct test complete. ---")

