import os
import json
import secrets
from datetime import datetime, date
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from supabase import create_client, Client
from pytz import timezone
import csv
import io

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(24))

# Timezone
EAT = timezone('Africa/Kampala')

# Supabase Configuration
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY') or os.environ.get('SUPABASE_KEY')
supabase: Client = None

if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Helper: Format UGX
@app.template_filter('format_ugx')
def format_ugx(value):
    try:
        return f"UGX {int(value):,}"
    except (ValueError, TypeError):
        return "UGX 0"

@app.template_filter('from_json')
def from_json(value):
    return json.loads(value) if value else []

# Helper: Current Time in EAT
def get_now_eat():
    return datetime.now(EAT)

# -- Auth Decorator --
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# -- Routes --

@app.route('/login', methods=['GET', 'POST'])
def login():
    try:
        if request.method == 'POST':
            password = request.form.get('password', '').strip()
            expected = os.environ.get('ADMIN_PASSWORD', 'admin123').strip()
            if password == expected:
                session['logged_in'] = True
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid password. Please check your Render environment variables.', 'danger')
        return render_template('login.html')
    except Exception as e:
        return f"CRITICAL LOGIN ERROR: {str(e)}", 500

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    try:
        if not supabase:
            return "ERROR: Supabase Client not initialized. Check SUPABASE_URL and SUPABASE_KEY environment variables.", 500

        # Top Summary Cards
        licenses_res = supabase.table('licenses').select('count', count='exact').execute()
        total_licenses = licenses_res.count if licenses_res else 0
        
        active_res = supabase.table('licenses').select('count', count='exact').eq('is_active', True).execute()
        active_licenses = active_res.count if active_res else 0
        
        # Revenue
        payments_res = supabase.table('payments').select('amount_ugx').execute()
        total_revenue = sum(p.get('amount_ugx', 0) for p in payments_res.data) if payments_res.data else 0
        
        return render_template('dashboard.html', 
                               total_licenses=total_licenses, 
                               active_licenses=active_licenses,
                               total_revenue=total_revenue)
    except Exception as e:
        return f"CRITICAL DASHBOARD ERROR: {str(e)}", 500

@app.route('/licenses')
@login_required
def licenses():
    search = request.args.get('search', '')
    plan = request.args.get('plan', '')
    
    query = supabase.table('licenses').select('*').order('created_at', desc=True)
    if search:
        query = query.ilike('pharmacy_name', f'%{search}%')
    if plan:
        query = query.eq('plan', plan)
        
    res = query.execute()
    licenses_list = res.data if res else []
    
    return render_template('licenses.html', 
                           licenses=licenses_list, 
                           now_date=date.today().isoformat())

@app.route('/licenses/generate', methods=['POST'])
@login_required
def generate_license():
    plan = request.form.get('plan')
    period = request.form.get('period')
    terminals = int(request.form.get('terminals', 1))
    
    # Generate Key
    key = f"CURE-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}"
    
    # Expiry Date Calculation
    today = date.today()
    if period == 'monthly':
        expires = today.replace(month=today.month + 1) if today.month < 12 else today.replace(year=today.year + 1, month=1)
    else: # annual
        expires = today.replace(year=today.year + 1)
        
    new_license = {
        'license_key': key,
        'plan': plan,
        'max_terminals': terminals,
        'expires_at': expires.isoformat(),
        'is_active': True,
        'machine_ids': '[]',
        'created_at': get_now_eat().isoformat()
    }
    
    supabase.table('licenses').insert(new_license).execute()
    flash(f'License {key} generated successfully!', 'success')
    return redirect(url_for('licenses'))

@app.route('/licenses/revoke/<key>', methods=['POST'])
@login_required
def revoke_license(key):
    confirm = request.form.get('confirm')
    if confirm == 'REVOKE':
        supabase.table('licenses').update({'is_active': False}).eq('license_key', key).execute()
        flash(f'License {key} revoked.', 'warning')
    return redirect(url_for('licenses'))

@app.route('/licenses/restore/<key>', methods=['POST'])
@login_required
def restore_license(key):
    supabase.table('licenses').update({'is_active': True}).eq('license_key', key).execute()
    flash(f'License {key} restored.', 'success')
    return redirect(url_for('licenses'))

@app.route('/licenses/reset-machines/<key>', methods=['POST'])
@login_required
def reset_machines(key):
    supabase.table('licenses').update({'machine_ids': '[]'}).eq('license_key', key).execute()
    # Log to transfer_log
    supabase.table('transfer_log').insert({
        'license_key': key,
        'reason': 'Admin Manual Reset',
        'created_at': get_now_eat().isoformat()
    }).execute()
    flash(f'Machine IDs reset for {key}.', 'info')
    return redirect(url_for('licenses'))

@app.route('/payments')
@login_required
def payments():
    res = supabase.table('payments').select('*').order('date', desc=True).execute()
    payments_list = res.data if res else []
    return render_template('payments.html', payments=payments_list)

@app.route('/customers')
@login_required
def customers():
    res = supabase.table('licenses').select('*').not_.is_('pharmacy_name', 'null').execute()
    customers_list = res.data if res else []
    return render_template('customers.html', customers=customers_list)

@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html')

# -- API ENDPOINTS --

@app.route('/api/activate', methods=['POST'])
def api_activate():
    data = request.json
    key = data.get('license_key')
    machine_id = data.get('machine_id')
    pharmacy_name = data.get('pharmacy_name')
    contact = data.get('contact')
    phone = data.get('phone')
    
    res = supabase.table('licenses').select('*').eq('license_key', key).execute()
    if not res.data:
        return jsonify({'valid': False, 'error': "Invalid license key"}), 404
        
    lic = res.data[0]
    if not lic['is_active']:
        return jsonify({'valid': False, 'error': "License revoked. Contact support."}), 403
        
    expires_at = datetime.fromisoformat(lic['expires_at']).date()
    if expires_at < date.today():
        return jsonify({'valid': False, 'error': "License expired. Please renew."}), 402
        
    machine_ids = json.loads(lic['machine_ids'])
    if machine_id in machine_ids:
        return jsonify({
            'valid': True, 
            'message': "Already activated",
            'plan': lic['plan'],
            'expires': lic['expires_at'],
            'pharmacy_name': lic['pharmacy_name'] or pharmacy_name
        })
        
    if len(machine_ids) >= lic['max_terminals']:
        return jsonify({
            'valid': False, 
            'error': "Maximum terminals reached.",
            'can_transfer': True
        }), 409
        
    machine_ids.append(machine_id)
    update_data = {'machine_ids': json.dumps(machine_ids)}
    if not lic['pharmacy_name']:
        update_data['pharmacy_name'] = pharmacy_name
        update_data['contact_person'] = contact
        update_data['phone'] = phone
    if not lic['activated_at']:
        update_data['activated_at'] = get_now_eat().isoformat()
        
    supabase.table('licenses').update(update_data).eq('license_key', key).execute()
    
    return jsonify({
        'valid': True,
        'plan': lic['plan'],
        'max_users': lic['max_users'],
        'max_terminals': lic['max_terminals'],
        'expires': lic['expires_at'],
        'pharmacy_name': lic['pharmacy_name'] or pharmacy_name
    })

@app.route('/api/validate', methods=['POST'])
def api_validate():
    data = request.json
    key = data.get('license_key')
    machine_id = data.get('machine_id')
    
    res = supabase.table('licenses').select('*').eq('license_key', key).execute()
    if not res.data:
        return jsonify({'valid': False, 'error': "Invalid license"}), 404
        
    lic = res.data[0]
    if not lic['is_active']:
        return jsonify({'valid': False, 'error': "License revoked"}), 403
        
    expires_at = datetime.fromisoformat(lic['expires_at']).date()
    if expires_at < date.today():
        return jsonify({'valid': False, 'error': "Expired", 'expired_on': lic['expires_at']}), 402
        
    machine_ids = json.loads(lic['machine_ids'])
    if machine_id not in machine_ids:
        return jsonify({'valid': False, 'error': "Not activated on this machine"}), 403
        
    supabase.table('licenses').update({'last_seen_at': get_now_eat().isoformat()}).eq('license_key', key).execute()
    
    days_left = (expires_at - date.today()).days
    warning = f"Expires in {days_left} days" if days_left < 30 else None
    
    return jsonify({
        'valid': True,
        'plan': lic['plan'],
        'max_users': lic['max_users'],
        'expires': lic['expires_at'],
        'pharmacy_name': lic['pharmacy_name'],
        'days_until_expiry': days_left,
        'warning': warning
    })

@app.route('/api/transfer', methods=['POST'])
def api_transfer():
    data = request.json
    key = data.get('license_key')
    old_id = data.get('old_machine_id')
    new_id = data.get('new_machine_id')
    reason = data.get('reason')
    
    res = supabase.table('licenses').select('*').eq('license_key', key).execute()
    if not res.data: return jsonify({'success': False, 'error': "Invalid license"}), 404
    
    lic = res.data[0]
    if not lic['is_active']: return jsonify({'success': False, 'error': "Revoked"}), 403
    
    machine_ids = json.loads(lic['machine_ids'])
    if old_id in machine_ids:
        machine_ids.remove(old_id)
        machine_ids.append(new_id)
        supabase.table('licenses').update({'machine_ids': json.dumps(machine_ids)}).eq('license_key', key).execute()
        supabase.table('transfer_log').insert({
            'license_key': key,
            'old_machine_id': old_id,
            'new_machine_id': new_id,
            'reason': reason,
            'created_at': get_now_eat().isoformat()
        }).execute()
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': "Original machine not found"}), 404

if __name__ == '__main__':
    app.run(debug=True)
