from flask import Flask, render_template, request, redirect, session, jsonify, send_file
import pymysql
import requests
import re
import csv
import os
import textwrap
from datetime import datetime

app = Flask(__name__)
app.secret_key = "super_secret_key"  # change for production

# ---------- Groq API config ----------
GROQ_API_KEY = " "  # replace if needed
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama3-70b-8192"  # recommended model; change if needed

# ---------- Helpers ----------
def fetch_schema_and_samples(db_config, sample_limit=50):
    """Return textual schema and a samples dict for prompt building."""
    try:
        conn = pymysql.connect(**db_config)
        cur = conn.cursor()
        cur.execute("SHOW TABLES")
        tables = [r[0] for r in cur.fetchall()]
        schema_text = ""
        samples = {}
        for t in tables:
            # columns
            try:
                cur.execute(f"DESCRIBE `{t}`")
                cols = [c[0] for c in cur.fetchall()]
            except Exception:
                cols = []
            schema_text += f"Table `{t}`: columns = ({', '.join(cols)})\n"
            # sample rows
            try:
                cur.execute(f"SELECT * FROM `{t}` LIMIT {sample_limit}")
                rows = cur.fetchall()
                samples[t] = {"columns": cols, "rows": rows}
                if rows:
                    for r in rows:
                        schema_text += "| " + " | ".join([str(x) if x is not None else "NULL" for x in r]) + " |\n"
            except Exception:
                samples[t] = {"columns": cols, "rows": []}
                schema_text += "(no sample rows or inaccessible)\n"
        conn.close()
        return schema_text, samples
    except Exception as e:
        return f"Error fetching schema: {e}", {}

def call_groq(prompt, timeout=30):
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": "You are an expert SQL assistant that writes valid MySQL SELECT queries when data retrieval is needed."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0,
        "max_tokens": 1500
    }
    resp = requests.post(GROQ_ENDPOINT, headers=headers, json=payload, timeout=timeout)
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, {"raw_text": resp.text}

def extract_sql_from_text(text):
    """Try to extract SQL from code fences or SQL: labels."""
    if not text:
        return None
    # strip HTML-like tags
    text = re.sub(r"<\/?[^>]+>", "", text)
    # find ```sql ... ```
    m = re.search(r"```sql\s*(.*?)```", text, re.S | re.I)
    if m:
        return m.group(1).strip()
    # find ``` ... ```
    m2 = re.search(r"```\s*(.*?)```", text, re.S)
    if m2:
        cand = m2.group(1).strip()
        # if contains SELECT, return
        if re.search(r"\bSELECT\b", cand, re.I):
            return cand
    # find SQL: ... Explanation pattern
    if "SQL:" in text:
        parts = re.split(r"SQL:", text, 1)
        after = parts[1]
        # stop at Explanation or ANSWER if present
        after = re.split(r"(Explanation:|ANSWER:|Answer:)", after, 1)[0]
        if re.search(r"\bSELECT\b", after, re.I):
            return after.strip()
    # fallback: first SELECT ... ; or SELECT ... end
    m3 = re.search(r"(SELECT[\s\S]*?);", text, re.I)
    if m3:
        return m3.group(1).strip()
    m4 = re.search(r"(SELECT[\s\S]*)", text, re.I)
    if m4:
        return m4.group(1).strip()
    return None

def is_safe_select(sql_text):
    if not sql_text:
        return False
    s = re.sub(r"\s+", " ", sql_text).strip().upper()
    # disallow multiple statements
    if ";" in s and s.count(";") > 1:
        return False
    # forbid DML/DDL
    forbidden = ["INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "TRUNCATE ", "CREATE ", "REPLACE ", "GRANT ", "REVOKE "]
    for kw in forbidden:
        if kw in s:
            return False
    # must contain SELECT
    if "SELECT" in s:
        return True
    return False

def execute_select(sql, db_config, limit=20):
    sql_run = sql.rstrip().rstrip(";")
    # add LIMIT if missing and query is simple SELECT
    if re.search(r"\bLIMIT\b", sql_run, re.I) is None and re.match(r"^\s*(SELECT|WITH)\b", sql_run, re.I):
        sql_run = sql_run + f" LIMIT {limit}"
    conn = pymysql.connect(**db_config)
    cur = conn.cursor()
    cur.execute(sql_run)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description] if cur.description else []
    conn.close()
    results = [dict(zip(cols, r)) for r in rows] if cols else []
    return results

def ask_groq_for_explanation(question, columns, results):
    # Build prompt asking for table output when multiple rows exist
    sample_rows_text = ""
    if results:
        # Prepare table preview text from actual results
        header = " | ".join(columns)
        rows_preview = []
        for r in results:
            rows_preview.append(" | ".join([str(r.get(c, "")) for c in columns]))
        sample_rows_text = header + "\n" + "\n".join(rows_preview)

    prompt = textwrap.dedent(f"""
    Provide the answer to the user's question **only** in clean, plain text.
    
    Rules:
    - If there are multiple rows in results, format them as a neat table without extra commentary.
    - Do not add SQL, code blocks, or explanations.
    - Keep it exactly in the same style as the data — no extra words.
    - Preserve numbers, currency symbols, and text exactly as they appear in the data.

    Question: {question}

    Columns: {columns}
    Data:
    {sample_rows_text}
    """)
    status, data = call_groq(prompt)
    if status != 200:
        # fallback: direct table
        if results:
            header = " | ".join(columns)
            rows = [" | ".join([str(r.get(c, "")) for c in columns]) for r in results]
            return "\n".join([header] + rows)
        return "No results."

    try:
        content = data['choices'][0]['message']['content']
        # Clean any accidental markdown fences
        return re.sub(r"```.*?```", "", content, flags=re.S).strip()
    except Exception:
        if results:
            header = " | ".join(columns)
            rows = [" | ".join([str(r.get(c, "")) for c in columns]) for r in results]
            return "\n".join([header] + rows)
        return "No explanation available."

    if status != 200:
        # fallback simple local answer
        if results:
            first = results[0]
            kvs = ", ".join([f"{k}: {v}" for k, v in list(first.items())[:3]])
            return f"Result (sample): {kvs}"
        return "No results."
    # extract content robustly
    try:
        content = data['choices'][0]['message']['content']
        # strip any code fences or SQL if present (shouldn't)
        content = re.sub(r"```.*?```", "", content, flags=re.S).strip()
        # Truncate to about 5 lines (heuristic)
        lines = [l.strip() for l in re.split(r'[\r\n]+', content) if l.strip()]
        paragraph = " ".join(lines[:5])
        return paragraph
    except Exception:
        if results:
            first = results[0]
            kvs = ", ".join([f"{k}: {v}" for k, v in list(first.items())[:3]])
            return f"Result (sample): {kvs}"
        return "No explanation available."

def save_qa(question, answer, sql):
    os.makedirs("report", exist_ok=True)
    fp = os.path.join("report", "qa_report.csv")
    exists = os.path.exists(fp)
    with open(fp, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["timestamp", "question", "answer", "sql"])
        w.writerow([datetime.utcnow().isoformat(), question, answer, sql or ""])

# ---------- Routes ----------
@app.route('/')
def index():
    return redirect('/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == "POST":
        email = request.form.get("email", "")
        password = request.form.get("password", "")
        # simple fixed creds (as you used)
        if email == "ashishamith27@gmail.com" and password == "ashish123":
            session['logged_in'] = True
            return redirect('/dashboard')
        return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")

@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'):
        return redirect('/login')
    return render_template("dashboard.html")

@app.route('/connect', methods=['POST'])
def connect():
    # accept form or json
    username = request.form.get('username') or (request.json.get('username') if request.is_json else None)
    password = request.form.get('password') or (request.json.get('password') if request.is_json else None)
    database = request.form.get('database') or (request.json.get('database') if request.is_json else None)
    host = 'localhost'

    if not username or not password or not database:
        return jsonify({"status": "error", "message": "username, password and database are required"}), 400

    db_config = {"host": host, "user": username, "password": password, "database": database}
    try:
        # test connection
        conn = pymysql.connect(**db_config)
        conn.close()
        session['db_config'] = db_config
        # fetch schema now and store
        schema_text, samples = fetch_schema_and_samples(db_config)
        session['db_schema_text'] = schema_text
        session['db_samples'] = samples
        return jsonify({"status": "success", "message": f"Connected to {database}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/ask', methods=['POST'])
def ask():
    # accept form or json
    if request.is_json:
        question = (request.json or {}).get("question", "")
    else:
        question = request.form.get("question", "")

    if not question:
        return jsonify({"error": "No question provided"}), 400

    db_config = session.get('db_config')
    if not db_config:
        return jsonify({"error": "No DB connected. Please connect first."}), 400

    # Get schema_text from session if present
    schema_text = session.get('db_schema_text', "")
    if not schema_text:
        schema_text, _ = fetch_schema_and_samples(db_config)

    # Step 1: Ask LLM to generate a single SELECT SQL for the question (backend only)
    prompt_sql = textwrap.dedent(f"""
You are an expert MySQL database developer with decades of experience writing perfectly valid, production-grade SQL queries. You never make syntax errors, you never assume non-existent data, and you always strictly follow the provided schema.

Input Provided:

Full MySQL database schema with exact table names, column names, and their data types.

Sample rows from each table to understand the relationships and content.

A natural language question (which can be simple or very complex).

Your Task:

Generate exactly ONE fully correct, optimized MySQL SELECT statement that answers the question.

Use only the provided schema and sample data — never invent or assume any table, column, or alias.

Ensure the query is syntactically perfect for MySQL and executes without error.

Use proper JOINs, GROUP BY, ORDER BY, LIMIT, subqueries, date functions, aggregations, CASE expressions, window functions, or any advanced SQL techniques required.

Handle all possible query types:

Filtering

Sorting

Aggregating

Ranking

Nested queries

Conditional logic

Percentages and ratios

Time-series analysis

Top/Bottom N results

Multi-step logic with subqueries or CTEs

Preserve exact case and spelling of table and column names from the schema.

No placeholders — always use actual names from the provided schema.

Query must be production-ready, fully optimized, and logically accurate.

Output Rules:

Output only the raw SQL query text.

Do not include Markdown formatting, triple backticks, or the word “sql”.

Do not include any explanation, commentary, or restatement of the question.

Do not output anything before or after the SQL query.



    Schema and samples:
    {schema_text}

    User question:
    {question}

    Constraints:
    - Only a single SELECT statement, do not output multiple statements.
    - Do NOT output any explanation, only the code block with the SQL.
    """)
    status, llm_data = call_groq(prompt_sql)
    if status != 200:
        return jsonify({"error": f"LLM error: status {status} - {llm_data}"}), 502

    # robust extraction
    try:
        content = llm_data['choices'][0]['message']['content']
    except Exception:
        return jsonify({"error": "Unexpected LLM response shape."}), 502

    sql_candidate = extract_sql_from_text(content)
    if not sql_candidate:
        return jsonify({"error": "LLM did not return a SQL query."}), 502

    # safety check
    if not is_safe_select(sql_candidate):
        return jsonify({"error": "Generated SQL is not a safe SELECT; aborting."}), 400

    # Step 2: Execute SQL
    try:
        results = execute_select(sql_candidate, db_config, limit=20)
    except Exception as e:
        return jsonify({"error": f"SQL execution error: {str(e)}", "sql": sql_candidate}), 500

    # Step 3: Ask LLM to produce a short (max 5-line) explanation using the results (NO SQL)
    columns = list(results[0].keys()) if results else []
    explanation = ask_groq_for_explanation(question, columns, results)

    # Save QA (store paragraph and SQL internally)
    save_qa(question, explanation, sql_candidate)

    # Return only the human-friendly paragraph and results (frontend will display paragraph only)
    return jsonify({"answer": explanation, "results": results})

@app.route('/download')
def download():
    fp = os.path.join("report", "qa_report.csv")
    if os.path.exists(fp):
        return send_file(fp, as_attachment=True)
    return jsonify({"error": "No report file found."}), 404

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/test')
def test():
    return jsonify({
        "status": "running",
        "logged_in": session.get('logged_in', False),
        "db_connected": bool(session.get('db_config'))
    })

if __name__ == "__main__":
    os.makedirs("report", exist_ok=True)
    app.run(host="0.0.0.0", port=5000, debug=True)
