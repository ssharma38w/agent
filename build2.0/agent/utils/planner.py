# /home/ubuntu/chatbot_project/utils/planner.py
import json
from agent import config # Use relative import
from agent.utils.llm_services import get_chat_ollama_instance
from typing import Optional

# Define the tools available for the planner to use
# This should be dynamically generated or kept in sync with actual tools
# Descriptions and argument schemas should match the Langchain Tool definitions and Pydantic InputModels
AVAILABLE_TOOLS_PROMPT = """
Available tools:
1. web_search:
   Description: Searches the web using DuckDuckGo or SerpAPI. Useful for finding current information, news, or general web content.
   Arguments Schema (Pydantic): {"query": "<string: search_query>"}

2. wikipedia_search:
   Description: Fetches a summary of a topic from Wikipedia. Best for factual, encyclopedic information.
   Arguments Schema (Pydantic): {"topic": "<string: topic_name>"}

3. get_weather:
   Description: Fetches real-time weather data for a given city using OpenWeatherMap API.
   Arguments Schema (Pydantic): {"city": "<string: city_name>"}

4. magnet_link_fetcher:
   Description: Fetches torrent magnet links for a given movie or show name. Use responsibly and be aware of content legality.
   Arguments Schema (Pydantic): {"query": "<string: movie_or_show_name>"}

5. document_retrieval_augmented_generation (rag_tool):
   Description: Answers questions based on a collection of local documents. Use this for queries that require information from specific uploaded or indexed files within the system.
   Arguments Schema (Pydantic): {"query": "<string: user_question_about_documents>"}

6. llm_response_generation:
   Description: If no specific tool is suitable, or to synthesize information from previous tool outputs, or for conversational responses (greetings, chit-chat, direct questions that don't need external data), use this tool to generate a direct text response using the LLM.
   Arguments Schema (Pydantic): {"prompt_to_llm": "<string: text_prompt_for_direct_response_or_synthesis>"}
7. news_search:
   Description: Searches for the latest news articles on a given topic using NewsAPI.
   Arguments Schema (Pydantic): {"query": "<string: news_topic>"}
"""

class Planner:
    def __init__(self):
        self.llm = get_chat_ollama_instance()
        if config.DEBUG_MODE:
            print(f"--- planner.py --- Planner initialized. LLM ready: {self.llm is not None}")

    def generate_plan(self, user_query: str, conversation_history: list) -> Optional[dict]:
        """
        Generates a plan in JSON format based on the user query and conversation history.
        The plan outlines steps, tools to use, and arguments for those tools.
        """
        if not self.llm:
            print("ERROR: Planner LLM not available. Cannot generate plan.")
            # Fallback plan if LLM is not available
            return {
                "original_query": user_query,
                "plan": [{
                    "step": 1, 
                    "tool": "llm_response_generation", 
                    "arguments": {"prompt_to_llm": f"I am currently unable to create a detailed plan. Can you try rephrasing or asking a simpler question? Original query: {user_query}"},
                    "reasoning": "Fallback due to planner LLM unavailability."
                }]
            }

        system_prompt = (
            """
You are an AI assistant acting as a Planner. Your role is to analyze the user's query 
and the conversation history to create a step-by-step plan to fulfill the user's request. 
The plan MUST be in JSON format. Each step in the plan must specify a 'tool' to use from the available list, 
'arguments' for that tool (as a JSON object strictly matching the tool's Pydantic Arguments Schema), and a brief 'reasoning' for the step.
If the user query is a simple greeting, chit-chat, or a direct question that doesn't require a specific tool, plan a single step using the 'llm_response_generation' tool.
For complex queries requiring information from multiple tools or synthesis of information, the final step in the plan should usually be 'llm_response_generation' to synthesize information from previous tool outputs into a coherent answer for the user. 
When planning arguments for a tool, ensure they precisely match the Pydantic schema provided (e.g., if schema is {\"query\": \"<string>\"}, arguments must be {\"query\": \"actual search string\"}).
Do not use a tool if the query can be answered directly by the LLM with 'llm_response_generation'.
"""
            + AVAILABLE_TOOLS_PROMPT +
            """
Output ONLY the JSON plan. Do not include any other text, explanations, or markdown code block fences before or after the JSON.
Example Plan Format (ensure arguments match the Pydantic schema for the chosen tool):
{
  "original_query": "What's the weather in Paris and what is the capital of France according to Wikipedia?",
  "plan": [
    {"step": 1, "tool": "get_weather", "arguments": {"city": "Paris"}, "reasoning": "User asked for weather in Paris."},
    {"step": 2, "tool": "wikipedia_search", "arguments": {"topic": "Capital of France"}, "reasoning": "User asked for the capital of France from Wikipedia."},
    {"step": 3, "tool": "llm_response_generation", "arguments": {"prompt_to_llm": "Synthesize the weather information for Paris and the capital of France from Wikipedia into a single, user-friendly response."}, "reasoning": "Combine results from previous tools for the user."}
  ]
}
"""
        )

        # Construct a simplified history for the planner prompt
        # Langchain's ChatOllama expects a list of BaseMessage objects or dicts with "role" and "content"
        prompt_messages = [{"role": "system", "content": system_prompt}]
        for msg in conversation_history[-3:]: # Last 3 turns for context
            prompt_messages.append(msg) # msg should already be in {"role": "user/assistant", "content": "..."} format
        prompt_messages.append({"role": "user", "content": f"Given our conversation history, generate a JSON plan for my new query: {user_query}"}) 

        if config.DEBUG_MODE:
            print(f"--- planner.py --- Sending prompt to LLM for planning. Query: {user_query}")
            # print(f"Planner LLM Prompt Messages: {json.dumps(prompt_messages, indent=2)}") # Can be very verbose

        try:
            # Using ChatOllama instance from llm_services
            # Requesting JSON directly if the model/Langchain wrapper supports it well.
            # Ollama's `format: json` in the request body is key.
            # The ChatOllama wrapper might need specific handling for this or it might pass it through.
            # Forcing JSON output can be done by adding `json_mode=True` or similar to model kwargs if supported,
            # or by instructing the model very clearly in the prompt and parsing carefully.
            # Let's assume the prompt is strong enough for now, and Ollama's `format: "json"` in the raw request helps.
            
            # The ChatOllama.invoke method takes the list of messages directly.
            # We need to ensure the LLM is instructed to output JSON. The system prompt does this.
            # Forcing JSON output with ChatOllama can be tricky. Some models respect `format="json"` in `bind_tools` or `with_structured_output`.
            # A simpler way for now is to rely on the prompt and parse the string output.
            
            # Constructing the prompt string for older Ollama /api/generate style if needed, but ChatOllama uses messages.
            # For ChatOllama, we'll use the `invoke` method with the messages list.
            # The `format: "json"` parameter is usually set in the Ollama server request, not directly in ChatOllama's invoke method's standard args.
            # However, ChatOllama can take `**kwargs` that are passed to the Ollama client.
            # Let's try passing `format="json"` via `bind_kwargs` or similar if available, or rely on prompt.

            # Simpler approach: Get raw string response and parse JSON, as done before, but using the LLM instance.
            # The `ChatOllama` instance might have a `_llm_type` or similar to indicate it's a chat model.
            # We need to ensure the output is a string that we can then parse as JSON.

            response_message = self.llm.invoke(prompt_messages, format="json") # Attempting to pass format directly
            plan_str = response_message.content
            
            if config.DEBUG_MODE:
                print(f"--- planner.py --- Raw plan string from LLM: {plan_str}")
            
            # Clean up potential markdown code block fences if the LLM adds them
            if isinstance(plan_str, str):
                if plan_str.startswith("```json"):
                    plan_str = plan_str.replace("```json", "").replace("```", "").strip()
                elif plan_str.startswith("```") and plan_str.endswith("```"):
                    plan_str = plan_str[3:-3].strip()
            else:
                # If it's not a string, it might already be parsed by a newer Langchain version with structured output
                if isinstance(plan_str, dict) and "plan" in plan_str:
                    return plan_str # Already a dict, assume it's the plan
                else:
                    raise json.JSONDecodeError("LLM did not return a string or valid plan dict.", str(plan_str), 0)

            plan = json.loads(plan_str)
            
            # Basic validation of plan structure
            if "plan" in plan and isinstance(plan["plan"], list):
                # Further validation: ensure each step has tool, arguments, reasoning
                for step in plan["plan"]:
                    if not all(k in step for k in ("tool", "arguments", "reasoning")):
                        raise ValueError(f"Invalid step in plan: {step}. Missing required keys.")
                    if not isinstance(step["arguments"], dict):
                        # This is a common LLM mistake, try to fix if it's a stringified dict
                        if isinstance(step["arguments"], str):
                            try:
                                step["arguments"] = json.loads(step["arguments"])
                            except json.JSONDecodeError:
                                raise ValueError(f"Step arguments for tool '{step['tool']}' are not a valid JSON object or stringified JSON: {step['arguments']}")
                        else:
                             raise ValueError(f"Step arguments for tool '{step['tool']}' are not a dictionary: {step['arguments']}")
                if "original_query" not in plan:
                    plan["original_query"] = user_query # Add it if missing
                return plan
            else:
                print(f"Error: LLM generated invalid plan structure (missing 'plan' list): {plan_str}")
                raise ValueError("LLM generated invalid plan structure.")

        except json.JSONDecodeError as e:
            error_msg = f"Error decoding plan JSON from LLM: {e}. Response was: {plan_str if 'plan_str' in locals() else 'not available'}"
            print(error_msg)
        except ValueError as e: # Catch our custom validation errors
            error_msg = f"Plan validation error: {e}. Raw response: {plan_str if 'plan_str' in locals() else 'not available'}"
            print(error_msg)
        except Exception as e:
            import traceback
            error_msg = f"An unexpected error occurred during planning: {e}"
            print(error_msg)
            if config.DEBUG_MODE:
                traceback.print_exc()
        
        # Fallback plan if any error occurs
        return {
            "original_query": user_query, 
            "plan": [{
                "step": 1, 
                "tool": "llm_response_generation", 
                "arguments": {"prompt_to_llm": f"I had trouble understanding that or planning for it. Could you please rephrase? Original query: {user_query}"},
                "reasoning": "Fallback due to a planning error."
            }]
        }

if __name__ == '__main__':
    print("--- Testing Planner (Direct Run) ---")
    # This direct test requires Ollama to be running and accessible.
    # It also assumes config.py and llm_services.py are set up correctly.
    
    test_planner = Planner()
    if not test_planner.llm:
        print("CRITICAL: Planner LLM could not be initialized. Exiting test.")
        exit(1)

    test_queries = [
        "What is the weather like in London today and also tell me about the Eiffel Tower from Wikipedia.",
        "Hi there, how are you?",
        "Search for the latest news on AI and then find its summary on Wikipedia.",
        "What is the meaning of life according to my documents?",
        "Fetch a magnet link for 'The Matrix' and tell me the weather in New York."
    ]
    test_history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there! How can I help you?"}
    ]

    for i, t_query in enumerate(test_queries):
        print(f"\n--- Test Query {i+1}: {t_query} ---")
        generated_plan = test_planner.generate_plan(t_query, test_history)
        print("Generated Plan:")
        print(json.dumps(generated_plan, indent=2))
        # Basic validation of the output for the test
        assert generated_plan is not None, f"Plan for query '{t_query}' was None"
        assert "plan" in generated_plan, f"'plan' key missing for query '{t_query}'"
        assert isinstance(generated_plan["plan"], list), f"'plan' is not a list for query '{t_query}'"
        if generated_plan["plan"]:
            first_step = generated_plan["plan"][0]
            assert "tool" in first_step, f"'tool' missing in first step for query '{t_query}'"
            assert "arguments" in first_step, f"'arguments' missing in first step for query '{t_query}'"
            assert isinstance(first_step["arguments"], dict), f"'arguments' not a dict in first step for query '{t_query}'"

    print("\n--- Planner direct run tests complete. Check output above. ---")

