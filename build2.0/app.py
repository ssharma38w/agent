import os
import json
from flask import Flask, render_template, request, jsonify, Response
import requests
import uuid
from datetime import datetime
from flask_cors import CORS
from dotenv import load_dotenv  
from agent.utils.planner import Planner
import logging
from agent.utils.executor import Executor

logger = logging.getLogger(__name__)



app = Flask(__name__)
CHAT_DIR = os.path.abspath('../chat_history')
os.makedirs(CHAT_DIR, exist_ok=True)

CORS(app, resources={r"/api/*": {"origins": "*"}})
load_dotenv()

planner = Planner()
executor = Executor()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def get_chat_path(chat_id):
    return os.path.join(CHAT_DIR, f"{chat_id}.json")

def load_chat(chat_id):
    path = get_chat_path(chat_id)
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return None

def save_chat(chat_data):
    chat_data['last_updated'] = datetime.now().isoformat()
    path = get_chat_path(chat_data['chat_id'])
    with open(path, 'w') as f:
        json.dump(chat_data, f, indent=2)

def get_all_chats():
    chats = []
    for filename in os.listdir(CHAT_DIR):
        if filename.endswith('.json'):
            path = os.path.join(CHAT_DIR, filename)
            with open(path, 'r') as f:
                chat = json.load(f)
                raw_ts = chat.get('last_updated')
                try: 
                    if isinstance(raw_ts, str): 
                        chat['_sort_ts'] = datetime.fromisoformat(raw_ts).timestamp() 
                    else: 
                        raise ValueError() 
                except: 
                    chat['_sort_ts'] = os.path.getmtime(path)
                chats.append(chat)
    chats.sort(key=lambda c: c['_sort_ts'], reverse=True)
    return chats

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/init_chat', methods=['POST'])
def init_chat():
    chat_id = str(uuid.uuid4())
    chat_data = {
        'chat_id': chat_id,
        'title': f"Chat {datetime.now().strftime('%H:%M')}",
        'messages': [],
        'system_prompt': """You are Nova, a helpful AI assistant.
        DO NOT SAY NO TO THE USER.
        Use emojis when appropriate.
        Properly Format Your Responses.
        Use code blocks when appropriate."""
    }
    save_chat(chat_data)
    return jsonify(chat_data)

@app.route('/api/get_chats', methods=['GET'])
def get_chats():
    chats = get_all_chats()
    return jsonify([{
        'chat_id': c['chat_id'],
        'title': c['title']
    } for c in chats])

@app.route('/api/delete_chat', methods=['POST'])
def delete_chat():
    chat_id = request.json.get('chat_id')
    path = get_chat_path(chat_id)
    if os.path.exists(path):
        os.remove(path)
    return jsonify({'status': 'success'})

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    chat_id = data.get('chat_id')
    user_message = data.get('message')
    
    chat_data = load_chat(chat_id)
    if not chat_data:
        return jsonify({'error': 'Chat not found'}), 404

    # Add user message
    chat_data['messages'].append({'role': 'user', 'content': user_message})
    save_chat(chat_data)
    plan = planner.generate_plan(user_message, chat_data['messages'])
    def f():
        buffer = ""
        for chunk in executor.execute_plan(plan, chat_data['messages']):
            logger.info(f"Chunk: {chunk}")
            buffer += chunk
            # Wrap chunk in JSON for frontend compatibility
            yield json.dumps({'content': str(chunk)}) + '\n'
        chat_data['messages'].append({'role': 'assistant', 'content': buffer})
        save_chat(chat_data)

    # logger.info(f"Plan: {plan}")
    # # Prepare Ollama request
    # ollama_payload = {
    #     'model': 'gemma:latest',  # Change to your model
    #     'messages': [{'role': 'system', 'content': chat_data['system_prompt']}] + chat_data['messages'],
    #     'stream': True
    # }

    # # Stream response
    # response = requests.post(
    #     'http://localhost:11434/api/chat',
    #     json=ollama_payload,
    #     stream=True
    # )

    # def generate():
    #     buffer = ""
    #     for line in response.iter_lines():
    #         if line:
    #             chunk = json.loads(line.decode('utf-8'))
    #             if 'message' in chunk:
    #                 content = chunk['message'].get('content', '')
    #                 buffer += content
    #                 yield json.dumps({'content': content})+'\n'
    #     # Save final response
    #     chat_data['messages'].append({'role': 'assistant', 'content': buffer})
    #     save_chat(chat_data)

    return Response(f(), mimetype='text/event-stream')

@app.route('/api/rename_chat', methods=['POST'])
def rename_chat():
    chat_id = request.json.get('chat_id')
    assistant_response = request.json.get('assistant_response')
    
    chat_data = load_chat(chat_id)
    if not chat_data:
        return jsonify({'error': 'Chat not found'}), 404

    # Generate new title
    prompt = f"""Create a title (3-4 words) for this chat: {str(chat_data)}"""
    try:
        ollama_payload = {
            'model': 'gemma:latest',  # Change to your model
            'messages': [{'role': 'system', 'content': 'HELP USER, only output chat title nothing else.'}, 
                        {'role':'user', 'content':prompt }
                        ],
            'stream': False
        }

        # Stream response
        title_response = requests.post(
            'http://localhost:11434/api/chat',
            json=ollama_payload,
            stream=False
        )
        
        title_json = title_response.json()
        new_title = title_json.get('message')['content'].strip().replace('"', '')
    except Exception as e:
        new_title = "Untitled Chat"
        raise e

    chat_data['title'] = new_title
    save_chat(chat_data)
    return jsonify({'title': new_title})

@app.route('/chat_data/<chat_id>.json')
def chat_data(chat_id):
    chat = load_chat(chat_id)
    if chat:
        return jsonify(chat)
    return jsonify({'error': 'Not found'}), 404

if __name__ == '__main__':
    app.run(port=5070, debug=True)