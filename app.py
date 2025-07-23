import streamlit as st
import json
import hashlib
import os
import re
import datetime
import shutil
from pathlib import Path
import time
from typing import Dict, List, Optional, Tuple
import uuid
from collections import defaultdict
import threading

# Configuration
USERS_FILE = "users.json"
SESSIONS_FILE = "sessions.json"
UPLOAD_DIR = "uploaded_documents"
LOG_DIR = "logs"
BACKUP_DIR = "backups"
MAX_BACKUPS = 5
SESSION_TIMEOUT = 24 * 60 * 60  # 24 hours in seconds

# Create necessary directories
for directory in [UPLOAD_DIR, LOG_DIR, BACKUP_DIR]:
    os.makedirs(directory, exist_ok=True)

# File lock for thread safety
file_lock = threading.Lock()

class DataManager:
    @staticmethod
    def load_json(filename: str, default=None):
        """Load JSON data with error handling"""
        if default is None:
            default = {}
        try:
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            st.error(f"Error loading {filename}: {e}")
        return default
    
    @staticmethod
    def save_json(filename: str, data: dict, create_backup=True):
        """Save JSON data with atomic write and backup"""
        with file_lock:
            try:
                # Create backup if file exists
                if create_backup and os.path.exists(filename):
                    DataManager.create_backup(filename)
                
                # Atomic write
                temp_file = f"{filename}.tmp"
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                # Replace original file
                shutil.move(temp_file, filename)
                return True
            except Exception as e:
                st.error(f"Error saving {filename}: {e}")
                return False
    
    @staticmethod
    def create_backup(filename: str):
        """Create backup with timestamp"""
        if not os.path.exists(filename):
            return
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{Path(filename).stem}_{timestamp}.json"
        backup_path = os.path.join(BACKUP_DIR, backup_name)
        
        try:
            shutil.copy2(filename, backup_path)
            DataManager.cleanup_old_backups(Path(filename).stem)
        except Exception as e:
            st.error(f"Backup creation failed: {e}")
    
    @staticmethod
    def cleanup_old_backups(file_prefix: str):
        """Keep only the latest MAX_BACKUPS backups"""
        try:
            backup_files = [f for f in os.listdir(BACKUP_DIR) if f.startswith(file_prefix)]
            backup_files.sort(reverse=True)
            
            for old_backup in backup_files[MAX_BACKUPS:]:
                os.remove(os.path.join(BACKUP_DIR, old_backup))
        except Exception as e:
            st.error(f"Backup cleanup failed: {e}")

class Validator:
    @staticmethod
    def validate_thai_name(name: str) -> Tuple[bool, str]:
        """Validate Thai name format"""
        if not name or len(name.strip()) < 2:
            return False, "ชื่อต้องมีอย่างน้อย 2 ตัวอักษร"
        
        # Allow Thai characters, English characters, and spaces
        thai_pattern = r'^[ก-๙a-zA-Z\s]+$'
        if not re.match(thai_pattern, name.strip()):
            return False, "ชื่อสามารถใช้ได้เฉพาะตัวอักษรไทยและอังกฤษเท่านั้น"
        
        return True, ""
    
    @staticmethod
    def validate_email(email: str) -> Tuple[bool, str]:
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, email):
            return False, "รูปแบบอีเมลไม่ถูกต้อง"
        return True, ""
    
    @staticmethod
    def validate_phone(phone: str) -> Tuple[bool, str]:
        """Validate Thai phone number"""
        # Remove spaces and dashes
        phone = re.sub(r'[\s-]', '', phone)
        
        # Thai mobile patterns
        if not re.match(r'^(06|08|09)\d{8}$', phone):
            return False, "หมายเลขโทรศัพท์ต้องเป็นเลข 10 หลัก เริ่มต้นด้วย 06, 08, หรือ 09"
        
        return True, ""
    
    @staticmethod
    def validate_citizen_id(citizen_id: str) -> Tuple[bool, str]:
        """Validate Thai citizen ID with checksum"""
        # Remove spaces and dashes
        citizen_id = re.sub(r'[\s-]', '', citizen_id)
        
        if not re.match(r'^\d{13}$', citizen_id):
            return False, "เลขบัตรประชาชนต้องเป็นตัวเลข 13 หลัก"
        
        # Checksum validation
        digits = [int(d) for d in citizen_id[:12]]
        checksum = sum(d * (13 - i) for i, d in enumerate(digits)) % 11
        check_digit = (11 - checksum) % 10
        
        if check_digit != int(citizen_id[12]):
            return False, "เลขบัตรประชาชนไม่ถูกต้อง"
        
        return True, ""
    
    @staticmethod
    def validate_gpax(gpax: str) -> Tuple[bool, str]:
        """Validate GPAX score"""
        try:
            score = float(gpax)
            if not (0.0 <= score <= 4.0):
                return False, "เกรดเฉลี่ยต้องอยู่ระหว่าง 0.00 - 4.00"
            return True, ""
        except ValueError:
            return False, "เกรดเฉลี่ยต้องเป็นตัวเลข"

class AuthManager:
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using SHA-256"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    @staticmethod
    def create_session(username: str) -> str:
        """Create new session"""
        session_id = str(uuid.uuid4())
        sessions = DataManager.load_json(SESSIONS_FILE, {})
        
        sessions[session_id] = {
            'username': username,
            'created_at': datetime.datetime.now().isoformat(),
            'expires_at': (datetime.datetime.now() + datetime.timedelta(seconds=SESSION_TIMEOUT)).isoformat()
        }
        
        DataManager.save_json(SESSIONS_FILE, sessions)
        return session_id
    
    @staticmethod
    def validate_session(session_id: str) -> Optional[str]:
        """Validate session and return username if valid"""
        if not session_id:
            return None
        
        sessions = DataManager.load_json(SESSIONS_FILE, {})
        session = sessions.get(session_id)
        
        if not session:
            return None
        
        # Check expiry
        expires_at = datetime.datetime.fromisoformat(session['expires_at'])
        if datetime.datetime.now() > expires_at:
            # Remove expired session
            del sessions[session_id]
            DataManager.save_json(SESSIONS_FILE, sessions)
            return None
        
        return session['username']
    
    @staticmethod
    def logout(session_id: str):
        """Remove session"""
        if not session_id:
            return
        
        sessions = DataManager.load_json(SESSIONS_FILE, {})
        if session_id in sessions:
            del sessions[session_id]
            DataManager.save_json(SESSIONS_FILE, sessions)

class UserManager:
    @staticmethod
    def check_duplicate(field: str, value: str, exclude_username: str = None) -> bool:
        """Check if value already exists for given field"""
        users = DataManager.load_json(USERS_FILE, {})
        
        for username, user_data in users.items():
            if exclude_username and username == exclude_username:
                continue
            if user_data.get(field) == value:
                return True
        return False
    
    @staticmethod
    def register_user(user_data: dict) -> Tuple[bool, str]:
        """Register new user"""
        users = DataManager.load_json(USERS_FILE, {})
        
        # Check duplicates
        duplicate_checks = [
            ('username', 'ชื่อผู้ใช้'),
            ('email', 'อีเมล'),
            ('phone', 'หมายเลขโทรศัพท์'),
            ('citizen_id', 'เลขบัตรประชาชน')
        ]
        
        for field, field_name in duplicate_checks:
            if UserManager.check_duplicate(field, user_data[field]):
                return False, f"{field_name}นี้ถูกใช้งานแล้ว"
        
        # Hash password
        user_data['password'] = AuthManager.hash_password(user_data['password'])
        user_data['created_at'] = datetime.datetime.now().isoformat()
        user_data['role'] = 'user'
        
        # Save user
        users[user_data['username']] = user_data
        
        if DataManager.save_json(USERS_FILE, users):
            # Log registration
            log_entry = f"{datetime.datetime.now().isoformat()} - User registered: {user_data['username']}\n"
            with open(os.path.join(LOG_DIR, 'user_changes.log'), 'a', encoding='utf-8') as f:
                f.write(log_entry)
            return True, "ลงทะเบียนสำเร็จ"
        
        return False, "เกิดข้อผิดพลาดในการบันทึกข้อมูล"
    
    @staticmethod
    def authenticate(username: str, password: str) -> Tuple[bool, str, dict]:
        """Authenticate user"""
        users = DataManager.load_json(USERS_FILE, {})
        
        if username not in users:
            return False, "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", {}
        
        user = users[username]
        hashed_password = AuthManager.hash_password(password)
        
        if user['password'] != hashed_password:
            return False, "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", {}
        
        return True, "เข้าสู่ระบบสำเร็จ", user
    
    @staticmethod
    def get_user(username: str) -> Optional[dict]:
        """Get user data"""
        users = DataManager.load_json(USERS_FILE, {})
        return users.get(username)
    
    @staticmethod
    def update_user(username: str, updated_data: dict) -> Tuple[bool, str]:
        """Update user data"""
        users = DataManager.load_json(USERS_FILE, {})
        
        if username not in users:
            return False, "ไม่พบผู้ใช้"
        
        # Check duplicates for changed fields
        current_user = users[username]
        duplicate_checks = [('email', 'อีเมล'), ('phone', 'หมายเลขโทรศัพท์')]
        
        for field, field_name in duplicate_checks:
            if field in updated_data and updated_data[field] != current_user.get(field):
                if UserManager.check_duplicate(field, updated_data[field], username):
                    return False, f"{field_name}นี้ถูกใช้งานแล้ว"
        
        # Log changes
        changes = []
        for key, new_value in updated_data.items():
            if key != 'password' and current_user.get(key) != new_value:
                changes.append(f"{key}: {current_user.get(key)} -> {new_value}")
        
        # Update user data
        users[username].update(updated_data)
        users[username]['updated_at'] = datetime.datetime.now().isoformat()
        
        if DataManager.save_json(USERS_FILE, users):
            # Log profile changes
            if changes:
                log_entry = f"{datetime.datetime.now().isoformat()} - Profile updated for {username}: {'; '.join(changes)}\n"
                with open(os.path.join(LOG_DIR, 'profile_changes.log'), 'a', encoding='utf-8') as f:
                    f.write(log_entry)
            return True, "อัพเดทข้อมูลสำเร็จ"
        
        return False, "เกิดข้อผิดพลาดในการบันทึกข้อมูล"

def init_admin_user():
    """Initialize admin user if not exists"""
    users = DataManager.load_json(USERS_FILE, {})
    
    if 'admin' not in users:
        admin_data = {
            'username': 'admin',
            'password': AuthManager.hash_password('admin123'),
            'role': 'admin',
            'first_name': 'ผู้ดูแล',
            'last_name': 'ระบบ',
            'email': 'admin@university.ac.th',
            'phone': '0800000000',
            'citizen_id': '1234567890123',
            'created_at': datetime.datetime.now().isoformat()
        }
        users['admin'] = admin_data
        DataManager.save_json(USERS_FILE, users)

# Initialize admin user
init_admin_user()

# Streamlit app configuration
st.set_page_config(
    page_title="ระบบอัพโหลดเอกสารสมัครเรียน",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
.main-header {
    text-align: center;
    padding: 1rem;
    background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%);
    color: white;
    border-radius: 10px;
    margin-bottom: 2rem;
}

.form-container {
    background: #f8f9fa;
    padding: 2rem;
    border-radius: 10px;
    border: 1px solid #dee2e6;
}

.success-message {
    padding: 1rem;
    background: #d4edda;
    border: 1px solid #c3e6cb;
    border-radius: 5px;
    color: #155724;
}

.error-message {
    padding: 1rem;
    background: #f8d7da;
    border: 1px solid #f5c6cb;
    border-radius: 5px;
    color: #721c24;
}

.info-box {
    padding: 1rem;
    background: #e2e3e5;
    border-radius: 5px;
    margin: 1rem 0;
}
</style>
""", unsafe_allow_html=True)

# Header
st.markdown("""
<div class="main-header">
    <h1>🏛️ ระบบอัพโหลดเอกสารสมัครเรียน</h1>
    <h3>มหาวิทยาลัยตัวอย่าง</h3>
</div>
""", unsafe_allow_html=True)

# Session management with URL parameter persistence
# Check for session_id in URL parameters first
query_params = st.query_params
session_id_from_url = query_params.get('session_id', None)

if 'session_id' not in st.session_state:
    st.session_state.session_id = session_id_from_url

if 'current_user' not in st.session_state:
    st.session_state.current_user = None

# If we have a session_id from URL but not in session_state, use it
if session_id_from_url and not st.session_state.session_id:
    st.session_state.session_id = session_id_from_url

# Validate current session
if st.session_state.session_id:
    username = AuthManager.validate_session(st.session_state.session_id)
    if username:
        st.session_state.current_user = UserManager.get_user(username)
        # Update URL with session_id to persist across refreshes
        if 'session_id' not in query_params or query_params['session_id'] != st.session_state.session_id:
            st.query_params['session_id'] = st.session_state.session_id
    else:
        st.session_state.session_id = None
        st.session_state.current_user = None
        # Remove session_id from URL if invalid
        if 'session_id' in query_params:
            del st.query_params['session_id']

# Main application logic
if not st.session_state.current_user:
    # Login/Register page
    tab1, tab2 = st.tabs(["เข้าสู่ระบบ", "ลงทะเบียน"])
    
    with tab1:
        st.markdown('<div class="form-container">', unsafe_allow_html=True)
        st.subheader("🔐 เข้าสู่ระบบ")
        
        with st.form("login_form"):
            username = st.text_input("ชื่อผู้ใช้")
            password = st.text_input("รหัสผ่าน", type="password")
            submit = st.form_submit_button("เข้าสู่ระบบ", use_container_width=True)
            
            if submit:
                if username and password:
                    success, message, user_data = UserManager.authenticate(username, password)
                    if success:
                        session_id = AuthManager.create_session(username)
                        st.session_state.session_id = session_id
                        st.session_state.current_user = user_data
                        # Set session_id in URL to persist across refreshes
                        st.query_params['session_id'] = session_id
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
                else:
                    st.error("กรุณากรอกชื่อผู้ใช้และรหัสผ่าน")
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Admin info
        with st.expander("ℹ️ ข้อมูลสำหรับผู้ดูแลระบบ"):
            st.info("ชื่อผู้ใช้: admin | รหัสผ่าน: admin123")
    
    with tab2:
        st.markdown('<div class="form-container">', unsafe_allow_html=True)
        st.subheader("📝 ลงทะเบียนผู้ใช้ใหม่")
        
        with st.form("register_form"):
            st.markdown("### ข้อมูลผู้สมัคร")
            
            col1, col2 = st.columns([1, 2])
            with col1:
                title = st.selectbox("คำนำหน้า *", ["นาย", "นางสาว", "นาง"])
            with col2:
                name_col1, name_col2 = st.columns(2)
                with name_col1:
                    first_name = st.text_input("ชื่อ *")
                with name_col2:
                    last_name = st.text_input("นามสกุล *")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**ข้อมูลส่วนตัว**")
                citizen_id = st.text_input("เลขบัตรประชาชน *", max_chars=13)
                phone = st.text_input("เบอร์โทรศัพท์ *", max_chars=10)
                email = st.text_input("อีเมล *")
                
                st.markdown("**ข้อมูลการศึกษา**")
                school_name = st.text_input("ชื่อโรงเรียน *")
                gpax = st.text_input("เกรดเฉลี่ย (GPAX) *", max_chars=4)
                graduation_year = st.selectbox("ปีที่จบการศึกษา *", 
                                             options=list(range(2020, 2030)))
            
            with col2:
                st.markdown("**ข้อมูลเข้าสู่ระบบ**")
                username = st.text_input("ชื่อผู้ใช้ *")
                password = st.text_input("รหัสผ่าน *", type="password")
                confirm_password = st.text_input("ยืนยันรหัสผ่าน *", type="password")
                
                st.markdown("**ข้อมูลเพิ่มเติม**")
                address = st.text_area("ที่อยู่")
                parent_name = st.text_input("ชื่อผู้ปกครอง")
                parent_phone = st.text_input("เบอร์ผู้ปกครอง")
                

            
            submit = st.form_submit_button("ลงทะเบียน", use_container_width=True)
            
            if submit:
                # Validation
                errors = []
                
                # Required fields
                required_fields = {
                    'title': title,
                    'first_name': first_name,
                    'last_name': last_name,
                    'citizen_id': citizen_id,
                    'phone': phone,
                    'email': email,
                    'school_name': school_name,
                    'gpax': gpax,
                    'username': username,
                    'password': password
                }
                
                for field, value in required_fields.items():
                    if not value or not value.strip():
                        errors.append("กรุณากรอกข้อมูลที่จำเป็นให้ครบถ้วน")
                        break
                
                # Password confirmation
                if password != confirm_password:
                    errors.append("รหัสผ่านไม่ตรงกัน")
                
                # Field validations
                if not errors:
                    validations = [
                        Validator.validate_thai_name(first_name),
                        Validator.validate_thai_name(last_name),
                        Validator.validate_email(email),
                        Validator.validate_phone(phone),
                        Validator.validate_citizen_id(citizen_id),
                        Validator.validate_gpax(gpax)
                    ]
                    
                    for is_valid, error_msg in validations:
                        if not is_valid:
                            errors.append(error_msg)
                
                if errors:
                    for error in errors:
                        st.error(error)
                else:
                    # Register user
                    user_data = {
                        'username': username,
                        'password': password,
                        'title': title,
                        'first_name': first_name,
                        'last_name': last_name,
                        'citizen_id': citizen_id,
                        'phone': phone,
                        'email': email,
                        'school_name': school_name,
                        'gpax': float(gpax),
                        'graduation_year': graduation_year,
                        'address': address,
                        'parent_name': parent_name,
                        'parent_phone': parent_phone
                    }
                    
                    success, message = UserManager.register_user(user_data)
                    if success:
                        st.success(message)
                        st.info("กรุณาเข้าสู่ระบบด้วยชื่อผู้ใช้และรหัสผ่านที่ลงทะเบียน")
                    else:
                        st.error(message)
        
        st.markdown('</div>', unsafe_allow_html=True)

else:
    # Main application for logged-in users
    user = st.session_state.current_user
    
    # Sidebar
    with st.sidebar:
        title_prefix = user.get('title', '')
        full_name = f"{title_prefix}{user['first_name']} {user['last_name']}" if title_prefix else f"{user['first_name']} {user['last_name']}"
        st.markdown(f"### สวัสดี, {full_name}")
        st.markdown(f"**บทบาท:** {user['role']}")
        
        if st.button("🚪 ออกจากระบบ", use_container_width=True):
            AuthManager.logout(st.session_state.session_id)
            st.session_state.session_id = None
            st.session_state.current_user = None
            # Remove session_id from URL on logout
            if 'session_id' in st.query_params:
                del st.query_params['session_id']
            st.rerun()
    
    # Main content based on user role
    if user['role'] == 'admin':
        # Admin interface
        tab1, tab2, tab3, tab4 = st.tabs(["📊 รายงานระบบ", "👥 จัดการผู้ใช้", "📁 จัดการเอกสาร", "⚙️ ตั้งค่า"])
        
        with tab1:
            st.subheader("📊 รายงานสถานะระบบ")
            
            # System health check
            col1, col2, col3 = st.columns(3)
            
            with col1:
                users = DataManager.load_json(USERS_FILE, {})
                st.metric("จำนวนผู้ใช้ทั้งหมด", len(users))
            
            with col2:
                if os.path.exists(UPLOAD_DIR):
                    files = [f for f in os.listdir(UPLOAD_DIR) if os.path.isfile(os.path.join(UPLOAD_DIR, f))]
                    st.metric("จำนวนไฟล์ที่อัพโหลด", len(files))
                else:
                    st.metric("จำนวนไฟล์ที่อัพโหลด", 0)
            
            with col3:
                sessions = DataManager.load_json(SESSIONS_FILE, {})
                active_sessions = 0
                now = datetime.datetime.now()
                for session in sessions.values():
                    expires_at = datetime.datetime.fromisoformat(session['expires_at'])
                    if now < expires_at:
                        active_sessions += 1
                st.metric("เซสชันที่ใช้งานอยู่", active_sessions)
            
            # Recent activities
            st.subheader("กิจกรรมล่าสุด")
            
            # User changes log
            user_log_path = os.path.join(LOG_DIR, 'user_changes.log')
            if os.path.exists(user_log_path):
                with open(user_log_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    recent_lines = lines[-10:] if len(lines) > 10 else lines
                    if recent_lines:
                        st.text("\n".join(recent_lines))
                    else:
                        st.info("ไม่มีกิจกรรมล่าสุด")
            else:
                st.info("ไม่มีกิจกรรมล่าสุด")
        
        with tab2:
            st.subheader("👥 จัดการผู้ใช้")
            
            users = DataManager.load_json(USERS_FILE, {})
            
            if users:
                # Filter out admin users
                regular_users = {k: v for k, v in users.items() if k != 'admin'}
                
                if regular_users:
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"**จำนวนผู้ใช้ทั้งหมด: {len(regular_users)} คน**")
                    with col2:
                        # Export to CSV button
                        if st.button("📊 ส่งออกข้อมูล CSV", use_container_width=True):
                            import pandas as pd
                            from io import StringIO
                            
                            # Prepare data for CSV
                            csv_data = []
                            for username, data in regular_users.items():
                                csv_data.append({
                                    'ชื่อผู้ใช้': username,
                                    'คำนำหน้า': data.get('title', ''),
                                    'ชื่อ': data.get('first_name', ''),
                                    'นามสกุล': data.get('last_name', ''),
                                    'เลขบัตรประชาชน': data.get('citizen_id', ''),
                                    'โทรศัพท์': data.get('phone', ''),
                                    'อีเมล': data.get('email', ''),
                                    'ที่อยู่': data.get('address', ''),
                                    'โรงเรียน': data.get('school_name', ''),
                                    'GPAX': data.get('gpax', ''),
                                    'ปีที่จบ': data.get('graduation_year', ''),
                                    'ชื่อผู้ปกครอง': data.get('parent_name', ''),
                                    'โทรศัพท์ผู้ปกครอง': data.get('parent_phone', ''),
                                    'วันที่ลงทะเบียน': data.get('created_at', '')[:10] if data.get('created_at') else ''
                                })
                            
                            # Create DataFrame and convert to CSV
                            df = pd.DataFrame(csv_data)
                            csv_string = df.to_csv(index=False, encoding='utf-8-sig')
                            
                            # Download button
                            st.download_button(
                                label="💾 ดาวน์โหลดไฟล์ CSV",
                                data=csv_string,
                                file_name=f"users_data_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                mime="text/csv",
                                use_container_width=True
                            )
                    
                    # Display each user with detailed information
                    for username, data in regular_users.items():
                        with st.expander(f"👤 {data.get('title', '')}{data.get('first_name', '')} {data.get('last_name', '')} ({username})"):
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                st.markdown("**ข้อมูลส่วนตัว**")
                                st.write(f"**คำนำหน้า:** {data.get('title', 'ไม่ระบุ')}")
                                st.write(f"**ชื่อ:** {data.get('first_name', 'ไม่ระบุ')}")
                                st.write(f"**นามสกุล:** {data.get('last_name', 'ไม่ระบุ')}")
                                st.write(f"**เลขบัตรประชาชน:** {data.get('citizen_id', 'ไม่ระบุ')}")
                                st.write(f"**โทรศัพท์:** {data.get('phone', 'ไม่ระบุ')}")
                                st.write(f"**อีเมล:** {data.get('email', 'ไม่ระบุ')}")
                                st.write(f"**ที่อยู่:** {data.get('address', 'ไม่ระบุ')}")
                            
                            with col2:
                                st.markdown("**ข้อมูลการศึกษา**")
                                st.write(f"**โรงเรียน:** {data.get('school_name', 'ไม่ระบุ')}")
                                st.write(f"**GPAX:** {data.get('gpax', 'ไม่ระบุ')}")
                                st.write(f"**ปีที่จบ:** {data.get('graduation_year', 'ไม่ระบุ')}")
                                st.write(f"**ผู้ปกครอง:** {data.get('parent_name', 'ไม่ระบุ')}")
                                st.write(f"**โทรศัพท์ผู้ปกครอง:** {data.get('parent_phone', 'ไม่ระบุ')}")
                            
                            # Document viewing section
                            st.markdown("**เอกสารที่อัพโหลด**")
                            citizen_id = data.get('citizen_id', '')
                            
                            if os.path.exists(UPLOAD_DIR) and citizen_id:
                                # Find files for this user
                                user_files = []
                                for filename in os.listdir(UPLOAD_DIR):
                                    if filename.startswith(citizen_id):
                                        user_files.append(filename)
                                
                                if user_files:
                                    st.write(f"พบเอกสาร {len(user_files)} ไฟล์")
                                    
                                    # Display files in columns
                                    file_cols = st.columns(min(len(user_files), 3))
                                    for i, filename in enumerate(user_files):
                                        with file_cols[i % 3]:
                                            # Parse document type from filename
                                            parts = filename.split('_')
                                            doc_type = parts[2].split('.')[0] if len(parts) > 2 else 'ไม่ทราบ'
                                            
                                            st.write(f"📄 {doc_type}")
                                            
                                            # Download button
                                            file_path = os.path.join(UPLOAD_DIR, filename)
                                            with open(file_path, 'rb') as f:
                                                st.download_button(
                                                    "📥 ดาวน์โหลด",
                                                    f.read(),
                                                    file_name=filename,
                                                    key=f"download_{username}_{i}"
                                                )
                                            
                                            # Preview button for images
                                            if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                                                if st.button(f"👁️ ดูตัวอย่าง", key=f"preview_{username}_{i}"):
                                                    st.image(file_path, caption=doc_type, width=300)
                                else:
                                    st.info("ยังไม่มีเอกสารที่อัพโหลด")
                            else:
                                st.info("ยังไม่มีเอกสารที่อัพโหลด")
                else:
                    st.info("ไม่มีผู้ใช้ในระบบ")
            else:
                st.info("ไม่มีผู้ใช้ในระบบ")
        
        with tab3:
            st.subheader("📁 จัดการเอกสาร")
            
            if os.path.exists(UPLOAD_DIR):
                files = [f for f in os.listdir(UPLOAD_DIR) if os.path.isfile(os.path.join(UPLOAD_DIR, f))]
                
                if files:
                    file_data = []
                    for filename in files:
                        file_path = os.path.join(UPLOAD_DIR, filename)
                        stat = os.stat(file_path)
                        
                        # Parse filename for student info
                        parts = filename.split('_')
                        citizen_id = parts[0] if len(parts) > 0 else 'ไม่ทราบ'
                        student_name = parts[1] if len(parts) > 1 else 'ไม่ทราบ'
                        doc_type = parts[2].split('.')[0] if len(parts) > 2 else 'ไม่ทราบ'
                        
                        file_data.append({
                            'ชื่อไฟล์': filename,
                            'ชื่อนักเรียน': student_name.replace('-', ' '),
                            'เลขบัตรประชาชน': citizen_id,
                            'ประเภทเอกสาร': doc_type,
                            'ขนาด (KB)': round(stat.st_size / 1024, 2),
                            'วันที่อัพโหลด': datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
                        })
                    
                    st.dataframe(file_data, use_container_width=True)
                    
                    # File preview
                    selected_file = st.selectbox("เลือกไฟล์เพื่อดูตัวอย่าง", files)
                    if selected_file:
                        file_path = os.path.join(UPLOAD_DIR, selected_file)
                        
                        col1, col2 = st.columns([3, 1])
                        with col2:
                            with open(file_path, 'rb') as f:
                                st.download_button(
                                    "📥 ดาวน์โหลด",
                                    f.read(),
                                    file_name=selected_file,
                                    use_container_width=True
                                )
                        
                        with col1:
                            # Preview based on file type
                            if selected_file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                                st.image(file_path, caption=selected_file)
                            elif selected_file.lower().endswith('.pdf'):
                                st.markdown(f"**PDF File:** {selected_file}")
                                # Note: PDF preview would require additional libraries
                                st.info("ใช้ปุ่มดาวน์โหลดเพื่อดู PDF")
                            else:
                                st.info(f"ไฟล์: {selected_file} (ใช้ปุ่มดาวน์โหลดเพื่อดูไฟล์)")
                else:
                    st.info("ไม่มีไฟล์ที่อัพโหลด")
            else:
                st.info("ไม่มีโฟลเดอร์เอกสาร")
        
        with tab4:
            st.subheader("⚙️ ตั้งค่าระบบ")
            
            # Backup management
            st.markdown("**การจัดการสำรองข้อมูล**")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("สำรองข้อมูลผู้ใช้", use_container_width=True):
                    DataManager.create_backup(USERS_FILE)
                    st.success("สำรองข้อมูลผู้ใช้เรียบร้อย")
            
            with col2:
                if st.button("สำรองข้อมูลเซสชัน", use_container_width=True):
                    DataManager.create_backup(SESSIONS_FILE)
                    st.success("สำรองข้อมูลเซสชันเรียบร้อย")
            
            # Show backup files
            if os.path.exists(BACKUP_DIR):
                backup_files = os.listdir(BACKUP_DIR)
                if backup_files:
                    st.markdown("**ไฟล์สำรองข้อมูล**")
                    for backup_file in sorted(backup_files, reverse=True):
                        st.text(backup_file)
                else:
                    st.info("ไม่มีไฟล์สำรองข้อมูล")
    
    else:
        # Regular user interface
        tab1, tab2, tab3 = st.tabs(["📤 อัพโหลดเอกสาร", "📋 เอกสารของฉัน", "👤 ข้อมูลส่วนตัว"])
        
        with tab1:
            st.subheader("📤 อัปโหลดเอกสารของคุณ")
            st.markdown("กรุณากรอกข้อมูลที่จำเป็นและอัปโหลดเอกสารของคุณ")
            
            st.markdown('<div class="form-container">', unsafe_allow_html=True)
            
            # User Information Section
            st.markdown("### ข้อมูลผู้สมัคร")
            
            col1, col2 = st.columns([1, 3])
            with col1:
                st.markdown("**คำนำหน้า:**")
                st.write(user.get('title', 'ไม่ระบุ'))
            with col2:
                st.markdown("**ชื่อ-สกุล:**")
                full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}"
                st.write(full_name)

            # Class Schedule Section for Cyber Security
            st.markdown("### เลือกตารางเรียน")
            st.markdown("ถ้าเรียนหลักสูตร Cyber Security ให้เลือกวันที่ต้องการเรียน (ถ้าไม่ได้เรียนให้เลือกไม่เรียน)*")
            
            # Radio buttons for class schedule
            schedule_options = [
                "ไม่เรียน",
                "เรียน จันทร์ - ศุกร์ (วันธรรมดา)",
                "เรียน เสาร์ - อาทิตย์ (วันหยุด)"
            ]
            
            selected_schedule = st.radio(
                "ถ้าเรียนหลักสูตร Cyber Security ให้เลือกวันที่ต้องการเรียน (ถ้าไม่ได้เรียนให้เลือกไม่เรียน)*",
                schedule_options,
                index=0,
                key="user_schedule_selection",
                label_visibility="collapsed"
            )
            
            st.markdown("---")
            
            # Required Documents Section
            st.markdown("### Required Documents")
            st.markdown("กรุณาอัปโหลดเอกสารที่จำเป็นทั้งหมดในรูปแบบที่ถูกต้อง (PDF, JPG, PNG)")
            st.markdown("---")
            
            # Document upload form with specific required documents
            with st.form("upload_form"):
                # 1. รูปถ่าย
                st.markdown("#### 1. รูปถ่าย *")
                photo_file = st.file_uploader(
                    "อัพโหลดรูปถ่าย",
                    type=['jpg', 'jpeg', 'png'],
                    help="Limit 200MB per file • JPG, JPEG, PNG",
                    key="photo_upload"
                )
                
                st.markdown("#### 2. สำเนาบัตรประจำตัวประชาชน *")
                id_card_file = st.file_uploader(
                    "อัพโหลดสำเนาบัตรประจำตัวประชาชน",
                    type=['pdf', 'jpg', 'jpeg', 'png'],
                    help="Limit 200MB per file • PDF, JPG, JPEG, PNG",
                    key="id_card_upload"
                )
                
                st.markdown("#### 3. สำเนาใบแสดงผลการเรียน *")
                transcript_file = st.file_uploader(
                    "อัพโหลดสำเนาใบแสดงผลการเรียน",
                    type=['pdf', 'jpg', 'jpeg', 'png'],
                    help="Limit 200MB per file • PDF, JPG, JPEG, PNG",
                    key="transcript_upload"
                )
                
                st.markdown("#### 4. สำเนาหลักฐานการเปลี่ยนชื่อ-สกุล หรือหลักฐานอื่นๆ (ถ้ามี)")
                other_file = st.file_uploader(
                    "อัพโหลดสำเนาหลักฐานการเปลี่ยนชื่อ-สกุล หรือหลักฐานอื่นๆ",
                    type=['pdf', 'jpg', 'jpeg', 'png'],
                    help="Limit 200MB per file • PDF, JPG, JPEG, PNG",
                    key="other_upload"
                )
                
                submit = st.form_submit_button("อัพโหลดเอกสารทั้งหมด", use_container_width=True)
                
                if submit:
                    # Check required documents
                    required_files = [photo_file, id_card_file, transcript_file]
                    required_names = ["รูปถ่าย", "สำเนาบัตรประจำตัวประชาชน", "สำเนาใบแสดงผลการเรียน"]
                    
                    missing_files = []
                    for i, file in enumerate(required_files):
                        if file is None:
                            missing_files.append(required_names[i])
                    
                    if missing_files:
                        st.error(f"กรุณาอัพโหลดเอกสารที่จำเป็น: {', '.join(missing_files)}")
                    else:
                        # Process all uploaded files
                        uploaded_files = [
                            (photo_file, "รูปถ่าย"),
                            (id_card_file, "สำเนาบัตรประจำตัวประชาชน"),
                            (transcript_file, "สำเนาใบแสดงผลการเรียน")
                        ]
                        
                        # Add optional file if uploaded
                        if other_file is not None:
                            uploaded_files.append((other_file, "หลักฐานการเปลี่ยนชื่อ-สกุล"))
                        
                        success_count = 0
                        error_messages = []
                        
                        for uploaded_file, doc_type in uploaded_files:
                            if uploaded_file is not None:
                                try:
                                    # Generate filename according to convention
                                    file_extension = uploaded_file.name.split('.')[-1]
                                    safe_name = f"{user['first_name']}-{user['last_name']}".replace(' ', '-')
                                    safe_doc_type = doc_type.replace(' ', '-').replace('/', '-')
                                    
                                    filename = f"{user['citizen_id']}_{safe_name}_{safe_doc_type}.{file_extension}"
                                    file_path = os.path.join(UPLOAD_DIR, filename)
                                    
                                    # Check file size (200MB limit)
                                    if uploaded_file.size > 200 * 1024 * 1024:
                                        error_messages.append(f"{doc_type}: ไฟล์มีขนาดเกิน 200MB")
                                        continue
                                    
                                    # Save file
                                    with open(file_path, 'wb') as f:
                                        f.write(uploaded_file.getbuffer())
                                    
                                    success_count += 1
                                    
                                    # Log upload
                                    log_entry = f"{datetime.datetime.now().isoformat()} - File uploaded by {user['username']}: {filename}\n"
                                    with open(os.path.join(LOG_DIR, 'user_changes.log'), 'a', encoding='utf-8') as f:
                                        f.write(log_entry)
                                    
                                except Exception as e:
                                    error_messages.append(f"{doc_type}: {str(e)}")
                        
                        # Show results
                        if success_count > 0:
                            st.success(f"อัพโหลดเอกสารเรียบร้อยแล้ว {success_count} ไฟล์")
                        
                        if error_messages:
                            for error in error_messages:
                                st.error(f"เกิดข้อผิดพลาด: {error}")
            
            st.markdown('</div>', unsafe_allow_html=True)
            
            # Upload guidelines
            with st.expander("📋 คำแนะนำการอัพโหลดเอกสาร"):
                st.markdown("""
                **เอกสารที่ต้องใช้สำหรับการสมัคร:**
                1. **รูปถ่าย*** - รูปถ่ายหน้าตรง ชัดเจน
                2. **สำเนาบัตรประจำตัวประชาชน*** - สำเนาบัตรประชาชนที่ชัดเจน
                3. **สำเนาใบแสดงผลการเรียน*** - ใบแสดงผลการเรียน (ม.6)
                4. **สำเนาหลักฐานการเปลี่ยนชื่อ-สกุล** - เฉพาะกรณีที่มีการเปลี่ยนชื่อ-สกุล
                
                **ข้อกำหนดไฟล์:**
                - ขนาดไฟล์ไม่เกิน 200 MB ต่อไฟล์
                - รองรับไฟล์: PDF, JPG, JPEG, PNG
                - ไฟล์ต้องชัดเจน อ่านได้
                - เอกสารที่มี * เป็นเอกสารที่จำเป็นต้องอัพโหลด
                
                **หมายเหตุ:**
                - ระบบจะตั้งชื่อไฟล์ใหม่ตามรูปแบบมาตรฐาน
                - สามารถอัพโหลดไฟล์เดิมซ้ำได้ (จะเขียนทับไฟล์เก่า)
                - กรุณาตรวจสอบความถูกต้องของเอกสารก่อนอัพโหลด
                """)
        
        with tab2:
            st.subheader("📋 เอกสารของฉัน")
            
            # List user's uploaded files
            if os.path.exists(UPLOAD_DIR):
                user_files = []
                for filename in os.listdir(UPLOAD_DIR):
                    if filename.startswith(user['citizen_id']):
                        file_path = os.path.join(UPLOAD_DIR, filename)
                        if os.path.isfile(file_path):
                            stat = os.stat(file_path)
                            user_files.append({
                                'filename': filename,
                                'path': file_path,
                                'size': stat.st_size,
                                'modified': stat.st_mtime
                            })
                
                if user_files:
                    st.markdown(f"**พบเอกสาร {len(user_files)} ไฟล์**")
                    
                    for file_info in sorted(user_files, key=lambda x: x['modified'], reverse=True):
                        with st.container():
                            col1, col2, col3 = st.columns([3, 1, 1])
                            
                            with col1:
                                # Parse document type from filename
                                parts = file_info['filename'].split('_')
                                doc_type = parts[2].split('.')[0] if len(parts) > 2 else 'ไม่ทราบ'
                                doc_type = doc_type.replace('-', ' ')
                                
                                st.markdown(f"**{doc_type}**")
                                st.caption(f"ขนาด: {round(file_info['size']/1024, 2)} KB | "
                                         f"อัพโหลดเมื่อ: {datetime.datetime.fromtimestamp(file_info['modified']).strftime('%d/%m/%Y %H:%M')}")
                            
                            with col2:
                                # Preview button
                                if st.button("👁️ ดูตัวอย่าง", key=f"preview_{file_info['filename']}"):
                                    st.session_state[f"show_preview_{file_info['filename']}"] = True
                            
                            with col3:
                                # Download button
                                with open(file_info['path'], 'rb') as f:
                                    st.download_button(
                                        "📥 ดาวน์โหลด",
                                        f.read(),
                                        file_name=file_info['filename'],
                                        key=f"download_{file_info['filename']}",
                                        use_container_width=True
                                    )
                            
                            # Show preview if requested
                            if st.session_state.get(f"show_preview_{file_info['filename']}", False):
                                if file_info['filename'].lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                                    st.image(file_info['path'], caption=file_info['filename'], width=400)
                                elif file_info['filename'].lower().endswith('.pdf'):
                                    st.info("📄 ไฟล์ PDF - ใช้ปุ่มดาวน์โหลดเพื่อดูไฟล์")
                                else:
                                    st.info(f"📄 ไฟล์ {file_info['filename']} - ใช้ปุ่มดาวน์โหลดเพื่อดูไฟล์")
                                
                                if st.button("❌ ปิด", key=f"close_{file_info['filename']}"):
                                    st.session_state[f"show_preview_{file_info['filename']}"] = False
                                    st.rerun()
                            
                            st.divider()
                else:
                    st.info("ยังไม่มีเอกสารที่อัพโหลด")
                    st.markdown("กรุณาไปที่แท็บ 'อัพโหลดเอกสาร' เพื่ออัพโหลดเอกสารของคุณ")
            else:
                st.info("ยังไม่มีเอกสารที่อัพโหลด")
        
        with tab3:
            st.subheader("👤 ข้อมูลส่วนตัว")
            
            # Profile view/edit
            col1, col2 = st.columns([2, 1])
            
            with col2:
                edit_mode = st.checkbox("✏️ แก้ไขข้อมูล")
            
            with col1:
                if not edit_mode:
                    # View mode
                    st.markdown('<div class="info-box">', unsafe_allow_html=True)
                    
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.markdown("**ข้อมูลส่วนตัว**")
                        st.text(f"ชื่อ: {user.get('first_name', '')}")
                        st.text(f"นามสกุล: {user.get('last_name', '')}")
                        st.text(f"เลขบัตรประชาชน: {user.get('citizen_id', '')}")
                        st.text(f"โทรศัพท์: {user.get('phone', '')}")
                        st.text(f"อีเมล: {user.get('email', '')}")
                    
                    with col_b:
                        st.markdown("**ข้อมูลการศึกษา**")
                        st.text(f"โรงเรียน: {user.get('school_name', '')}")
                        st.text(f"เกรดเฉลี่ย: {user.get('gpax', '')}")
                        st.text(f"ปีที่จบ: {user.get('graduation_year', '')}")
                        st.text(f"หลักสูตรที่สนใจ: {user.get('program', '')}")
                    
                    if user.get('address'):
                        st.markdown("**ที่อยู่**")
                        st.text(user['address'])
                    
                    if user.get('parent_name') or user.get('parent_phone'):
                        st.markdown("**ข้อมูลผู้ปกครอง**")
                        if user.get('parent_name'):
                            st.text(f"ชื่อผู้ปกครอง: {user['parent_name']}")
                        if user.get('parent_phone'):
                            st.text(f"เบอร์ผู้ปกครอง: {user['parent_phone']}")
                    
                    st.markdown('</div>', unsafe_allow_html=True)
                
                else:
                    # Edit mode
                    st.markdown('<div class="form-container">', unsafe_allow_html=True)
                    
                    with st.form("profile_edit_form"):
                        col_a, col_b = st.columns(2)
                        
                        with col_a:
                            st.markdown("**ข้อมูลส่วนตัว**")
                            new_first_name = st.text_input("ชื่อ", value=user.get('first_name', ''))
                            new_last_name = st.text_input("นามสกุล", value=user.get('last_name', ''))
                            new_phone = st.text_input("โทรศัพท์", value=user.get('phone', ''))
                            new_email = st.text_input("อีเมล", value=user.get('email', ''))
                            
                            st.markdown("**ข้อมูลเพิ่มเติม**")
                            new_address = st.text_area("ที่อยู่", value=user.get('address', ''))
                            new_parent_name = st.text_input("ชื่อผู้ปกครอง", value=user.get('parent_name', ''))
                            new_parent_phone = st.text_input("เบอร์ผู้ปกครอง", value=user.get('parent_phone', ''))
                        
                        with col_b:
                            st.markdown("**ข้อมูลการศึกษา**")
                            new_school_name = st.text_input("โรงเรียน", value=user.get('school_name', ''))
                            new_gpax = st.text_input("เกรดเฉลี่ย", value=str(user.get('gpax', '')))
                            new_graduation_year = st.selectbox(
                                "ปีที่จบการศึกษา",
                                options=list(range(2020, 2030)),
                                index=list(range(2020, 2030)).index(user.get('graduation_year', 2024))
                            )
                            new_program = st.selectbox(
                                "หลักสูตรที่สนใจ",
                                options=[
                                    "วิทยาการคอมพิวเตอร์",
                                    "วิศวกรรมคอมพิวเตอร์",
                                    "เทคโนโลยีสารสนเทศ",
                                    "วิศวกรรมซอฟต์แวร์"
                                ],
                                index=[
                                    "วิทยาการคอมพิวเตอร์",
                                    "วิศวกรรมคอมพิวเตอร์",
                                    "เทคโนโลยีสารสนเทศ",
                                    "วิศวกรรมซอฟต์แวร์"
                                ].index(user.get('program', "วิทยาการคอมพิวเตอร์"))
                            )
                            
                            st.markdown("**เปลี่ยนรหัสผ่าน (ไม่บังคับ)**")
                            new_password = st.text_input("รหัสผ่านใหม่", type="password")
                            confirm_new_password = st.text_input("ยืนยันรหัสผ่านใหม่", type="password")
                        
                        submit_edit = st.form_submit_button("💾 บันทึกการเปลี่ยนแปลง", use_container_width=True)
                        
                        if submit_edit:
                            # Validation
                            errors = []
                            
                            # Validate required fields
                            if not all([new_first_name, new_last_name, new_phone, new_email, new_school_name, new_gpax]):
                                errors.append("กรุณากรอกข้อมูลที่จำเป็นให้ครบถ้วน")
                            
                            # Validate formats
                            if not errors:
                                validations = [
                                    Validator.validate_thai_name(new_first_name),
                                    Validator.validate_thai_name(new_last_name),
                                    Validator.validate_email(new_email),
                                    Validator.validate_phone(new_phone),
                                    Validator.validate_gpax(new_gpax)
                                ]
                                
                                for is_valid, error_msg in validations:
                                    if not is_valid:
                                        errors.append(error_msg)
                            
                            # Password validation
                            if new_password:
                                if new_password != confirm_new_password:
                                    errors.append("รหัสผ่านใหม่ไม่ตรงกัน")
                                elif len(new_password) < 6:
                                    errors.append("รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร")
                            
                            if errors:
                                for error in errors:
                                    st.error(error)
                            else:
                                # Update user data
                                updated_data = {
                                    'first_name': new_first_name,
                                    'last_name': new_last_name,
                                    'phone': new_phone,
                                    'email': new_email,
                                    'school_name': new_school_name,
                                    'gpax': float(new_gpax),
                                    'graduation_year': new_graduation_year,
                                    'program': new_program,
                                    'address': new_address,
                                    'parent_name': new_parent_name,
                                    'parent_phone': new_parent_phone
                                }
                                
                                if new_password:
                                    updated_data['password'] = AuthManager.hash_password(new_password)
                                
                                success, message = UserManager.update_user(user['username'], updated_data)
                                if success:
                                    st.success(message)
                                    # Update session user data
                                    st.session_state.current_user.update(updated_data)
                                    st.rerun()
                                else:
                                    st.error(message)
                    
                    st.markdown('</div>', unsafe_allow_html=True)

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; padding: 1rem;">
    <p>© 2024 มหาวิทยาลัยตัวอย่าง | ระบบอัพโหลดเอกสารสมัครเรียน</p>
    <p>พัฒนาด้วย Streamlit | เวอร์ชัน 1.0</p>
</div>
""", unsafe_allow_html=True)