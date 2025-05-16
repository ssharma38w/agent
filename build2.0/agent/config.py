# /home/ubuntu/chatbot_project/config.py

# --- LLM Configuration ---
# Specifies the default Ollama model to be used by the planner and executor.
# Users can change this value to use other Ollama models like 'llama3', 'gemma', etc.
# Ensure the selected model is available in your local Ollama installation.
OLLAMA_MODEL = "huihui_ai/qwen2.5-1m-abliterated:latest"

# --- Ollama Embedding Model Configuration ---
# Specifies the Ollama model to be used for generating embeddings (e.g., for RAG).
# Ensure this model is suitable for embedding tasks and available in your Ollama installation.
# Often, models like 'nomic-embed-text' or 'mxbai-embed-large' are used, or even general models like 'mistral' can provide embeddings.
OLLAMA_EMBEDDING_MODEL = "huihui_ai/qwen2.5-1m-abliterated:latest" # Defaulting to mistral, user can change to a dedicated embedding model
OLLAMA_EMBEDDING_CHUNK_SIZE = 1000 # For Langchain OllamaEmbeddings, if it supports chunk_size directly or for text splitting before embedding

# --- Ollama Connection ---
# Base URL for the Ollama API server.
OLLAMA_BASE_URL = "http://localhost:11434"

# --- Application Settings ---
# Base URL of this Flask application, used by the executor to call tool endpoints.
# This should match the host and port where the Flask app is running.
APP_BASE_URL = "http://localhost:5000" # Ensure this is accurate for your setup

# --- Debug Mode ---
# Set to True for verbose logging and more detailed error messages in responses.
# Set to False for production environments.
DEBUG_MODE = True

# --- API Keys Configuration File ---
# Path to the JSON file containing API keys for various services (e.g., OpenWeatherMap, SerpAPI).
# The `example_config.json` provides a template for this file.
# Using an absolute path is generally safer for server applications.
API_KEYS_FILE = "agent/config.json"

# --- Web Search Tool Configuration ---
# Preferred web search provider. Options: "duckduckgo", "serpapi"
# If "serpapi" is chosen, a SERPAPI_API_KEY must be provided in config.json.
WEB_SEARCH_PROVIDER = "serpapi"

# --- Weather Tool Configuration ---
# API provider for weather. Default is "openweathermap".
# Requires an API key in config.json (e.g., OPENWEATHERMAP_API_KEY).
WEATHER_API_PROVIDER = "openweathermap"

# --- RAG Configuration ---
DATA_DIR = "data/" # Directory for RAG source documents
VECTORSTORE_PATH = "vectorstore/" # Directory to persist FAISS or ChromaDB
TEXT_SPLITTER_CHUNK_SIZE = 1000
TEXT_SPLITTER_CHUNK_OVERLAP = 200

# --- Optional: Model Selector (Advanced) ---
# For a UI-based model selector, the frontend and backend would need more complex logic.
# For now, changing OLLAMA_MODEL and OLLAMA_EMBEDDING_MODEL here is the primary way to switch models.
# AVAILABLE_OLLAMA_MODELS = ["mistral", "llama3", "gemma:2b", "gemma:7b"]
# AVAILABLE_EMBEDDING_MODELS = ["nomic-embed-text", "mxbai-embed-large", "mistral"]

# --- Langchain Specific Settings ---
# Temperature for LLM responses (0.0 to 1.0). Lower is more deterministic, higher is more creative.
LLM_TEMPERATURE = 0.7
# Maximum number of tokens for LLM responses, if applicable to the Langchain component.
# LLM_MAX_TOKENS = 2048 # Often handled by the model itself or specific chain configurations
FLASK_PORT = 5000 # Port for the Flask app to run on
