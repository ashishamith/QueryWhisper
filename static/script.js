// Chat box reference
const chatBox = document.getElementById("chatBox");

// Add a message to the chat
function addMessage(sender, text) {
    const msg = document.createElement("div");
    msg.classList.add("message", sender);
    msg.textContent = text;
    chatBox.appendChild(msg);
    chatBox.scrollTop = chatBox.scrollHeight;
}

// Connect to database
document.getElementById("connectBtn").addEventListener("click", async () => {
    const host = document.getElementById("db_host").value.trim();
    const user = document.getElementById("db_user").value.trim();
    const password = document.getElementById("db_password").value.trim();
    const dbname = document.getElementById("db_name").value.trim();

    if (!host || !user || !password || !dbname) {
        addMessage("bot", "⚠ Please fill in all database details.");
        return;
    }

    try {
        const res = await fetch("/connect", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                host: host,
                user: user,
                password: password,
                database: dbname
            })
        });

        const data = await res.json();
        if (data.success) {
            addMessage("bot", "✅ Database connected successfully!");
        } else {
            addMessage("bot", "❌ Failed to connect: " + (data.error || "Unknown error"));
        }
    } catch (err) {
        addMessage("bot", "❌ Error: " + err.message);
    }
});

// Ask a question
document.getElementById("askBtn").addEventListener("click", async () => {
    const question = document.getElementById("questionInput").value.trim();
    if (!question) return;

    addMessage("user", "You: " + question);
    document.getElementById("questionInput").value = "";

    try {
        const res = await fetch("/ask", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question })
        });

        const data = await res.json();
        if (data.answer) {
            addMessage("bot", "Bot: " + data.answer);
        } else {
            addMessage("bot", "❌ Error: " + (data.error || "No response"));
        }
    } catch (err) {
        addMessage("bot", "❌ Error: " + err.message);
    }
});

// Download report
document.getElementById("downloadReportBtn").addEventListener("click", () => {
    window.location.href = "/download_report";
});

// Logout
document.getElementById("logoutBtn").addEventListener("click", () => {
    window.location.href = "/logout";
});
