let currentChatId = null;
let allChats = [];
let messageCount = {};

document.addEventListener('DOMContentLoaded', async () => {
    await loadChats();
    
    const res = await fetch('/api/get_chats');
    allChats = await res.json();
    
    if (allChats.length === 0) {
        await createNewChat();
    } else {
        loadChat(allChats[0].chat_id);
    }
});

async function loadChats() {
    const res = await fetch('/api/get_chats');
    allChats = await res.json();
    
    const chatList = document.getElementById('chatList');
    chatList.innerHTML = '';
    
    allChats.forEach(chat => {
        const tab = document.createElement('div');
        tab.className = 'chat-tab';
        
        const title = document.createElement('span');
        title.textContent = chat.title;
        title.onclick = () => loadChat(chat.chat_id);
        
        const deleteIcon = document.createElement('span');
        deleteIcon.className = 'delete-icon';
        deleteIcon.textContent = '🗑️';
        deleteIcon.onclick = async (e) => {
            e.stopPropagation();
            await fetch('/api/delete_chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({chat_id: chat.chat_id})
            });
            await loadChats();
            if (currentChatId === chat.chat_id) {
                document.getElementById('chatArea').innerHTML = '';
                document.getElementById('chatHeader').textContent = 'Nova';
                currentChatId = null;
            }
        };
        
        tab.appendChild(title);
        tab.appendChild(deleteIcon);
        chatList.appendChild(tab);
    });
}

async function createNewChat() {
    const res = await fetch('/api/init_chat', {method: 'POST'});
    const data = await res.json();
    await loadChats();
    loadChat(data.chat_id);
}

async function loadChat(chat_id) {
    currentChatId = chat_id;
    messageCount[currentChatId] = 0;

    const res = await fetch(`/chat_data/${chat_id}.json`);
    const chatData = await res.json();

    document.querySelectorAll('.chat-tab').forEach(tab => tab.classList.remove('active'));
    const activeTab = [...document.getElementById('chatList').children].find(
        tab => tab.firstChild.textContent === chatData.title
    );
    if (activeTab) activeTab.classList.add('active');

    document.getElementById('chatTitle').textContent = chatData.title;

    const chatArea = document.getElementById('chatArea');
    chatArea.innerHTML = '';
    chatData.messages.forEach(msg => appendMessage(msg.role, msg.content));
}

function appendMessage(role, content) {
    const div = document.createElement('div');
    div.className = `message ${role}`;

    if (role === 'assistant') {
        div.innerHTML += DOMPurify.sanitize(marked.parse(content), { ADD_TAGS: ['pre', 'code'] });
        setTimeout(() => Prism.highlightAllUnder(div), 0);
        setTimeout(() => attachCopyButtons(div), 100);
    } else {
        div.textContent = content;
    }

    document.getElementById('chatArea').appendChild(div);
    const chatArea = document.getElementById('chatArea');
    chatArea.scrollTop = chatArea.scrollHeight;
    document.getElementById('chatInput').focus();
}

function attachCopyButtons(container) {
    container.querySelectorAll('pre').forEach(pre => {
        if (!pre.querySelector('.copy-btn')) {
            const btn = document.createElement('button');
            btn.className = 'copy-btn';
            btn.textContent = 'Copy';
            btn.onclick = () => {
                navigator.clipboard.writeText(pre.textContent);
                btn.textContent = 'Copied!';
                setTimeout(() => btn.textContent = 'Copy', 2000);
            };
            pre.appendChild(btn);
        }
    });
}

async function sendMessage() {
    const input = document.getElementById('chatInput');
    let message = input.value.trim();
    if (!message || !currentChatId) return;

    // Add user message
    appendMessage('user', message);
    input.value = '';
    input.style.height = '40px';
    messageCount[currentChatId] = (messageCount[currentChatId] || 0) + 1;

    // Show typing indicator
    const typingDiv = document.createElement('div');
    typingDiv.className = 'message bot';
    typingDiv.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';
    document.getElementById('chatArea').appendChild(typingDiv);
    document.getElementById('chatArea').scrollTop = document.getElementById('chatArea').scrollHeight;

    // Stream response
    const res = await fetch('/api/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({chat_id: currentChatId, message})
    });

    const reader = res.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    const div = document.createElement('div');
    div.className = 'message assistant';
    document.getElementById('chatArea').replaceChild(div, typingDiv);

    // inside scripts.js

    let fullMarkdown = '';
    while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');

    for (let i = 0; i < lines.length - 1; i++) {
        try {
        const chunk = JSON.parse(lines[i]);
        fullMarkdown += chunk.content;

        // 1. Extract code blocks (```...``` or inline code)
        const codePattern = /```[\\s\\S]*?```|`[^`]+`/g;
        const segments = fullMarkdown.split(codePattern);
        const codeBlocks = fullMarkdown.match(codePattern) || [];

        // 2. Clear previous
        div.innerHTML = '';

        // 3. Rebuild message safely
        segments.forEach((seg, idx) => {
            if (seg.trim()) {
            const span = document.createElement('span');
            span.textContent = seg;  // ✅ Render plain text as-is
            div.appendChild(span);
            }

            if (codeBlocks[idx]) {
            const codeHtml = DOMPurify.sanitize(
                marked.parse(codeBlocks[idx]),
                { ADD_TAGS: ['pre', 'code'], ALLOWED_ATTR: [] }
            );
            const wrapper = document.createElement('div');
            wrapper.innerHTML = codeHtml;
            div.appendChild(wrapper);
            }
        });

        Prism.highlightAllUnder(div);
        attachCopyButtons(div);

        } catch (e) {}
    }

    buffer = lines[lines.length - 1];
    }



    div.scrollTop = div.scrollHeight;

    // Rename chat after second message
    if (messageCount[currentChatId] === 2) {
        const assistantMsg = div.textContent;
        const renameRes = await fetch('/api/rename_chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                chat_id: currentChatId,
                assistant_response: assistantMsg
            })
        });
        const data = await renameRes.json();
        document.getElementById('chatTitle').textContent = data.title;
        await loadChats();
    }
}

document.getElementById('chatInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        if (e.shiftKey) {
            const input = e.target;
            input.value += '\n';
            input.style.height = 'auto';
            input.style.height = `${input.scrollHeight}px`;
        } else {
            sendMessage();
        }
    }
});

function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('hidden');
    document.getElementById('main').classList.toggle('expanded');
}

document.getElementById('newChatBtn').addEventListener('click', createNewChat);

// Add typing indicator styles
document.head.insertAdjacentHTML('beforeend', `
<style>
.typing-indicator {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 12px 16px;
    border-radius: 12px;
    background-color: #1F2937;
    color: #E5E7EB;
}

.typing-indicator span {
    width: 10px;
    height: 10px;
    background-color: #67e8f9;
    border-radius: 50%;
    animation: typing 1s infinite;
}

.typing-indicator span:nth-child(2) {
    animation-delay: 0.2s;
}

.typing-indicator span:nth-child(3) {
    animation-delay: 0.4s;
}

@keyframes typing {
    0% { transform: scale(0); }
    50% { transform: scale(1); }
    100% { transform: scale(0); }
}
</style>
`);