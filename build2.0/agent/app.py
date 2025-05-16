# /home/ubuntu/chatbot_project/app.py
from flask import Flask, render_template, request, jsonify, Response
import json

# Import utility modules - these now handle their own LLM/tool initializations
from utils.planner import Planner
from utils.executor import Executor

# Import configuration from config.py
import config # Use relative import for config when app is part of a package

app = Flask(__name__)

# --- Initialize Planner and Executor ---
# These classes now manage their dependencies (LLM, tools) internally based on config
planner = Planner() 
executor = Executor()

# --- Conversation History (Simple In-Memory) --- 
conversation_history = []
chat_title = "Untitled Chat"

# --- Routes --- 
@app.route("/")
def index():
    """Serves the main chat page."""
    return render_template("index.html", title=chat_title)

@app.route("/chat", methods=["POST"])
def chat():
    """Handles incoming chat messages, generates a plan, executes it, and streams responses."""
    global conversation_history, chat_title

    user_message_data = request.get_json()
    if not user_message_data or "message" not in user_message_data:
        return jsonify({"error": "No message provided or invalid format"}), 400
    
    user_message = user_message_data["message"]

    conversation_history.append({"role": "user", "content": user_message})

    # Update chat title based on the first significant user message
    if chat_title == "Untitled Chat" and len(user_message.split()) >= config.TITLE_GENERATION_MIN_WORDS:
        # Basic title generation: first few words
        title_candidate = " ".join(user_message.split()[:config.TITLE_GENERATION_MAX_WORDS])
        # Further refinement could be added here (e.g., LLM-based summarization for title)
        chat_title = title_candidate + "..." if len(user_message.split()) > config.TITLE_GENERATION_MAX_WORDS else title_candidate
        if config.DEBUG_MODE:
            print(f"--- app.py:/chat --- Chat title updated to: {chat_title}")

    if config.DEBUG_MODE:
        print(f"\n--- app.py:/chat --- User Message: {user_message}")
        # Show relevant history for planning (e.g., last 3 turns, excluding current user message which is passed separately)
        history_for_planner = conversation_history[:-1]
        print(f"--- app.py:/chat --- Generating plan with history (last {config.PLANNER_HISTORY_TURNS} turns): {json.dumps(history_for_planner[-config.PLANNER_HISTORY_TURNS:])}")
    
    # Generate plan using the refactored Planner
    # The planner now uses ChatOllama instance from llm_services
    generated_plan = planner.generate_plan(user_message, conversation_history[:-1]) # Pass history without current message
    
    if config.DEBUG_MODE:
        print(f"--- app.py:/chat --- Generated Plan: {json.dumps(generated_plan, indent=2)}")

    def generate_response_stream():
        bot_response_parts = []
        try:
            # The refactored Executor now handles Langchain tools directly and streams responses
            for chunk in executor.execute_plan(generated_plan, conversation_history):
                bot_response_parts.append(str(chunk)) # Ensure chunk is string
                yield str(chunk)
            
            full_bot_response = "".join(bot_response_parts)
            if full_bot_response.strip():
                # Avoid adding generic error messages from executor/planner to history as assistant responses
                # This logic can be refined based on how errors are structured by Executor/Planner
                is_error_message = full_bot_response.startswith("Error:") or \
                                   full_bot_response.startswith("⚠️ Sorry") or \
                                   "Could not connect to Ollama" in full_bot_response or \
                                   "issue with planning" in full_bot_response or \
                                   "unable to create a detailed plan" in full_bot_response or \
                                   "had trouble understanding that" in full_bot_response
                
                if not is_error_message:
                    conversation_history.append({"role": "assistant", "content": full_bot_response})
                elif config.DEBUG_MODE:
                    print(f"--- app.py:/chat --- Bot error/fallback response not added to history: {full_bot_response}")
            
            if config.DEBUG_MODE:
                print(f"--- app.py:/chat --- Full bot response streamed: {full_bot_response}")
                print(f"--- app.py:/chat --- Updated history (last 3 turns): {json.dumps(conversation_history[-3:])}")

        except Exception as e:
            error_message = f"Critical error in /chat stream: {e}"
            if config.DEBUG_MODE:
                import traceback
                traceback.print_exc()
                print(f"--- app.py:/chat --- {error_message}")
            yield f"⚠️ Sorry, a critical server error occurred. Please check server logs or try again. (Details: {str(e) if config.DEBUG_MODE else ''})"

    return Response(generate_response_stream(), mimetype="text/event-stream") # Changed to text/event-stream for better client handling

# The /tools/<tool_name> endpoint is no longer needed as the Executor calls tools directly.
# If specific tool actions need to be exposed via HTTP for other reasons (e.g., manual testing), 
# they could be added, but they are not part of the primary agent flow anymore.

@app.route("/health")
def health_check():
    """A simple health check endpoint."""
    # Could add checks for LLM/Ollama connectivity here if desired
    return jsonify({"status": "healthy", "message": "Chatbot application is running."}), 200

if __name__ == "__main__":
    print(f"Starting Flask app on host 0.0.0.0, port {config.FLASK_PORT}")
    print(f"Ollama URL: {config.OLLAMA_BASE_URL}")
    print(f"Default LLM Model: {config.OLLAMA_MODEL}")
    print(f"Default Embedding Model: {config.OLLAMA_EMBEDDING_MODEL}")
    print(f"Debug Mode: {config.DEBUG_MODE}")
    print(f"API Keys File: {config.API_KEYS_FILE}")
    print(f"RAG Data Directory: {config.DATA_DIR}")
    print(f"Vectorstore Path: {config.VECTORSTORE_PATH}")
    
    # Ensure RAG vector store is initialized on startup if not already handled lazily by RagTool
    # This can be done by calling the initialization function from rag_tool.py if it makes sense
    # For now, RagTool initializes its vector store on first use or when its get_tool is called.
    try:
        from utils.llm_services import get_chat_ollama_instance, get_ollama_embeddings_instance
        llm_instance = get_chat_ollama_instance()
        emb_instance = get_ollama_embeddings_instance()
        if not llm_instance:
            print("WARNING: ChatOllama LLM instance failed to initialize on startup check.")
        if not emb_instance:
            print("WARNING: OllamaEmbeddings instance failed to initialize on startup check.")
        
        # Attempt to initialize RAG tool to build vector store if not present
        # This is a bit of an eager load, but can be useful for first run.
        if config.INITIALIZE_RAG_ON_STARTUP:
            print("Attempting to initialize RAG vector store on startup...")
            from tools.rag_tool import _initialize_vector_store as init_rag_vs # Accessing protected member for startup
            init_rag_vs() # This will build/load the FAISS index
            print("RAG vector store initialization attempt complete.")

    except Exception as e:
        print(f"Error during startup initializations: {e}")

    app.run(host="0.0.0.0", port=config.FLASK_PORT, debug=config.DEBUG_MODE)

