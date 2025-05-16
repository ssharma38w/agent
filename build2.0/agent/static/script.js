// /home/ubuntu/chatbot_project/static/script.js

document.addEventListener("DOMContentLoaded", () => {
    const chatMessages = document.getElementById("chat-messages");
    const chatInput = document.getElementById("chat-input");
    const loadingIndicator = document.getElementById("loading-indicator");
    const chatTitleElement = document.getElementById("chat-title");

    // Function to add a message to the chat display
    function addMessage(sender, text, isStreaming = false) {
        const messageBubble = document.createElement("div");
        messageBubble.classList.add("message-bubble");
        messageBubble.classList.add(sender); // "user" or "bot"
        
        // Simple text parsing for newlines, can be expanded for markdown later
        messageBubble.innerHTML = text.replace(/\n/g, "<br>"); 

        if (isStreaming && sender === "bot") {
            messageBubble.classList.add("streaming");
        }

        chatMessages.appendChild(messageBubble);
        scrollToBottom();
        return messageBubble; // Return for potential updates (streaming)
    }

    // Function to scroll to the bottom of the chat messages
    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // Function to update chat title
    function updateChatTitle(newTitle) {
        if (newTitle && newTitle.trim() !== "") {
            document.title = newTitle;
            if (chatTitleElement) {
                chatTitleElement.textContent = newTitle;
            }
        }
    }

    // Handle chat input
    chatInput.addEventListener("keypress", async (event) => {
        if (event.key === "Enter" && chatInput.value.trim() !== "") {
            const userMessage = chatInput.value.trim();
            addMessage("user", userMessage);
            chatInput.value = ""; // Clear input field
            loadingIndicator.style.display = "flex"; // Show loading indicator

            let firstUserMessage = true;
            if (chatMessages.querySelectorAll(".message-bubble.user").length === 1) {
                // This is the first user message of the session (client-side perspective)
                // The backend will handle the actual title logic based on its conversation state.
                // We can try to update it optimistically or wait for a backend signal.
                // For now, the backend sets the title on first message and re-renders index.html
                // or we can have a specific endpoint/message to update title dynamically.
                // Let's assume for now the backend handles title update and we might refresh or get a signal.
                // A simple client-side update for now:
                if (userMessage.split(" ").length > 3) {
                    const newTitle = userMessage.split(" ").slice(0, 6).join(" ") + "...";
                    // updateChatTitle(newTitle); // Backend handles this for now via page reload or specific mechanism
                }
            }

            try {
                const response = await fetch("/chat", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({ message: userMessage }),
                });

                loadingIndicator.style.display = "none"; // Hide loading indicator once headers are received

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({ detail: "Unknown error occurred." }));
                    addMessage("bot", `Error: ${response.status} ${response.statusText}. ${errorData.detail || ""}`);
                    return;
                }

                // Handle streaming response
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let botMessageBubble = null; // To hold the streaming bot message bubble
                let accumulatedResponse = "";

                while (true) {
                    const { value, done } = await reader.read();
                    if (done) {
                        if (botMessageBubble) {
                            botMessageBubble.classList.remove("streaming");
                        }
                        break;
                    }
                    const chunk = decoder.decode(value, { stream: true });
                    accumulatedResponse += chunk;
                    if (!botMessageBubble) {
                        botMessageBubble = addMessage("bot", accumulatedResponse, true);
                    } else {
                        botMessageBubble.innerHTML = accumulatedResponse.replace(/\n/g, "<br>");
                        scrollToBottom();
                    }
                }

            } catch (error) {
                console.error("Error sending message:", error);
                loadingIndicator.style.display = "none";
                addMessage("bot", "⚠️ Sorry, an error occurred while connecting to the server. Please try again.");
            }
        }
    });

    // Initial focus on input
    chatInput.focus();
});

