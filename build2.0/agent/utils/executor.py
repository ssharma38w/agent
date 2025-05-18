import json
from pydantic import ValidationError

from agent import config
from agent.utils.llm_services import get_chat_ollama_instance
from typing import List, Dict
# Import tool getter functions
from agent.tools.web_search import get_web_search_langchain_tool, WebSearchOutput
from agent.tools.news_search import get_news_langchain_tool, NewsOutput
from agent.tools.wiki import get_wiki_langchain_tool, WikiOutput
from agent.tools.weather import get_weather_langchain_tool, WeatherOutput
from agent.tools.magnet import get_magnet_fetcher_langchain_tool, MagnetOutput
from agent.tools.rag_tool import get_rag_langchain_tool, RagOutput

# Helper to load API keys once
_api_keys_instance = None

def get_api_keys():
    global _api_keys_instance
    if _api_keys_instance is None:
        try:
            with open(config.API_KEYS_FILE, "r") as f:
                _api_keys_instance = json.load(f)
            if config.DEBUG_MODE:
                print(f"--- executor.py --- API keys loaded from {config.API_KEYS_FILE}")
        except FileNotFoundError:
            if config.DEBUG_MODE:
                print(f"--- executor.py --- API keys file not found at {config.API_KEYS_FILE}. Some tools may not work.")
            _api_keys_instance = {}
        except json.JSONDecodeError:
            if config.DEBUG_MODE:
                print(f"--- executor.py --- Error decoding API keys file {config.API_KEYS_FILE}. Malformed JSON.")
            _api_keys_instance = {}
        except Exception as e:
            if config.DEBUG_MODE:
                print(f"--- executor.py --- An unexpected error occurred while loading API keys: {e}")
            _api_keys_instance = {}
    return _api_keys_instance

class Executor:
    def __init__(self):
        self.llm = get_chat_ollama_instance()
        self.api_keys = get_api_keys()
        self.tools = self._initialize_tools()
        if config.DEBUG_MODE:
            print(f"--- executor.py --- Executor initialized. LLM ready: {self.llm is not None}. Tools loaded: {list(self.tools.keys())}")

    def _initialize_tools(self):
        """Initializes and returns a dictionary of available Langchain tools."""
        tools_dict = {}
        try:
            tools_dict["web_search"] = get_web_search_langchain_tool(self.api_keys, config)
            # tools_dict["wikipedia_search"] = get_wiki_langchain_tool(self.api_keys, config)
            # tools_dict["get_weather"] = get_weather_langchain_tool(self.api_keys, config)
            # tools_dict["magnet_link_fetcher"] = get_magnet_fetcher_langchain_tool(self.api_keys, config)
            # tools_dict["document_retrieval_augmented_generation"] = get_rag_langchain_tool(self.api_keys, config)
            tools_dict["news_search"] = get_news_langchain_tool(self.api_keys, config)
        except Exception as e:
            if config.DEBUG_MODE:
                print(f"--- executor.py --- Error initializing tools: {e}. Some tools may be unavailable.")
        return tools_dict

    def execute_step(self, step_plan: dict, chat_history: list, context):
        """Executes a single step from the plan using Langchain tools."""
        tool_name = step_plan.get("tool")
        # Arguments from the planner are expected to be a dictionary matching the tool's Pydantic InputModel fields
        # or a single string if the tool's adapter handles it (e.g. for query-based tools)
        arguments = step_plan.get("arguments", {})
        reasoning = step_plan.get("reasoning", "No reasoning provided.")

        if config.DEBUG_MODE:
            print(f"Executor: Executing step - Tool: {tool_name}, Args: {arguments}, Reasoning: {reasoning}")

        if tool_name == "llm_response_generation":
            prompt_to_llm = arguments.get("prompt_to_llm", f"""Answer user in a conversational tone, based on the given context.
                                          Use code blocks if required.

                                          User Query: 
                                          {chat_history[-1]['content']}

                                          Context:
                                          {context}
                                          """)
            # Always pass the current chat_history as context
            return self._get_llm_synthesis_stream(
                prompt=prompt_to_llm,
                system_prompt="Help User",
                chat_history=chat_history
            )
        
        selected_tool = self.tools.get(tool_name)
        if not selected_tool:
            error_msg = f"Tool \'{tool_name}\' not found or not initialized."
            if config.DEBUG_MODE:
                print(f"Executor: {error_msg}")
            return {"tool_name": tool_name, "status": "error", "output": error_msg, "is_stream": False}

        try:
            # Langchain tools expect a single input string or a dict for structured tools.
            # Our tool adapters are designed to take the primary argument (e.g., query, city) directly.
            # The planner should provide arguments that the tool.run() method can handle.
            # If `arguments` is a dict and the tool has `args_schema`, Langchain passes it.
            # If `arguments` is a string, it's passed as the first arg.
            # For our tools, the planner should provide the arguments as a dictionary that matches the Pydantic InputModel.
            # The `tool.run()` method will then pass this to our adapter, which validates it.
            
            # If the tool's args_schema expects a single string (e.g. simple query), 
            # and planner provides `{"query": "value"}`, we might need to extract "value".
            # However, our Pydantic InputModels for tools like web_search, wiki, etc., expect `{"query": "..."}` or `{"topic": "..."}`.
            # So, passing the `arguments` dict directly to `tool.run()` should work.
            tool_input_arg = arguments # This assumes planner provides a dict matching the tool's InputModel
            if isinstance(arguments, dict) and len(arguments) == 1 and selected_tool.args_schema:
                 # If args_schema expects a single field (e.g. query) and planner sends { "query": "value" }
                 # Langchain tool.run might handle this correctly if the func expects `query=value`
                 # Or if the func expects a single string, we might need to extract it.
                 # For now, let's assume the planner provides the arguments correctly for tool.run(arguments_dict)
                 pass # Keep tool_input_arg as the dictionary

            raw_tool_result_json_str = selected_tool.run(tool_input_arg)
            
            # The tool itself returns a JSON string of its Pydantic OutputModel
            tool_result_dict = json.loads(raw_tool_result_json_str)

            if config.DEBUG_MODE:
                print(f"Executor: Tool \'{tool_name}\' executed. Parsed result: {tool_result_dict}")
            
            # Check for error field in the Pydantic OutputModel's dict representation
            if tool_result_dict.get("error"):
                return {"tool_name": tool_name, "status": "error", "output": tool_result_dict, "is_stream": False}
            else:
                return {"tool_name": tool_name, "status": "success", "output": tool_result_dict, "is_stream": False}

        except ValidationError as e:
            error_msg = f"Input validation error for tool \'{tool_name}\': {e}"
            if config.DEBUG_MODE:
                print(f"Executor: {error_msg}")
            return {"tool_name": tool_name, "status": "error", "output": {"error": error_msg, "details": str(e.errors())}, "is_stream": False}
        except json.JSONDecodeError as e:
            error_msg = f"Error decoding JSON response from tool \'{tool_name}\': {e}. Raw response: {raw_tool_result_json_str[:500]}"
            if config.DEBUG_MODE:
                print(f"Executor: {error_msg}")
            return {"tool_name": tool_name, "status": "error", "output": {"error": error_msg}, "is_stream": False}
        except Exception as e:
            import traceback
            error_msg = f"Unexpected error executing tool \'{tool_name}\': {str(e)}"
            if config.DEBUG_MODE:
                print(f"Executor: {error_msg}")
                traceback.print_exc()
            return {"tool_name": tool_name, "status": "error", "output": {"error": error_msg}, "is_stream": False}

    def _get_llm_synthesis_stream(self, prompt: str, context_summary: str = "", system_prompt: str = "", chat_history: list = None):
        """Generates a response from the LLM, using context from tool executions, system prompt, and chat history."""
        if not self.llm:
            yield "Error: LLM not available for response synthesis."
            return

        # Compose messages for the LLM
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if chat_history:
            messages.extend(chat_history)
        if context_summary:
            messages.append({"role": "system", "content": f"Context from tools:\n{context_summary}"})
        messages.append({"role": "user", "content": prompt})

        if config.DEBUG_MODE:
            print(f"Executor (_get_llm_synthesis_stream): Final messages for LLM: {messages}")

        try:
            for chunk in self.llm.stream(messages):
                yield chunk.content
        except Exception as e:
            error_msg = f"Error during LLM synthesis stream: {e}"
            if config.DEBUG_MODE:
                print(f"Executor: {error_msg}")
            yield f"Error: Could not get response from LLM. Details: {error_msg}"

    def execute_plan(self, plan_json: dict, conversation_history: list):
        """
        Executes the entire plan sequentially.
        Streams responses for llm_response_generation steps.
        Collects tool outputs for final synthesis if needed.
        """
        if not self.llm:
            yield "Error: The main language model is not available. Cannot execute plan."
            return
            
        if not plan_json or "plan" not in plan_json or not isinstance(plan_json["plan"], list):
            if config.DEBUG_MODE:
                print(f"Executor: Invalid or empty plan received: {plan_json}")
            yield "I encountered an issue with planning. Could you please rephrase your request?"
            return

        plan_steps = plan_json["plan"]
        tool_outputs_for_synthesis = []
        final_response_streamed = False
        context=''
        for i, step in enumerate(plan_steps):
            step_tool_name = step.get("tool")
            execution_result = self.execute_step(step, conversation_history, context)

            if step_tool_name == "llm_response_generation":
                # This is a streaming generator itself
                for chunk in execution_result: # execution_result is the stream from _get_llm_synthesis_stream
                    yield chunk
                final_response_streamed = True
                # If an llm_response_generation step is encountered, assume it's the final response or a direct answer.
                # Stop further plan execution as per original logic.
                return 
            else:
                # It's a regular tool call (non-streaming output from execute_step)
                tool_outputs_for_synthesis.append(execution_result)
                context = context + '\n\n' + str(execution_result)
                # conversation_history.append({
                #             "role": "system",
                #             "content": f"Tool '{step_tool_name}' \n**LATEST KNOWLEDGE**: {json.dumps(execution_result.get('output', {}))}"
                #         })
                if execution_result["status"] == "error" and config.DEBUG_MODE:
                    print(f"Executor: Tool \'{step_tool_name}\' failed. Error: {execution_result['output']}")
                    # Decide if we should stop or continue. For now, continue and let synthesis handle it.

        # If the plan finished and no llm_response_generation step was encountered (or it wasn't the last one that returned)
        if not final_response_streamed and tool_outputs_for_synthesis:
            if config.DEBUG_MODE:
                print("Executor: Plan ended. Synthesizing final response from collected tool outputs.")
            
            synthesis_prompt = f"Based on the results of the operations, provide a comprehensive answer to the user's original query: \nOriginal query: {plan_json.get('original_query', 'Not available')} "
            
            context_summary = ""
            successful_tool_details = []
            failed_tool_details = []

            for out in tool_outputs_for_synthesis:
                output_data = out.get("output", {})
                if out.get("status") == "success":
                    # output_data is already a dict from the Pydantic model
                    successful_tool_details.append(f"Tool '{out['tool_name']}' reported: {json.dumps(output_data)}")
                else:
                    error_detail = output_data.get("error", "Unknown error")
                    if isinstance(output_data, dict) and "details" in output_data:
                        error_detail += f" (Details: {output_data['details']})"
                    failed_tool_details.append(f"Tool '{out['tool_name']}' failed with error: {error_detail}")
            
            if successful_tool_details:
                context_summary += "\nSuccessful operations:\n" + "\n".join(successful_tool_details)
            if failed_tool_details:
                context_summary += "\nFailed operations:\n" + "\n".join(failed_tool_details)
            if not context_summary:
                context_summary = "No information was gathered from agent.tools."

            stream_generator = self._get_llm_synthesis_stream(synthesis_prompt, context_summary.strip())
            for chunk in stream_generator:
                yield chunk
        elif not plan_steps: # Empty plan
             yield "I received an empty plan. How can I assist you?"
        elif not tool_outputs_for_synthesis and not final_response_streamed:
            yield "I carried out the steps, but there was no information to report or an issue occurred."


if __name__ == '__main__':
    # This direct test requires Ollama to be running and accessible.
    # It also assumes config.py is set up correctly.
    print("--- Testing Executor (Direct Run) ---")
    # Ensure API keys are loaded if needed by tools, though these tests might not hit them hard.
    # The RAG tool initialization might run if not already done.
    
    # For the executor to run tools, the tools need to be initialized.
    # The __init__ of Executor does this.
    test_executor = Executor()
    if not test_executor.llm:
        print("CRITICAL: LLM could not be initialized. Executor tests will be limited.")
        # exit(1)

    # Test Case 1: Plan with a (mocked) tool call and then LLM synthesis
    # For this test to work without external Flask endpoints, tools must be callable directly.
    # Our Langchain tools are now directly callable.
    print("\n--- Executing Test Plan 1 (Weather + Synthesis) ---")
    test_plan_1 = {
        "original_query": "What's the weather in London and summarize it?",
        "plan": [
            {"step": 1, "tool": "get_weather", "arguments": {"city": "London"}, "reasoning": "User asked for weather in London."},
            {"step": 2, "tool": "llm_response_generation", "arguments": {"prompt_to_llm": "Summarize the weather information provided for the user and mention the city."}, "reasoning": "Synthesize weather data into a response."}
        ]
    }
    if test_executor.llm:
        for chunk_num, chunk in enumerate(test_executor.execute_plan(test_plan_1, [])):
            print(chunk, end="")
            if chunk_num > 20 and config.DEBUG_MODE: # Limit output in debug for brevity
                print("... (output truncated for test)")
                break
        print("\n")
    else:
        print("Skipping Test Plan 1 due to missing LLM.")

    # Test Case 2: Plan with only direct LLM response
    print("--- Executing Test Plan 2 (Direct LLM Story) ---")
    test_plan_2 = {
        "original_query": "Tell me a short story.",
        "plan": [
            {"step": 1, "tool": "llm_response_generation", "arguments": {"prompt_to_llm": "Tell me a short story about a brave robot that explores a new planet."}, "reasoning": "User asked for a story."}
        ]
    }
    if test_executor.llm:
        for chunk_num, chunk in enumerate(test_executor.execute_plan(test_plan_2, [])):
            print(chunk, end="")
            if chunk_num > 20 and config.DEBUG_MODE:
                print("... (output truncated for test)")
                break
        print("\n")
    else:
        print("Skipping Test Plan 2 due to missing LLM.")

    # Test Case 3: Plan with a RAG tool call then synthesis
    print("--- Executing Test Plan 3 (RAG + Synthesis) ---")
    # This assumes `ai_document.md` is in `data` and vector store can be built/loaded.
    test_plan_3 = {
        "original_query": "What is AI according to the documents?",
        "plan": [
            {"step": 1, "tool": "document_retrieval_augmented_generation", "arguments": {"query": "What is AI?"}}
        ]
    }