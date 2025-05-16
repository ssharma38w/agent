# /home/ubuntu/chatbot_project/tools/yahoofinance_tool.py
"""
Tool for fetching stock market data from Yahoo Finance, focusing on the Indian equity market.
Uses provided Datasource APIs.
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

# --- Pydantic Schemas (already defined, ensure they are complete and accurate) ---
# Common input parameters
class YahooFinanceCommonInput(BaseModel):
    region: str = Field("IN", description="Region, defaults to IN for India")
    lang: str = Field("en-IN", description="Language, defaults to en-IN for India")

# --- Schemas for get_stock_profile ---
class StockProfileInput(YahooFinanceCommonInput):
    symbol: str = Field(..., description="Stock symbol, e.g., RELIANCE.NS")

class CompanyOfficer(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    age: Optional[int] = None
    totalPay: Optional[Dict[str, Any]] = None
    exercisedValue: Optional[Dict[str, Any]] = None
    unexercisedValue: Optional[Dict[str, Any]] = None

class SummaryProfile(BaseModel):
    address1: Optional[str] = None
    address2: Optional[str] = None # Added as it is in API docs
    city: Optional[str] = None
    zip_code: Optional[str] = Field(None, alias="zip")
    country: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[HttpUrl] = None # Changed to HttpUrl
    industry: Optional[str] = None
    industryKey: Optional[str] = None # Added
    industryDisp: Optional[str] = None # Added
    sector: Optional[str] = None
    sectorKey: Optional[str] = None # Added
    sectorDisp: Optional[str] = None # Added
    longBusinessSummary: Optional[str] = None
    fullTimeEmployees: Optional[int] = None
    companyOfficers: Optional[List[CompanyOfficer]] = Field(default_factory=list)
    irWebsite: Optional[HttpUrl] = None # Added
    # executiveTeam: Optional[List[Any]] = Field(default_factory=list) # API docs show this, but structure is not defined, CompanyOfficer is more specific
    maxAge: Optional[int] = None # Added

class StockProfileOutput(BaseModel):
    summaryProfile: Optional[SummaryProfile] = None
    error: Optional[str] = None
    message: Optional[str] = None

# --- Schemas for get_stock_chart ---
class StockChartInput(YahooFinanceCommonInput):
    symbol: str = Field(..., description="Stock symbol, e.g., INFY.NS")
    interval: str = Field("1d", description="Data interval (e.g., 1m, 5m, 1d, 1wk, 1mo)")
    range: str = Field("1mo", description="Data range (e.g., 1d, 5d, 1mo, 1y, max)")
    comparisons: Optional[str] = None
    events: Optional[str] = None
    includePrePost: bool = False
    includeAdjustedClose: bool = True
    useYfid: bool = True # API default is True
    # period1: Optional[str] = None
    # period2: Optional[str] = None

class StockChartMetaData(BaseModel):
    currency: Optional[str] = None
    symbol: Optional[str] = None
    exchangeName: Optional[str] = None
    fullExchangeName: Optional[str] = None
    instrumentType: Optional[str] = None
    firstTradeDate: Optional[int] = None
    regularMarketTime: Optional[int] = None
    hasPrePostMarketData: Optional[bool] = None
    gmtoffset: Optional[int] = None
    timezone: Optional[str] = None
    exchangeTimezoneName: Optional[str] = None
    regularMarketPrice: Optional[float] = None
    fiftyTwoWeekHigh: Optional[float] = None
    fiftyTwoWeekLow: Optional[float] = None
    regularMarketDayHigh: Optional[float] = None
    regularMarketDayLow: Optional[float] = None
    regularMarketVolume: Optional[int] = None
    # Removed longName, shortName as they are not in the provided API schema for meta
    chartPreviousClose: Optional[float] = None
    priceHint: Optional[int] = None
    # currentTradingPeriod: Optional[Dict[str, Any]] = None # Complex, can add later if needed
    dataGranularity: Optional[str] = None
    range: Optional[str] = None
    validRanges: Optional[List[str]] = Field(default_factory=list)

class StockChartIndicators(BaseModel):
    quote: Optional[List[Dict[str, Optional[List[Optional[float]]]]]] = None
    adjclose: Optional[List[Dict[str, Optional[List[Optional[float]]]]]] = None

class StockChartData(BaseModel):
    meta: Optional[StockChartMetaData] = None
    timestamp: Optional[List[Optional[int]]] = Field(default_factory=list)
    indicators: Optional[StockChartIndicators] = None

class StockChartOutput(BaseModel):
    chart: Optional[StockChartData] = None
    error: Optional[str] = None
    message: Optional[str] = None

# --- Schemas for get_stock_sec_filing ---
class StockSecFilingsInput(YahooFinanceCommonInput):
    symbol: str = Field(..., description="Stock symbol, e.g., TCS.NS")

class SecFilingExhibit(BaseModel):
    type: Optional[str] = None
    url: Optional[HttpUrl] = None

class SecFiling(BaseModel):
    date: Optional[str] = None
    epochDate: Optional[int] = None
    type: Optional[str] = None
    title: Optional[str] = None
    edgarUrl: Optional[HttpUrl] = None
    exhibits: Optional[List[SecFilingExhibit]] = Field(default_factory=list)
    maxAge: Optional[int] = None

class StockSecFilingsOutput(BaseModel):
    filings: Optional[List[SecFiling]] = Field(default_factory=list)
    error: Optional[str] = None
    message: Optional[str] = None

# --- Schemas for get_stock_insights ---
class StockInsightsInput(YahooFinanceCommonInput):
    symbol: str = Field(..., description="Stock symbol, e.g., WIPRO.NS")

class TechnicalOutlook(BaseModel):
    stateDescription: Optional[str] = None
    direction: Optional[str] = None
    score: Optional[float] = None
    scoreDescription: Optional[str] = None
    sectorDirection: Optional[str] = None # Added
    sectorScore: Optional[float] = None # Added
    sectorScoreDescription: Optional[str] = None # Added
    indexDirection: Optional[str] = None # Added
    indexScore: Optional[float] = None # Added
    indexScoreDescription: Optional[str] = None # Added

class StockValuation(BaseModel):
    color: Optional[int] = None
    description: Optional[str] = None
    discount: Optional[str] = None
    relativeValue: Optional[str] = None
    provider: Optional[str] = None

class CompanySnapshotDetail(BaseModel):
    innovativeness: Optional[float] = None
    hiring: Optional[float] = None
    sustainability: Optional[float] = None
    insiderSentiments: Optional[float] = None
    earningsReports: Optional[float] = None
    dividends: Optional[float] = None

class CompanySnapshot(BaseModel):
    sectorInfo: Optional[str] = None
    company: Optional[CompanySnapshotDetail] = None
    sector: Optional[CompanySnapshotDetail] = None

class StockInsightsData(BaseModel):
    symbol: Optional[str] = None
    # instrumentInfo
    shortTermOutlook: Optional[TechnicalOutlook] = None
    intermediateTermOutlook: Optional[TechnicalOutlook] = None
    longTermOutlook: Optional[TechnicalOutlook] = None
    valuation: Optional[StockValuation] = None
    # companySnapshot
    companySnapshot: Optional[CompanySnapshot] = None
    # Add more fields like recommendation, events, reports, sigDevs, secReports from API schema

class StockInsightsOutput(BaseModel):
    insights: Optional[StockInsightsData] = None
    error: Optional[str] = None
    message: Optional[str] = None

# --- Schemas for get_stock_holders (Insider) ---
class StockHoldersInput(YahooFinanceCommonInput):
    symbol: str = Field(..., description="Stock symbol, e.g., HDFCBANK.NS")

class FormattedValue(BaseModel):
    raw: Optional[float] = None # Changed to float for monetary/numerical values
    fmt: Optional[str] = None
    longFmt: Optional[str] = None

class InsiderHolderDetail(BaseModel):
    maxAge: Optional[int] = None
    name: Optional[str] = None
    relation: Optional[str] = None
    url: Optional[HttpUrl] = None
    transactionDescription: Optional[str] = None
    latestTransDate: Optional[FormattedValue] = None
    positionDirect: Optional[FormattedValue] = None
    positionDirectDate: Optional[FormattedValue] = None # Added

class StockHoldersOutput(BaseModel):
    holders: Optional[List[InsiderHolderDetail]] = Field(default_factory=list)
    error: Optional[str] = None
    message: Optional[str] = None

# --- Schemas for get_stock_what_analyst_are_saying (Research Reports) ---
class StockAnalystReportsInput(YahooFinanceCommonInput):
    symbol: str = Field(..., description="Stock symbol, e.g., ITC.NS")

class AnalystReportHit(BaseModel):
    report_title: Optional[str] = None
    ticker: Optional[List[str]] = Field(default_factory=list)
    provider: Optional[str] = None
    author: Optional[str] = None
    pdf_url: Optional[HttpUrl] = None
    snapshot_url: Optional[HttpUrl] = None
    id: Optional[str] = None
    report_type: Optional[str] = None
    abstract: Optional[str] = None
    report_date: Optional[int] = None

class StockAnalystReportsOutput(BaseModel):
    reports: Optional[List[AnalystReportHit]] = Field(default_factory=list)
    error: Optional[str] = None
    message: Optional[str] = None

# --- General Input to select the type of YahooFinance action ---
class YahooFinanceActionInput(BaseModel):
    action: str = Field(..., description="Action to perform: get_profile, get_chart, get_sec_filings, get_insights, get_holders, get_analyst_reports")
    parameters: Dict[str, Any]

# --- Core Tool Logic ---

api_client = ApiClient()

def _call_datasource_api(api_name: str, query_params: dict) -> Any:
    if config.DEBUG_MODE:
        print(f"--- yahoofinance_tool.py (_call_datasource_api) --- Calling API: {api_name}, Params: {query_params}")
    try:
        response = api_client.call_api(api_name, query=query_params)
        if config.DEBUG_MODE:
            print(f"--- yahoofinance_tool.py (_call_datasource_api) --- Response: {response}")
        # Basic check for top-level error structure common in some APIs
        if isinstance(response, dict) and response.get("error") and not response.get("result") and not response.get("quoteSummary") and not response.get("chart") and not response.get("finance") :
            return {"error_message": str(response["error"])}
        return response
    except Exception as e:
        if config.DEBUG_MODE:
            import traceback
            print(f"--- yahoofinance_tool.py (_call_datasource_api) --- API Call Error: {e}")
            traceback.print_exc()
        return {"error_message": f"API call failed: {str(e)}"}

def _get_stock_profile(params: StockProfileInput) -> StockProfileOutput:
    api_response = _call_datasource_api("YahooFinance/get_stock_profile", params.model_dump())
    if isinstance(api_response, dict) and api_response.get("error_message"):
        return StockProfileOutput(error=api_response["error_message"])
    try:
        # Response structure: { "quoteSummary": { "result": [ { "summaryProfile": { ... } } ], "error": null } }
        if api_response and api_response.get("quoteSummary") and api_response["quoteSummary"].get("result") and 
           len(api_response["quoteSummary"]["result"]) > 0 and api_response["quoteSummary"]["result"][0].get("summaryProfile"):
            profile_data = api_response["quoteSummary"]["result"][0]["summaryProfile"]
            return StockProfileOutput(summaryProfile=SummaryProfile(**profile_data), message="Profile fetched successfully.")
        else:
            err_msg = "Profile data not found in API response or unexpected structure."
            if api_response and api_response.get("quoteSummary") and api_response["quoteSummary"].get("error"):
                err_msg = f"API Error: {api_response["quoteSummary"]["error"]}"
            return StockProfileOutput(error=err_msg)
    except ValidationError as ve:
        return StockProfileOutput(error=f"Data validation error for profile: {str(ve)}")
    except Exception as e:
        return StockProfileOutput(error=f"Error processing profile data: {str(e)}")

def _get_stock_chart(params: StockChartInput) -> StockChartOutput:
    api_response = _call_datasource_api("YahooFinance/get_stock_chart", params.model_dump(exclude_none=True))
    if isinstance(api_response, dict) and api_response.get("error_message"):
        return StockChartOutput(error=api_response["error_message"])
    try:
        # Response structure: { "chart": { "result": [ { ...chart_data... } ], "error": null } }
        if api_response and api_response.get("chart") and api_response["chart"].get("result") and 
           len(api_response["chart"]["result"]) > 0:
            chart_data = api_response["chart"]["result"][0]
            # Timestamps can be null if data is missing for a point, filter them out before validation
            if chart_data.get("timestamp"):
                chart_data["timestamp"] = [ts for ts in chart_data["timestamp"] if ts is not None]
            return StockChartOutput(chart=StockChartData(**chart_data), message="Chart data fetched successfully.")
        else:
            err_msg = "Chart data not found in API response or unexpected structure."
            if api_response and api_response.get("chart") and api_response["chart"].get("error"):
                err_msg = f"API Error: {api_response["chart"]["error"]}"
            return StockChartOutput(error=err_msg)
    except ValidationError as ve:
        return StockChartOutput(error=f"Data validation error for chart: {str(ve)}")
    except Exception as e:
        return StockChartOutput(error=f"Error processing chart data: {str(e)}")

def _get_stock_sec_filings(params: StockSecFilingsInput) -> StockSecFilingsOutput:
    api_response = _call_datasource_api("YahooFinance/get_stock_sec_filing", params.model_dump())
    if isinstance(api_response, dict) and api_response.get("error_message"):
        return StockSecFilingsOutput(error=api_response["error_message"])
    try:
        if api_response and api_response.get("quoteSummary") and api_response["quoteSummary"].get("result") and 
           len(api_response["quoteSummary"]["result"]) > 0 and api_response["quoteSummary"]["result"][0].get("secFilings"):
            filings_data = api_response["quoteSummary"]["result"][0]["secFilings"].get("filings", [])
            return StockSecFilingsOutput(filings=[SecFiling(**f) for f in filings_data], message="SEC filings fetched successfully.")
        else:
            err_msg = "SEC filings not found in API response or unexpected structure."
            if api_response and api_response.get("quoteSummary") and api_response["quoteSummary"].get("error"):
                err_msg = f"API Error: {api_response["quoteSummary"]["error"]}"
            return StockSecFilingsOutput(error=err_msg)
    except ValidationError as ve:
        return StockSecFilingsOutput(error=f"Data validation error for SEC filings: {str(ve)}")
    except Exception as e:
        return StockSecFilingsOutput(error=f"Error processing SEC filings data: {str(e)}")

def _get_stock_insights(params: StockInsightsInput) -> StockInsightsOutput:
    api_response = _call_datasource_api("YahooFinance/get_stock_insights", params.model_dump())
    if isinstance(api_response, dict) and api_response.get("error_message"):
        return StockInsightsOutput(error=api_response["error_message"])
    try:
        # Response: { "finance": { "result": { ...insights_data... }, "error": null } }
        if api_response and api_response.get("finance") and api_response["finance"].get("result"):
            data = api_response["finance"]["result"]
            # Manual mapping due to complex/nested structure and Pydantic model simplification
            insights_obj = StockInsightsData(
                symbol=data.get("symbol"),
                shortTermOutlook=data.get("instrumentInfo", {}).get("technicalEvents", {}).get("shortTermOutlook"),
                intermediateTermOutlook=data.get("instrumentInfo", 
(Content truncated due to size limit. Use line ranges to read in chunks)