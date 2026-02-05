from flask import Flask, render_template, request, redirect, session, jsonify, send_file
import psycopg2
import psycopg2.extras
import requests
import re
import csv
import os
import textwrap
from datetime import datetime

# -----------------------------
# Flask App Config
# -----------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "fallback_secret")

# -----------------------------
# Groq API Config
# -----------------------------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama3-70b-8192"

# -----------------------------
# Database Config (Supabase)
# -----------------------------
# Use Supabase Session Pooler URI (IPv4 supported)
DB_URL = os.environ.get("DB_URL")

if not DB_URL:
    raise Exception("❌ DB_URL is missing. Add it in Render Environment Variables.")


# -----------------------------
# Helpers
# -----------------------------
def get_db_connection():
    """Create PostgreSQL connection using Supabase DB_URL."""
    return psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.DictCursor)


def fetch_schema_and_samples(sample_limit=20):
    """Fetch schema + sample rows for LLM prompt."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Get all tables
        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema='public'
        """)
        tables = [r[0] for r in cur.fetchall()]

        schema_text = ""

        for t in tables:
            schema_text += f"\nTable `{t}`:\n"

            # Columns
            cur.execute(f"""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = '{t}'
            """)
            cols = [c[0] for c in cur.fetchall()]
            schema_text += f"Columns = ({', '.join(cols)})\n"

            # Sample rows
            try:
                cur.execute(f"SELECT * FROM {t} LIMIT {sample_limit}")
                rows = cur.fetchall()

                for r in rows[:3]:
                    schema_text += "| " + " | ".join([str(x) for x in r]) + " |\n"

            except Exception:
                schema_text += "(No sample rows)\n"

        conn.close()
        return schema_text

    except Exception as e:
        return f"Error fetching schema: {e}"


def call_groq(prompt, timeout=30):
    """Call Groq API."""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": "You are an expert SQL assistant for PostgreSQL."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0,
        "max_tokens": 1200
    }

    resp = requests.post(GROQ_ENDPOINT, headers=headers, json=payload, timeout=timeout)
    return resp.status_code, resp.json()


def extract_sql_from_text(text):
    """Extract SQL from LLM response."""
    if not text:
        return None

    m = re.search(r"(SELECT[\s\S]*)", text, re.I)
    if m:
        return m.group(1).strip()

    return None


def is_safe_select(sql_text):
    """Only allow safe SELECT queries."""
    if not sql_text:
        return False

    s = sql_text.upper()

    forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE"]
    for kw in forbidden:
        if kw in s:
            return False

    return "SELECT" in s


def execute_select(sql, limit=20):
    """Execute SQL query safely."""
    sql_run = sql.rstrip().rstrip(";")

    if "LIMIT" not in sql_run.upper():
        sql_run += f" LIMIT {limit}"

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(sql_run)

    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]

    conn.close()

    results = [dict(zip(cols, r)) for r in rows]
    return results


def save_qa(question, answer, sql):
    """Save Q&A logs."""
    os.makedirs("report", exist_ok=True)
    fp = os.path.join("report", "qa_report.csv")

    exists = os.path.exists(fp)

    with open(fp, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)

        if not exists:
            w.writerow(["timestamp", "question", "answer", "sql"])

        w.writerow([datetime.utcnow().isoformat(), question, answer, sql])


# -----------------------------
# Routes
# -----------------------------
@app.route("/")
def index():
    return redirect("/dashboard")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/ask", methods=["POST"])
def ask():
    question = request.form.get("question", "")

    if not question:
        return jsonify({"error": "No question provided"}), 400

    # Fetch schema for prompt
    schema_text = fetch_schema_and_samples()

    # Prompt LLM for SQL
    prompt_sql = f"""
You are an expert PostgreSQL assistant.

Schema:
{schema_text}

User Question:
{question}

Rules:
- Output ONLY ONE PostgreSQL SELECT query.
- No explanations.
"""

    status, llm_data = call_groq(prompt_sql)

    if status != 200:
        return jsonify({"error": "Groq API failed"}), 500

    sql_text = llm_data["choices"][0]["message"]["content"]
    sql_candidate = extract_sql_from_text(sql_text)

    if not sql_candidate:
        return jsonify({"error": "No SQL generated"}), 500

    if not is_safe_select(sql_candidate):
        return jsonify({"error": "Unsafe SQL blocked"}), 400

    # Execute query
    try:
        results = execute_select(sql_candidate)
    except Exception as e:
        return jsonify({"error": f"SQL error: {str(e)}", "sql": sql_candidate}), 500

    # Save report
    save_qa(question, str(results[:3]), sql_candidate)

    return jsonify({
        "answer": "Query executed successfully ✅",
        "results": results
    })


@app.route("/download")
def download():
    fp = os.path.join("report", "qa_report.csv")
    if os.path.exists(fp):
        return send_file(fp, as_attachment=True)
    return jsonify({"error": "No report file found"}), 404


@app.route("/test")
def test():
    return jsonify({"status": "running"})


# -----------------------------
# Run Server
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
