from flask import Flask, request, jsonify
import secrets
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta

app = Flask(__name__)

# Render/Supabase Connection String
# IMPORTANT: This must be the "Connection String" (postgres://...), not the API URL
DATABASE_URL = os.environ.get('DATABASE_URL')
# Use ADMIN_PASSWORD to match what you entered in Render
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'cure-admin-secret')

def get_db_connection():
    # If using Supabase, ensure the URL starts with postgresql:// and uses sslmode=require
    url = DATABASE_URL
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    
    conn = psycopg2.connect(url, sslmode='require')
    return conn

def init_db():
    if not DATABASE_URL:
        return
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS licenses (
                license_key TEXT PRIMARY KEY,
                machine_id TEXT,
                pharmacy_name TEXT,
                contact_person TEXT,
                phone TEXT,
                expires_at TEXT,
                is_activated BOOLEAN DEFAULT FALSE,
                max_users INTEGER DEFAULT 5,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Database Init Error: {e}")

@app.route('/')
def home():
    return "Cure Pharma License Server is Running"

@app.route('/validate', methods=['POST'])
def validate():
    data = request.json
    key = data.get('license_key')
    machine_id = data.get('machine_id')
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM licenses WHERE license_key = %s", (key,))
        license_info = cur.fetchone()
        cur.close()
        conn.close()
    except Exception as e:
        return jsonify({"valid": False, "error": f"Database error: {str(e)}"}), 500
    
    if not license_info:
        return jsonify({"valid": False, "error": "Invalid license key"}), 404
    
    if not license_info['is_activated']:
        return jsonify({"valid": False, "error": "License not activated"}), 400
        
    if license_info['machine_id'] != machine_id:
        return jsonify({"valid": False, "error": "License registered to another machine"}), 403
        
    expiry_date = datetime.strptime(license_info['expires_at'], "%Y-%m-%d")
    if datetime.now() > expiry_date:
        return jsonify({
            "valid": False, 
            "error": "License expired", 
            "expires": license_info['expires_at']
        }), 402
        
    return jsonify({
        "valid": True,
        "pharmacy_name": license_info['pharmacy_name'],
        "expires": license_info['expires_at'],
        "max_users": license_info['max_users']
    })

@app.route('/activate', methods=['POST'])
def activate():
    data = request.json
    key = data.get('license_key')
    machine_id = data.get('machine_id')
    pharmacy_name = data.get('pharmacy_name')
    contact_person = data.get('contact_person')
    phone = data.get('phone')
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT * FROM licenses WHERE license_key = %s", (key,))
        license_info = cur.fetchone()
        
        if not license_info:
            cur.close()
            conn.close()
            return jsonify({"success": False, "error": "Invalid license key"}), 404
            
        if license_info['is_activated']:
            cur.close()
            conn.close()
            return jsonify({"success": False, "error": "License already activated"}), 400
            
        cur.execute("""
            UPDATE licenses 
            SET is_activated = TRUE, machine_id = %s, pharmacy_name = %s, 
                contact_person = %s, phone = %s
            WHERE license_key = %s
        """, (machine_id, pharmacy_name, contact_person, phone, key))
        conn.commit()
        
        expires_at = license_info['expires_at']
        cur.close()
        conn.close()
        
        return jsonify({
            "success": True,
            "pharmacy_name": pharmacy_name,
            "expires": expires_at
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Database error: {str(e)}"}), 500

@app.route('/admin/generate', methods=['POST'])
def generate_key():
    # Use ADMIN_PASSWORD header or password from request
    auth = request.headers.get('Admin-Secret') or request.json.get('admin_password')
    if auth != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401
        
    new_key = f"CURE-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}"
    expiry = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO licenses (license_key, expires_at, max_users)
            VALUES (%s, %s, %s)
        """, (new_key, expiry, 5))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"license_key": new_key})
    except Exception as e:
        return jsonify({"error": f"Database error: {str(e)}"}), 500

if __name__ == '__main__':
    if DATABASE_URL:
        init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8000)))
