# /home/ubuntu/chatbot_project/utils/llm_services.py
from langchain_community.chat_models import ChatOllama
from langchain_community.embeddings import OllamaEmbeddings
from agent import config # Use relative import from parent directory for config

# Global instances, initialized once
_chat_llm_instance = None
_embedding_model_instance = None

def get_chat_ollama_instance():
    """Initializes and returns a singleton ChatOllama instance."""
    global _chat_llm_instance
    if _chat_llm_instance is None:
        if config.DEBUG_MODE:
            print(f"--- llm_services.py --- Initializing ChatOllama with model: {config.OLLAMA_MODEL}, base_url: {config.OLLAMA_BASE_URL}, temperature: {config.LLM_TEMPERATURE}")
        try:
            _chat_llm_instance = ChatOllama(
                model=config.OLLAMA_MODEL,
                base_url=config.OLLAMA_BASE_URL,
                temperature=config.LLM_TEMPERATURE
                # Add other parameters like top_k, top_p, mirostat if needed from config
            )
            # Test with a simple invoke to ensure connection
            # _chat_llm_instance.invoke("Hello") 
            # Commenting out the test invoke to avoid issues if Ollama is not immediately ready during import/startup
            # It will be tested when first used by planner/executor
        except Exception as e:
            print(f"ERROR: Failed to initialize ChatOllama: {e}")
            # Potentially raise the error or handle it by returning None / a dummy LLM
            # For now, let it be None, and calling code should check
            _chat_llm_instance = None # Ensure it remains None on failure
            # raise # Re-raise to make the problem visible immediately during startup
    return _chat_llm_instance

def get_ollama_embeddings_instance():
    """Initializes and returns a singleton OllamaEmbeddings instance."""
    global _embedding_model_instance
    if _embedding_model_instance is None:
        if config.DEBUG_MODE:
            print(f"--- llm_services.py --- Initializing OllamaEmbeddings with model: {config.OLLAMA_EMBEDDING_MODEL}, base_url: {config.OLLAMA_BASE_URL}")
        try:
            _embedding_model_instance = OllamaEmbeddings(
                model=config.OLLAMA_EMBEDDING_MODEL,
                base_url=config.OLLAMA_BASE_URL,
                # For OllamaEmbeddings, chunk_size is not a direct parameter.
                # It is typically handled during text splitting before calling embed_documents.
                # config.OLLAMA_EMBEDDING_CHUNK_SIZE might be used by the RAG pipeline's text splitter.
            )
            # Test with a simple embedding to ensure connection
            # _embedding_model_instance.embed_query("Test embedding")
            # Commenting out test to avoid startup issues
        except Exception as e:
            print(f"ERROR: Failed to initialize OllamaEmbeddings: {e}")
            _embedding_model_instance = None
            # raise
    return _embedding_model_instance

# Example of how to use them (primarily for testing this module directly)
if __name__ == "__main__":
    print("Attempting to initialize LLM and Embedding services...")
    
    # Ensure config is loaded (this might require adjusting paths if run directly)
    # For direct execution, you might need to temporarily add parent to sys.path
    # import sys
    # import os
    # sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # from chatbot_project import config # This won't work due to relative import in llm_services.py
    # The relative import `from .. import config` assumes this module is part of a package.

    # To test this file directly, you would typically mock `config` or run it as part of the main app.
    # For now, we assume it's imported by other modules that handle the package structure correctly.

    # Simulate config for standalone testing if needed:
    class MockConfig:
        OLLAMA_MODEL = "huihui_ai/qwen2.5-1m-abliterated:latest"
        OLLAMA_EMBEDDING_MODEL = "huihui_ai/qwen2.5-1m-abliterated:latest" # or "nomic-embed-text"
        OLLAMA_BASE_URL = "http://localhost:11434"
        LLM_TEMPERATURE = 0.2
        DEBUG_MODE = True
    
    # Monkey patch config for this direct test run
    original_config = config
    config = MockConfig()

    llm = get_chat_ollama_instance()
    if llm:
        print("ChatOllama instance created.")
        try:
            # Test invocation (ensure Ollama server is running with the model)
            # response = llm.invoke("What is the capital of France? Respond concisely.")
            # print(f"LLM Test Response: {response.content}")
            print("LLM Test Invoke commented out. Run with app to test fully.")
        except Exception as e:
            print(f"Error testing LLM invoke: {e}")
    else:
        print("Failed to create ChatOllama instance.")

    embeddings = get_ollama_embeddings_instance()
    if embeddings:
        print("OllamaEmbeddings instance created.")
        try:
            # Test embedding (ensure Ollama server is running with the embedding model)
            # vector = embeddings.embed_query("This is a test sentence.")
            # print(f"Embedding Test Vector (first 5 dims): {vector[:5]}")
            print("Embedding Test commented out. Run with app to test fully.")
        except Exception as e:
            print(f"Error testing embeddings: {e}")
    else:
        print("Failed to create OllamaEmbeddings instance.")
    
    # Restore original config if it was monkey-patched
    config = original_config

