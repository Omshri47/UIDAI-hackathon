import os
import pandas as pd
import sqlite3
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'super_secret_hackathon_key'

# --- 1. DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY, email TEXT UNIQUE, password TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- 2. DATA LOADING ---
DATA_FOLDER = 'data'

def load_data():
    try:
        if not os.path.exists(DATA_FOLDER):
            os.makedirs(DATA_FOLDER)
            return pd.DataFrame()

        all_files = [os.path.join(DATA_FOLDER, f) for f in os.listdir(DATA_FOLDER) if f.endswith('.csv')]
        if not all_files: return pd.DataFrame()
        
        # Optimize: Read specific cols to save memory
        df = pd.concat([pd.read_csv(f) for f in all_files], ignore_index=True)
        df.columns = df.columns.str.strip()
        
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], format='%d-%m-%Y', errors='coerce')
            
        return df
    except Exception as e:
        print(f"Data Load Error: {e}")
        return pd.DataFrame()

df_main = load_data()

# --- 3. ROUTES ---

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email=?", (email,))
        user = c.fetchone()
        conn.close()
        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]; session['email'] = user[1]
            return redirect(url_for('dashboard'))
        else: return render_template('login.html', error="Invalid Credentials")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            email = request.form['email']
            password = generate_password_hash(request.form['password'])
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, password))
            conn.commit(); conn.close()
            return redirect(url_for('login'))
        except: return render_template('register.html', error="Email exists")
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('login'))
    # Get States List
    states = sorted(df_main['state'].dropna().unique().tolist()) if not df_main.empty else []
    return render_template('dashboard.html', states=states, user=session.get('email'))

@app.route('/reports')
def reports():
    if 'user_id' not in session: return redirect(url_for('login'))
    return render_template('reports.html', user=session.get('email'))

@app.route('/settings')
def settings():
    if 'user_id' not in session: return redirect(url_for('login'))
    return render_template('settings.html', user=session.get('email'))

# --- 4. API LOGIC ---

@app.route('/api/migration_data')
def get_migration_data():
    selected_state = request.args.get('state', 'All')
    
    if df_main.empty: return jsonify({"error": "No Data"})

    # Filter Data
    data = df_main.copy()
    if selected_state != 'All':
        data = data[data['state'] == selected_state]

    # KPIs
    total_18_plus = int(data['demo_age_17_'].sum()) if 'demo_age_17_' in data.columns else 0
    total_kids = int(data['demo_age_5_17'].sum()) if 'demo_age_5_17' in data.columns else 0
    
    # Identify Top Hub (District vs State)
    group_col = 'state' if selected_state == 'All' else 'district'
    
    if group_col in data.columns and 'demo_age_17_' in data.columns:
        # Get the single highest area
        top_hub_data = data.groupby(group_col)['demo_age_17_'].sum().sort_values(ascending=False)
        top_hub_name = top_hub_data.index[0] if not top_hub_data.empty else "N/A"
        top_hub_val = int(top_hub_data.values[0]) if not top_hub_data.empty else 0
    else:
        top_hub_name, top_hub_val = "N/A", 0

    # Charts Data
    # 1. Bar Chart (Top 10 Locations)
    bar_data = data.groupby(group_col)['demo_age_17_'].sum().sort_values(ascending=False).head(10)
    
    # 2. Line Chart (Trend)
    line_data = data.groupby('date')['demo_age_17_'].sum().reset_index().sort_values('date')
    
    # 3. Pie Chart
    pie_values = [total_kids, total_18_plus]
    pie_labels = ["Students (5-17)", "Workforce (18+)"]

    # Summary Text Generation
    location_type = "State" if selected_state == "All" else "District"
    summary_text = [
        f"<strong>Overview:</strong> Total migration updates in {selected_state} are {total_18_plus + total_kids:,}.",
        f"<strong>Key Driver:</strong> The Workforce (18+) segment drives {int((total_18_plus/(total_18_plus+total_kids+1))*100)}% of movement.",
        f"<strong>Top Hotspot:</strong> The highest activity is in the {location_type} of <b>{top_hub_name}</b> ({top_hub_val:,} updates).",
        "<strong>Action:</strong> Recommended deployment of mobile enrolment units to this hub."
    ]

    return jsonify({
        "kpi": { "total": f"{total_18_plus:,}", "top_hub": top_hub_name },
        "bar_chart": { "labels": bar_data.index.tolist(), "values": bar_data.values.tolist(), "label": f"Top {group_col}s" },
        "line_chart": { "labels": line_data['date'].dt.strftime('%Y-%m-%d').tolist(), "values": line_data['demo_age_17_'].tolist() },
        "pie_chart": { "labels": pie_labels, "values": pie_values },
        "summary": summary_text
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)