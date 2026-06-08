from flask import Flask, request, jsonify
import secrets
import hashlib
import sqlite3
import os
from datetime import datetime, timedelta

app = Flask(__name__)
DB_PATH = "licenses.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS licenses (
                license_key TEXT PRIMARY KEY,
                machine_id TEXT,
                pharmacy_name TEXT,
                contact_person TEXT,
                phone TEXT,
                expires_at TEXT,
                is_activated INTEGER DEFAULT 0,
                max_users INTEGER DEFAULT 5,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()

@app.route('/validate', methods=['POST'])
def validate():
    data = request.json
    key = data.get('license_key')
    machine_id = data.get('machine_id')
    
    with get_db() as conn:
        license_info = conn.execute(
            "SELECT * FROM licenses WHERE license_key = ?", (key,)
        ).fetchone()
    
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
    
    with get_db() as conn:
        license_info = conn.execute(
            "SELECT * FROM licenses WHERE license_key = ?", (key,)
        ).fetchone()
        
        if not license_info:
            return jsonify({"success": False, "error": "Invalid license key"}), 404
            
        if license_info['is_activated']:
            return jsonify({"success": False, "error": "License already activated"}), 400
            
        conn.execute("""
            UPDATE licenses 
            SET is_activated = 1, machine_id = ?, pharmacy_name = ?, 
                contact_person = ?, phone = ?
            WHERE license_key = ?
        """, (machine_id, pharmacy_name, contact_person, phone, key))
        conn.commit()
        
        # Re-fetch for response
        license_info = conn.execute(
            "SELECT expires_at FROM licenses WHERE license_key = ?", (key,)
        ).fetchone()
    
    return jsonify({
        "success": True,
        "pharmacy_name": pharmacy_name,
        "expires": license_info['expires_at']
    })

@app.route('/admin/generate', methods=['POST'])
def generate_key():
    if request.headers.get('Admin-Secret') != os.environ.get('ADMIN_SECRET', 'cure-admin-secret'):
        return jsonify({"error": "Unauthorized"}), 401
        
    new_key = f"CURE-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}"
    expiry = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
    
    with get_db() as conn:
        conn.execute("""
            INSERT INTO licenses (license_key, expires_at, max_users)
            VALUES (?, ?, ?)
        """, (new_key, expiry, 5))
        conn.commit()
        
    return jsonify({"license_key": new_key})

if __name__ == '__main__':
    init_db()
    app.run(port=int(os.environ.get('PORT', 8000)))
