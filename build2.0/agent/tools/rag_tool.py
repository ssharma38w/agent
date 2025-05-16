# /home/ubuntu/chatbot_project/tools/rag_tool.py
import json
import os
from typing import Optional, Dict, Any, List, Type
from pydantic import BaseModel, Field, HttpUrl, ValidationError
from langchain.tools import Tool
import functools

from langchain_community.vectorstores import FAISS
from langchain.chains import RetrievalQA
from langchain_community.document_loaders import DirectoryLoader, TextLoader # Added TextLoader for .md
from langchain.text_splitter import RecursiveCharacterTextSplitter
# Assuming llm_services.py is in utils, and config.py is in the root of chatbot_project
from agent.utils.llm_services import get_chat_ollama_instance, get_ollama_embeddings_instance
from agent import config

# --- Pydantic Schemas for RAG Tool ---
class RagInput(BaseModel):
    query: str = Field(..., description="The query to answer using retrieved documents.")

    class Config:
        extra = "forbid"

class DocumentSource(BaseModel):
    source_id: str = Field(..., description="Identifier for the source document (e.g., filename, URL).")
    content_snippet: Optional[str] = Field(None, description="A relevant snippet from the source document.")
    page_number: Optional[int] = Field(None, description="Page number if applicable (e.g., for PDFs).")
    # Potentially add other metadata like document title, last modified date, etc.

class RagOutput(BaseModel):
    query: str = Field(..., description="The original query.")
    answer: Optional[str] = Field(None, description="The answer generated from the RAG pipeline.")
    source_documents: Optional[List[DocumentSource]] = Field(None, description="A list of source documents used to generate the answer.")
    error: Optional[str] = Field(None, description="Error message if the RAG process failed.")
    details: Optional[str] = Field(None, description="Additional details for errors.")

    class Config:
        extra = "forbid"

# Global vector store instance to avoid reloading/rebuilding on every call (can be improved with persistence)
_vector_store_instance = None

def _initialize_vector_store():
    """Initializes the vector store from documents in the data directory."""
    global _vector_store_instance
    if _vector_store_instance is not None:
        return _vector_store_instance

    if config.DEBUG_MODE:
        print(f"--- rag_tool.py --- Initializing vector store from: {config.DATA_DIR}")

    try:
        # Check if a pre-built FAISS index exists
        embedding_function = get_ollama_embeddings_instance()
        if embedding_function is None:
            raise ValueError("OllamaEmbeddings instance could not be created.")

        if os.path.exists(config.VECTORSTORE_PATH) and os.path.isdir(config.VECTORSTORE_PATH):
            if config.DEBUG_MODE:
                print(f"--- rag_tool.py --- Loading existing FAISS index from: {config.VECTORSTORE_PATH}")
            _vector_store_instance = FAISS.load_local(config.VECTORSTORE_PATH, embedding_function, allow_dangerous_deserialization=True)
            if config.DEBUG_MODE:
                print("--- rag_tool.py --- FAISS index loaded successfully.")
            return _vector_store_instance
        
        if config.DEBUG_MODE:
            print(f"--- rag_tool.py --- No existing FAISS index found at {config.VECTORSTORE_PATH}. Building new one.")

        # Load documents (currently only .md files)
        # For PDF, would use PyPDFLoader or UnstructuredPDFLoader
        # Using TextLoader for .md files as DirectoryLoader might need specific loader types.
        loader = DirectoryLoader(config.DATA_DIR, glob="**/*.md", loader_cls=TextLoader, loader_kwargs={"encoding": "utf-8"}, show_progress=True, use_multithreading=False)
        documents = loader.load()

        if not documents:
            if config.DEBUG_MODE:
                print("--- rag_tool.py --- No documents found in data directory. RAG will not be effective.")
            # Create an empty FAISS index if no documents are found to prevent errors on load_local
            # This is a bit of a workaround; ideally, the tool should report this state.
            # For now, let it proceed, and retrieval will yield no results.
            # Or, we can set _vector_store_instance to a specific state indicating no docs.
            _vector_store_instance = "NO_DOCS_LOADED" # Special state
            return _vector_store_instance

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.TEXT_SPLITTER_CHUNK_SIZE,
            chunk_overlap=config.TEXT_SPLITTER_CHUNK_OVERLAP
        )
        texts = text_splitter.split_documents(documents)
        
        if config.DEBUG_MODE:
            print(f"--- rag_tool.py --- Loaded {len(documents)} documents, split into {len(texts)} chunks.")

        _vector_store_instance = FAISS.from_documents(texts, embedding_function)
        # Save the FAISS index
        os.makedirs(config.VECTORSTORE_PATH, exist_ok=True)
        _vector_store_instance.save_local(config.VECTORSTORE_PATH)
        if config.DEBUG_MODE:
            print(f"--- rag_tool.py --- FAISS index built and saved to: {config.VECTORSTORE_PATH}")
        
        return _vector_store_instance

    except Exception as e:
        print(f"ERROR: Failed to initialize vector store: {e}")
        _vector_store_instance = None # Ensure it's None on failure
        return None

# --- Core Tool Logic ---
def _run_rag_logic(inp: RagInput, api_keys: Dict[str, str], app_config: Any) -> RagOutput: # Renamed config to app_config to avoid clash
    """
    Internal logic for performing Retrieval Augmented Generation using local documents.
    """
    query = inp.query

    if app_config.DEBUG_MODE:
        print(f"--- tools/rag_tool.py (_run_rag_logic) --- Processing RAG query: {query}")

    try:
        vector_store = _initialize_vector_store()
        if vector_store is None:
            return RagOutput(query=query, error="RAG vector store could not be initialized.", details="Check Ollama embedding model and data directory.")
        if vector_store == "NO_DOCS_LOADED":
             return RagOutput(query=query, answer="No documents have been loaded into the knowledge base. I cannot answer this query from local documents.", source_documents=[])

        llm = get_chat_ollama_instance()
        if llm is None:
            return RagOutput(query=query, error="ChatOllama LLM instance could not be created for RAG.")

        # Create RetrievalQA chain
        # k can be configured in config.py if needed
        retriever = vector_store.as_retriever(search_kwargs={"k": 3})
        
        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",  # Other types: map_reduce, refine, map_rerank
            retriever=retriever,
            return_source_documents=True # Crucial for citations
        )

        if app_config.DEBUG_MODE:
            print(f"--- rag_tool.py --- Executing RAG chain for query: {query}")
        
        result = qa_chain.invoke({"query": query}) # Langchain 0.1.0+ uses invoke

        answer = result.get("result")
        source_docs_data = result.get("source_documents", [])
        
        formatted_sources = []
        for doc in source_docs_data:
            source_id = doc.metadata.get("source", "Unknown Source")
            # Try to extract filename if it's a path
            source_id = os.path.basename(source_id)
            page_num = doc.metadata.get("page") # if available from loader
            formatted_sources.append(DocumentSource(
                source_id=source_id,
                content_snippet=doc.page_content[:200] + "..." if doc.page_content else None, # First 200 chars as snippet
                page_number=page_num
            ))
        
        if not answer and not formatted_sources:
             return RagOutput(query=query, answer="I couldn't find a specific answer in the documents for your query.", source_documents=[])

        return RagOutput(query=query, answer=answer, source_documents=formatted_sources)

    except Exception as e:
        if app_config.DEBUG_MODE:
            import traceback
            traceback.print_exc()
        return RagOutput(query=query, error=f"An error occurred during RAG pipeline execution: {str(e)}")

# --- Langchain Tool Definition ---
def _rag_langchain_adapter(query: str, api_keys_instance: Dict[str, str], config_instance: Any) -> str:
    try:
        inp = RagInput(query=query)
    except ValidationError as e:
        error_output = RagOutput(query=query, error="Input validation failed for RAG tool", details=str(e))
        return error_output.model_dump_json()
    
    # Pass the main config object to _run_rag_logic
    output = _run_rag_logic(inp, api_keys_instance, config_instance) 
    return output.model_dump_json()

def get_rag_langchain_tool(api_keys_instance: Dict[str, str], config_instance: Any) -> Tool:
    """Returns a Langchain Tool instance for Retrieval Augmented Generation."""
    # Initialize vector store once when the tool is created/first requested, if not already done.
    # This is a bit eager; could be lazy-loaded on first call too.
    _initialize_vector_store() 

    func_with_context = functools.partial(
        _rag_langchain_adapter, 
        api_keys_instance=api_keys_instance, 
        config_instance=config_instance # Pass the main config object
    )
    
    return Tool(
        name="document_retrieval_augmented_generation",
        func=func_with_context,
        description="Answers questions based on a collection of local documents. Use this for queries that require information from specific uploaded or indexed files. Input should be the user\'s question. Returns a JSON string with the answer and source documents, or an error.",
        args_schema=RagInput,
    )

# --- Direct callable function for app.py (if needed) ---
def run_rag_tool_direct(args_dict: dict, api_keys: Dict[str, str], app_config: Any) -> dict:
    try:
        inp = RagInput(**args_dict)
    except ValidationError as e:
        return RagOutput(query=args_dict.get("query", "N/A"), error="Input validation failed", details=str(e)).model_dump()
    
    output = _run_rag_logic(inp, api_keys, app_config)
    return output.model_dump()

if __name__ == "__main__":
    # This __main__ block is for basic testing and might require adjustments
    # to paths or mocking if run outside the main application context.
    print("--- Testing RAG Tool (Standalone) ---")
    
    # For direct testing, ensure config.py and utils/llm_services.py are accessible.
    # This often means running from the root of the chatbot_project or adjusting sys.path.
    # Example: Add chatbot_project to PYTHONPATH or run as `python -m chatbot_project.tools.rag_tool`

    # Create a dummy config for testing if not running as part of the app
    # This is simplified; real config would be loaded by the app
    class MockLocalConfig:
        DEBUG_MODE = True
        DATA_DIR = "../data"  # Adjust path relative to this file if run directly
        VECTORSTORE_PATH = "../vectorstore_test" # Use a test-specific path
        TEXT_SPLITTER_CHUNK_SIZE = 500
        TEXT_SPLITTER_CHUNK_OVERLAP = 50
        # LLM/Embedding settings (ensure these match what llm_services expects or mock llm_services)
        OLLAMA_MODEL = "mistral"
        OLLAMA_EMBEDDING_MODEL = "mistral" # or "nomic-embed-text"
        OLLAMA_BASE_URL = "http://localhost:11434"
        LLM_TEMPERATURE = 0.1 # More deterministic for testing

    mock_config_instance = MockLocalConfig()
    
    # Crucial: For this test to work, the main `config` module used by `llm_services`
    # and `_initialize_vector_store` needs to be effectively this `mock_config_instance`.
    # This is tricky with Python imports. A better test setup would use pytest and fixtures.
    # For now, we rely on the fact that `config` is imported at the top of this file.
    # If you run this file directly, `from .. import config` will likely fail.
    # You might need to temporarily change it to `import config` and have a `config.py` in the same dir for this test.

    # Let's assume `config` is already the main app config for this illustrative test.
    # And `llm_services` can pick it up.

    # Create a dummy data file for testing if it doesn't exist
    if not os.path.exists(mock_config_instance.DATA_DIR):
        os.makedirs(mock_config_instance.DATA_DIR)
    sample_doc_path = os.path.join(mock_config_instance.DATA_DIR, "test_rag_doc.md")
    if not os.path.exists(sample_doc_path):
        with open(sample_doc_path, "w") as f:
            f.write("# Test Document for RAG\n\nThis document talks about apples and oranges.\nApples are red or green. Oranges are orange.\nLangchain is a framework for LLMs.")
        print(f"Created sample document: {sample_doc_path}")

    # Clean up old test vectorstore if it exists to force rebuild
    if os.path.exists(mock_config_instance.VECTORSTORE_PATH):
        import shutil
        shutil.rmtree(mock_config_instance.VECTORSTORE_PATH)
        print(f"Removed old test vectorstore: {mock_config_instance.VECTORSTORE_PATH}")

    # Test with the direct function call, passing the mock_config_instance
    print("\n--- Testing run_rag_tool_direct --- ")
    # Note: This test relies on Ollama server being up and models available.
    try:
        test_query = RagInput(query="What are apples?")
        # For this direct test, we pass mock_config_instance as the `app_config` argument
        # The `_initialize_vector_store` and `llm_services` will still try to use the globally imported `config`
        # This is a limitation of this simple __main__ test. 
        # To truly test with mock_config, `config` itself would need to be patched before imports.
        
        # For a more controlled test, we should mock get_chat_ollama_instance and get_ollama_embeddings_instance
        # or ensure the global `config` is what we want it to be.
        # For now, this test will likely use the main `config.py` values if run via `python -m ...`
        
        # Let's try to make the test use the mock_config by overriding the global `config` for the test scope
        # This is generally not good practice but can work for simple script tests.
        original_main_config = config # Save the original config from the top-level import
        globals()['config'] = mock_config_instance # Override global config for this test run

        rag_result = run_rag_tool_direct({"query": "What color are apples?"}, {}, mock_config_instance)
        print(json.dumps(rag_result, indent=2))

        rag_result_lc = run_rag_tool_direct({"query": "Tell me about Langchain from the document."}, {}, mock_config_instance)
        print(json.dumps(rag_result_lc, indent=2))

        globals()['config'] = original_main_config # Restore original config

    except Exception as e:
        print(f"Error during RAG direct test: {e}")
        import traceback
        traceback.print_exc()

    print("\nNote: For full RAG tool testing, ensure Ollama is running with required models, ")
    print("and paths in config.py (or mock_config_instance here) are correct.")

