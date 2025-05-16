# /home/ubuntu/chatbot_project/tools/weather.py
import requests
import json
from typing import Optional, Dict, Any, Type
from pydantic import BaseModel, Field, ValidationError
from langchain.tools import Tool
import functools

# --- Pydantic Schemas for Weather Tool ---
class WeatherInput(BaseModel):
    city: str = Field(..., description="The city name for which to fetch weather information.")

    class Config:
        extra = "forbid"

class WeatherOutput(BaseModel):
    city_name: Optional[str] = Field(None, description="The name of the city for the weather report.")
    temperature_celsius: Optional[float] = Field(None, description="Temperature in Celsius.")
    temperature_fahrenheit: Optional[float] = Field(None, description="Temperature in Fahrenheit.")
    description: Optional[str] = Field(None, description="A brief description of the weather conditions (e.g., clear sky, light rain).")
    humidity: Optional[int] = Field(None, description="Humidity percentage.")
    wind_speed_mps: Optional[float] = Field(None, description="Wind speed in meters per second.")
    error: Optional[str] = Field(None, description="Error message if fetching weather data failed.")
    details: Optional[str] = Field(None, description="Additional details for errors.")

    class Config:
        extra = "forbid"

# --- Core Tool Logic (Placeholder - to be fully implemented later) ---
def _run_weather_logic(inp: WeatherInput, api_keys: Dict[str, str], config: Any) -> WeatherOutput:
    """
    Internal logic for fetching real-time weather data for a given city using OpenWeatherMap API.
    """
    city = inp.city
    api_key = api_keys.get("OPENWEATHERMAP_API_KEY")

    if config.DEBUG_MODE:
        print(f"--- tools/weather.py (_run_weather_logic) --- Fetching weather for city: {city}")

    if not api_key:
        return WeatherOutput(city_name=city, error="OpenWeatherMap API key not found in configuration.", details="Please add OPENWEATHERMAP_API_KEY to your config.json.")

    # Actual API call and data processing will be implemented in Phase 4
    # For now, returning a placeholder success or error based on a simple check
    # This placeholder logic will be replaced with a real API call to OpenWeatherMap
    base_url = "http://api.openweathermap.org/data/2.5/weather?"
    complete_url = base_url + "appid=" + api_key + "&q=" + city + "&units=metric" # units=metric for Celsius

    try:
        response = requests.get(complete_url, timeout=10)
        response.raise_for_status() # Raises an HTTPError for bad responses (4XX or 5XX)
        data = response.json()

        if data.get("cod") != 200: # Check for API-specific error codes
            error_message = data.get("message", "Unknown error from OpenWeatherMap API.")
            return WeatherOutput(city_name=city, error=f"OpenWeatherMap API Error: {error_message}")

        main_data = data.get("main", {})
        weather_data = data.get("weather", [{}])[0]
        wind_data = data.get("wind", {})

        temp_celsius = main_data.get("temp")
        temp_fahrenheit = (temp_celsius * 9/5) + 32 if temp_celsius is not None else None
        
        return WeatherOutput(
            city_name=data.get("name", city),
            temperature_celsius=temp_celsius,
            temperature_fahrenheit=round(temp_fahrenheit, 2) if temp_fahrenheit is not None else None,
            description=weather_data.get("description"),
            humidity=main_data.get("humidity"),
            wind_speed_mps=wind_data.get("speed")
        )

    except requests.exceptions.Timeout:
        return WeatherOutput(city_name=city, error="Request to OpenWeatherMap API timed out.")
    except requests.exceptions.RequestException as e:
        return WeatherOutput(city_name=city, error=f"Failed to connect to OpenWeatherMap API: {str(e)}")
    except json.JSONDecodeError:
        return WeatherOutput(city_name=city, error="Failed to parse JSON response from OpenWeatherMap API.")
    except Exception as e:
        return WeatherOutput(city_name=city, error=f"An unexpected error occurred in weather tool: {str(e)}")

# --- Langchain Tool Definition ---
def _weather_langchain_adapter(city: str, api_keys_instance: Dict[str, str], config_instance: Any) -> str:
    try:
        inp = WeatherInput(city=city)
    except ValidationError as e:
        error_output = WeatherOutput(city_name=city, error="Input validation failed", details=str(e))
        return error_output.model_dump_json()
    
    output = _run_weather_logic(inp, api_keys_instance, config_instance)
    return output.model_dump_json()

def get_weather_langchain_tool(api_keys_instance: Dict[str, str], config_instance: Any) -> Tool:
    """Returns a Langchain Tool instance for fetching weather information."""
    func_with_context = functools.partial(
        _weather_langchain_adapter, 
        api_keys_instance=api_keys_instance, 
        config_instance=config_instance
    )
    
    return Tool(
        name="get_weather",
        func=func_with_context,
        description="Fetches real-time weather data for a given city. Input should be the city name. Returns a JSON string with weather details or an error.",
        args_schema=WeatherInput,
    )

# --- Direct callable function for app.py (if needed) ---
def run_weather_tool_direct(args_dict: dict, api_keys: Dict[str, str], config: Any) -> dict:
    try:
        inp = WeatherInput(**args_dict)
    except ValidationError as e:
        return WeatherOutput(city_name=args_dict.get("city"), error="Input validation failed", details=str(e)).model_dump()
    
    output = _run_weather_logic(inp, api_keys, config)
    return output.model_dump()

if __name__ == "__main__":
    class DummyConfig:
        DEBUG_MODE = True
        # Add other config attributes if _run_weather_logic expects them

    dummy_config_instance = DummyConfig()
    # Simulate API keys for testing - REPLACE WITH YOUR ACTUAL KEY FOR REAL TESTS
    # Ensure config.json exists in the parent directory with your key for this test to work fully.
    dummy_api_keys_instance = {}
    try:
        with open("../config.json", "r") as f:
            loaded_keys = json.load(f)
            dummy_api_keys_instance = {"OPENWEATHERMAP_API_KEY": loaded_keys.get("OPENWEATHERMAP_API_KEY", "YOUR_KEY_HERE_IF_NOT_IN_CONFIG_JSON")}
            if dummy_api_keys_instance["OPENWEATHERMAP_API_KEY"] == "YOUR_KEY_HERE_IF_NOT_IN_CONFIG_JSON" or not dummy_api_keys_instance["OPENWEATHERMAP_API_KEY"]:
                 print("WARNING: OpenWeatherMap API key not found or is a placeholder. Live tests will fail.")
    except FileNotFoundError:
        print("Warning: ../config.json not found. Using placeholder API key for OpenWeatherMap. Live tests will fail.")
        dummy_api_keys_instance = {"OPENWEATHERMAP_API_KEY": "YOUR_KEY_HERE_FILE_NOT_FOUND"}
    except json.JSONDecodeError:
        print("Warning: ../config.json is not valid JSON. Using placeholder API key. Live tests will fail.")
        dummy_api_keys_instance = {"OPENWEATHERMAP_API_KEY": "YOUR_KEY_HERE_JSON_ERROR"}
    except Exception as e:
        print(f"Error loading API keys: {e}. Using placeholder API key. Live tests will fail.")
        dummy_api_keys_instance = {"OPENWEATHERMAP_API_KEY": "YOUR_KEY_HERE_GENERAL_ERROR"}


    print("--- Testing Weather Tool (Example: London) via Langchain Tool Adapter ---")
    lc_weather_tool = get_weather_langchain_tool(dummy_api_keys_instance, dummy_config_instance)
    try:
        # Note: This test will make a live API call if a valid key is provided.
        result_json_str = lc_weather_tool.func(city="London")
        print(json.dumps(json.loads(result_json_str), indent=2))
    except Exception as e:
        print(f"Error during Langchain tool direct func call: {e}")

    print("\n--- Testing Weather Tool (Example: NonExistentCity123) via Langchain Tool Adapter ---")
    try:
        result_json_str_nonexistent = lc_weather_tool.func(city="NonExistentCity123abc")
        print(json.dumps(json.loads(result_json_str_nonexistent), indent=2))
    except Exception as e:
        print(f"Error during Langchain tool direct func call: {e}")

    print("\n--- Testing Weather Tool (Invalid Input to Pydantic model directly) ---")
    try:
        invalid_input = WeatherInput(city_name="test") # type: ignore
    except ValidationError as e:
        print(f"Caught expected validation error for Pydantic model: {e}")

    print("\n--- Testing run_weather_tool_direct (Example: Paris) ---")
    direct_result_paris = run_weather_tool_direct({"city": "Paris"}, dummy_api_keys_instance, dummy_config_instance)
    print(json.dumps(direct_result_paris, indent=2))

    print("\n--- Testing run_weather_tool_direct (Invalid Input) ---")
    direct_invalid_result = run_weather_tool_direct({"city_name": "test"}, dummy_api_keys_instance, dummy_config_instance)
    print(json.dumps(direct_invalid_result, indent=2))

