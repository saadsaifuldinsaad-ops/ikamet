import os
import re
import sqlite3
import random
from datetime import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import json

from flask import Flask, request, render_template, jsonify, send_from_directory, session, redirect, url_for
from authlib.integrations.flask_client import OAuth

app = Flask(__name__, template_folder='.')
app.config['SECRET_KEY'] = 'saad_secure_admin_key_2026'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

app.config['GOOGLE_CLIENT_ID'] = '454315786561-4g34eggjhg3jtf72bsv3c9ufo1fvg2ln.apps.googleusercontent.com'
app.config['GOOGLE_CLIENT_SECRET'] = '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'

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# --- إعداد قاعدة بيانات SQLite بدلاً من ملفات JSON ---
DB_NAME = 'system_database.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, password TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS prices (key TEXT PRIMARY KEY, value TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT, phone TEXT, message TEXT, timestamp TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS threads (id INTEGER PRIMARY KEY AUTOINCREMENT, message_id INTEGER, sender TEXT, text TEXT, timestamp TEXT, FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE)''')
    conn.commit()
    conn.close()

init_db()

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'pdf'}

ADMIN_TARGET_NAME = "saad1234"
ADMIN_TARGET_EMAIL = "saadsaifuldinsaad@gmail.com"
otp_storage = {}

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "saadsaifuldinsaad@gmail.com"
SENDER_PASSWORD = "pipwpnsbuchpetmm"
MAIL_SENDER_DISPLAY = "خدمات الإقامات والتأمين <no-reply@residence-system.com>"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- دوال التعامل مع القاعدة بدلاً من JSON ---
def load_users():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT email, password FROM users')
    rows = cursor.fetchall()
    conn.close()
    
    users_db = {row[0]: row[1] for row in rows}
    if not users_db:
        users_db = {ADMIN_TARGET_EMAIL: "123456"}
        save_users(users_db)
    return users_db

def save_users(users_data):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    for email, pwd in users_data.items():
        cursor.execute('INSERT OR REPLACE INTO users (email, password) VALUES (?, ?)', (email, pwd))
    conn.commit()
    conn.close()

def load_prices():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM prices WHERE key = "main_data"')
    row = cursor.fetchone()
    conn.close()
    
    if row and row[0]:
        try:
            return json.loads(row[0])
        except:
            pass
            
    default_prices = {
        "residence_fee": 200,
        "insurance_rates": {
            "0_16": 1500, "17_25": 500, "26_35": 600, "36_45": 700,
            "46_55": 850, "56_60": 1000, "61_64": 1200, "65_69": 3000
        }
    }
    save_prices(default_prices)
    return default_prices

def save_prices(data):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO prices (key, value) VALUES ("main_data", ?)', (json.dumps(data, ensure_ascii=False),))
    conn.commit()
    conn.close()

def load_config():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM config WHERE key = "main_config"')
    row = cursor.fetchone()
    conn.close()
    
    if row and row[0]:
        try:
            return json.loads(row[0])
        except:
            pass
            
    default_config = {
        "residence_types": {
            'tourist': 'إقامة سياحية (Turistik)',
            'real_estate': 'إقامة عقارية (Taşınmaz)',
            'student': 'إقامة طالب (Öğrenci)',
            'family': 'إقامة عائلية (Aile)',
            'turkmen': 'إقامة تركمانية / أصول تركية (Türk Soylu)',
            'humanitarian': 'إنسانية (Insani)',
            'commercial': 'إقامة تجارية / شركة (Ticari)',
            'treatment': 'إقامة علاجية (Tedavi)',
            'long_term': 'إقامة دائمة (Uzun Dönem)'
        },
        "marital_statuses": {
            'single': 'أعزب / عزباء (Bekâr)',
            'married': 'متزوج / متزوجة (Evli)',
            'widowed': 'أرمل / أرملة (Dul)',
            'divorced': "مطلق / مطلقة (Boşanmış)",
            'separated': "منفصل / منفصلة (Ayrı)",
            'engaged': "خطيب / خطيبة (Nişanlı)"
        },
        "residence_durations": {
            '0.5': 'ستة أشهر (6 Aylar)',
            '1': 'سنة واحدة (1 Yıl)',
            '1.5': 'سنة ونصف (1.5 Yıl)',
            '2': 'سنتين (2 Yıl)'
        },
        "insurance_options": {
            'no': 'لا (بدون تأمين صحي)',
            'yes': 'نعم (إضافة تأمين صحي)'
        },
        "document_labels": {
            'passport': 'صورة الجواز',
            'personal-photo': 'صورة شخصية',
            'kimlik-front': 'كملك أمامي',
            'kimlik-back': 'كملك خلفي',
            'deed': 'صورة الطابو',
            'bill': 'فاتورة (ماء-كهرباء)'
        }
    }
    save_config(default_config)
    return default_config

def save_config(data):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO config (key, value) VALUES ("main_config", ?)', (json.dumps(data, ensure_ascii=False),))
    conn.commit()
    conn.close()

def load_messages():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, email, phone, message, timestamp FROM messages ORDER BY id DESC')
    msg_rows = cursor.fetchall()
    
    messages_list = []
    for m in msg_rows:
        m_id, name, email, phone, message, timestamp = m
        cursor.execute('SELECT sender, text, timestamp FROM threads WHERE message_id = ? ORDER BY id ASC', (m_id,))
        t_rows = cursor.fetchall()
        thread = [{"sender": tr[0], "text": tr[1], "timestamp": tr[2]} for tr in t_rows]
        
        messages_list.append({
            "id": m_id,
            "name": name,
            "email": email,
            "phone": phone,
            "message": message,
            "timestamp": timestamp,
            "thread": thread
        })
    conn.close()
    return messages_list

def send_admin_notification(event_type, user_email):
    try:
        msg = MIMEMultipart()
        msg['From'] = MAIL_SENDER_DISPLAY
        msg['To'] = SENDER_EMAIL
        msg['Subject'] = f"🔔 إشعار نشاط جديد: {event_type}"
        
        body = f"""مرحباً سعد،

تم رصد نشاط جديد على النظام الموقع:
📌 نوع النشاط: {event_type}
👤 البريد الإلكتروني للمستخدم: {user_email}
🕒 وقت النشاط: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, SENDER_EMAIL, msg.as_string())
    except Exception as e:
        print(f"خطأ في إرسال الإشعار: {e}")

def send_admin_alert_email(new_data):
    try:
        old_prices = load_prices()
        old_fee = old_prices.get("residence_fee", 200)
        new_fee = new_data.get("residence_fee", 200)
        fee_change_text = f"📌 رسوم الموعد الثابتة: تم تغييرها من ({old_fee} TL) إلى ({new_fee} TL)\n" if old_fee != new_fee else f"📌 رسوم الموعد الثابتة: بقت مثل ما هي ({new_fee} TL)\n"

        old_rates = old_prices.get("insurance_rates", {})
        new_rates = new_data.get("insurance_rates", {})
        
        rates_labels = {
            "0_16": "فئة (0-16 سنة)", "17_25": "فئة (17-25 سنة)",
            "26_35": "فئة (26-35 سنة)", "36_45": "فئة (36-45 سنة)",
            "46_55": "فئة (46-55 سنة)", "56_60": "فئة (56-60 سنة)",
            "61_64": "فئة (61-64 سنة)", "65_69": "فئة (65-69 سنة)"
        }

        changes_list = []
        for key, label in rates_labels.items():
            o_val = old_rates.get(key, 0)
            n_val = new_rates.get(key, 0)
            if o_val != n_val:
                changes_list.append(f"🔸 {label}: من ({o_val} TL) ➔ إلى ({n_val} TL)")

        changes_summary = "\n".join(changes_list) if changes_list else "لم يتم تغيير أي سعر في فئات التأمين."

        msg = MIMEMultipart()
        msg['From'] = MAIL_SENDER_DISPLAY
        msg['To'] = SENDER_EMAIL
        msg['Subject'] = "⚠️ تنبيه: تم رصد تعديل وتغيير في أسعار لوحة التحكم"
        
        body = f"""مرحباً سعد،
تم إجراء تحديث على الأسعار في لوحة التحكم، وإليك التفاصيل:

{fee_change_text}
--------------------------------------------------
📋 تفاصيل تغييرات أسعار التأمين الصحي:
{changes_summary}
--------------------------------------------------
🕒 وقت التعديل: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, SENDER_EMAIL, msg.as_string())
    except Exception as e:
        print(f"خطأ في إرسال الإيميل: {e}")

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', error_code=404, error_message="عذراً، الصفحة التي تبحث عنها غير موجودة."), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', error_code=500, error_message="عذراً، حدث خطأ غير متوقع في النظام. جاري العمل على إصلاحه."), 500

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/index2')
def index2():
    return render_template('index2.html')

@app.route('/verify', methods=['GET', 'POST'])
@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp_page():
    error_message = None
    email_param = request.args.get('email', '').strip()
    
    if request.method == 'POST':
        email = session.get('pending_google_email', '').strip()
        if not email:
            email = email_param or request.form.get('email', '').strip()
        
        if request.is_json:
            data = request.json or {}
            otp_code = str(data.get('otp_code', '')).strip()
            if not email:
                email = str(data.get('email', '')).strip()
        else:
            otp_code = str(request.form.get('otp_code', '')).strip()
            if not email:
                email = str(request.form.get('email', '')).strip()

        if email and otp_storage.get(email) == otp_code:
            session['is_authenticated'] = True
            if email == ADMIN_TARGET_EMAIL:
                session['is_admin'] = True
            otp_storage.pop(email, None)
            
            send_admin_notification("تسجيل دخول ناجح (OTP)", email)
            
            target_url = url_for('index2')
            if request.is_json:
                return jsonify({'status': 'success', 'redirect': target_url})
            else:
                return redirect(target_url)
        else:
            error_message = 'رمز التحقق غير صحيح، يرجى المحاولة مرة أخرى.'
            if request.is_json:
                return jsonify({'status': 'error', 'message': error_message}), 400
            
    return render_template('verify_otp.html', error_message=error_message, email=email_param)

@app.route('/success')
def success_wait():
    return render_template('success_wait.html')

@app.route('/register', methods=['GET'])
def register_page():
    return render_template('register.html')

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '').strip()

    if not name or not email or not password:
        return jsonify({'error': 'يرجى ملء جميع الحقول المطلوبة'}), 400

    # 🔴 التحقق الذكي: يجب أن ينتهي البريد الإلكتروني حصراً بـ @gmail.com
    if not email.endswith('@gmail.com'):
        return jsonify({'error': 'خطأ: يجب أن يكون البريد الإلكتروني من نوع Gmail (ينتهي بـ @gmail.com حصراً)'}), 400

    users_db = load_users()
    if email in users_db:
        return jsonify({'error': 'هذا البريد الإلكتروني مسجل مسبقاً!'}), 400

    users_db[email] = password
    save_users(users_db)

    send_admin_notification("إنشاء حساب جديد", email)

    otp_code = str(random.randint(100000, 999999))
    otp_storage[email] = otp_code
    session['pending_google_email'] = email

    try:
        msg = MIMEMultipart()
        msg['From'] = MAIL_SENDER_DISPLAY
        msg['To'] = email
        msg['Subject'] = "🔐 كود التحقق لتفعيل حسابك الجديد"
        msg.attach(MIMEText(f"مرحباً {name},\n\nرمز التحقق الخاص بك هو: {otp_code}", 'plain', 'utf-8'))
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, email, msg.as_string())
        return jsonify({'success': True, 'message': 'تم إرسال كود التحقق بنجاح'})
    except Exception as e:
        return jsonify({'error': 'فشل إرسال البريد الإلكتروني لتأكيد الحساب'}), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.json or {}
        step = data.get('step')
        email = data.get('email', '').strip()
        password = data.get('password', '').strip()

        users_db = load_users()

        if step == 'login':
            if email not in users_db or users_db[email] != password:
                return jsonify({'status': 'error', 'message': 'البريد الإلكتروني أو كلمة المرور غير صحيحة!'}), 400

            if email:
                otp_code = str(random.randint(100000, 999999))
                otp_storage[email] = otp_code
                session['pending_google_email'] = email
                try:
                    msg = MIMEMultipart()
                    msg['From'] = MAIL_SENDER_DISPLAY
                    msg['To'] = email
                    msg['Subject'] = "🔐 رمز التحقق لتسجيل الدخول (OTP)"
                    msg.attach(MIMEText(f"مرحباً، رمز التحقق الخاص بك هو: {otp_code}", 'plain', 'utf-8'))
                    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                        server.starttls()
                        server.login(SENDER_EMAIL, SENDER_PASSWORD)
                        server.sendmail(SENDER_EMAIL, email, msg.as_string())
                    return jsonify({'status': 'otp_sent', 'message': 'تم التحقق من بياناتك وإرسال رمز التحقق إلى بريدك'})
                except Exception as e:
                    return jsonify({'status': 'error', 'message': 'فشل إرسال البريد الإلكتروني'}), 500
            else:
                return jsonify({'status': 'error', 'message': 'يرجى إدخال البريد الإلكتروني'}), 400

        elif step == 'verify':
            otp_code = data.get('otp_code', '').strip()
            if email and otp_storage.get(email) == otp_code:
                session['is_authenticated'] = True
                if email == ADMIN_TARGET_EMAIL:
                    session['is_admin'] = True
                otp_storage.pop(email, None)
                
                send_admin_notification("تسجيل دخول ناجح (عبر نموذج الموقع)", email)
                
                return jsonify({'status': 'success', 'redirect': url_for('index2')})
            else:
                return jsonify({'status': 'error', 'message': 'رمز التحقق غير صحيح'}), 400

    return render_template('login.html')

@app.route('/login/google')
def google_login():
    redirect_uri = url_for('google_auth', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/login/google/auth')
def google_auth():
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo')
        if not user_info:
            user_info = google.get('https://www.googleapis.com/oauth2/v3/userinfo').json()
        
        email = user_info.get('email')
        if email:
            otp_code = str(random.randint(100000, 999999))
            otp_storage[email] = otp_code
            session['pending_google_email'] = email
            
            try:
                msg = MIMEMultipart()
                msg['From'] = MAIL_SENDER_DISPLAY
                msg['To'] = email
                msg['Subject'] = "🔐 رمز التحقق لتسجيل الدخول عبر جوجل (OTP)"
                msg.attach(MIMEText(f"مرحباً، رمز التحقق الخاص بك هو: {otp_code}", 'plain', 'utf-8'))
                with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                    server.starttls()
                    server.login(SENDER_EMAIL, SENDER_PASSWORD)
                    server.sendmail(SENDER_EMAIL, email, msg.as_string())
            except Exception as e:
                print(f"خطأ في إرسال إيميل جوجل OTP: {e}")

            return redirect(url_for('verify_otp_page', email=email))
        else:
            return render_template('error.html', error_code=400, error_message="عذراً، لم نتمكن من الحصول على البريد الإلكتروني من حساب جوجل."), 400
    except Exception as e:
        return render_template('error.html', error_code=500, error_message=f"فشل تسجيل الدخول عبر جوجل (خطأ في المصادقة): {e}"), 500

@app.route('/admin')
def admin_page():
    if not session.get('is_authenticated') or not session.get('is_admin'):
        return redirect(url_for('login'))
    return send_from_directory('.', 'admin.html')

@app.route('/api/prices', methods=['GET'])
def get_prices():
    return jsonify(load_prices())

@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify(load_config())

@app.route('/api/admin/request-otp', methods=['POST'])
def request_otp():
    data = request.json or {}
    email = data.get('email', '').strip()

    if email == ADMIN_TARGET_EMAIL:
        otp_code = str(random.randint(100000, 999999))
        otp_storage[ADMIN_TARGET_EMAIL] = otp_code
        try:
            msg = MIMEMultipart()
            msg['From'] = MAIL_SENDER_DISPLAY
            msg['To'] = email
            msg['Subject'] = "🔐 رمز التحقق للوصول إلى لوحة التحكم (OTP)"
            msg.attach(MIMEText(f"مرحباً سعد، رمز التحقق الخاص بك هو: {otp_code}", 'plain', 'utf-8'))
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.sendmail(SENDER_EMAIL, email, msg.as_string())
            return jsonify({'status': 'success'})
        except Exception:
            return jsonify({'status': 'error', 'message': 'فشل إرسال الإيميل'}), 500
    return jsonify({'status': 'unauthorized'}), 403

@app.route('/api/admin/verify-otp', methods=['POST'])
def verify_admin_otp():
    data = request.json or {}
    code = data.get('code', '').strip()
    if otp_storage.get(ADMIN_TARGET_EMAIL) == code:
        session['is_admin'] = True
        session['is_authenticated'] = True
        otp_storage.pop(ADMIN_TARGET_EMAIL, None)
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/admin/update-prices', methods=['POST'])
def update_prices():
    if not session.get('is_admin'):
        return jsonify({'status': 'unauthorized'}), 403
    data = request.json
    if data:
        save_prices(data)
        send_admin_alert_email(data)
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/admin/update-config', methods=['POST'])
def update_config():
    if not session.get('is_admin'):
        return jsonify({'status': 'unauthorized'}), 403
    data = request.json
    if data:
        save_config(data)
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/admin/messages', methods=['GET'])
def get_messages():
    if not session.get('is_admin'):
        return jsonify({'status': 'unauthorized'}), 403
    return jsonify(load_messages())

@app.route('/api/admin/delete-message/<int:msg_id>', methods=['DELETE'])
def delete_admin_message(msg_id):
    if not session.get('is_admin'):
        return jsonify({'status': 'unauthorized'}), 403
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM messages WHERE id = ?', (msg_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/api/messages/edit-thread-item', methods=['POST'])
def edit_thread_item():
    data = request.json
    if not data:
        return jsonify({'status': 'error'}), 400
    
    client_email = data.get('email', '').strip()
    timestamp = data.get('timestamp', '').strip()
    new_text = data.get('new_text', '').strip()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM messages WHERE email = ?', (client_email,))
    row = cursor.fetchone()
    
    updated = False
    if row:
        m_id = row[0]
        cursor.execute('''
            UPDATE threads SET text = ? WHERE message_id = ? AND timestamp = ?
        ''', (new_text, m_id, timestamp))
        if cursor.rowcount > 0:
            updated = True
            conn.commit()
    conn.close()
            
    if updated:
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 404

@app.route('/api/messages/delete-thread-item', methods=['POST'])
def delete_thread_item():
    data = request.json
    if not data:
        return jsonify({'status': 'error'}), 400
    
    client_email = data.get('email', '').strip()
    timestamp = data.get('timestamp', '').strip()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM messages WHERE email = ?', (client_email,))
    row = cursor.fetchone()
    
    updated = False
    if row:
        m_id = row[0]
        cursor.execute('''
            DELETE FROM threads WHERE message_id = ? AND timestamp = ?
        ''', (m_id, timestamp))
        if cursor.rowcount > 0:
            updated = True
            conn.commit()
    conn.close()
            
    if updated:
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 404

@app.route('/api/admin/send-reply', methods=['POST'])
def admin_send_reply():
    if not session.get('is_admin'):
        return jsonify({'status': 'unauthorized'}), 403
    
    data = request.json
    if not data:
        return jsonify({'status': 'error', 'message': 'بيانات غير صالحة'}), 400
        
    client_email = data.get('email', '').strip()
    reply_text = data.get('reply', '').strip()
    
    if not client_email or not reply_text:
        return jsonify({'status': 'error', 'message': 'يرجى إدخال البريد ونص الرسالة'}), 400
        
    timestamp_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM messages WHERE email = ?', (client_email,))
    row = cursor.fetchone()
    
    if row:
        m_id = row[0]
        cursor.execute('''
            INSERT INTO threads (message_id, sender, text, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (m_id, "admin", reply_text, timestamp_now))
        conn.commit()
    conn.close()

    try:
        msg = MIMEMultipart()
        msg['From'] = MAIL_SENDER_DISPLAY
        msg['To'] = client_email
        msg['Subject'] = "💬 رد من إدارة الموقع على استفسارك"
        
        body = f"مرحباً بك,\n\n{reply_text}\n\nمع تحيات إدارة الموقع."
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, client_email, msg.as_string())
            
        return jsonify({'status': 'success', 'message': 'تم إرسال الرد بنجاح'})
    except Exception as e:
        print(f"خطأ في إرسال الرد: {e}")
        return jsonify({'status': 'error', 'message': 'فشل إرسال الرد'}), 500

@app.route('/api/client-messages', methods=['POST'])
def client_get_messages():
    data = request.json
    client_email = data.get('email', '').strip()
    if not client_email:
        return jsonify([])
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM messages WHERE email = ?', (client_email,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return jsonify([])
        
    m_id = row[0]
    cursor.execute('SELECT sender, text, timestamp FROM threads WHERE message_id = ? ORDER BY id ASC', (m_id,))
    t_rows = cursor.fetchall()
    conn.close()
    
    thread = [{"sender": tr[0], "text": tr[1], "timestamp": tr[2]} for tr in t_rows]
    return jsonify(thread)

@app.route('/send-chat', methods=['POST'])
def send_chat():
    data = request.json
    if not data:
        return jsonify({'status': 'error', 'message': 'بيانات غير صالحة'}), 400
    
    name = re.sub(r'<[^>]*>', '', data.get('name', 'غير معروف')).strip()
    email = re.sub(r'<[^>]*>', '', data.get('email', '')).strip()
    phone = re.sub(r'[^0-9]', '', data.get('phone', '')).strip()
    message = re.sub(r'<[^>]*>', '', data.get('message', '')).strip()

    if email == ADMIN_TARGET_EMAIL:
        return jsonify({'status': 'success', 'message': 'تم الحفظ'})

    email_regex = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    if not re.match(email_regex, email):
        return jsonify({'status': 'error', 'message': 'يرجى إدخال بريد إلكتروني صحيح'}), 400

    phone_formatted = f"+90 {phone}" if phone and len(phone) == 10 else "غير متوفر"
    timestamp_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM messages WHERE email = ?', (email,))
    row = cursor.fetchone()

    if row:
        m_id = row[0]
        cursor.execute('''
            INSERT INTO threads (message_id, sender, text, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (m_id, "client", message, timestamp_now))
    else:
        cursor.execute('''
            INSERT INTO messages (name, email, phone, message, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, email, phone_formatted, message, timestamp_now))
        m_id = cursor.lastrowid
        cursor.execute('''
            INSERT INTO threads (message_id, sender, text, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (m_id, "client", message, timestamp_now))
        
    conn.commit()
    conn.close()

    try:
        msg = MIMEMultipart()
        msg['From'] = MAIL_SENDER_DISPLAY
        msg['To'] = SENDER_EMAIL
        msg['Subject'] = f"💬 رسالة جديدة من الزبون: {name}"
        msg.add_header('Reply-To', email)

        body = f"👤 اسم الزبون: {name}\n📧 الإيميل: {email}\n📱 الهاتف: {phone_formatted}\n\nنص الرسالة الجديدة:\n{message}\n\n🕒 الوقت: {timestamp_now}"
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, SENDER_EMAIL, msg.as_string())
            
        return jsonify({'status': 'success'})
    except Exception as e:
        print(f"خطأ في إرسال البريد: {e}")
        return jsonify({'status': 'error', 'message': 'فشل إرسال الرسالة'}), 500

@app.route('/submit', methods=['POST'])
def submit_form():
    prices = load_prices()
    config = load_config()
    
    phone = re.sub(r'[^0-9]', '', request.form.get('phone-number', ''))
    res_type = request.form.get('residence-type', 'غير متوفر')
    res_label = config.get('residence_types', {}).get(res_type, res_type)
    
    marital_status = request.form.get('marital-status', 'غير متوفر')
    marital_label = config.get('marital_statuses', {}).get(marital_status, 'غير متوفر')

    spouse_nationality = request.form.get('spouse-nationality', '')
    spouse_nationality_text = ""
    if marital_status == 'married':
        if spouse_nationality == 'turkish':
            spouse_nationality_text = " (الزوج / الزوجة: تركي 🇹🇷)"
        elif spouse_nationality == 'foreign':
            spouse_nationality_text = " (الزوج / الزوجة: أجنبي 🌍)"

    duration = request.form.get('residence-duration', 'غير متوفر')
    insurance = request.form.get('insurance-option', 'no')
    insurance_duration = request.form.get('insurance-duration', '1')
    birth_date = request.form.get('birth-date', 'N/A')

    insurance_price = 0
    insurance_status_text = 'لا (بدون تأمين)'
    
    if insurance == 'yes' and birth_date != 'N/A':
        try:
            b_date = datetime.strptime(birth_date, '%Y-%m-%d')
            today = datetime.today()
            age = today.year - b_date.year - ((today.month, today.day) < (b_date.month, b_date.day))
            
            rates = prices['insurance_rates']
            if 0 <= age <= 16: annual_rate = rates.get("0_16", 0)
            elif 17 <= age <= 25: annual_rate = rates.get("17_25", 500)
            elif 26 <= age <= 35: annual_rate = rates.get("26_35", 600)
            elif 36 <= age <= 45: annual_rate = rates.get("36_45", 700)
            elif 46 <= age <= 55: annual_rate = rates.get("46_55", 850)
            elif 56 <= age <= 60: annual_rate = rates.get("56_60", 1000)
            elif 61 <= age <= 64: annual_rate = rates.get("61_64", 1200)
            elif 65 <= age <= 69: annual_rate = rates.get("65_69", 0)
            else: annual_rate = 0

            years_count = int(insurance_duration) if insurance_duration.isdigit() else 1
            insurance_price = annual_rate * years_count
            insurance_status_text = f'نعم (مشمول - العمر {age} سنة)'
        except Exception:
            pass

    total_price = prices['residence_fee'] + insurance_price

    msg = MIMEMultipart()
    msg['From'] = MAIL_SENDER_DISPLAY
    msg['To'] = SENDER_EMAIL
    msg['Subject'] = f"🔒 طلب إقامة آمن: {res_label} - الرقم: +90 {phone}"

    body = f"""
    📥 تفاصيل طلب الإقامة:
    --------------------------------------------------
    🔹 رقم الموبايل: +90 {phone}
    🔹 نوع الإقامة: {res_label}
    🔹 الحالة الاجتماعية: {marital_label}
                           {spouse_nationality_text}
    🔹 مدة الإقامة: {duration} سنة
    🔹 تاريخ الميلاد: {birth_date}
    🔹 التأمين الصحي: {insurance_status_text}
    --------------------------------------------------
    💰 المبلغ الإجمالي النهائي: {total_price} TL
    --------------------------------------------------
    📂 المستندات والملفات المرفقة:
    """
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    doc_labels = config.get('document_labels', {})
    for field_key, arabic_label in doc_labels.items():
        files = request.files.getlist(field_key)
        for file in files:
            if file and file.filename != '':
                if not allowed_file(file.filename):
                    continue
                try:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(file.read())
                    encoders.encode_base64(part)
                    
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    safe_filename = f"{arabic_label}.{ext}"
                    part.add_header('Content-Disposition', 'attachment', filename=('utf-8', '', safe_filename))
                    
                    msg.attach(part)
                except Exception as e:
                    print(f"خطأ في مرفق {arabic_label}: {e}")

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, SENDER_EMAIL, msg.as_string())
    except Exception as e:
        print(f"خطأ في إرسال الإيميل النهائي: {e}")

    return render_template('success_wait.html', total_price=total_price)

if __name__ == '__main__':
    app.run(debug=False, port=5000)