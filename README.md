# 🔍 QueryWhisper

**QueryWhisper** is a Flask-based AI-powered app that transforms **natural language questions** into **SQL queries**, executes them safely on a MySQL database, and returns results with a clear explanation.  
Powered by **Groq’s LLaMA 3**, it makes querying databases as simple as chatting with an assistant.  

---

## ✨ Features
- 🔑 **Secure Login** – User authentication before accessing the dashboard  
- 🔌 **MySQL Connector** – Connect easily to any MySQL database with credentials  
- 🧠 **Natural Language → SQL** – Converts human questions into optimized SQL `SELECT` queries  
- 🛡️ **Safe Execution** – Runs only safe, read-only queries (no destructive operations)  
- 📊 **Smart Query Runner** – Executes SQL and returns structured results  
- 🤖 **AI Explanations** – Summarizes SQL output into short, neat human-readable answers  
- 📂 **Query Logs** – Stores all Q&A sessions (question, SQL, AI answer) in CSV reports  
- 🌐 **Web UI + API** – Intuitive dashboard + programmatic API endpoints  

---

## 🛠️ Tech Stack
- **Backend**: Flask (Python)  
- **Database**: MySQL (via PyMySQL)  
- **AI Model**: Groq LLaMA3 (`llama3-70b-8192`)  
- **Frontend**: Flask Jinja Templates (Login + Dashboard)  
- **Other Tools**: Pandas (CSV reports), Regex (query sanitization)  

---

## 📂 Project Structure
QueryWhisper/
│── app.py # Main Flask app
│── templates/
│ ├── login.html # Login page
│ ├── dashboard.html # Dashboard UI
│── report/ # Auto-generated query-answer CSV logs
│── requirements.txt # Python dependencies

yaml
Copy
Edit

---

## ⚙️ Installation & Setup

### 1️⃣ Clone the Repository
```bash
git clone https://github.com/ashishamith/QueryWhisper.git
cd QueryWhisper
2️⃣ Create a Virtual Environment & Install Dependencies
bash
Copy
Edit
python -m venv venv
source venv/bin/activate   # On Linux/Mac
venv\Scripts\activate      # On Windows

pip install -r requirements.txt
3️⃣ Configure Environment Variables
Create a .env file in the project root:

ini
Copy
Edit
GROQ_API_KEY=your_groq_api_key
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=yourpassword
MYSQL_DATABASE=ecommerce
4️⃣ Run the App
bash
Copy
Edit
python app.py
The app will start at:
👉 http://127.0.0.1:5000

▶️ Working Flow
Here’s how QueryWhisper works step by step:

Login

User enters username & password on /login

After authentication → redirected to Dashboard

Ask a Question

Example: "Which city has the most customers?"

Natural Language → SQL

LLaMA3 (via Groq API) converts the question into an optimized SQL query

Example:

sql
Copy
Edit
SELECT city, COUNT(*) AS total_customers
FROM customers
GROUP BY city
ORDER BY total_customers DESC
LIMIT 1;
SQL Safety Check

Regex filter ensures only SELECT queries are allowed

Prevents INSERT, UPDATE, DELETE, DROP

Execute Query

Safe SQL runs against the connected MySQL database

Raw results are fetched

AI Explanation

LLaMA3 generates a short, human-friendly answer

Example: "Delhi has the highest number of customers (15)."

Store Report

Question, SQL, and AI answer are saved in /report/query_logs.csv

Return Results

Dashboard displays:

Generated SQL

Query result table

AI-generated explanation

💡 Example Queries
"Show the top 3 cities with the highest number of customers"

"What is the ratio of customers in Delhi vs Mumbai?"

"Which states have more Gmail users than Yahoo users?"

"Find the most common last name among customers"

🚀 Future Improvements
🔗 Support for PostgreSQL & SQLite

📈 Interactive charts for query results

🗄️ Multi-user session management

📊 Export reports in Excel & PDF formats

🎯 Advanced fine-tuning for text-to-SQL accuracy