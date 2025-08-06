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
import base64
import pandas as pd
import io

# Constants
USERS_FILE = "users.json"
SESSIONS_FILE = "sessions.json"
UPLOAD_DIR = "uploaded_documents"
LOG_DIR = "logs"
BACKUP_DIR = "backups"
MESSAGES_FILE = "messages.json"
MAX_BACKUPS = 5
SESSION_TIMEOUT = 24 * 60 * 60  # 24 hours in seconds

# Thai provinces list
THAI_PROVINCES = [
    "กรุงเทพมหานคร", "กระบี่", "กาญจนบุรี", "กาฬสินธุ์", "กำแพงเพชร", "ขอนแก่น", "จันทบุรี", "ฉะเชิงเทรา",
    "ชลบุรี", "ชัยนาท", "ชัยภูมิ", "ชุมพร", "เชียงราย", "เชียงใหม่", "ตรัง", "ตราด", "ตาก", "นครนายก",
    "นครปฐม", "นครพนม", "นครราชสีมา", "นครศรีธรรมราช", "นครสวรรค์", "นนทบุรี", "นราธิวาส", "น่าน",
    "บึงกาฬ", "บุรีรัมย์", "ปทุมธานี", "ประจวบคีรีขันธ์", "ปราจีนบุรี", "ปัตตานี", "พระนครศรีอยุธยา", "พังงา",
    "พัทลุง", "พิจิตร", "พิษณุโลก", "เพชรบุรี", "เพชรบูรณ์", "แพร่", "ภูเก็ต", "มหาสารคาม", "มุกดาหาร",
    "แม่ฮ่องสอน", "ยโสธร", "ยะลา", "ร้อยเอ็ด", "ระนอง", "ระยอง", "ราชบุรี", "ลพบุรี", "ลำปาง", "ลำพูน",
    "เลย", "ศรีสะเกษ", "สกลนคร", "สงขลา", "สตูล", "สมุทรปราการ", "สมุทรสงคราม", "สมุทรสาคร", "สระแก้ว",
    "สระบุรี", "สิงห์บุรี", "สุโขทัย", "สุพรรณบุรี", "สุราษฎร์ธานี", "สุรินทร์", "หนองคาย", "หนองบัวลำภู",
    "อ่างทอง", "อำนาจเจริญ", "อุดรธานี", "อุตรดิตถ์", "อุทัยธานี", "อุบลราชธานี"
]

# Thai title prefixes
THAI_TITLES = [
    "นาย", "นาง", "นางสาว"
]

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
        """Validate Thai citizen ID - check length only"""
        if not citizen_id:
            return False, "กรุณากรอกเลขบัตรประชาชน"
        
        # Remove spaces, dashes, and other non-digit characters
        clean_id = re.sub(r'[^0-9]', '', citizen_id)
        
        # Check if empty after cleaning
        if not clean_id:
            return False, "เลขบัตรประชาชนต้องเป็นตัวเลขเท่านั้น"
        
        # Check length only - must be exactly 13 digits
        if len(clean_id) != 13:
            return False, f"เลขบัตรประชาชนต้องมี 13 หลัก (ปัจจุบัน {len(clean_id)} หลัก)"
        
        return True, ""
    
    @staticmethod
    def validate_citizen_id_with_uniqueness(citizen_id: str, exclude_username: str = None) -> Tuple[bool, str]:
        """Validate Thai citizen ID - check length and uniqueness"""
        # First check basic validation
        is_valid, error_msg = Validator.validate_citizen_id(citizen_id)
        if not is_valid:
            return is_valid, error_msg
        
        # Clean the ID for uniqueness check
        clean_id = re.sub(r'[^0-9]', '', citizen_id)
        
        # Check for duplicates in the system
        if UserManager.check_duplicate('citizen_id', clean_id, exclude_username):
            return False, "เลขบัตรประชาชนนี้มีอยู่ในระบบแล้ว"
        
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
        duplicate_checks = [('email', 'อีเมล'), ('phone', 'หมายเลขโทรศัพท์'), ('citizen_id', 'เลขบัตรประชาชน')]
        
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

class MessageManager:
    @staticmethod
    def send_message(sender_username: str, subject: str, message: str, message_type: str = "general") -> Tuple[bool, str]:
        """Send message to admin"""
        messages = DataManager.load_json(MESSAGES_FILE, [])
        
        message_data = {
            "id": str(uuid.uuid4()),
            "sender_username": sender_username,
            "subject": subject,
            "message": message,
            "message_type": message_type,
            "timestamp": datetime.datetime.now().isoformat(),
            "is_read": False,
            "reply": None,
            "reply_timestamp": None
        }
        
        messages.append(message_data)
        
        if DataManager.save_json(MESSAGES_FILE, messages):
            # Log message
            log_entry = f"{datetime.datetime.now().isoformat()} - Message sent from {sender_username}: {subject}\n"
            with open(os.path.join(LOG_DIR, 'messages.log'), 'a', encoding='utf-8') as f:
                f.write(log_entry)
            return True, "ส่งข้อความสำเร็จ"
        
        return False, "เกิดข้อผิดพลาดในการส่งข้อความ"
    
    @staticmethod
    def get_messages(unread_only: bool = False) -> List[dict]:
        """Get all messages or unread messages only"""
        messages = DataManager.load_json(MESSAGES_FILE, [])
        
        if unread_only:
            return [msg for msg in messages if not msg.get('is_read', False)]
        
        # Sort by timestamp (newest first)
        return sorted(messages, key=lambda x: x.get('timestamp', ''), reverse=True)
    
    @staticmethod
    def mark_as_read(message_id: str) -> bool:
        """Mark message as read"""
        messages = DataManager.load_json(MESSAGES_FILE, [])
        
        for message in messages:
            if message.get('id') == message_id:
                message['is_read'] = True
                return DataManager.save_json(MESSAGES_FILE, messages)
        
        return False
    
    @staticmethod
    def reply_to_message(message_id: str, reply_text: str) -> bool:
        """Reply to a message"""
        messages = DataManager.load_json(MESSAGES_FILE, [])
        
        for message in messages:
            if message.get('id') == message_id:
                message['reply'] = reply_text
                message['reply_timestamp'] = datetime.datetime.now().isoformat()
                message['is_read'] = True
                return DataManager.save_json(MESSAGES_FILE, messages)
        
        return False
    
    @staticmethod
    def delete_message(message_id: str) -> bool:
        """Delete a message"""
        messages = DataManager.load_json(MESSAGES_FILE, [])
        
        messages = [msg for msg in messages if msg.get('id') != message_id]
        
        return DataManager.save_json(MESSAGES_FILE, messages)
    
    @staticmethod
    def get_user_messages(username: str) -> List[dict]:
        """Get messages from specific user"""
        messages = DataManager.load_json(MESSAGES_FILE, [])
        
        user_messages = [msg for msg in messages if msg.get('sender_username') == username]
        
        # Sort by timestamp (newest first)
        return sorted(user_messages, key=lambda x: x.get('timestamp', ''), reverse=True)

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
    page_icon="https://upload.wikimedia.org/wikipedia/th/thumb/b/bb/Informatics_MSU_Logo.svg/1200px-Informatics_MSU_Logo.svg.png",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Thai:wght@100;200;300;400;500;600;700&display=swap" rel="stylesheet">

<style>
/* Global font family */
* {
    font-family: 'IBM Plex Sans Thai', sans-serif !important;
}

body {
    font-family: 'IBM Plex Sans Thai', sans-serif !important;
}

.main-header {
    text-align: center;
    padding: 2rem 1rem;
    background: linear-gradient(135deg, #1e40af 0%, #1e3a8a 50%, #312e81 100%);
    border-radius: 15px;
    margin-bottom: 2rem;
    color: white;
}
.logo-circle {
    width: 80px;
    height: 80px;
    background: rgba(255, 255, 255, 0.2);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0 auto 1rem auto;
    border: 2px solid rgba(255, 255, 255, 0.3);
}
.logo-circle img {
    width: 50px;
    height: 50px;
    border-radius: 50%;
}
.main-header h1 {
    margin: 0.5rem 0;
    font-size: 2rem;
    font-weight: 700;
}
.main-header h3 {
    margin: 0.5rem 0;
    font-size: 1.3rem;
    font-weight: 400;
    opacity: 0.9;
}
.main-header p {
    margin: 1rem 0 0 0;
    font-size: 1rem;
    opacity: 0.8;
}

/* Center container for personal info and edit pages */
.center-container {
    max-width: 900px;
    margin: 0 auto;
    padding: 0 1rem;
}

/* Global animations */
@keyframes slideIn {
    from {
        opacity: 0;
        transform: translateY(-20px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

@keyframes rotate {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}

@keyframes pulse {
    0% { transform: scale(1); }
    50% { transform: scale(1.05); }
    100% { transform: scale(1); }
}

@keyframes float {
    0%, 100% { transform: translateY(0px); }
    50% { transform: translateY(-10px); }
}

/* Action button styling */
.action-button {
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    transform: translateY(0);
}

.action-button:hover {
    transform: translateY(-3px);
    box-shadow: 0 10px 25px rgba(0,0,0,0.2);
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

/* Enhanced file uploader styling */
.stFileUploader > div > div > div > div {
    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
    border: 2px dashed #1e40af;
    border-radius: 15px;
    padding: 2rem;
    transition: all 0.3s ease;
}

.stFileUploader > div > div > div > div:hover {
    border-color: #1e3a8a;
    background: linear-gradient(135deg, #bfdbfe 0%, #60a5fa 100%);
    transform: translateY(-2px);
    box-shadow: 0 8px 25px rgba(0,123,255,0.15);
}

/* Radio button styling */
.stRadio > div {
    background: #f8f9fa;
    padding: 1rem;
    border-radius: 10px;
    border: 1px solid #e9ecef;
}

.stRadio > div > label {
    background: white;
    padding: 0.8rem 1.2rem;
    margin: 0.3rem 0;
    border-radius: 8px;
    border: 1px solid #dee2e6;
    transition: all 0.2s ease;
    cursor: pointer;
}

.stRadio > div > label:hover {
    background: #bfdbfe;
    border-color: #1e40af;
    transform: translateX(5px);
}

/* Form submit button enhancement */
.stFormSubmitButton > button {
    background: linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%);
    border: none;
    border-radius: 12px;
    padding: 1rem 2rem;
    font-size: 1.1rem;
    font-weight: 600;
    color: white;
    transition: all 0.3s ease;
    box-shadow: 0 4px 15px rgba(0,123,255,0.3);
}

.stFormSubmitButton > button:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 25px rgba(0,123,255,0.4);
    background: linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%);
}

/* Tab styling enhancement */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    background: #f8f9fa;
    padding: 0.5rem;
    border-radius: 15px;
    margin-bottom: 2rem;
}

.stTabs [data-baseweb="tab"] {
    background: white;
    border-radius: 10px;
    padding: 0.8rem 1.5rem;
    border: 1px solid #e9ecef;
    transition: all 0.3s ease;
}

.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%);
    color: white;
    border-color: #1e40af;
    box-shadow: 0 4px 15px rgba(30,64,175,0.3);
}

/* Smooth animations for all elements */
* {
    transition: all 0.2s ease;
}

/* Custom scrollbar */
::-webkit-scrollbar {
    width: 8px;
}

::-webkit-scrollbar-track {
    background: #f1f1f1;
    border-radius: 10px;
}

::-webkit-scrollbar-thumb {
    background: linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%);
    border-radius: 10px;
}

::-webkit-scrollbar-thumb:hover {
    background: linear-gradient(135deg, #1e3a8a 0%, #1e3a8a 100%);
}

/* Button alignment styling for equal size buttons */
.stButton > button, .stDownloadButton > button {
    height: 40px !important;
    min-height: 40px !important;
    max-height: 40px !important;
    width: 100% !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 0.5rem !important;
    font-size: 1.1rem !important;
    line-height: 1 !important;
    border-radius: 8px !important;
    margin: 0 !important;
    box-sizing: border-box !important;
}

/* Ensure columns have equal height and alignment */
.stColumns > div {
    display: flex !important;
    align-items: stretch !important;
    height: 40px !important;
}

.stColumns > div > div {
    display: flex !important;
    flex-direction: column !important;
    justify-content: center !important;
    height: 100% !important;
}

/* Ensure equal column widths */
.stColumns [data-testid="column"] {
    flex: 1 !important;
    min-width: 0 !important;
}

/* Apply IBM Plex Sans Thai to all Streamlit components */
.stApp, .stApp * {
    font-family: 'IBM Plex Sans Thai', sans-serif !important;
}

.stMarkdown, .stMarkdown * {
    font-family: 'IBM Plex Sans Thai', sans-serif !important;
}

.stText, .stText * {
    font-family: 'IBM Plex Sans Thai', sans-serif !important;
}

.stTextInput > div > div > input {
    font-family: 'IBM Plex Sans Thai', sans-serif !important;
}

.stSelectbox > div > div > div {
    font-family: 'IBM Plex Sans Thai', sans-serif !important;
}

.stButton > button {
    font-family: 'IBM Plex Sans Thai', sans-serif !important;
}

.stRadio > div > label {
    font-family: 'IBM Plex Sans Thai', sans-serif !important;
}

.stTabs [data-baseweb="tab"] {
    font-family: 'IBM Plex Sans Thai', sans-serif !important;
}

h1, h2, h3, h4, h5, h6 {
    font-family: 'IBM Plex Sans Thai', sans-serif !important;
}

p, span, div, label, input, select, textarea {
    font-family: 'IBM Plex Sans Thai', sans-serif !important;
}
</style>
""", unsafe_allow_html=True)

# Simple header with logo
st.markdown("""
<div class="main-header">
    <img src="https://upload.wikimedia.org/wikipedia/th/thumb/b/bb/Informatics_MSU_Logo.svg/1200px-Informatics_MSU_Logo.svg.png" 
         style="width:80px;height:80px;object-fit:cover;margin:0 auto 1rem auto;display:block;" 
         onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
    <div style="width:60px;height:60px;background:white;color:#1e40af;font-weight:bold;font-size:1.2rem;display:none;margin:0 auto 1rem auto;text-align:center;line-height:60px;border-radius:8px;">MSU</div>
    <h1>ระบบอัพโหลดเอกสารสมัครเรียน</h1>
    <h3>มหาวิทยาลัยมหาสารคาม</h3>
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
        
        # ปุ่มลืมรหัสผ่าน
        st.markdown("<br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("ลืมรหัสผ่าน?", use_container_width=True, type="secondary"):
                st.session_state.show_forgot_password = True
                st.rerun()
        
        # ฟอร์มลืมรหัสผ่าน
        if st.session_state.get('show_forgot_password', False):
            st.markdown("---")
            st.markdown("""
            <div style="
                background: #fff3cd;
                border: 1px solid #ffeaa7;
                border-radius: 10px;
                padding: 1.5rem;
                margin: 1rem 0;
            ">
                <h4 style="color: #856404; margin-bottom: 1rem; display: flex; align-items: center;">
                    ขอรีเซ็ตรหัสผ่าน
                </h4>
                <p style="color: #856404; margin: 0;">กรุณากรอกข้อมูลด้านล่างเพื่อส่งคำขอรีเซ็ตรหัสผ่านไปยังผู้ดูแลระบบ</p>
            </div>
            """, unsafe_allow_html=True)
            
            with st.form("forgot_password_form"):
                 st.markdown("**ข้อมูลสำหรับการยืนยันตัวตน**")
                 forgot_username = st.text_input("ชื่อผู้ใช้ *", placeholder="กรอกชื่อผู้ใช้ของคุณ")
                 
                 col1, col2 = st.columns(2)
                 with col1:
                     forgot_first_name = st.text_input("ชื่อ *", placeholder="กรอกชื่อจริง")
                 with col2:
                     forgot_last_name = st.text_input("นามสกุล *", placeholder="กรอกนามสกุล")
                 
                 forgot_citizen_id = st.text_input("เลขบัตรประจำตัวประชาชน *", placeholder="กรอกเลขบัตรประจำตัวประชาชน 13 หลัก", max_chars=13)
                 

                 
                 col1, col2 = st.columns(2)
                 with col1:
                     submit_forgot = st.form_submit_button("ส่งคำขอรีเซ็ตรหัสผ่าน", use_container_width=True)
                 with col2:
                     cancel_forgot = st.form_submit_button("ยกเลิก", use_container_width=True, type="secondary")
                 
                 if submit_forgot:
                     if forgot_username and forgot_first_name and forgot_last_name and forgot_citizen_id:
                         # ตรวจสอบว่าข้อมูลตรงกับที่ลงทะเบียนไว้หรือไม่
                         user_data = UserManager.get_user(forgot_username)
                         if (user_data and 
                             user_data.get('citizen_id') == forgot_citizen_id and 
                             user_data.get('first_name') == forgot_first_name and
                             user_data.get('last_name') == forgot_last_name):
                             # ส่งข้อความไปหา admin
                             subject = f"คำขอรีเซ็ตรหัสผ่าน - {forgot_username}"
                             message_content = f"""ชื่อผู้ใช้: {forgot_username}
ชื่อ: {forgot_first_name}
สกุล: {forgot_last_name}
เลขบัตรประจำตัวประชาชน: {forgot_citizen_id}
ประเภทข้อความ: ลืมรหัสผ่าน
ข้อความ: ผู้ใช้ลืมรหัสผ่าน"""
                             
                             success, msg = MessageManager.send_message(forgot_username, subject, message_content, "password_reset")
                             if success:
                                 st.session_state.password_reset_success = True
                                 st.markdown("""
                                 <div style="
                                     background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                                     color: white;
                                     padding: 2rem;
                                     border-radius: 15px;
                                     text-align: center;
                                     margin: 1.5rem 0;
                                     box-shadow: 0 8px 25px rgba(16, 185, 129, 0.3);
                                     animation: slideIn 0.6s ease-out;
                                     border: 1px solid rgba(255, 255, 255, 0.2);
                                 ">
                                     <div style="
                                         width: 80px;
                                         height: 80px;
                                         background: rgba(255, 255, 255, 0.2);
                                         border-radius: 50%;
                                         margin: 0 auto 1.5rem;
                                         display: flex;
                                         align-items: center;
                                         justify-content: center;
                                         font-size: 2.5rem;
                                         animation: pulse 2s infinite;
                                     ">🔑</div>
                                     <h3 style="
                                         margin: 0 0 1rem 0;
                                         font-size: 1.5rem;
                                         font-weight: 600;
                                         text-shadow: 0 2px 4px rgba(0,0,0,0.1);
                                     ">ส่งคำขอรีเซ็ตรหัสผ่านสำเร็จ!</h3>
                                     <div style="
                                         background: rgba(255, 255, 255, 0.15);
                                         padding: 1.5rem;
                                         border-radius: 12px;
                                         margin: 1rem 0;
                                         backdrop-filter: blur(10px);
                                     ">
                                         <p style="
                                             margin: 0 0 1rem 0;
                                             font-size: 1.1rem;
                                             line-height: 1.6;
                                             opacity: 0.95;
                                         "><strong>รหัสผ่านใหม่ของคุณจะเป็น:</strong><br>
                                         <span style="
                                             font-size: 1.2rem;
                                             font-weight: 600;
                                             color: #fef3c7;
                                             text-shadow: 0 1px 2px rgba(0,0,0,0.2);
                                         ">เลขบัตรประจำตัวประชาชนของคุณ</span></p>
                                         <p style="
                                             margin: 0;
                                             font-size: 1rem;
                                             opacity: 0.9;
                                         ">ผู้ดูแลระบบจะติดต่อกลับภายใน <strong>1-2 วันทำการ</strong></p>
                                     </div>
                                     <div style="
                                         margin-top: 1.5rem;
                                         padding-top: 1rem;
                                         border-top: 1px solid rgba(255, 255, 255, 0.2);
                                         font-size: 0.9rem;
                                         opacity: 0.8;
                                     ">
                                         💡 <em>กรุณาเก็บรักษาข้อมูลนี้ไว้เป็นความลับ</em>
                                     </div>
                                 </div>
                                 """, unsafe_allow_html=True)
                                 # เพิ่มปุ่มปิดให้ผู้ใช้
                                 st.markdown("""
                                 <div style="text-align: center; margin-top: 1rem;">
                                 </div>
                                 """, unsafe_allow_html=True)
                             else:
                                 st.error(f"เกิดข้อผิดพลาด: {msg}")
                         else:
                             st.error("ข้อมูลที่กรอกไม่ตรงกับข้อมูลในระบบ กรุณาตรวจสอบและลองใหม่อีกครั้ง")
                     else:
                         st.error("กรุณากรอกข้อมูลให้ครบถ้วน")
                 
                 if cancel_forgot:
                     st.session_state.show_forgot_password = False
                     st.rerun()
            
            # ปุ่มกลับไปหน้าเข้าสู่ระบบ (นอก form)
            if st.session_state.get('password_reset_success', False):
                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    if st.button("กลับไปหน้าเข้าสู่ระบบ", key="back_to_login", type="primary", use_container_width=True):
                        st.session_state.show_forgot_password = False
                        st.session_state.password_reset_success = False
                        st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
        
    with tab2:
        st.subheader("ลงทะเบียนผู้ใช้ใหม่")
        
        with st.form("register_form"):
            # ส่วนที่ 1: ข้อมูลผู้สมัคร
            with st.container():
                st.markdown("### ข้อมูลผู้สมัคร")
                
                # ชื่อ-นามสกุล
                with st.expander("ชื่อ-นามสกุล", expanded=True):
                    col1, col2 = st.columns([1, 3])
                    with col1:
                        title = st.selectbox("คำนำหน้า *", THAI_TITLES)
                    with col2:
                        name_col1, name_col2 = st.columns(2)
                        with name_col1:
                            first_name = st.text_input("ชื่อ *", placeholder="กรอกชื่อจริง")
                        with name_col2:
                            last_name = st.text_input("นามสกุล *", placeholder="กรอกนามสกุล")
                
                # ข้อมูลส่วนตัว
                with st.expander("ข้อมูลส่วนตัว", expanded=True):
                    col1, col2 = st.columns(2)
                    with col1:
                        citizen_id = st.text_input("เลขบัตรประชาชน *", max_chars=13, placeholder="1234567890123")
                        birth_date = st.date_input("วันเดือนปีเกิด *", 
                                                 min_value=datetime.date(1950, 1, 1),
                                                 max_value=datetime.date.today(),
                                                 value=datetime.date(2000, 1, 1))
                    with col2:
                        phone = st.text_input("เบอร์โทรศัพท์ *", max_chars=10, placeholder="0812345678")
                        email = st.text_input("อีเมล *", placeholder="example@email.com")
                
                # ข้อมูลการศึกษา
                with st.expander("ข้อมูลการศึกษา", expanded=True):
                    col1, col2 = st.columns(2)
                    with col1:
                        school_name = st.text_input("สถาบันการศึกษาที่จบ *", placeholder="สถาบันการศึกษา...")
                        major = st.text_input("สาขาวิชาที่จบ *", placeholder="วิทย์-คณิต...")
                        gpax = st.text_input("เกรดเฉลี่ย (GPAX) *", max_chars=4, placeholder="3.50")
                    with col2:
                        graduation_year = st.selectbox("ปีที่จบการศึกษา *", 
                                                     options=list(range(2020, 2030)))
                
                # ข้อมูลเพิ่มเติม
                with st.expander("ข้อมูลเพิ่มเติม", expanded=True):
                    col1, col2 = st.columns(2)
                    with col1:
                        address = st.text_area("ที่อยู่(ที่สามารถติดต่อได้)", placeholder="บ้านเลขที่ ถนน ตำบล อำเภอ รหัสไปรษณีย์")
                        province = st.selectbox("จังหวัด *", options=[""] + THAI_PROVINCES, index=0)
                    with col2:
                        parent_name = st.text_input("ชื่อผู้ปกครอง", placeholder="ชื่อ-นามสกุล ผู้ปกครอง")
                        parent_phone = st.text_input("เบอร์ผู้ปกครอง", placeholder="0812345678", max_chars=10)
            
            # ส่วนที่ 2: ข้อมูลเข้าสู่ระบบ (แยกออกมาต่างหาก)
            st.markdown("---")
            with st.container():
                st.markdown("### ข้อมูลเข้าสู่ระบบ")
                
                login_col1, login_col2 = st.columns([2, 1])
                with login_col1:
                    with st.container():
                        st.markdown("**สร้างบัญชีผู้ใช้**")
                        username = st.text_input("ชื่อผู้ใช้ *", 
                                                placeholder="ชื่อผู้ใช้ 4-20 ตัวอักษร",
                                                help="ชื่อผู้ใช้ควรมีความยาว 4-20 ตัวอักษร")
                        password = st.text_input("รหัสผ่าน *", 
                                                type="password", 
                                                placeholder="รหัสผ่านอย่างน้อย 6 ตัวอักษร",
                                                help="รหัสผ่านควรมีความยาวอย่างน้อย 6 ตัวอักษร")
                        confirm_password = st.text_input("ยืนยันรหัสผ่าน *", 
                                                        type="password",
                                                        placeholder="กรอกรหัสผ่านอีกครั้ง")
                
                with login_col2:
                    st.info("**คำแนะนำ**\n\nกรุณาจดจำชื่อผู้ใช้และรหัสผ่านไว้สำหรับเข้าสู่ระบบ")
                    
                    with st.expander("ข้อกำหนด"):
                        st.markdown("""
                        **ชื่อผู้ใช้:**
                        • ความยาว 4-20 ตัวอักษร
                        • ใช้ได้เฉพาะตัวอักษรและตัวเลข
                        
                        **รหัสผ่าน:**
                        • ความยาวอย่างน้อย 6 ตัวอักษร
                        • ควรใช้ตัวอักษรและตัวเลขผสมกัน
                        """)
                

            
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
                    'birth_date': birth_date,
                    'phone': phone,
                    'email': email,
                    'school_name': school_name,
                    'major': major,
                    'gpax': gpax,
                    'province': province,
                    'username': username,
                    'password': password
                }
                
                for field, value in required_fields.items():
                    if field == 'birth_date':
                        if not value:
                            errors.append("กรุณากรอกข้อมูลที่จำเป็นให้ครบถ้วน")
                            break
                    elif field == 'graduation_year':
                        if not value:
                            errors.append("กรุณากรอกข้อมูลที่จำเป็นให้ครบถ้วน")
                            break
                    else:
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
                        Validator.validate_citizen_id_with_uniqueness(citizen_id),
                        Validator.validate_gpax(gpax)
                    ]
                    
                    # Validate parent phone if provided
                    if parent_phone and parent_phone.strip():
                        is_valid, error_msg = Validator.validate_phone(parent_phone)
                        if not is_valid:
                            errors.append(f"เบอร์ผู้ปกครอง: {error_msg}")
                    
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
                        'birth_date': birth_date.strftime('%Y-%m-%d'),
                        'phone': phone,
                        'email': email,
                        'school_name': school_name,
                        'major': major,
                        'gpax': round(float(gpax), 2),
                        'graduation_year': graduation_year,
                        'address': address,
                        'province': province,
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
        
        # Message to admin button for regular users
        if user['role'] == 'user':
            st.markdown("---")
            if st.button("ส่งข้อความให้แอดมิน", use_container_width=True):
                st.session_state.show_message_form = True
                st.rerun()
        
        if st.button("ออกจากระบบ", use_container_width=True):
            AuthManager.logout(st.session_state.session_id)
            st.session_state.session_id = None
            st.session_state.current_user = None
            # Remove session_id from URL on logout
            if 'session_id' in st.query_params:
                del st.query_params['session_id']
            st.rerun()
    
    # Main content based on user role
    if user['role'] == 'admin':
        # Admin interface with tabs
        tab1, tab2, tab3 = st.tabs(["อัพโหลดเอกสาร(Admin)", "เอกสารที่อัพโหลด", "จัดการผู้ใช้"])
        
        with tab1:
            # Header Section with Beautiful Styling for Admin
            st.markdown("""
            <div style="
                background: linear-gradient(135deg, #dc3545 0%, #c82333 100%);
                padding: 2.5rem;
                border-radius: 20px;
                color: white;
                margin-bottom: 2rem;
                box-shadow: 0 8px 25px rgba(0,0,0,0.15);
                text-align: center;
            ">
                <div style="
                    width: 100px;
                    height: 100px;
                    background: rgba(255,255,255,0.2);
                    border-radius: 50%;
                    margin: 0 auto 1.5rem;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 3rem;
                    backdrop-filter: blur(10px);
                ">👨‍💼</div>
                <h2 style="margin: 0 0 0.5rem 0; font-size: 2rem; font-weight: 600;">อัพโหลดเอกสาร (Admin)</h2>
                <p style="margin: 0; opacity: 0.9; font-size: 1.1rem;">อัพโหลดเอกสารในฐานะผู้ดูแลระบบ</p>
            </div>
            """, unsafe_allow_html=True)
            

            

            
            with st.form("admin_upload_form"):
                # Student Information Section for Admin
                st.markdown("""
                <div style="
                    background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
                    padding: 2rem;
                    border-radius: 15px;
                    color: white;
                    margin-bottom: 2rem;
                    box-shadow: 0 6px 20px rgba(40, 167, 69, 0.3);
                    text-align: center;
                ">
                    <div style="
                        width: 80px;
                        height: 80px;
                        background: rgba(255,255,255,0.2);
                        border-radius: 50%;
                        margin: 0 auto 1rem;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 2.5rem;
                        backdrop-filter: blur(10px);
                    ">👤</div>
                    <h3 style="margin: 0 0 0.5rem 0; font-size: 1.6rem; font-weight: 600;">ข้อมูลนักเรียน</h3>
                    <p style="margin: 0; opacity: 0.9; font-size: 1rem;">กรุณากรอกข้อมูลนักเรียนที่จะใช้ในการตั้งชื่อไฟล์</p>
                </div>
                """, unsafe_allow_html=True)
                
                # Student information input fields
                # ข้อมูลพื้นฐาน
                with st.expander("ข้อมูลพื้นฐาน", expanded=True):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        student_title = st.selectbox("คำนำหน้า *", options=[""] + THAI_TITLES, index=0)
                    with col2:
                        student_first_name = st.text_input(
                            "ชื่อ *",
                            help="ชื่อจริงของนักเรียน",
                            placeholder="สมชาย"
                        )
                    with col3:
                        student_last_name = st.text_input(
                            "นามสกุล *",
                            help="นามสกุลของนักเรียน",
                            placeholder="ใจดี"
                        )
                
                # ข้อมูลส่วนตัว
                with st.expander("ข้อมูลส่วนตัว", expanded=True):
                    col1, col2 = st.columns(2)
                    with col1:
                        student_citizen_id = st.text_input(
                            "เลขบัตรประชาชน *",
                            max_chars=13,
                            help="เลขบัตรประชาชน 13 หลัก",
                            placeholder="1234567890123"
                        )
                        student_birth_date = st.date_input(
                            "วันเดือนปีเกิด *",
                            min_value=datetime.date(1950, 1, 1),
                            max_value=datetime.date.today(),
                            value=datetime.date(2000, 1, 1)
                        )
                    with col2:
                        student_phone = st.text_input(
                            "เบอร์โทรศัพท์ *",
                            max_chars=10,
                            placeholder="0812345678"
                        )
                        student_email = st.text_input(
                            "อีเมล *",
                            placeholder="example@email.com"
                        )
                
                # ข้อมูลการศึกษา
                with st.expander("ข้อมูลการศึกษา", expanded=True):
                    col1, col2 = st.columns(2)
                    with col1:
                        student_school_name = st.text_input(
                            "สถาบันการศึกษาที่จบ *",
                            placeholder="สถาบันการศึกษา..."
                        )
                        student_major = st.text_input(
                            "สาขาวิชาที่จบ *",
                            placeholder="วิทย์-คณิต..."
                        )
                        student_gpax = st.text_input(
                            "เกรดเฉลี่ย (GPAX) *",
                            max_chars=4,
                            placeholder="3.50"
                        )
                    with col2:
                        student_graduation_year = st.selectbox(
                            "ปีที่จบการศึกษา *",
                            options=list(range(2020, 2030))
                        )
                
                # ข้อมูลเพิ่มเติม
                with st.expander("ข้อมูลเพิ่มเติม", expanded=True):
                    col1, col2 = st.columns(2)
                    with col1:
                        student_address = st.text_area(
                            "ที่อยู่(ที่สามารถติดต่อได้)",
                            placeholder="บ้านเลขที่ ถนน ตำบล อำเภอ รหัสไปรษณีย์"
                        )
                        student_province = st.selectbox(
                            "จังหวัด *",
                            options=[""] + THAI_PROVINCES,
                            index=0
                        )
                    with col2:
                        student_parent_name = st.text_input(
                            "ชื่อผู้ปกครอง",
                            placeholder="ชื่อ-นามสกุล ผู้ปกครอง"
                        )
                        student_parent_phone = st.text_input(
                            "เบอร์ผู้ปกครอง",
                            placeholder="0812345678",
                            max_chars=10
                        )
                
                st.markdown("<br>", unsafe_allow_html=True)
                
                # Document upload sections with beautiful cards for admin
                documents = [
                    {
                        "title": "1. รูปถ่าย",
                        "icon": "",
                        "color": "#dc3545",
                        "key": "admin_photo_upload",
                        "types": ['jpg', 'jpeg', 'png'],
                        "help": "รูปถ่ายหน้าตรง ชัดเจน • JPG, JPEG, PNG • สูงสุด 200MB",
                        "required": True
                    },
                    {
                        "title": "2. สำเนาบัตรประจำตัวประชาชน",
                        "icon": "",
                        "color": "#28a745",
                        "key": "admin_id_card_upload",
                        "types": ['pdf', 'jpg', 'jpeg', 'png'],
                        "help": "สำเนาบัตรประชาชนที่ชัดเจน • PDF, JPG, JPEG, PNG • สูงสุด 200MB",
                        "required": True
                    },
                    {
                        "title": "3. สำเนาใบแสดงผลการเรียน",
                        "icon": "",
                        "color": "#ffc107",
                        "key": "admin_transcript_upload",
                        "types": ['pdf', 'jpg', 'jpeg', 'png'],
                        "help": "ใบแสดงผลการเรียน • PDF, JPG, JPEG, PNG • สูงสุด 200MB",
                        "required": True
                    },
                    {
                        "title": "4. หลักฐานการเปลี่ยนชื่อ-สกุล หรือหลักฐานอื่นๆ",
                        "icon": "",
                        "color": "#6c757d",
                        "key": "admin_other_upload",
                        "types": ['pdf', 'jpg', 'jpeg', 'png'],
                        "help": "เอกสารเพิ่มเติม • PDF, JPG, JPEG, PNG • สูงสุด 200MB",
                        "required": False
                    }
                ]
                
                uploaded_files = {}
                
                for doc in documents:
                    # Create card for each document
                    required_text = " *" if doc["required"] else " (ไม่บังคับ)"
                    st.markdown(f"""
                    <div style="
                        background: linear-gradient(135deg, {doc['color']}15 0%, {doc['color']}05 100%);
                        padding: 1.5rem;
                        border-radius: 15px;
                        border-left: 4px solid {doc['color']};
                        margin-bottom: 1.5rem;
                        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
                    ">
                        <h4 style="color: {doc['color']}; margin-bottom: 1rem; display: flex; align-items: center; font-size: 1.2rem;">
                            <span style="margin-right: 0.8rem; font-size: 1.4rem;">{doc['icon']}</span> 
                            {doc['title']}{required_text}
                        </h4>
                        <p style="color: #6c757d; margin-bottom: 1rem; font-size: 0.9rem; line-height: 1.5;">
                            {doc['help']}
                        </p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # File uploader
                    uploaded_files[doc['key']] = st.file_uploader(
                        f"เลือกไฟล์สำหรับ {doc['title']}",
                        type=doc['types'],
                        help=doc['help'],
                        key=doc['key'],
                        label_visibility="collapsed"
                    )
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                
                # Submit button with enhanced styling
                st.markdown("<br>", unsafe_allow_html=True)
                submit = st.form_submit_button(
                    "อัพโหลดเอกสารทั้งหมด (Admin)", 
                    use_container_width=True,
                    type="primary"
                )
                
                # Extract individual file variables for compatibility
                admin_photo_file = uploaded_files['admin_photo_upload']
                admin_id_card_file = uploaded_files['admin_id_card_upload']
                admin_transcript_file = uploaded_files['admin_transcript_upload']
                admin_other_file = uploaded_files['admin_other_upload']
                
                if submit:
                    # Validate student information
                    validation_errors = []
                    
                    # Validate required fields
                    if not student_citizen_id or len(student_citizen_id.strip()) != 13:
                        validation_errors.append("กรุณากรอกเลขบัตรประชาชนนักเรียนให้ครบ 13 หลัก")
                    elif not student_citizen_id.isdigit():
                        validation_errors.append("เลขบัตรประชาชนต้องเป็นตัวเลขเท่านั้น")
                    
                    if not student_title:
                        validation_errors.append("กรุณาเลือกคำนำหน้านักเรียน")
                    
                    if not student_first_name or not student_first_name.strip():
                        validation_errors.append("กรุณากรอกชื่อนักเรียน")
                    
                    if not student_last_name or not student_last_name.strip():
                        validation_errors.append("กรุณากรอกนามสกุลนักเรียน")
                    
                    if not student_birth_date:
                        validation_errors.append("กรุณาเลือกวันเกิดนักเรียน")
                    
                    if not student_email or not student_email.strip():
                        validation_errors.append("กรุณากรอกอีเมลนักเรียน")
                    elif "@" not in student_email:
                        validation_errors.append("รูปแบบอีเมลไม่ถูกต้อง")
                    
                    if not student_phone or not student_phone.strip():
                        validation_errors.append("กรุณากรอกเบอร์โทรศัพท์นักเรียน")
                    elif not student_phone.isdigit() or len(student_phone) != 10:
                        validation_errors.append("เบอร์โทรศัพท์ต้องเป็นตัวเลข 10 หลัก")
                    
                    if not student_school_name or not student_school_name.strip():
                        validation_errors.append("กรุณากรอกสถาบันการศึกษาที่จบ")
                    
                    if not student_major or not student_major.strip():
                        validation_errors.append("กรุณากรอกสาขาวิชาที่จบ")
                    
                    if not student_gpax or not student_gpax.strip():
                        validation_errors.append("กรุณากรอกเกรดเฉลี่ยนักเรียน")
                    else:
                        try:
                            gpax_value = float(student_gpax)
                            if gpax_value < 0 or gpax_value > 4:
                                validation_errors.append("เกรดเฉลี่ยต้องอยู่ระหว่าง 0.00 - 4.00")
                        except ValueError:
                            validation_errors.append("เกรดเฉลี่ยต้องเป็นตัวเลข")
                    
                    if not student_graduation_year:
                        validation_errors.append("กรุณาเลือกปีที่จบการศึกษานักเรียน")
                    
                    if not student_address or not student_address.strip():
                        validation_errors.append("กรุณากรอกที่อยู่นักเรียน")
                    
                    if not student_province:
                        validation_errors.append("กรุณาเลือกจังหวัดนักเรียน")
                    
                    if not student_parent_name or not student_parent_name.strip():
                        validation_errors.append("กรุณากรอกชื่อผู้ปกครองนักเรียน")
                    
                    if not student_parent_phone or not student_parent_phone.strip():
                        validation_errors.append("กรุณากรอกเบอร์โทรศัพท์ผู้ปกครองนักเรียน")
                    elif not student_parent_phone.isdigit() or len(student_parent_phone) != 10:
                        validation_errors.append("เบอร์โทรศัพท์ผู้ปกครองต้องเป็นตัวเลข 10 หลัก")
                    
                    # Check required documents
                    required_files = [admin_photo_file, admin_id_card_file, admin_transcript_file]
                    required_names = ["รูปถ่าย", "สำเนาบัตรประจำตัวประชาชน", "สำเนาใบแสดงผลการเรียน"]
                    
                    missing_files = []
                    for i, file in enumerate(required_files):
                        if file is None:
                            missing_files.append(required_names[i])
                    
                    if validation_errors:
                        for error in validation_errors:
                            st.error(f"{error}")
                    elif missing_files:
                        st.error(f"กรุณาอัพโหลดเอกสารที่จำเป็น: {', '.join(missing_files)}")
                    else:
                        # Process all uploaded files for admin
                        uploaded_files_list = [
                            (admin_photo_file, "รูปถ่าย"),
                            (admin_id_card_file, "สำเนาบัตรประจำตัวประชาชน"),
                            (admin_transcript_file, "สำเนาใบแสดงผลการเรียน")
                        ]
                        
                        # Add optional file if uploaded
                        if admin_other_file is not None:
                            uploaded_files_list.append((admin_other_file, "หลักฐานการเปลี่ยนชื่อ-สกุล"))
                        
                        success_count = 0
                        error_messages = []
                        
                        # Remove all existing files for this student before uploading new ones
                        try:
                            safe_name = f"{student_first_name.strip()}-{student_last_name.strip()}".replace(' ', '-')
                            student_file_prefix = f"{student_citizen_id.strip()}_{safe_name}_"
                            
                            # Find and remove all files that belong to this student
                            for existing_file in os.listdir(UPLOAD_DIR):
                                if existing_file.startswith(student_file_prefix):
                                    existing_file_path = os.path.join(UPLOAD_DIR, existing_file)
                                    try:
                                        os.remove(existing_file_path)
                                        # Log file removal with student information
                                        student_info = f"{student_title} {student_first_name.strip()} {student_last_name.strip()} (ID: {student_citizen_id.strip()})"
                                        log_entry = f"{datetime.datetime.now().isoformat()} - Old student file removed by admin {user['username']} for student {student_info}: {existing_file}\n"
                                        with open(os.path.join(LOG_DIR, 'user_changes.log'), 'a', encoding='utf-8') as f:
                                            f.write(log_entry)
                                    except Exception as e:
                                        error_messages.append(f"ไม่สามารถลบไฟล์เก่า {existing_file} ได้: {str(e)}")
                        except Exception as e:
                            error_messages.append(f"เกิดข้อผิดพลาดในการตรวจสอบไฟล์เก่า: {str(e)}")
                        
                        for uploaded_file, doc_type in uploaded_files_list:
                            if uploaded_file is not None:
                                try:
                                    # Generate filename according to convention using student info
                                    file_extension = uploaded_file.name.split('.')[-1]
                                    safe_name = f"{student_first_name.strip()}-{student_last_name.strip()}".replace(' ', '-')
                                    safe_doc_type = doc_type.replace(' ', '-').replace('/', '-')
                                    
                                    filename = f"{student_citizen_id.strip()}_{safe_name}_{safe_doc_type}.{file_extension}"
                                    file_path = os.path.join(UPLOAD_DIR, filename)
                                    
                                    # Check file size (200MB limit)
                                    if uploaded_file.size > 200 * 1024 * 1024:
                                        error_messages.append(f"{doc_type}: ไฟล์มีขนาดเกิน 200MB")
                                        continue
                                    
                                    # Save file
                                    with open(file_path, 'wb') as f:
                                        f.write(uploaded_file.getbuffer())
                                    
                                    success_count += 1
                                    
                                    # Log upload with complete student information
                                    student_info = f"{student_title} {student_first_name.strip()} {student_last_name.strip()} (ID: {student_citizen_id.strip()})"
                                    log_entry = f"{datetime.datetime.now().isoformat()} - Admin file uploaded by {user['username']} for student {student_info}: {filename}\n"
                                    with open(os.path.join(LOG_DIR, 'user_changes.log'), 'a', encoding='utf-8') as f:
                                        f.write(log_entry)
                                    
                                except Exception as e:
                                    error_messages.append(f"{doc_type}: {str(e)}")
                        
                        # Show results
                        if success_count > 0:
                            st.success(f"อัพโหลดเอกสารสำเร็จ {success_count} ไฟล์")
                            
                            # Add student information to users.json
                            try:
                                # Generate username from citizen ID
                                student_username = f"student_{student_citizen_id.strip()}"
                                
                                # Generate a default password (can be changed later)
                                default_password = f"{student_citizen_id.strip()}@{student_birth_date.year}"
                                hashed_password = AuthManager.hash_password(default_password)
                                
                                # Prepare student data
                                student_data = {
                                    "username": student_username,
                                    "password": hashed_password,
                                    "role": "user",
                                    "title": student_title,
                                    "first_name": student_first_name.strip(),
                                    "last_name": student_last_name.strip(),
                                    "email": student_email.strip(),
                                    "phone": student_phone.strip(),
                                    "citizen_id": student_citizen_id.strip(),
                                    "birth_date": student_birth_date.isoformat(),
                                    "school_name": student_school_name.strip(),
                                    "major": student_major.strip(),
                                    "gpax": student_gpax.strip(),
                                    "graduation_year": student_graduation_year,
                                    "address": student_address.strip(),
                                    "province": student_province,
                                    "parent_name": student_parent_name.strip(),
                                    "parent_phone": student_parent_phone.strip(),
                                    "created_at": datetime.datetime.now().isoformat(),
                                    "created_by_admin": user['username']
                                }
                                
                                # Load existing users
                                users = DataManager.load_json(USERS_FILE, {})
                                
                                # Check if student already exists
                                if student_username in users:
                                    # Update existing student data
                                    users[student_username].update(student_data)
                                    st.info(f"อัพเดทข้อมูลนักเรียน: {student_title} {student_first_name} {student_last_name}")
                                else:
                                    # Add new student
                                    users[student_username] = student_data
                                    st.success(f"เพิ่มข้อมูลนักเรียนใหม่: {student_title} {student_first_name} {student_last_name}")
                                
                                # Save updated users data
                                DataManager.save_json(USERS_FILE, users)
                                
                                # Log student creation/update
                                student_info = f"{student_title} {student_first_name.strip()} {student_last_name.strip()} (ID: {student_citizen_id.strip()})"
                                log_entry = f"{datetime.datetime.now().isoformat()} - Student account created/updated by admin {user['username']} for {student_info} (username: {student_username})\n"
                                with open(os.path.join(LOG_DIR, 'user_changes.log'), 'a', encoding='utf-8') as f:
                                    f.write(log_entry)
                                
                                # Show login credentials
                                st.info(f"ข้อมูลการเข้าสู่ระบบของนักเรียน:\n- ชื่อผู้ใช้: {student_username}\n- รหัสผ่านเริ่มต้น: {default_password}")
                                
                            except Exception as e:
                                st.error(f"เกิดข้อผิดพลาดในการบันทึกข้อมูลนักเรียน: {str(e)}")
                        
                        if error_messages:
                            for error in error_messages:
                                st.error(f"{error}")
                        
                        if success_count > 0:
                            st.balloons()
            

        
            with tab2:
                # Header Section with Beautiful Styling for Documents View
                st.markdown("""
                <div style="
                    background: linear-gradient(135deg, #17a2b8 0%, #138496 100%);
                    padding: 2.5rem;
                    border-radius: 20px;
                    color: white;
                    margin-bottom: 2rem;
                    box-shadow: 0 8px 25px rgba(0,0,0,0.15);
                    text-align: center;
                ">
                    <div style="
                        width: 100px;
                        height: 100px;
                        background: rgba(255,255,255,0.2);
                        border-radius: 50%;
                        margin: 0 auto 1.5rem;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 3rem;
                        backdrop-filter: blur(10px);
                    ">📄</div>
                    <h2 style="margin: 0 0 0.5rem 0; font-size: 2rem; font-weight: 600;">เอกสารที่อัพโหลด</h2>
                    <p style="margin: 0; opacity: 0.9; font-size: 1.1rem;">จัดการและตรวจสอบเอกสารของนักเรียนทั้งหมด</p>
                </div>
                """, unsafe_allow_html=True)
                
                if os.path.exists(UPLOAD_DIR):
                    files = [f for f in os.listdir(UPLOAD_DIR) if os.path.isfile(os.path.join(UPLOAD_DIR, f))]
                    
                    if files:
                        # Group files by student
                        students_data = {}
                        required_docs = ['photo', 'id-card', 'transcript']
                        doc_type_map = {
                            'photo': 'รูปถ่าย',
                            'id-card': 'สำเนาบัตรประจำตัวประชาชน', 
                            'transcript': 'สำเนาใบแสดงผลการเรียน',
                            'name-change': 'หลักฐานการเปลี่ยนชื่อ-สกุล',
                            'other': 'เอกสารอื่นๆ'
                        }
                        
                        for filename in files:
                            parts = filename.split('_')
                            if len(parts) >= 3:
                                citizen_id = parts[0]
                                student_name = parts[1].replace('-', ' ')
                                doc_type = parts[2].split('.')[0]
                                
                                if citizen_id not in students_data:
                                    students_data[citizen_id] = {
                                        'name': student_name,
                                        'files': [],
                                        'has_photo': False,
                                        'has_id_card': False,
                                        'has_transcript': False,
                                        'has_name_change': False,
                                        'other_docs': 0
                                    }
                                
                                file_path = os.path.join(UPLOAD_DIR, filename)
                                stat = os.stat(file_path)
                                
                                students_data[citizen_id]['files'].append({
                                    'filename': filename,
                                    'doc_type': doc_type,
                                    'doc_type_thai': doc_type_map.get(doc_type, doc_type),
                                    'size_kb': round(stat.st_size / 1024, 2),
                                    'upload_date': datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%d/%m/%Y %H:%M')
                                })
                                
                                # Track document completeness
                                if doc_type == 'รูปถ่าย':
                                    students_data[citizen_id]['has_photo'] = True
                                elif doc_type == 'สำเนาบัตรประจำตัวประชาชน':
                                    students_data[citizen_id]['has_id_card'] = True
                                elif doc_type == 'สำเนาใบแสดงผลการเรียน':
                                    students_data[citizen_id]['has_transcript'] = True
                                elif doc_type == 'หลักฐานการเปลี่ยนชื่อ-สกุล':
                                    students_data[citizen_id]['has_name_change'] = True
                                else:
                                    students_data[citizen_id]['other_docs'] += 1
                        
                        # Statistics cards removed - now displayed only in user_tab1
                        
                        # Filter options with beautiful card design
                        st.markdown("""
                        <div style="
                            background: #f8f9fa;
                            padding: 1.5rem;
                            border-radius: 15px;
                            border-left: 4px solid #17a2b8;
                            margin: 1.5rem 0;
                            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                        ">
                            <h4 style="color: #17a2b8; margin-bottom: 1rem; display: flex; align-items: center;">
                                ตัวกรองและการค้นหา
                            </h4>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            search_student = st.text_input("ค้นหาชื่อนักเรียนหรือเลขบัตรประจำตัวประชาชน", placeholder="พิมพ์ชื่อนักเรียนหรือเลขบัตรประจำตัวประชาชน...")
                        with col2:
                            status_filter = st.selectbox("กรองตามสถานะ", ['ทั้งหมด', 'เอกสารครบถ้วน', 'เอกสารไม่ครบ'])
                        
                        # Display students
                        filtered_students = []
                        for citizen_id, data in students_data.items():
                            # Apply search filter - search both name and citizen ID
                            if search_student:
                                search_term = search_student.lower()
                                if (search_term not in data['name'].lower() and 
                                    search_term not in citizen_id):
                                    continue
                            
                            # Apply status filter
                            is_complete = data['has_photo'] and data['has_id_card'] and data['has_transcript']
                            if status_filter == 'เอกสารครบถ้วน' and not is_complete:
                                continue
                            elif status_filter == 'เอกสารไม่ครบ' and is_complete:
                                continue
                            
                            filtered_students.append((citizen_id, data))
                        
                        # Pagination setup
                        students_per_page = 10
                        total_students = len(filtered_students)
                        total_pages = (total_students + students_per_page - 1) // students_per_page if total_students > 0 else 1
                        
                        # Initialize page number in session state
                        if 'current_page' not in st.session_state:
                            st.session_state.current_page = 1
                        
                        # Ensure current page is within valid range
                        if st.session_state.current_page > total_pages:
                            st.session_state.current_page = total_pages
                        if st.session_state.current_page < 1:
                            st.session_state.current_page = 1
                        
                        # Student List Header with pagination info
                        if filtered_students:
                            # Calculate pagination
                            start_idx = (st.session_state.current_page - 1) * students_per_page
                            end_idx = start_idx + students_per_page
                            current_page_students = filtered_students[start_idx:end_idx]
                            
                            # Student List Header with pagination info
                            st.markdown(f"""
                            <div style="
                                background: #f8f9fa;
                                padding: 1.5rem;
                                border-radius: 15px;
                                border-left: 4px solid #6c757d;
                                margin: 1.5rem 0;
                                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                            ">
                                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem;">
                                    <h4 style="color: #6c757d; margin: 0; display: flex; align-items: center;">
                                        รายชื่อนักเรียน
                                    </h4>
                                    <div style="color: #6c757d; font-size: 0.9rem;">
                                        หน้า {st.session_state.current_page} จาก {total_pages} | แสดง {len(current_page_students)} จาก {total_students} คน
                                    </div>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            # Pagination controls
                            if total_pages > 1:
                                col1, col2, col3, col4, col5 = st.columns([1, 1, 2, 1, 1])
                                
                                with col1:
                                    if st.button("หน้าแรก", disabled=(st.session_state.current_page == 1), use_container_width=True):
                                        st.session_state.current_page = 1
                                        st.rerun()
                                
                                with col2:
                                    if st.button("ก่อนหน้า", disabled=(st.session_state.current_page == 1), use_container_width=True):
                                        st.session_state.current_page -= 1
                                        st.rerun()
                                
                                with col3:
                                    # Page selector
                                    page_options = list(range(1, total_pages + 1))
                                    selected_page = st.selectbox(
                                        "เลือกหน้า:",
                                        page_options,
                                        index=st.session_state.current_page - 1,
                                        key="page_selector"
                                    )
                                    if selected_page != st.session_state.current_page:
                                        st.session_state.current_page = selected_page
                                        st.rerun()
                                
                                with col4:
                                    if st.button("ถัดไป", disabled=(st.session_state.current_page == total_pages), use_container_width=True):
                                        st.session_state.current_page += 1
                                        st.rerun()
                                
                                with col5:
                                    if st.button("หน้าสุดท้าย", disabled=(st.session_state.current_page == total_pages), use_container_width=True):
                                        st.session_state.current_page = total_pages
                                        st.rerun()
                            
                            # Display students for current page
                            for citizen_id, data in current_page_students:
                                is_complete = data['has_photo'] and data['has_id_card'] and data['has_transcript']
                                status_color = "#28a745" if is_complete else "#dc3545"
                                status_text = "ครบถ้วน" if is_complete else "ไม่ครบ"
                                status_bg = "linear-gradient(135deg, #28a745 0%, #20c997 100%)" if is_complete else "linear-gradient(135deg, #dc3545 0%, #c82333 100%)"
                                
                                # Prepare document status lists
                                complete_docs = []
                                missing_docs = []
                                
                                # Check each required document
                                if data['has_photo']:
                                    complete_docs.append("รูปถ่าย")
                                else:
                                    missing_docs.append("รูปถ่าย")
                                    
                                if data['has_id_card']:
                                    complete_docs.append("สำเนาบัตรประจำตัวประชาชน")
                                else:
                                    missing_docs.append("สำเนาบัตรประจำตัวประชาชน")
                                    
                                if data['has_transcript']:
                                    complete_docs.append("สำเนาใบแสดงผลการเรียน")
                                else:
                                    missing_docs.append("สำเนาใบแสดงผลการเรียน")
                                
                                # Optional documents
                                if data['has_name_change']:
                                    complete_docs.append("หลักฐานการเปลี่ยนชื่อ-สกุล")
                                
                                if data['other_docs'] > 0:
                                    complete_docs.append(f"เอกสารอื่นๆ ({data['other_docs']} ไฟล์)")
                                
                                # Create document status text
                                complete_text = ", ".join(complete_docs) if complete_docs else "ไม่มี"
                                missing_text = ", ".join(missing_docs) if missing_docs else "ไม่มี"
                                
                                # Create missing documents section HTML - DISABLED
                                # missing_section = ""
                                # if missing_docs:
                                #     missing_section = f'''
                                #     <div style="margin-top: 1rem;">
                                #         <h5 style="color: #dc3545; margin: 0 0 0.5rem 0; font-size: 1rem; display: flex; align-items: center;">
                                #             <span style="margin-right: 0.5rem;">❌</span> เอกสารที่ขาด:
                                #         </h5>
                                #         <p style="margin: 0; color: #666; font-size: 0.9rem; line-height: 1.4;">{missing_text}</p>
                                #     </div>
                                #     '''
                                missing_section = ""  # Always empty to hide missing documents section
                                
                                # Student Card Header with document details (Compact version)
                                st.markdown(f"""
                                <div style="
                                    background: {status_bg};
                                    padding: 0.6rem 1rem;
                                    border-radius: 10px 10px 0 0;
                                    color: white;
                                    margin-top: 0.8rem;
                                    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                                ">
                                    <div style="display: flex; align-items: center; justify-content: space-between;">
                                        <div>
                                            <h4 style="margin: 0; font-size: 1rem; font-weight: 600;">{data['name']}</h4>
                                            <p style="margin: 0.2rem 0 0 0; opacity: 0.9; font-size: 0.75rem;">เลขบัตรประจำตัวประชาชน: {citizen_id}</p>
                                        </div>
                                        <div style="text-align: right;">
                                            <span style="font-size: 0.9rem; font-weight: 600;">{status_text}</span>
                                        </div>
                                    </div>
                                </div>
                                
                                <div style="
                                    background: white;
                                    padding: 0.8rem;
                                    border-radius: 0 0 10px 10px;
                                    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                                    margin-bottom: 0.6rem;
                                ">
                                    <div style="margin-bottom: 0.5rem;">
                                        <h5 style="color: #28a745; margin: 0 0 0.3rem 0; font-size: 0.85rem; display: flex; align-items: center;">
                                            เอกสารที่ครบ:
                                        </h5>
                                        <p style="margin: 0; color: #666; font-size: 0.75rem; line-height: 1.3;">{complete_text}</p>
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
                                
                                with st.expander("ดูรายละเอียดเอกสาร", expanded=False):
                                    # สรุปสถานะเอกสารแบบเรียบง่าย
                                    col1, col2 = st.columns([2, 1])
                                    
                                    with col1:
                                        # แสดงสถานะเอกสารจำเป็นในรูปแบบ checklist
                                        st.markdown("**เอกสารจำเป็น:**")
                                        
                                        # รูปถ่าย
                                        photo_icon = "✓" if data['has_photo'] else "✗"
                                        st.markdown(f"{photo_icon} รูปถ่าย")
                                        
                                        # บัตรประชาชน
                                        id_icon = "✓" if data['has_id_card'] else "✗"
                                        st.markdown(f"{id_icon} สำเนาบัตรประจำตัวประชาชน")
                                        
                                        # ใบแสดงผลการเรียน
                                        transcript_icon = "✓" if data['has_transcript'] else "✗"
                                        st.markdown(f"{transcript_icon} สำเนาใบแสดงผลการเรียน")
                                        
                                        # เอกสารเสริม
                                        st.markdown("\n**เอกสารเสริม:**")
                                        name_change_icon = "✓" if data['has_name_change'] else "-"
                                        st.markdown(f"{name_change_icon} หลักฐานการเปลี่ยนชื่อ-สกุล")
                                        
                                        other_count = data['other_docs']
                                        if other_count > 0:
                                            st.markdown(f"เอกสารอื่นๆ: {other_count} ไฟล์")
                                    
                                    with col2:
                                        # แสดงสถานะรวม
                                        completion_percentage = sum([data['has_photo'], data['has_id_card'], data['has_transcript']]) / 3 * 100
                                        
                                        if completion_percentage == 100:
                                            st.success(f"ครบถ้วน\n{completion_percentage:.0f}%")
                                        elif completion_percentage >= 66:
                                            st.warning(f"เกือบครบ\n{completion_percentage:.0f}%")
                                        else:
                                            st.error(f"ไม่ครบ\n{completion_percentage:.0f}%")
                                    
                                    st.divider()
                                    
                                    # รายการไฟล์แบบเรียบง่าย
                                    st.markdown("**รายการไฟล์ที่อัพโหลด:**")
                                    
                                    if data['files']:
                                        # แสดงรายการไฟล์ในรูปแบบตาราง
                                        for file_info in data['files']:
                                            col1, col2, col3 = st.columns([3, 2, 1])
                                            
                                            with col1:
                                                # ไอคอนตามประเภทไฟล์
                                                if file_info['filename'].lower().endswith(('.png', '.jpg', '.jpeg')):
                                                    file_icon = "IMG"
                                                elif file_info['filename'].lower().endswith('.pdf'):
                                                    file_icon = "DOC"
                                                else:
                                                    file_icon = "FILE"
                                                
                                                st.markdown(f"{file_icon} **{file_info['doc_type_thai']}**")
                                                st.caption(f"ขนาด: {file_info['size_kb']} KB | อัพโหลด: {file_info['upload_date']}")
                                            
                                            with col2:
                                                # จัดเรียงปุ่มทั้ง 3 ปุ่มในแถวเดียวกันแบบสวยงาม
                                                file_path = os.path.join(UPLOAD_DIR, file_info['filename'])
                                                
                                                # เพิ่ม CSS สำหรับปุ่มที่สวยงาม
                                                st.markdown("""
                                                <style>
                                                .action-buttons-container {
                                                    display: flex;
                                                    gap: 8px;
                                                    align-items: center;
                                                    justify-content: center;
                                                    margin: 0.5rem 0;
                                                    padding: 0.5rem;
                                                    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                                                    border-radius: 12px;
                                                    border: 1px solid rgba(0,0,0,0.1);
                                                    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
                                                }
                                                .action-btn {
                                                    flex: 1;
                                                    min-height: 40px;
                                                    border-radius: 8px;
                                                    font-weight: 600;
                                                    transition: all 0.3s ease;
                                                    border: none;
                                                    cursor: pointer;
                                                }
                                                .action-btn:hover {
                                                    transform: translateY(-2px);
                                                    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                                                }
                                                </style>
                                                """, unsafe_allow_html=True)
                                                
                                                # สร้าง columns สำหรับปุ่มทั้ง 3 ปุ่ม
                                                btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 1], gap="medium")
                                                
                                                # ปุ่มดูตัวอย่าง
                                                preview_key = f"preview_{citizen_id}_{file_info['filename']}"
                                                
                                                # เริ่มต้น session state สำหรับเก็บรายการไฟล์ที่เปิดดู
                                                if 'opened_previews' not in st.session_state:
                                                    st.session_state.opened_previews = set()
                                                
                                                # ตรวจสอบว่าไฟล์นี้เปิดดูอยู่หรือไม่
                                                is_previewing = preview_key in st.session_state.opened_previews
                                                
                                                with btn_col1:
                                                    if is_previewing:
                                                        # ปุ่มปิดตัวอย่าง
                                                        if st.button("ปิด", key=f"close_{preview_key}", use_container_width=True, type="secondary", help="ปิดตัวอย่าง"):
                                                            st.session_state.opened_previews.discard(preview_key)
                                                            st.rerun()
                                                    else:
                                                        # ปุ่มเปิดตัวอย่าง
                                                        if st.button("ดู", key=f"open_{preview_key}", use_container_width=True, type="primary", help="ดูตัวอย่างไฟล์"):
                                                            st.session_state.opened_previews.add(preview_key)
                                                            st.rerun()
                                                
                                                with btn_col2:
                                                    # ปุ่มดาวน์โหลด
                                                    with open(file_path, 'rb') as f:
                                                        st.download_button(
                                                            "ดาวน์โหลด",
                                                            f.read(),
                                                            file_name=file_info['filename'],
                                                            key=f"download_{citizen_id}_{file_info['filename']}",
                                                            help="ดาวน์โหลดไฟล์",
                                                            use_container_width=True,
                                                            type="primary"
                                                        )
                                                
                                                with btn_col3:
                                                    # ปุ่มลบเอกสาร (สำหรับ admin เท่านั้น)
                                                    delete_key = f"delete_{citizen_id}_{file_info['filename']}"
                                                    if st.button(
                                                        "ลบ", 
                                                        key=delete_key,
                                                        help="ลบเอกสาร",
                                                        type="secondary",
                                                        use_container_width=True
                                                    ):
                                                        # แสดง confirmation dialog
                                                        st.session_state[f"confirm_delete_{delete_key}"] = True
                                            
                                            with col3:
                                                # ย้ายส่วนนี้มาเป็น col3 เพื่อให้มีพื้นที่เพิ่มเติม
                                                pass
                                                
                                                # Confirmation dialog
                                                if st.session_state.get(f"confirm_delete_{delete_key}", False):
                                                    st.warning(f"คุณต้องการลบไฟล์ '{file_info['doc_type_thai']}' ของ {data['name']} หรือไม่?")
                                                    
                                                    col_confirm, col_cancel = st.columns(2)
                                                    with col_confirm:
                                                        if st.button("ยืนยันลบ", key=f"confirm_yes_{delete_key}", type="primary", use_container_width=True):
                                                            try:
                                                                # ลบไฟล์จากระบบ
                                                                if os.path.exists(file_path):
                                                                    os.remove(file_path)
                                                                    st.success(f"ลบไฟล์ '{file_info['doc_type_thai']}' เรียบร้อยแล้ว")
                                                                    
                                                                    # บันทึก log การลบไฟล์
                                                                    log_entry = f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Admin '{user['username']}' deleted file '{file_info['filename']}' for student '{data['name']}' (ID: {citizen_id})\n"
                                                                    with open(os.path.join(LOG_DIR, "file_deletions.log"), "a", encoding="utf-8") as log_file:
                                                                        log_file.write(log_entry)
                                                                    
                                                                    # รีเซ็ต confirmation state
                                                                    del st.session_state[f"confirm_delete_{delete_key}"]
                                                                    st.rerun()
                                                                else:
                                                                    st.error("ไม่พบไฟล์ที่ต้องการลบ")
                                                            except Exception as e:
                                                                st.error(f"เกิดข้อผิดพลาดในการลบไฟล์: {str(e)}")
                                                    
                                                    with col_cancel:
                                                        if st.button("ยกเลิก", key=f"confirm_no_{delete_key}", use_container_width=True):
                                                            del st.session_state[f"confirm_delete_{delete_key}"]
                                                            st.rerun()
                                            
                                            # แสดงตัวอย่างไฟล์ถ้าเปิดดูอยู่
                                            if is_previewing:
                                                file_path = os.path.join(UPLOAD_DIR, file_info['filename'])
                                                
                                                # สร้าง container สำหรับแสดงตัวอย่าง
                                                st.markdown("""
                                                <div style="
                                                    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                                                    padding: 1.5rem;
                                                    border-radius: 15px;
                                                    margin: 1rem 0;
                                                    border: 2px solid #1e40af;
                                                    box-shadow: 0 4px 15px rgba(30,64,175,0.1);
                                                ">
                                                    <h5 style="color: #1e40af; margin-bottom: 1rem; display: flex; align-items: center;">
                                                        ตัวอย่างไฟล์
                                                    </h5>
                                                </div>
                                                """, unsafe_allow_html=True)
                                                
                                                try:
                                                    # ตรวจสอบประเภทไฟล์และแสดงตัวอย่าง
                                                    if file_info['filename'].lower().endswith(('.png', '.jpg', '.jpeg')):
                                                        # แสดงรูปภาพ
                                                        st.image(file_path, caption=f"ตัวอย่าง: {file_info['doc_type_thai']}", use_container_width=True)
                                                    elif file_info['filename'].lower().endswith('.pdf'):
                                                        # แสดง PDF
                                                        with open(file_path, 'rb') as pdf_file:
                                                            pdf_data = pdf_file.read()
                                                            st.markdown("""
                                                            <div style="
                                                                background: white;
                                                                padding: 1rem;
                                                                border-radius: 10px;
                                                                border: 1px solid #dee2e6;
                                                                text-align: center;
                                                            ">
                                                                <p style="margin: 0; color: #6c757d;">ไฟล์ PDF พร้อมดาวน์โหลด</p>
                                                                <p style="margin: 0.5rem 0 0 0; font-size: 0.9rem; color: #868e96;">กดปุ่มดาวน์โหลดเพื่อดูเอกสารแบบเต็ม</p>
                                                            </div>
                                                            """, unsafe_allow_html=True)
                                                            
                                                            # แสดง PDF ใน iframe (ถ้าเบราว์เซอร์รองรับ)
                                                            import base64
                                                            base64_pdf = base64.b64encode(pdf_data).decode('utf-8')
                                                            pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="400" type="application/pdf"></iframe>'
                                                            st.markdown(pdf_display, unsafe_allow_html=True)
                                                    else:
                                                        st.info("ไม่สามารถแสดงตัวอย่างไฟล์ประเภทนี้ได้ กรุณาดาวน์โหลดเพื่อดู")
                                                except Exception as e:
                                                    st.error(f"ไม่สามารถแสดงตัวอย่างไฟล์ได้: {str(e)}")
                                            
                                            st.markdown("---")
                                    
                                    else:
                                        st.markdown("""
                                        <div style="
                                            background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%);
                                            padding: 2rem;
                                            border-radius: 15px;
                                            text-align: center;
                                            margin: 1rem 0;
                                            border: 2px dashed #ffc107;
                                            box-shadow: 0 4px 15px rgba(255,193,7,0.1);
                                        ">
                                            <div style="
                                                width: 80px;
                                                height: 80px;
                                                background: rgba(255,193,7,0.2);
                                                border-radius: 50%;
                                                margin: 0 auto 1rem;
                                                display: flex;
                                                align-items: center;
                                                justify-content: center;
                                                font-size: 2rem;
                                            ">📂</div>
                                            <h4 style="color: #856404; margin-bottom: 0.5rem;">ยังไม่มีไฟล์ที่อัพโหลด</h4>
                                            <p style="color: #856404; margin: 0; opacity: 0.8;">นักเรียนยังไม่ได้อัพโหลดเอกสารใดๆ</p>
                                        </div>
                                        """, unsafe_allow_html=True)
                        else:
                            # No students found message with beautiful styling
                            st.markdown("""
                            <div style="
                                background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                                padding: 3rem;
                                border-radius: 20px;
                                text-align: center;
                                margin: 2rem 0;
                                border: 2px dashed #6c757d;
                                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                            ">
                                <div style="
                                    width: 120px;
                                    height: 120px;
                                    background: rgba(108,117,125,0.1);
                                    border-radius: 50%;
                                    margin: 0 auto 1.5rem;
                                    display: flex;
                                    align-items: center;
                                    justify-content: center;
                                    font-size: 3rem;
                                ">🔍</div>
                                <h3 style="color: #6c757d; margin-bottom: 1rem; font-size: 1.5rem;">ไม่พบนักเรียนที่ตรงกับเงื่อนไขการค้นหา</h3>
                                <p style="color: #868e96; font-size: 1.1rem; margin: 0;">ลองปรับเปลี่ยนคำค้นหาหรือตัวกรองเพื่อค้นหานักเรียน</p>
                            </div>
                            """, unsafe_allow_html=True)
                    
                    # Add pagination controls below the student list or "no students found" message
                    if total_pages > 1:
                        st.markdown("<br>", unsafe_allow_html=True)
                        col1, col2, col3, col4, col5 = st.columns([1, 1, 2, 1, 1])
                        
                        with col2:
                            if st.button("หน้าก่อนหน้า", disabled=(current_page == 1), key="prev_page"):
                                st.session_state.current_page = current_page - 1
                                st.rerun()
                        
                        with col3:
                            st.info(f"**หน้า {current_page} จาก {total_pages}**")
                        
                        with col4:
                            if st.button("หน้าถัดไป", disabled=(current_page == total_pages), key="next_page"):
                                st.session_state.current_page = current_page + 1
                                st.rerun()
                    
                    else:
                        pass  # No message when no documents are uploaded
                else:
                # Folder not found message with beautiful styling
                    st.markdown("""
                    <div style="
                        background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%);
                        padding: 3rem;
                        border-radius: 20px;
                        text-align: center;
                        margin: 2rem 0;
                        border: 2px dashed #ffc107;
                        box-shadow: 0 4px 15px rgba(255,193,7,0.2);
                    ">
                        <div style="
                            width: 120px;
                            height: 120px;
                            background: rgba(255,193,7,0.1);
                            border-radius: 50%;
                            margin: 0 auto 1.5rem;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            font-size: 3rem;
                        ">📁</div>
                        <h3 style="color: #856404; margin-bottom: 1rem; font-size: 1.5rem;">ไม่พบโฟลเดอร์เก็บเอกสาร</h3>
                        <p style="color: #856404; font-size: 1.1rem; margin: 0;">โฟลเดอร์เก็บเอกสารยังไม่ถูกสร้าง กรุณาติดต่อผู้ดูแลระบบ</p>
                    </div>
                    """, unsafe_allow_html=True)  
        
            with tab3:
                # User Management Tab with sub-tabs
                st.markdown("""
                <div style="
                    background: linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%);
                    padding: 2.5rem;
                    border-radius: 20px;
                    color: white;
                    margin-bottom: 2rem;
                    box-shadow: 0 8px 25px rgba(0,0,0,0.15);
                    text-align: center;
                ">
                    <div style="
                        width: 100px;
                        height: 100px;
                        background: rgba(255,255,255,0.2);
                        border-radius: 50%;
                        margin: 0 auto 1.5rem;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 2.5rem;
                    ">👥</div>
                    <h2 style="margin: 0 0 0.5rem 0; font-size: 2rem; font-weight: 700;">จัดการผู้ใช้</h2>
                    <p style="margin: 0; font-size: 1.1rem; opacity: 0.9;">แสดงและแก้ไขข้อมูลผู้ใช้ทั้งหมดในระบบ</p>
                </div>
                """, unsafe_allow_html=True)
                
                # Sub-tabs within User Management - แยกการแสดงผลอย่างชัดเจน
                user_tab1, user_tab2, user_tab3 = st.tabs(["สถิติและข้อมูลภาพรวม", "ตารางรายชื่อผู้ใช้ทั้งหมด", "จัดการข้อความ"])
                
                with user_tab1: 
                    # Load all users
                    users = DataManager.load_json(USERS_FILE, {})

                    if users:
                        # Group provinces by regions
                        regions = {
                            "ภาคเหนือ": ["เชียงราย", "เชียงใหม่", "ลำปาง", "ลำพูน", "แม่ฮ่องสอน", "น่าน", "พะเยา", "แพร่", "อุตรดิตถ์", "ตาก", "สุโขทัย", "พิษณุโลก", "พิจิตร", "เพชรบูรณ์", "กำแพงเพชร", "นครสวรรค์", "อุทัยธานี"],
                            "ภาคตะวันออกเฉียงเหนือ": ["หนองคาย", "บึงกาฬ", "เลย", "อุดรธานี", "หนองบัวลำภู", "ขอนแก่น", "กาฬสินธุ์", "มหาสารคาม", "ร้อยเอ็ด", "ยโสธร", "มุกดาหาร", "นครพนม", "สกลนคร", "นครราชสีมา", "ชัยภูมิ", "บุรีรัมย์", "สุรินทร์", "ศรีสะเกษ", "อุบลราชธานี", "อำนาจเจริญ"],
                            "ภาคกลาง": ["กรุงเทพมหานคร", "นนทบุรี", "ปทุมธานี", "สมุทรปราการ", "สมุทรสงคราม", "สมุทรสาคร", "นครปฐม", "พระนครศรีอยุธยา", "อ่างทอง", "ลพบุรี", "สิงห์บุรี", "ชัยนาท", "สุพรรณบุรี", "กาญจนบุรี", "ราชบุรี", "เพชรบุรี", "ประจวบคีรีขันธ์", "นครนายก", "ปราจีนบุรี", "สระแก้ว", "ฉะเชิงเทรา", "ชลบุรี", "ระยอง", "จันทบุรี", "ตราด", "สระบุรี"],
                            "ภาคใต้": ["เพชรบุรี", "ประจวบคีรีขันธ์", "ชุมพร", "ระนอง", "สุราษฎร์ธานี", "พังงา", "ภูเก็ต", "กระบี่", "นครศรีธรรมราช", "ตรัง", "พัทลุง", "สงขลา", "สตูล", "ปัตตานี", "ยะลา", "นราธิวาส"]
                        }
                
                    # Count students by region
                    region_counts = {region: 0 for region in regions.keys()}
                    total_students = 0
                
                    for user in users.values():
                        if user.get('role') != 'admin':
                            total_students += 1
                            user_province = user.get('province', '')
                            for region, provinces in regions.items():
                                if user_province in provinces:
                                    region_counts[region] += 1
                                    break
                
                    # Display regional statistics
                    st.markdown("""
                    <div style="
                        background: linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%);
                        padding: 2rem;
                        border-radius: 15px;
                        color: white;
                        text-align: center;
                        margin-bottom: 2rem;
                        box-shadow: 0 4px 15px rgba(30,64,175,0.3);
                    ">
                        <h3 style="margin: 0 0 1rem 0; font-size: 1.8rem;">สถิตินักเรียนทั้งหมด</h3>
                        <p style="margin: 0; opacity: 0.9; font-size: 1.1rem;">จำนวนนักเรียนทั้งหมด: """ + str(total_students) + """ คน</p>
                    </div>
                    """, unsafe_allow_html=True)
                
                    # Display region statistics in columns
                    col1, col2, col3, col4 = st.columns(4)
                    
                    region_colors = [
                        "linear-gradient(135deg, #10b981 0%, #059669 100%)",  # Green
                        "linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)",  # Blue
                        "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)",  # Orange
                        "linear-gradient(135deg, #ef4444 0%, #dc2626 100%)"   # Red
                    ]
                
                    region_icons = ["", "", "", ""]
                    
                    for i, (region, count) in enumerate(region_counts.items()):
                        with [col1, col2, col3, col4][i]:
                            st.markdown(f"""
                            <div style="
                                background: {region_colors[i]};
                                padding: 1.5rem;
                                border-radius: 15px;
                                color: white;
                                text-align: center;
                                box-shadow: 0 4px 15px rgba(0,0,0,0.2);
                                margin-bottom: 1rem;
                            ">
                                <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">{region_icons[i]}</div>
                                <h3 style="margin: 0; font-size: 2rem; font-weight: 700;">{count}</h3>
                                <p style="margin: 0; opacity: 0.9; font-size: 0.9rem;">{region}</p>
                            </div>
                            """, unsafe_allow_html=True)
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                
                    # คำอธิบายเพิ่มเติม
                    st.info("💡 **หมายเหตุ:** แท็บนี้แสดงเฉพาะสถิติและข้อมูลภาพรวม หากต้องการดูรายละเอียดผู้ใช้แต่ละคน กรุณาไปที่แท็บ 'ตารางรายชื่อผู้ใช้ทั้งหมด'")
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    
                    # Search
                    search_term = st.text_input("ค้นหาผู้ใช้", placeholder="ค้นหาด้วยเลขบัตรประชาชน, ชื่อ-นามสกุล, ชื่อผู้ใช้, อีเมล หรือเบอร์โทร")
                    
                    # Reset pagination when search term changes
                    if 'last_search_term' not in st.session_state:
                        st.session_state.last_search_term = ""
                    
                    if search_term != st.session_state.last_search_term:
                        st.session_state.user_page = 0
                        st.session_state.last_search_term = search_term
                
                    # Filter users (exclude all admin users)
                    filtered_users = {}
                    for username, user_data in users.items():
                        # Always skip admin users
                        if user_data.get('role') == 'admin':
                            continue
                        
                        # Search filter
                        if search_term:
                            search_fields = [
                                user_data.get('citizen_id', '').lower(),
                                user_data.get('first_name', '').lower(),
                                user_data.get('last_name', '').lower(),
                            ]
                            if not any(search_term.lower() in field for field in search_fields):
                                continue
                        
                        filtered_users[username] = user_data
                
                    if filtered_users:
                        # Initialize pagination state
                        if 'user_page' not in st.session_state:
                            st.session_state.user_page = 0
                        
                        # Convert to list for pagination
                        users_list = list(filtered_users.items())
                        users_per_page = 10
                        total_users = len(users_list)
                        total_pages = (total_users + users_per_page - 1) // users_per_page
                        
                        # Calculate start and end indices
                        start_idx = st.session_state.user_page * users_per_page
                        end_idx = min(start_idx + users_per_page, total_users)
                        current_page_users = users_list[start_idx:end_idx]
                        
                        # Display pagination info
                        st.markdown(f"""
                        <div style="
                            background: #f8f9fa;
                            padding: 1rem;
                            border-radius: 10px;
                            margin-bottom: 1rem;
                            text-align: center;
                            border: 1px solid #e9ecef;
                        ">
                            <strong>แสดงผู้ใช้ {start_idx + 1}-{end_idx} จากทั้งหมด {total_users} คน (หน้า {st.session_state.user_page + 1}/{total_pages})</strong>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Pagination controls
                        if total_pages > 1:
                            col1, col2, col3 = st.columns([1, 2, 1])
                            
                            with col1:
                                if st.button("หน้าก่อนหน้า", disabled=st.session_state.user_page == 0, key="prev_page"):
                                    st.session_state.user_page -= 1
                                    st.rerun()
                            
                            with col3:
                                if st.button("หน้าถัดไป", disabled=st.session_state.user_page >= total_pages - 1, key="next_page"):
                                    st.session_state.user_page += 1
                                    st.rerun()
                        
                        # Display users in a table-like format
                        for username, user_data in current_page_users:
                            with st.expander(f"{user_data.get('citizen_id', 'ไม่ระบุ')} {user_data.get('title', '')}{user_data.get('first_name', '')} {user_data.get('last_name', '')} (@{username})", expanded=False):
                                # User info display and edit form
                                col1, col2 = st.columns([1, 1])
                                
                                with col1:
                                    st.markdown("""
                                    <div style="
                                        background: #f8f9fa;
                                        padding: 1.5rem;
                                        border-radius: 10px;
                                        border-left: 4px solid #1e3a8a;
                                        margin-bottom: 1rem;
                                    ">
                                        <h4 style="color: #1e3a8a; margin-bottom: 1rem;">ข้อมูลปัจจุบัน</h4>
                                    </div>
                                    """, unsafe_allow_html=True)
                                    
                                    # Display current user data in organized cards
                                    
                                    # Personal Information Card
                                    st.markdown(f"""
                                    <div style="
                                        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                                        padding: 1.5rem;
                                        border-radius: 15px;
                                        border-left: 4px solid #1e40af;
                                        margin-bottom: 1rem;
                                        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                                    ">
                                        <h5 style="color: #1e40af; margin-bottom: 1rem; display: flex; align-items: center; font-size: 1.1rem;">
                                            ข้อมูลส่วนตัว
                                        </h5>
                                        <div style="
                                            background: rgba(255,255,255,0.9);
                                            padding: 1.2rem;
                                            border-radius: 10px;
                                            border: 1px solid #e9ecef;
                                            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
                                        ">
                                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.8rem; margin-bottom: 0.8rem;">
                                                <div style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0; border-bottom: 1px solid #f1f3f4;">
                                                    <strong style="color: #495057; min-width: 80px;">ชื่อผู้ใช้:</strong>
                                                    <span style="color: #6c757d;">{username}</span>
                                                </div>
                                                <div style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0; border-bottom: 1px solid #f1f3f4;">
                                                    <strong style="color: #495057; min-width: 80px;">บทบาท:</strong>
                                                    <span style="color: #6c757d;">{'ผู้ดูแลระบบ' if user_data.get('role') == 'admin' else 'นักเรียน'}</span>
                                                </div>
                                            </div>
                                            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0.8rem;">
                                                <div style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0; border-bottom: 1px solid #f1f3f4;">
                                                    <strong style="color: #495057;">คำนำหน้า:</strong>
                                                    <span style="color: #6c757d;">{user_data.get('title', 'ไม่ระบุ')}</span>
                                                </div>
                                                <div style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0; border-bottom: 1px solid #f1f3f4;">
                                                    <strong style="color: #495057;">ชื่อ:</strong>
                                                    <span style="color: #6c757d;">{user_data.get('first_name', 'ไม่ระบุ')}</span>
                                                </div>
                                                <div style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0; border-bottom: 1px solid #f1f3f4;">
                                                    <strong style="color: #495057;">นามสกุล:</strong>
                                                    <span style="color: #6c757d;">{user_data.get('last_name', 'ไม่ระบุ')}</span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                    """, unsafe_allow_html=True)
                                    
                                    # Contact Information Card
                                    st.markdown(f"""
                                    <div style="
                                        background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
                                        padding: 1.5rem;
                                        border-radius: 15px;
                                        border-left: 4px solid #0ea5e9;
                                        margin-bottom: 1rem;
                                        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                                    ">
                                        <h5 style="color: #0ea5e9; margin-bottom: 1rem; display: flex; align-items: center; font-size: 1.1rem;">
                                            ข้อมูลติดต่อ
                                        </h5>
                                        <div style="
                                            background: rgba(255,255,255,0.9);
                                            padding: 1.2rem;
                                            border-radius: 10px;
                                            border: 1px solid #e9ecef;
                                            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
                                        ">
                                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.8rem;">
                                                <div style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0; border-bottom: 1px solid #f1f3f4;">
                                                    <strong style="color: #495057; min-width: 80px;">อีเมล:</strong>
                                                    <span style="color: #6c757d; word-break: break-all;">{user_data.get('email', 'ไม่ระบุ')}</span>
                                                </div>
                                                <div style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0; border-bottom: 1px solid #f1f3f4;">
                                                    <strong style="color: #495057; min-width: 80px;">เบอร์โทร:</strong>
                                                    <span style="color: #6c757d;">{user_data.get('phone', 'ไม่ระบุ')}</span>
                                                </div>
                                            </div>
                                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.8rem; margin-top: 0.8rem;">
                                                <div style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0; border-bottom: 1px solid #f1f3f4;">
                                                    <strong style="color: #495057;">เลขบัตรประชาชน:</strong>
                                                    <span style="color: #6c757d;">{user_data.get('citizen_id', 'ไม่ระบุ')}</span>
                                                </div>
                                                <div style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0; border-bottom: 1px solid #f1f3f4;">
                                                    <strong style="color: #495057;">วันเกิด:</strong>
                                                    <span style="color: #6c757d;">{user_data.get('birth_date', 'ไม่ระบุ')}</span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                    """, unsafe_allow_html=True)
                                    
                                    # Education Information Card
                                    st.markdown(f"""
                                    <div style="
                                        background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
                                        padding: 1.5rem;
                                        border-radius: 15px;
                                        border-left: 4px solid #22c55e;
                                        margin-bottom: 1rem;
                                        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                                    ">
                                        <h5 style="color: #22c55e; margin-bottom: 1rem; display: flex; align-items: center; font-size: 1.1rem;">
                                            ข้อมูลการศึกษา
                                        </h5>
                                        <div style="
                                            background: rgba(255,255,255,0.9);
                                            padding: 1.2rem;
                                            border-radius: 10px;
                                            border: 1px solid #e9ecef;
                                            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
                                        ">
                                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.8rem; margin-bottom: 0.8rem;">
                                                <div style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0; border-bottom: 1px solid #f1f3f4;">
                                                    <strong style="color: #495057;">สถาบันการศึกษาที่จบ:</strong>
                                                    <span style="color: #6c757d;">{user_data.get('school_name', user_data.get('school', 'ไม่ระบุ'))}</span>
                                                </div>
                                                <div style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0; border-bottom: 1px solid #f1f3f4;">
                                                    <strong style="color: #495057;">สาขาวิชาที่จบ:</strong>
                                                    <span style="color: #6c757d;">{user_data.get('major', 'ไม่ระบุ')}</span>
                                                </div>
                                            </div>
                                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.8rem;">
                                                <div style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0; border-bottom: 1px solid #f1f3f4;">
                                                    <strong style="color: #495057;">GPAX:</strong>
                                                    <span style="color: #6c757d;">{user_data.get('gpax', 'ไม่ระบุ')}</span>
                                                </div>
                                                <div style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0; border-bottom: 1px solid #f1f3f4;">
                                                    <strong style="color: #495057;">ปีจบการศึกษา:</strong>
                                                    <span style="color: #6c757d;">{user_data.get('graduation_year', 'ไม่ระบุ')}</span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                    """, unsafe_allow_html=True)
                                    
                                    # Address Information Card
                                    st.markdown(f"""
                                    <div style="
                                        background: linear-gradient(135deg, #fefce8 0%, #fef3c7 100%);
                                        padding: 1.5rem;
                                        border-radius: 15px;
                                        border-left: 4px solid #f59e0b;
                                        margin-bottom: 1rem;
                                        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                                    ">
                                        <h5 style="color: #f59e0b; margin-bottom: 1rem; display: flex; align-items: center; font-size: 1.1rem;">
                                            ที่อยู่และผู้ปกครอง
                                        </h5>
                                        <div style="
                                            background: rgba(255,255,255,0.9);
                                            padding: 1.2rem;
                                            border-radius: 10px;
                                            border: 1px solid #e9ecef;
                                            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
                                        ">
                                            <div style="margin-bottom: 1rem;">
                                                <div style="display: flex; align-items: flex-start; gap: 0.5rem; padding: 0.5rem 0; border-bottom: 1px solid #f1f3f4;">
                                                    <div style="flex: 1;">
                                                        <strong style="color: #495057; display: block; margin-bottom: 0.3rem;">ที่อยู่:</strong>
                                                        <span style="color: #6c757d; line-height: 1.5;">{user_data.get('address', 'ไม่ระบุ')}</span>
                                                    </div>
                                                </div>
                                                <div style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0; border-bottom: 1px solid #f1f3f4;">
                                                    <strong style="color: #495057;">จังหวัด:</strong>
                                                    <span style="color: #6c757d;">{user_data.get('province', 'ไม่ระบุ')}</span>
                                                </div>
                                            </div>
                                            <div style="border-top: 2px solid #f1f3f4; padding-top: 1rem;">
                                                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.8rem;">
                                                    <div style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0;">
                                                        <strong style="color: #495057;">ชื่อผู้ปกครอง:</strong>
                                                        <span style="color: #6c757d;">{user_data.get('parent_name', 'ไม่ระบุ')}</span>
                                                    </div>
                                                    <div style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0;">
                                                        <strong style="color: #495057;">เบอร์ผู้ปกครอง:</strong>
                                                        <span style="color: #6c757d;">{user_data.get('parent_phone', 'ไม่ระบุ')}</span>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                    """, unsafe_allow_html=True)
                                
                                with col2:
                                    # Admin Edit Form
                                    st.markdown("""
                                    <div style="
                                        background: #f8f9fa;
                                        padding: 1.5rem;
                                        border-radius: 10px;
                                        border-left: 4px solid #28a745;
                                        margin-bottom: 1rem;
                                        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                                    ">
                                        <h4 style="color: #28a745; margin-bottom: 1rem; display: flex; align-items: center;">
                                            แก้ไขข้อมูลผู้ใช้ (Admin)
                                        </h4>
                                    </div>
                                    """, unsafe_allow_html=True)
                                    
                                    with st.form(f"admin_edit_form_{username}"):
                                        # ข้อมูลส่วนตัว
                                        st.markdown("**ข้อมูลส่วนตัว**")
                                        col_a, col_b = st.columns(2)
                                        with col_a:
                                            # คำนำหน้า
                                            current_title = user_data.get('title', '')
                                            if current_title in THAI_TITLES:
                                                title_index = THAI_TITLES.index(current_title)
                                            else:
                                                title_index = 0
                                            new_title = st.selectbox("คำนำหน้า", THAI_TITLES, index=title_index, key=f"title_{username}")
                                            
                                            new_first_name = st.text_input("ชื่อ", value=user_data.get('first_name', ''), key=f"fname_{username}")
                                            new_last_name = st.text_input("นามสกุล", value=user_data.get('last_name', ''), key=f"lname_{username}")
                                        with col_b:
                                            new_citizen_id = st.text_input("เลขบัตรประชาชน", value=user_data.get('citizen_id', ''), max_chars=13, key=f"cid_{username}")
                                            new_phone = st.text_input("โทรศัพท์", value=user_data.get('phone', ''), max_chars=10, key=f"phone_{username}")
                                            new_email = st.text_input("อีเมล", value=user_data.get('email', ''), key=f"email_{username}")
                                        
                                        # ข้อมูลการศึกษา
                                        st.markdown("**ข้อมูลการศึกษา**")
                                        col_c, col_d = st.columns(2)
                                        with col_c:
                                            new_school_name = st.text_input("สถาบันการศึกษาที่จบ", value=user_data.get('school_name', ''), key=f"school_{username}")
                                            new_major = st.text_input("สาขาวิชาที่จบ", value=user_data.get('major', ''), key=f"major_{username}")
                                            # Format GPAX
                                            gpax_value = user_data.get('gpax', '')
                                            if gpax_value and gpax_value != '':
                                                try:
                                                    gpax_formatted = f"{float(gpax_value):.2f}"
                                                except (ValueError, TypeError):
                                                    gpax_formatted = str(gpax_value)
                                            else:
                                                gpax_formatted = ''
                                            new_gpax = st.text_input("เกรดเฉลี่ย", value=gpax_formatted, key=f"gpax_{username}")
                                        with col_d:
                                            current_year = user_data.get('graduation_year', 2024)
                                            year_options = list(range(2020, 2030))
                                            if current_year in year_options:
                                                year_index = year_options.index(current_year)
                                            else:
                                                year_index = year_options.index(2024)
                                            new_graduation_year = st.selectbox(
                                                "ปีที่จบการศึกษา",
                                                options=year_options,
                                                index=year_index,
                                                key=f"year_{username}"
                                            )
                                        
                                        # ที่อยู่และข้อมูลผู้ปกครอง
                                        st.markdown("**ที่อยู่และข้อมูลผู้ปกครอง**")
                                        new_address = st.text_area("ที่อยู่", value=user_data.get('address', ''), key=f"addr_{username}")
                                        
                                        # Province selection
                                        current_province = user_data.get('province', '')
                                        province_options = [""] + THAI_PROVINCES
                                        province_index = 0
                                        if current_province and current_province in THAI_PROVINCES:
                                            province_index = province_options.index(current_province)
                                        
                                        new_province = st.selectbox("จังหวัด", options=province_options, index=province_index, key=f"prov_{username}")
                                        
                                        col_e, col_f = st.columns(2)
                                        with col_e:
                                            new_parent_name = st.text_input("ชื่อผู้ปกครอง", value=user_data.get('parent_name', ''), key=f"pname_{username}")
                                        with col_f:
                                            new_parent_phone = st.text_input("เบอร์ผู้ปกครอง", value=user_data.get('parent_phone', ''), max_chars=10, key=f"pphone_{username}")
                                        
                                        # เปลี่ยนรหัสผ่าน
                                        st.markdown("**เปลี่ยนรหัสผ่าน (ไม่บังคับ)**")
                                        col_g, col_h = st.columns(2)
                                        with col_g:
                                            new_password = st.text_input("รหัสผ่านใหม่", type="password", key=f"pwd_{username}")
                                        with col_h:
                                            confirm_new_password = st.text_input("ยืนยันรหัสผ่านใหม่", type="password", key=f"cpwd_{username}")
                                        
                                        submit_admin_edit = st.form_submit_button("💾 บันทึกการเปลี่ยนแปลง", use_container_width=True)
                                    
                                    # ปุ่มลบผู้ใช้และรีเซ็ตรหัสผ่าน (นอก form)
                                    st.markdown("<br>", unsafe_allow_html=True)
                                    col_action1, col_action2 = st.columns(2)
                                    
                                    with col_action1:
                                        if st.button(f"🔄 รีเซ็ตรหัสผ่าน", key=f"reset_pwd_{username}", use_container_width=True, type="secondary"):
                                            # รีเซ็ตรหัสผ่านเป็นรหัสบัตรประชาชน
                                            citizen_id = user_data.get('citizen_id', '')
                                            if citizen_id:
                                                reset_data = {
                                                    'password': AuthManager.hash_password(citizen_id),
                                                    'updated_at': datetime.datetime.now().isoformat(),
                                                    'updated_by_admin': user['username']
                                                }
                                                success, message = UserManager.update_user(username, reset_data)
                                                if success:
                                                    st.success(f"รีเซ็ตรหัสผ่านของ {username} เป็น {citizen_id} สำเร็จ!")
                                                    time.sleep(1)
                                                    st.rerun()
                                                else:
                                                    st.error(f"{message}")
                                            else:
                                                st.error("ไม่พบรหัสบัตรประชาชนของผู้ใช้นี้")
                                    
                                    with col_action2:
                                        if st.button(f"ลบผู้ใช้", key=f"delete_{username}", use_container_width=True, type="primary"):
                                            # ยืนยันการลบ
                                            if f"confirm_delete_{username}" not in st.session_state:
                                                st.session_state[f"confirm_delete_{username}"] = True
                                                st.warning(f"คุณแน่ใจหรือไม่ที่จะลบผู้ใช้ {username}? กดปุ่มลบอีกครั้งเพื่อยืนยัน")
                                                st.rerun()
                                            else:
                                                # ลบผู้ใช้
                                                users = DataManager.load_json(USERS_FILE, {})
                                                if username in users:
                                                    # ลบไฟล์เอกสารของผู้ใช้
                                                    user_files_pattern = f"{user_data.get('citizen_id', '')}_{user_data.get('first_name', '')}-{user_data.get('last_name', '')}_*"
                                                    import glob
                                                    user_files = glob.glob(os.path.join(UPLOAD_DIR, user_files_pattern))
                                                    for file_path in user_files:
                                                        try:
                                                            os.remove(file_path)
                                                        except:
                                                            pass
                                                    
                                                    # ลบผู้ใช้จากฐานข้อมูล
                                                    del users[username]
                                                    DataManager.save_json(USERS_FILE, users)
                                                    
                                                    # ลบ session ของผู้ใช้ (ถ้ามี)
                                                    sessions = DataManager.load_json(SESSIONS_FILE, {})
                                                    sessions_to_delete = []
                                                    for session_id, session_data in sessions.items():
                                                        if session_data.get('username') == username:
                                                            sessions_to_delete.append(session_id)
                                                    
                                                    for session_id in sessions_to_delete:
                                                        del sessions[session_id]
                                                    
                                                    if sessions_to_delete:
                                                        DataManager.save_json(SESSIONS_FILE, sessions)
                                                    
                                                    # Log การลบ
                                                    log_entry = f"{datetime.datetime.now().isoformat()} - Admin {user['username']} deleted user {username}\n"
                                                    with open(os.path.join(LOG_DIR, "user_changes.log"), "a", encoding="utf-8") as f:
                                                        f.write(log_entry)
                                                    
                                                    st.success(f"ลบผู้ใช้ {username} สำเร็จ!")
                                                    # รีเซ็ตสถานะการยืนยัน
                                                    if f"confirm_delete_{username}" in st.session_state:
                                                        del st.session_state[f"confirm_delete_{username}"]
                                                    time.sleep(1)
                                                    st.rerun()
                                                else:
                                                    st.error("ไม่พบผู้ใช้ในระบบ")
                                        
                                        # รีเซ็ตสถานะการยืนยันเมื่อไม่ได้กดปุ่มลบ
                                        if f"confirm_delete_{username}" in st.session_state:
                                            if st.button(f"ยกเลิกการลบ", key=f"cancel_delete_{username}", use_container_width=True):
                                                del st.session_state[f"confirm_delete_{username}"]
                                                st.rerun()
                                        
                                        if submit_admin_edit:
                                            # Validation
                                            errors = []
                                            
                                            # Validate required fields
                                            if not all([new_first_name, new_last_name, new_citizen_id, new_phone, new_email, new_school_name, new_gpax]):
                                                errors.append("กรุณากรอกข้อมูลที่จำเป็นให้ครบถ้วน")
                                            
                                            # Validate formats
                                            if not errors:
                                                validations = [
                                        Validator.validate_thai_name(new_first_name),
                                        Validator.validate_thai_name(new_last_name),
                                        Validator.validate_citizen_id(new_citizen_id) if new_citizen_id == user.get('citizen_id') else Validator.validate_citizen_id_with_uniqueness(new_citizen_id, username),
                                        Validator.validate_email(new_email),
                                        Validator.validate_phone(new_phone),
                                        Validator.validate_gpax(new_gpax)
                                    ]
                                                
                                                # Validate parent phone if provided
                                                if new_parent_phone and new_parent_phone.strip():
                                                    is_valid, error_msg = Validator.validate_phone(new_parent_phone)
                                                    if not is_valid:
                                                        errors.append(f"เบอร์ผู้ปกครอง: {error_msg}")
                                                
                                                for is_valid, error_msg in validations:
                                                    if not is_valid:
                                                        errors.append(error_msg)
                                            
                                            # Check for duplicates (excluding current user)
                                            if not errors:
                                                if UserManager.check_duplicate('email', new_email, username):
                                                    errors.append("อีเมลนี้มีอยู่ในระบบแล้ว")
                                                if UserManager.check_duplicate('phone', new_phone, username):
                                                    errors.append("เบอร์โทรศัพท์นี้มีอยู่ในระบบแล้ว")
                                            
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
                                                    'title': new_title,
                                                    'first_name': new_first_name,
                                                    'last_name': new_last_name,
                                                    'citizen_id': new_citizen_id,
                                                    'phone': new_phone,
                                                    'email': new_email,
                                                    'school_name': new_school_name,
                                                    'major': new_major,
                                                    'gpax': round(float(new_gpax), 2),
                                                    'graduation_year': new_graduation_year,
                                                    'address': new_address,
                                                    'province': new_province,
                                                    'parent_name': new_parent_name,
                                                    'parent_phone': new_parent_phone,
                                                    'updated_at': datetime.datetime.now().isoformat(),
                                                    'updated_by_admin': user['username']  # Track who made the change
                                                }
                                                
                                                if new_password:
                                                    updated_data['password'] = AuthManager.hash_password(new_password)
                                                
                                                success, message = UserManager.update_user(username, updated_data)
                                                if success:
                                                    st.success(f"บันทึกข้อมูลของ {username} สำเร็จ!")
                                                    time.sleep(1)
                                                    st.rerun()
                                                else:
                                                    st.error(f"{message}")
                    
                        # Bottom pagination controls (duplicate for better UX)
                        if total_pages > 1:
                            st.markdown("<br>", unsafe_allow_html=True)
                            col1, col2, col3 = st.columns([1, 2, 1])
                            
                            with col1:
                                if st.button("หน้าก่อนหน้า", disabled=st.session_state.user_page == 0, key="prev_page_bottom"):
                                    st.session_state.user_page -= 1
                                    st.rerun()
                            
                            with col2:
                                st.markdown(f"""
                                <div style="
                                    text-align: center;
                                    padding: 0.5rem;
                                    color: #6c757d;
                                    font-weight: 500;
                                ">
                                    หน้า {st.session_state.user_page + 1} จาก {total_pages}
                                </div>
                                """, unsafe_allow_html=True)
                            
                            with col3:
                                if st.button("หน้าถัดไป", disabled=st.session_state.user_page >= total_pages - 1, key="next_page_bottom"):
                                    st.session_state.user_page += 1
                                    st.rerun()
                    else:
                        pass
                
                with user_tab2:
                    # Header Section
                    st.markdown("""
                    <div style="
                        background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
                        padding: 2.5rem;
                        border-radius: 20px;
                        color: white;
                        margin-bottom: 2rem;
                        box-shadow: 0 8px 25px rgba(0,0,0,0.15);
                        text-align: center;
                    ">
                        <div style="
                            width: 100px;
                            height: 100px;
                            background: rgba(255,255,255,0.2);
                            border-radius: 50%;
                            margin: 0 auto 1.5rem;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            font-size: 3rem;
                            backdrop-filter: blur(10px);
                        ">👥</div>
                        <h2 style="margin: 0 0 0.5rem 0; font-size: 2rem; font-weight: 600;">ตารางรายชื่อผู้ใช้ทั้งหมด</h2>
                        <p style="margin: 0; font-size: 1.1rem; opacity: 0.9;">แสดงข้อมูลผู้ใช้ทั้งหมดในระบบ</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Load users data
                    users = DataManager.load_json(USERS_FILE, {})
                    
                    # Filter out admin users
                    regular_users = {username: user_data for username, user_data in users.items() 
                                if user_data.get('role') != 'admin'}
                    
                    if regular_users:
                        # Search functionality
                        search_term = st.text_input("ค้นหาผู้ใช้", placeholder="ค้นหาด้วยชื่อ, นามสกุล, เลขบัตรประชาชน, อีเมล หรือเบอร์โทร")
                        
                        # Filter users based on search
                        if search_term:
                            filtered_users = {}
                            for username, user_data in regular_users.items():
                                search_fields = [
                                    user_data.get('first_name', '').lower(),
                                    user_data.get('last_name', '').lower(),
                                    user_data.get('citizen_id', '').lower(),
                                    user_data.get('email', '').lower(),
                                    user_data.get('phone', '').lower()
                                ]
                                if any(search_term.lower() in field for field in search_fields):
                                    filtered_users[username] = user_data
                        else:
                            filtered_users = regular_users
                        
                        if filtered_users:
                            # Display total count
                            st.markdown(f"""
                            <div style="
                                background: #e3f2fd;
                                padding: 1rem;
                                border-radius: 10px;
                                margin-bottom: 1rem;
                                text-align: center;
                                border: 1px solid #bbdefb;
                            ">
                                <strong>จำนวนผู้ใช้ทั้งหมด: {len(filtered_users)} คน</strong>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            # Prepare data for table
                            table_data = []
                            for username, user_data in filtered_users.items():
                                # Calculate age from birth_date
                                age = "-"
                                if user_data.get('birth_date'):
                                    try:
                                        birth_date = datetime.datetime.strptime(user_data['birth_date'], '%Y-%m-%d')
                                        today = datetime.datetime.now()
                                        age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
                                    except:
                                        age = "-"
                                
                                # Format registration date
                                reg_date = "-"
                                if user_data.get('created_at'):
                                    try:
                                        created_at = datetime.datetime.fromisoformat(user_data['created_at'])
                                        reg_date = created_at.strftime('%d/%m/%Y %H:%M')
                                    except:
                                        reg_date = "-"
                                
                                table_data.append({
                                    'คำนำหน้า': user_data.get('title', '-'),
                                    'ชื่อ': user_data.get('first_name', '-'),
                                    'สกุล': user_data.get('last_name', '-'),
                                    'เบอร์โทรศัพท์': user_data.get('phone', '-'),
                                    'อีเมล': user_data.get('email', '-'),
                                    'รหัสบัตรประชาชน': user_data.get('citizen_id', '-'),
                                    'วันเดือนปีเกิด': user_data.get('birth_date', '-'),
                                    'อายุ': str(age),
                                    'สาขาวิชาที่จบ': user_data.get('major', '-'),
                                    'สถาบันการศึกษาที่จบ': user_data.get('school_name', '-'),
                                    'ที่อยู่': user_data.get('address', '-'),
                                    'จังหวัด': user_data.get('province', '-'),
                                    'GPAX': str(user_data.get('gpax', '-')),
                                    'วันเวลาที่ลงทะเบียน': reg_date
                                })
                            
                            
                            # Convert to DataFrame for better display
                            import pandas as pd
                            df = pd.DataFrame(table_data)
                            
                            # Display the dataframe with custom styling
                            st.dataframe(
                                df,
                                use_container_width=True,
                                hide_index=True,
                                column_config={
                                    'คำนำหน้า': st.column_config.TextColumn('คำนำหน้า', width='small'),
                                    'ชื่อ': st.column_config.TextColumn('ชื่อ', width='medium'),
                                    'สกุล': st.column_config.TextColumn('สกุล', width='medium'),
                                    'เบอร์โทรศัพท์': st.column_config.TextColumn('เบอร์โทรศัพท์', width='medium'),
                                    'อีเมล': st.column_config.TextColumn('อีเมล', width='large'),
                                    'รหัสบัตรประชาชน': st.column_config.TextColumn('รหัสบัตรประชาชน', width='large'),
                                    'วันเดือนปีเกิด': st.column_config.TextColumn('วันเดือนปีเกิด', width='medium'),
                                    'อายุ': st.column_config.TextColumn('อายุ', width='small'),
                                    'สาขาวิชาที่จบ': st.column_config.TextColumn('สาขาวิชาที่จบ', width='large'),
                                    'สถาบันการศึกษาที่จบ': st.column_config.TextColumn('สถาบันการศึกษาที่จบ', width='large'),
                                    'ที่อยู่': st.column_config.TextColumn('ที่อยู่', width='large'),
                                    'จังหวัด': st.column_config.TextColumn('จังหวัด', width='medium'),
                                    'GPAX': st.column_config.TextColumn('GPAX', width='small'),
                                    'วันเวลาที่ลงทะเบียน': st.column_config.TextColumn('วันเวลาที่ลงทะเบียน', width='large')
                                }
                            )
                            
                            st.markdown('</div>', unsafe_allow_html=True)
                            
                            # Export functionality
                            st.markdown("<br>", unsafe_allow_html=True)
                            col1, col2, col3 = st.columns([1, 1, 2])
                            
                            with col1:
                                # Download as CSV
                                csv = df.to_csv(index=False, encoding='utf-8-sig')
                                st.download_button(
                                    label="ดาวน์โหลด CSV",
                                    data=csv,
                                    file_name=f"users_list_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                    mime="text/csv",
                                    use_container_width=True
                                )
                            
                            with col2:
                                # Download as Excel
                                import io
                                buffer = io.BytesIO()
                                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                                    df.to_excel(writer, index=False, sheet_name='Users')
                                
                                st.download_button(
                                    label="ดาวน์โหลด Excel",
                                    data=buffer.getvalue(),
                                    file_name=f"users_list_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    use_container_width=True
                                )
                            
                        else:
                            st.markdown("""
                            <div style="
                                background: #fff3cd;
                                padding: 2rem;
                                border-radius: 15px;
                                text-align: center;
                                border: 1px solid #ffeaa7;
                                margin: 2rem 0;
                            ">
                                <div style="
                                    width: 80px;
                                    height: 80px;
                                    background: #ffeaa7;
                                    border-radius: 50%;
                                    margin: 0 auto 1rem;
                                    display: flex;
                                    align-items: center;
                                    justify-content: center;
                                    font-size: 2rem;
                                ">❓</div>
                                <h3 style="color: #856404; margin-bottom: 1rem;">ไม่พบผลการค้นหา</h3>
                                <p style="color: #856404; margin: 0;">ไม่พบผู้ใช้ที่ตรงกับคำค้นหา "{search_term}"</p>
                            </div>
                            """, unsafe_allow_html=True)
                            
                    else:
                        st.markdown("""
                        <div style="
                            background: #f8d7da;
                            padding: 2rem;
                            border-radius: 15px;
                            text-align: center;
                            border: 1px solid #f5c6cb;
                            margin: 2rem 0;
                        ">
                            <div style="
                                width: 80px;
                                height: 80px;
                                background: #f5c6cb;
                                border-radius: 50%;
                                margin: 0 auto 1rem;
                                display: flex;
                                align-items: center;
                                justify-content: center;
                                font-size: 2rem;
                            ">👤</div>
                            <h3 style="color: #721c24; margin-bottom: 1rem;">ไม่มีผู้ใช้ในระบบ</h3>
                            <p style="color: #721c24; margin: 0;">ยังไม่มีผู้ใช้ลงทะเบียนในระบบ</p>
                        </div>
                        """, unsafe_allow_html=True)
            
                with user_tab3:
                    # Header Section
                    st.markdown("""
                    <div style="
                        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
                        padding: 2.5rem;
                        border-radius: 20px;
                        color: white;
                        margin-bottom: 2rem;
                        box-shadow: 0 8px 25px rgba(0,0,0,0.15);
                        text-align: center;
                    ">
                        <div style="
                            width: 100px;
                            height: 100px;
                            background: rgba(255,255,255,0.2);
                            border-radius: 50%;
                            margin: 0 auto 1.5rem;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            font-size: 3rem;
                            backdrop-filter: blur(10px);
                        ">💬</div>
                        <h2 style="margin: 0 0 0.5rem 0; font-size: 2rem; font-weight: 600;">จัดการข้อความ</h2>
                        <p style="margin: 0; font-size: 1.1rem; opacity: 0.9;">ดูและจัดการข้อความจากผู้ใช้</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Load messages
                    messages = MessageManager.get_messages()
                    
                    if messages:
                        # Filter options
                        col1, col2 = st.columns([1, 1])
                        with col1:
                            filter_option = st.selectbox(
                                "กรองข้อความ",
                                ["ทั้งหมด", "ยังไม่ได้อ่าน", "อ่านแล้ว"]
                            )
                        
                        with col2:
                            message_type_filter = st.selectbox(
                                "ประเภทข้อความ",
                                ["ทั้งหมด", "ลืมรหัสผ่าน", "ปัญหาการอัพโหลดเอกสาร", "ปัญหาการลงทะเบียน", "อื่นๆ"]
                            )
                        
                        # Filter messages
                        filtered_messages = messages
                        
                        if filter_option == "ยังไม่ได้อ่าน":
                            filtered_messages = [msg for msg in filtered_messages if not msg.get('is_read', False)]
                        elif filter_option == "อ่านแล้ว":
                            filtered_messages = [msg for msg in filtered_messages if msg.get('is_read', False)]
                        
                        if message_type_filter != "ทั้งหมด":
                            type_mapping = {
                                "ลืมรหัสผ่าน": "forgot_password",
                                "ปัญหาการอัพโหลดเอกสาร": "document_upload_issue",
                                "ปัญหาการลงทะเบียน": "registration_issue",
                                "อื่นๆ": "other"
                            }
                            filtered_messages = [msg for msg in filtered_messages if msg.get('message_type') == type_mapping.get(message_type_filter)]
                        
                        # Sort by timestamp (newest first)
                        filtered_messages.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
                        
                        if filtered_messages:
                            st.info(f"**จำนวนข้อความ: {len(filtered_messages)} ข้อความ**")
                            
                            # Display messages
                            for i, message in enumerate(filtered_messages):
                                # Message card
                                read_status = "อ่านแล้ว" if message.get('is_read', False) else "ยังไม่ได้อ่าน"
                                read_color = "#28a745" if message.get('is_read', False) else "#dc3545"
                                
                                # Format timestamp
                                try:
                                    timestamp = datetime.datetime.fromisoformat(message.get('timestamp', ''))
                                    formatted_time = timestamp.strftime('%d/%m/%Y %H:%M')
                                except:
                                    formatted_time = message.get('timestamp', 'ไม่ทราบ')
                                
                                # Message type display
                                type_display = {
                                    "forgot_password": "ลืมรหัสผ่าน",
                                    "document_upload_issue": "ปัญหาการอัพโหลดเอกสาร",
                                    "registration_issue": "ปัญหาการลงทะเบียน",
                                    "other": "อื่นๆ"
                                }.get(message.get('message_type', 'other'), "อื่นๆ")
                                
                                # ดึงข้อมูลผู้ใช้จาก username
                                sender_user = UserManager.get_user(message.get('sender_username', ''))
                                sender_display = "ไม่ทราบ"
                                if sender_user:
                                    title = sender_user.get('title', '')
                                    first_name = sender_user.get('first_name', '')
                                    last_name = sender_user.get('last_name', '')
                                    citizen_id = sender_user.get('citizen_id', '')
                                    sender_display = f"{title}{first_name} {last_name} ({citizen_id})"
                                
                                with st.expander(f"{type_display} | {message.get('subject', 'ไม่มีหัวข้อ')} | {sender_display} | {read_status}", expanded=False):
                                    # แสดงข้อมูลข้อความในรูปแบบ Streamlit components
                                    
                                    # แสดงข้อมูลผู้ส่งและวันที่ส่ง
                                    col1, col2 = st.columns(2)
                                    with col1:
                                        # ดึงข้อมูลผู้ใช้เพื่อแสดงชื่อ-สกุล และรหัสบัตรประชาชน
                                        sender_user = UserManager.get_user(message.get('sender_username', ''))
                                        if sender_user:
                                            sender_display = f"{sender_user.get('first_name', '')} {sender_user.get('last_name', '')} ({sender_user.get('citizen_id', '')})"
                                        else:
                                            sender_display = message.get('sender_username', 'ไม่ทราบ')
                                        st.info(f"**ผู้ส่ง:** {sender_display}")
                                    with col2:
                                        st.info(f"**วันที่ส่ง:** {formatted_time}")
                                    
                                    # แสดงประเภทและสถานะ
                                    col3, col4 = st.columns(2)
                                    with col3:
                                        st.info(f"**ประเภท:** {type_display}")
                                    with col4:
                                        if message.get('is_read', False):
                                            st.success(f"**สถานะ:** {read_status}")
                                        else:
                                            st.error(f"**สถานะ:** {read_status}")
                                    
                                    # แสดงหัวข้อ
                                    st.write(f"**หัวข้อ:** {message.get('subject', 'ไม่มีหัวข้อ')}")
                                    
                                    # แสดงเนื้อหาข้อความ
                                    st.write("**เนื้อหาข้อความ:**")
                                    st.text_area(
                                        "",
                                        value=message.get('message', 'ไม่มีข้อความ'),
                                        height=100,
                                        disabled=True,
                                        key=f"message_content_{i}"
                                    )
                                    
                                    # แสดงการตอบกลับที่มีอยู่แล้ว (ถ้ามี)
                                    if message.get('reply'):
                                        st.success("**การตอบกลับจากแอดมิน**")
                                        st.text_area(
                                            "",
                                            value=message.get('reply', ''),
                                            height=100,
                                            disabled=True,
                                            key=f"reply_content_{i}"
                                        )
                                        
                                        # แสดงวันที่ตอบกลับ
                                        if message.get('reply_timestamp'):
                                            try:
                                                reply_timestamp = datetime.datetime.fromisoformat(message.get('reply_timestamp', ''))
                                                formatted_reply_time = reply_timestamp.strftime('%d/%m/%Y %H:%M')
                                                st.caption(f"ตอบกลับเมื่อ: {formatted_reply_time}")
                                            except:
                                                pass
                                    
                                    # Action buttons
                                    st.write("**การดำเนินการ**")
                                    
                                    col1, col2 = st.columns([1, 1])
                                    
                                    with col1:
                                        if not message.get('is_read', False):
                                            if st.button(f"ทำเครื่องหมายว่าอ่านแล้ว", key=f"read_{message.get('id')}", use_container_width=True):
                                                if MessageManager.mark_as_read(message.get('id')):
                                                    st.success("ทำเครื่องหมายว่าอ่านแล้วเรียบร้อย")
                                                    st.rerun()
                                                else:
                                                    st.error("เกิดข้อผิดพลาดในการทำเครื่องหมาย")
                                    
                                    with col2:
                                        if st.button(f"ลบข้อความ", key=f"delete_{message.get('id')}", use_container_width=True, type="secondary"):
                                            if MessageManager.delete_message(message.get('id')):
                                                st.success("ลบข้อความเรียบร้อย")
                                                st.rerun()
                                            else:
                                                st.error("เกิดข้อผิดพลาดในการลบข้อความ")
                        else:
                            st.warning("**ไม่พบข้อความที่ตรงกับเงื่อนไข**\n\nลองเปลี่ยนตัวกรองเพื่อดูข้อความอื่นๆ")
                    else:
                        st.error("**ไม่มีข้อความ**\n\nยังไม่มีผู้ใช้ส่งข้อความมาในระบบ")
                    
    else:
        # Regular user interface
        # Check if user wants to show message form
        if st.session_state.get('show_message_form', False):
            # Message form interface
            st.error("**ส่งข้อความให้แอดมิน**\n\nหากคุณลืมรหัสผ่านหรือมีปัญหาอื่นๆ กรุณาส่งข้อความมาที่นี่")
            
            # Back button
            if st.button("กลับไปหน้าหลัก", use_container_width=True):
                st.session_state.show_message_form = False
                st.rerun()
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # Message form
            with st.form("message_form"):
                st.info("**กรอกข้อมูลข้อความ**")
                
                # Message type selection
                message_type = st.selectbox(
                    "ประเภทปัญหา",
                    ["ปัญหาการอัพโหลดเอกสาร", "ปัญหาการเข้าสู่ระบบ", "ปัญหาข้อมูลส่วนตัว", "อื่นๆ"],
                    help="เลือกประเภทปัญหาที่คุณพบ"
                )
                
                # Subject
                subject = st.text_input(
                    "หัวข้อ",
                    placeholder="กรุณาระบุหัวข้อของปัญหา",
                    help="ระบุหัวข้อสั้นๆ ที่อธิบายปัญหาของคุณ"
                )
                
                # Message content
                message_content = st.text_area(
                    "รายละเอียดปัญหา",
                    placeholder="กรุณาอธิบายปัญหาที่พบโดยละเอียด...",
                    height=150,
                    help="อธิบายปัญหาที่คุณพบโดยละเอียดเพื่อให้แอดมินสามารถช่วยเหลือได้อย่างมีประสิทธิภาพ"
                )
                
                st.markdown('</div>', unsafe_allow_html=True)
                
                # Submit button
                submitted = st.form_submit_button(
                    "ส่งข้อความ",
                    use_container_width=True
                )
                
                if submitted:
                    if not subject.strip():
                        st.error("กรุณากรอกหัวข้อ")
                    elif not message_content.strip():
                        st.error("กรุณากรอกรายละเอียดปัญหา")
                    else:
                        # Send message
                        success, message = MessageManager.send_message(
                            sender_username=user['username'],
                            subject=subject,
                            message=message_content,
                            message_type=message_type
                        )
                        
                        if success:
                            st.success("ส่งข้อความเรียบร้อยแล้ว! แอดมินจะตอบกลับโดยเร็วที่สุด")
                            st.balloons()
                            time.sleep(2)
                            st.session_state.show_message_form = False
                            st.rerun()
                        else:
                            st.error(f"เกิดข้อผิดพลาด: {message}")
        
        else:
            # Normal tabs interface
            tab1, tab2, tab3 = st.tabs(["อัพโหลดเอกสาร", "เอกสารของฉัน", "ข้อมูลส่วนตัว"])
            
            with tab1:
                st.markdown("""
                <div style="
                    background: linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%);
                    padding: 2.5rem;
                    border-radius: 20px;
                    color: white;
                    margin-bottom: 2rem;
                    box-shadow: 0 8px 25px rgba(0,0,0,0.15);
                    text-align: center;
                ">
                    <div style="
                        width: 100px;
                        height: 100px;
                        background: rgba(255,255,255,0.2);
                        border-radius: 50%;
                        margin: 0 auto 1.5rem;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 3rem;
                        backdrop-filter: blur(10px);
                    ">📄</div>
                    <h2 style="margin: 0 0 0.5rem 0; font-size: 2rem; font-weight: 600;">อัพโหลดเอกสารของคุณ</h2>
                    <p style="margin: 0; opacity: 0.9; font-size: 1.1rem;">กรุณากรอกข้อมูลที่จำเป็นและอัพโหลดเอกสารของคุณ</p>
                </div>
                """, unsafe_allow_html=True)
                
                # User Information Section with Card Design
                st.markdown("""
                <div style="
                    background: #f8f9fa;
                    padding: 2rem;
                    border-radius: 15px;
                    border-left: 4px solid #3b82f6;
                    margin-bottom: 2rem;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.08);
                ">
                    <h3 style="color: #3b82f6; margin-bottom: 1.5rem; display: flex; align-items: center; font-size: 1.4rem;">
                        ข้อมูลผู้สมัคร
                    </h3>
                """, unsafe_allow_html=True)
                
                col1, col2 = st.columns([1, 3])
                with col1:
                    st.markdown("""
                    <div style="
                        background: rgba(59,130,246,0.1);
                        padding: 1rem;
                        border-radius: 10px;
                        text-align: center;
                        margin-bottom: 1rem;
                    ">
                        <strong style="color: #3b82f6;">คำนำหน้า</strong><br>
                        <span style="color: #495057; font-size: 1.1rem;">{}</span>
                    </div>
                    """.format(user.get('title', 'ไม่ระบุ')), unsafe_allow_html=True)
                with col2:
                    full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}"
                    st.markdown("""
                    <div style="    
                        background: rgba(0,123,255,0.1);
                        padding: 1rem;
                        border-radius: 10px;
                        text-align: center;
                        margin-bottom: 1rem;
                    ">
                        <strong style="color: #3b82f6;">ชื่อ-สกุล</strong><br>
                        <span style="color: #495057; font-size: 1.1rem;">{}</span>
                    </div>
                    """.format(full_name), unsafe_allow_html=True)
                
                # Class Schedule Section integrated within user info card
                st.markdown("""
                    <div style="
                        background: rgba(30,58,138,0.1);
                        padding: 1.5rem;
                        border-radius: 10px;
                        margin-bottom: 1.5rem;
                    ">
                        <h4 style="color: #1e3a8a; margin-bottom: 1rem; display: flex; align-items: center; font-size: 1.2rem;">
                            เลือกตารางเรียน
                        </h4>
                        <p style="color: #6c757d; margin-bottom: 1rem; font-size: 0.95rem; line-height: 1.5;">
                            ถ้าเรียนหลักสูตร Cyber Security ให้เลือกวันที่ต้องการเรียน (ถ้าไม่ได้เรียนให้เลือกไม่เรียน) <span style="color: #dc3545;">*</span>
                        </p>
                """, unsafe_allow_html=True)
                
                # Radio buttons for class schedule within the same padding
                schedule_options = [
                    "ไม่เรียน",
                    "เรียน จันทร์ - ศุกร์ (วันธรรมดา)",
                    "เรียน เสาร์ - อาทิตย์ (วันหยุด)"
                ]
                
                selected_schedule = st.radio(
                    "เลือกตารางเรียน",
                    schedule_options,
                    index=0,
                    key="user_schedule_selection",
                    label_visibility="collapsed"
                )
                
                st.markdown('</div>', unsafe_allow_html=True)
                
                # Required Documents Section with Beautiful Header
                st.markdown("""
                <div style="
                    background: linear-gradient(135deg, #3b82f6 0%, #1e40af 100%);
                    padding: 2rem;
                    border-radius: 15px;
                    color: white;
                    margin-bottom: 2rem;
                    box-shadow: 0 6px 20px rgba(59, 130, 246, 0.3);
                    text-align: center;
                ">
                    <div style="
                        width: 80px;
                        height: 80px;
                        background: rgba(255,255,255,0.2);
                        border-radius: 50%;
                        margin: 0 auto 1rem;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 2.5rem;
                        backdrop-filter: blur(10px);
                    ">📋</div>
                    <h3 style="margin: 0 0 0.5rem 0; font-size: 1.6rem; font-weight: 600;">เอกสารที่จำเป็น</h3>
                    <p style="margin: 0; opacity: 0.9; font-size: 1rem;">กรุณาอัพโหลดเอกสารที่จำเป็นทั้งหมดในรูปแบบที่ถูกต้อง (PDF, JPG, PNG)</p>
                </div>
                """, unsafe_allow_html=True)
                
                with st.form("upload_form"):
                    # Document upload sections with beautiful cards
                    documents = [
                        {
                            "title": "1. รูปถ่าย",
                            "icon": "",
                            "color": "#007bff",
                            "key": "photo_upload",
                            "types": ['jpg', 'jpeg', 'png'],
                            "help": "รูปถ่ายหน้าตรง ชัดเจน • JPG, JPEG, PNG • สูงสุด 200MB",
                            "required": True
                        },
                        {
                            "title": "2. สำเนาบัตรประจำตัวประชาชน",
                            "icon": "",
                            "color": "#28a745",
                            "key": "id_card_upload",
                            "types": ['pdf', 'jpg', 'jpeg', 'png'],
                            "help": "สำเนาบัตรประชาชนที่ชัดเจน • PDF, JPG, JPEG, PNG • สูงสุด 200MB",
                            "required": True
                        },
                        {
                            "title": "3. สำเนาใบแสดงผลการเรียน",
                            "icon": "",
                            "color": "#ffc107",
                            "key": "transcript_upload",
                            "types": ['pdf', 'jpg', 'jpeg', 'png'],
                            "help": "ใบแสดงผลการเรียน (ม.6) • PDF, JPG, JPEG, PNG • สูงสุด 200MB",
                            "required": True
                        },
                        {
                            "title": "4. สำเนาหลักฐานการเปลี่ยนชื่อ-สกุล หรือหลักฐานอื่นๆ",
                            "icon": "",
                            "color": "#6c757d",
                            "key": "other_upload",
                            "types": ['pdf', 'jpg', 'jpeg', 'png'],
                            "help": "เฉพาะกรณีที่มีการเปลี่ยนชื่อ-สกุล • PDF, JPG, JPEG, PNG • สูงสุด 200MB",
                            "required": False
                        }
                    ]
                    
                    uploaded_files = {}
                    
                    for doc in documents:
                        # Create card for each document
                        required_text = " *" if doc["required"] else " (ไม่บังคับ)"
                        st.markdown(f"""
                        <div style="
                            background: linear-gradient(135deg, {doc['color']}15 0%, {doc['color']}05 100%);
                            padding: 1.5rem;
                            border-radius: 15px;
                            border-left: 4px solid {doc['color']};
                            margin-bottom: 1.5rem;
                            box-shadow: 0 4px 15px rgba(0,0,0,0.05);
                        ">
                            <h4 style="color: {doc['color']}; margin-bottom: 1rem; display: flex; align-items: center; font-size: 1.2rem;">
                                {doc['title']}{required_text}
                            </h4>
                            <p style="color: #6c757d; margin-bottom: 1rem; font-size: 0.9rem; line-height: 1.5;">
                                {doc['help']}
                            </p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # File uploader
                        uploaded_files[doc['key']] = st.file_uploader(
                            f"เลือกไฟล์สำหรับ {doc['title']}",
                            type=doc['types'],
                            help=doc['help'],
                            key=doc['key'],
                            label_visibility="collapsed"
                        )
                        
                        st.markdown("<br>", unsafe_allow_html=True)
                    
                    # Submit button with enhanced styling
                    st.markdown("<br>", unsafe_allow_html=True)
                    submit = st.form_submit_button(
                        "อัพโหลดเอกสารทั้งหมด", 
                        use_container_width=True,
                        type="primary"
                    )
                    
                    # Extract individual file variables for compatibility
                    photo_file = uploaded_files['photo_upload']
                    id_card_file = uploaded_files['id_card_upload']
                    transcript_file = uploaded_files['transcript_upload']
                    other_file = uploaded_files['other_upload']
                    
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
                            
                            # Remove all existing files for this user before uploading new ones
                            try:
                                safe_name = f"{user['first_name']}-{user['last_name']}".replace(' ', '-')
                                user_file_prefix = f"{user['citizen_id']}_{safe_name}_"
                                
                                # Find and remove all files that belong to this user
                                for existing_file in os.listdir(UPLOAD_DIR):
                                    if existing_file.startswith(user_file_prefix):
                                        existing_file_path = os.path.join(UPLOAD_DIR, existing_file)
                                        try:
                                            os.remove(existing_file_path)
                                            # Log file removal
                                            log_entry = f"{datetime.datetime.now().isoformat()} - Old file removed for {user['username']}: {existing_file}\n"
                                            with open(os.path.join(LOG_DIR, 'user_changes.log'), 'a', encoding='utf-8') as f:
                                                f.write(log_entry)
                                        except Exception as e:
                                            error_messages.append(f"ไม่สามารถลบไฟล์เก่า {existing_file} ได้: {str(e)}")
                            except Exception as e:
                                error_messages.append(f"เกิดข้อผิดพลาดในการตรวจสอบไฟล์เก่า: {str(e)}")
                            
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
                
                # Upload guidelines with enhanced design
                st.markdown("""
                <div style="
                    background: linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%);
                    padding: 2rem;
                    border-radius: 15px;
                    color: white;
                    margin: 2rem 0;
                    box-shadow: 0 6px 20px rgba(30, 64, 175, 0.3);
                ">
                    <h3 style="margin: 0 0 1.5rem 0; display: flex; align-items: center; font-size: 1.5rem;">
                        คำแนะนำการอัพโหลดเอกสาร
                    </h3>
                </div>
                """, unsafe_allow_html=True)
                
                # Guidelines content with cards
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("""
                    <div style="
                        background: #ffffff;
                        padding: 2rem;
                        border-radius: 15px;
                        border-left: 4px solid #1e40af;
                        margin-bottom: 1.5rem;
                        box-shadow: 0 4px 15px rgba(0,0,0,0.08);
                    ">
                        <h4 style="color: #1e40af; margin-bottom: 1.5rem; display: flex; align-items: center;">
                            เอกสารที่จำเป็น
                        </h4>
                        <div style="color: #495057; line-height: 1.8;">
                            <div style="margin-bottom: 0.8rem; display: flex; align-items: center;">
                                <span style="color: #1e40af; margin-right: 0.5rem;"></span>
                                <strong>รูปถ่าย</strong> <span style="color: #dc3545;">*</span><br>
                                <small style="color: #6c757d; margin-left: 1.5rem;">รูปถ่ายหน้าตรง ชัดเจน</small>
                            </div>
                            <div style="margin-bottom: 0.8rem; display: flex; align-items: center;">
                                <span style="color: #28a745; margin-right: 0.5rem;"></span>
                                <strong>สำเนาบัตรประชาชน</strong> <span style="color: #dc3545;">*</span><br>
                                <small style="color: #6c757d; margin-left: 1.5rem;">สำเนาบัตรประชาชนที่ชัดเจน</small>
                            </div>
                            <div style="margin-bottom: 0.8rem; display: flex; align-items: center;">
                                <span style="color: #ffc107; margin-right: 0.5rem;"></span>
                                <strong>ใบแสดงผลการเรียน</strong> <span style="color: #dc3545;">*</span><br>
                                <small style="color: #6c757d; margin-left: 1.5rem;">ใบแสดงผลการเรียน (ม.6)</small>
                            </div>
                            <div style="margin-bottom: 0.8rem; display: flex; align-items: center;">
                                <span style="color: #6c757d; margin-right: 0.5rem;"></span>
                                <strong>หลักฐานการเปลี่ยนชื่อ-สกุล</strong><br>
                                <small style="color: #6c757d; margin-left: 1.5rem;">เฉพาะกรณีที่มีการเปลี่ยนชื่อ-สกุล</small>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col2:
                    st.markdown("""
                    <div style="
                        background: #ffffff;
                        padding: 2rem;
                        border-radius: 15px;
                        border-left: 4px solid #28a745;
                        margin-bottom: 1.5rem;
                        box-shadow: 0 4px 15px rgba(0,0,0,0.08);
                    ">
                        <h4 style="color: #28a745; margin-bottom: 1.5rem; display: flex; align-items: center;">
                            ข้อกำหนดไฟล์
                        </h4>
                        <div style="color: #495057; line-height: 1.8;">
                            <div style="margin-bottom: 0.8rem; display: flex; align-items: center;">
                                <span style="color: #dc3545; margin-right: 0.5rem;"></span>
                                <span>ขนาดไฟล์ไม่เกิน <strong>200 MB</strong></span>
                            </div>
                            <div style="margin-bottom: 0.8rem; display: flex; align-items: center;">
                                <span style="color: #007bff; margin-right: 0.5rem;"></span>
                                <span>รองรับ: <strong>PDF, JPG, JPEG, PNG</strong></span>
                            </div>
                            <div style="margin-bottom: 0.8rem; display: flex; align-items: center;">
                                <span style="color: #ffc107; margin-right: 0.5rem;"></span>
                                <span>ไฟล์ต้อง<strong>ชัดเจน อ่านได้</strong></span>
                            </div>
                            <div style="margin-bottom: 0.8rem; display: flex; align-items: center;">
                                <span style="color: #dc3545; margin-right: 0.5rem;"></span>
                                <span>เอกสารที่มี <strong style="color: #dc3545;">*</strong> เป็นเอกสารจำเป็น</span>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                
                # Additional notes
                st.markdown("""
                <div style="
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    padding: 1.5rem;
                    border-radius: 15px;
                    color: white;
                    margin: 1.5rem 0;
                    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
                ">
                    <h4 style="margin: 0 0 1rem 0; display: flex; align-items: center;">
                        <span style="margin-right: 0.8rem;">💡</span> หมายเหตุสำคัญ
                    </h4>
                    <div style="opacity: 0.9; line-height: 1.6;">
                        <p style="margin: 0.5rem 0;">• ระบบจะตั้งชื่อไฟล์ใหม่ตามรูปแบบมาตรฐาน</p>
                        <p style="margin: 0.5rem 0;">• สามารถอัพโหลดไฟล์เดิมซ้ำได้ (จะเขียนทับไฟล์เก่า)</p>
                        <p style="margin: 0.5rem 0;">• กรุณาตรวจสอบความถูกต้องของเอกสารก่อนอัพโหลด</p>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        
            with tab2:
                # Center container start
                st.markdown('<div class="center-container">', unsafe_allow_html=True)
                
                # Documents Header Card
                st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%);
                    padding: 2rem;
                    border-radius: 15px;
                    color: white;
                    margin-bottom: 1.5rem;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                ">
                    <div style="text-align: center; margin-bottom: 1rem;">
                        <div style="
                            width: 80px;
                            height: 80px;
                            background: rgba(255,255,255,0.2);
                            border-radius: 50%;
                            margin: 0 auto 1rem;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            font-size: 2rem;
                    ">📁</div>
                    <h3 style="margin: 0; font-size: 1.5rem;">เอกสารของฉัน</h3>
                    <p style="margin: 0.5rem 0 0 0; opacity: 0.9;">@{user.get('username', '')}</p>
                </div>
                </div>
                """, unsafe_allow_html=True)
                
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
                        # Documents Container with compact header
                        st.markdown("""
                        <div style="
                            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                            padding: 1.5rem;
                            border-radius: 15px;
                            border: 1px solid #dee2e6;
                            margin-bottom: 1.5rem;
                            box-shadow: 0 4px 15px rgba(0,0,0,0.06);
                        ">
                            <div style="text-align: center; margin-bottom: 1rem;">
                                <div style="
                                    width: 50px;
                                    height: 50px;
                                    background: linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%);
                                    border-radius: 50%;
                                    margin: 0 auto 0.5rem;
                                    display: flex;
                                    align-items: center;
                                    justify-content: center;
                                    font-size: 1.2rem;
                                    color: white;
                                    box-shadow: 0 2px 8px rgba(30, 64, 175, 0.2);
                                ">📄</div>
                                <h3 style="color: #1e40af; margin: 0 0 0.25rem 0; font-size: 1.2rem; font-weight: 600;">รายการเอกสารที่อัพโหลด</h3>
                                <p style="color: #6c757d; margin: 0; font-size: 0.9rem;">จัดการและดูเอกสารของคุณ</p>
                            </div>
                        
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Group files by document type
                    files_by_type = {}
                    for file_info in user_files:
                        # Parse document type from filename
                        parts = file_info['filename'].split('_')
                        doc_type = parts[2].split('.')[0] if len(parts) > 2 else 'ไม่ทราบ'
                        doc_type = doc_type.replace('-', ' ')
                        
                        # Set appropriate icon based on document type
                        doc_icon = "DOC"
                        if 'บัตรประชาชน' in doc_type or 'citizen' in doc_type.lower():
                            doc_icon = "ID"
                        elif 'ทะเบียนบ้าน' in doc_type or 'house' in doc_type.lower():
                            doc_icon = "HOME"
                        elif 'ประกาศนียบัตร' in doc_type or 'certificate' in doc_type.lower() or 'ใบรับรอง' in doc_type:
                            doc_icon = "EDU"
                        elif 'ใบสมัคร' in doc_type or 'application' in doc_type.lower():
                            doc_icon = "DOC"
                        elif 'รูปถ่าย' in doc_type or 'photo' in doc_type.lower() or 'picture' in doc_type.lower():
                            doc_icon = "IMG"
                        elif 'transcript' in doc_type.lower() or 'ใบแสดงผลการเรียน' in doc_type:
                            doc_icon = "XLS"
                        
                        if doc_type not in files_by_type:
                            files_by_type[doc_type] = {'files': [], 'icon': doc_icon}
                        files_by_type[doc_type]['files'].append(file_info)
                    
                    # Display files grouped by type
                    for doc_type, type_info in files_by_type.items():
                        files = sorted(type_info['files'], key=lambda x: x['modified'], reverse=True)
                        doc_icon = type_info['icon']
                        
                        # Document type header
                        st.markdown(f"""
                        <div style="
                            background: linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%);
                            color: white;
                            padding: 1rem 1.5rem;
                            border-radius: 12px 12px 0 0;
                            margin: 1.5rem 0 0 0;
                            display: flex;
                            align-items: center;
                            gap: 0.75rem;
                            font-weight: 600;
                            box-shadow: 0 4px 15px rgba(30, 64, 175, 0.3);
                        ">
                            <span style="font-size: 1.5rem;">{doc_icon}</span>
                            <span style="font-size: 1.1rem;">{doc_type}</span>
                            <span style="
                                background: rgba(255,255,255,0.2);
                                padding: 0.25rem 0.75rem;
                                border-radius: 20px;
                                font-size: 0.85rem;
                                margin-left: auto;
                            ">{len(files)} ไฟล์</span>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        for i, file_info in enumerate(files):
                            # Determine file extension and appropriate styling
                            file_ext = file_info['filename'].split('.')[-1].lower()
                            if file_ext in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp']:
                                file_type_icon = "IMG"
                                file_type_color = "#10b981"
                                file_type_name = "รูปภาพ"
                            elif file_ext == 'pdf':
                                file_type_icon = "PDF"
                                file_type_color = "#ef4444"
                                file_type_name = "PDF"
                            elif file_ext in ['doc', 'docx']:
                                file_type_icon = "DOC"
                                file_type_color = "#2563eb"
                                file_type_name = "Word"
                            elif file_ext in ['xls', 'xlsx']:
                                file_type_icon = "XLS"
                                file_type_color = "#16a34a"
                                file_type_name = "Excel"
                            else:
                                file_type_icon = "DOC"
                                file_type_color = "#6b7280"
                                file_type_name = "เอกสาร"
                            
                            # File card with enhanced design
                            border_radius = "0 0 12px 12px" if i == len(files) - 1 else "0"
                            st.markdown(f"""
                            <div style="
                                background: white;
                                padding: 1.5rem;
                                border: 1px solid #e5e7eb;
                                border-top: none;
                                border-radius: {border_radius};
                                margin: 0;
                                transition: all 0.3s ease;
                                position: relative;
                            " onmouseover="this.style.backgroundColor='#f8fafc'; this.style.transform='translateX(5px)';" onmouseout="this.style.backgroundColor='white'; this.style.transform='translateX(0)';">
                                <div style="display: flex; align-items: center; justify-content: space-between;">
                                    <div style="display: flex; align-items: center; flex: 1;">
                                        <div style="
                                            width: 60px;
                                            height: 60px;
                                            background: linear-gradient(135deg, {file_type_color} 0%, {file_type_color}dd 100%);
                                            border-radius: 12px;
                                            display: flex;
                                            align-items: center;
                                            justify-content: center;
                                            margin-right: 1.5rem;
                                            color: white;
                                            font-size: 1.5rem;
                                            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                                        ">{file_type_icon}</div>
                                        <div style="flex: 1;">
                                            <h6 style="margin: 0 0 0.5rem 0; color: #1f2937; font-size: 1rem; font-weight: 600; line-height: 1.3;">{file_info['filename']}</h6>
                                            <div style="display: flex; gap: 1.5rem; flex-wrap: wrap; margin-bottom: 0.5rem;">
                                                <div style="display: flex; align-items: center; gap: 0.5rem;">
                                                    <span style="color: #6b7280; font-size: 0.8rem;">FILE</span>
                                                    <span style="color: #6b7280; font-size: 0.85rem;">{file_type_name}</span>
                                                </div>
                                                <div style="display: flex; align-items: center; gap: 0.5rem;">
                                                    <span style="color: #6b7280; font-size: 0.8rem;">💾</span>
                                                    <span style="color: #6b7280; font-size: 0.85rem;">{file_info['size']/1024:.1f} KB</span>
                                                </div>
                                                <div style="display: flex; align-items: center; gap: 0.5rem;">
                                                    <span style="color: #6b7280; font-size: 0.8rem;">📅</span>
                                                    <span style="color: #6b7280; font-size: 0.85rem;">{datetime.datetime.fromtimestamp(file_info['modified']).strftime('%d/%m/%Y')}</span>
                                                </div>
                                                <div style="display: flex; align-items: center; gap: 0.5rem;">
                                                    <span style="color: #6b7280; font-size: 0.8rem;">🕒</span>
                                                    <span style="color: #6b7280; font-size: 0.85rem;">{datetime.datetime.fromtimestamp(file_info['modified']).strftime('%H:%M น.')}</span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            """, unsafe_allow_html=True)
                        
                        # Action buttons integrated within the document card
                        st.markdown("""
                        <style>
                        .doc-action-btn {
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            color: white;
                            border: none;
                            padding: 0.5rem 1rem;
                            border-radius: 8px;
                            font-size: 0.9rem;
                            font-weight: 500;
                            cursor: pointer;
                            transition: all 0.3s ease;
                            text-decoration: none;
                            display: inline-block;
                            margin: 0.2rem;
                        }
                        .doc-action-btn:hover {
                            transform: translateY(-2px);
                            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
                        }
                        .doc-preview-btn {
                            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
                        }
                        .doc-download-btn {
                            background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
                        }
                        .doc-edit-btn {
                            background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
                        }
                        </style>
                        """, unsafe_allow_html=True)
                        
                        # เพิ่ม CSS สำหรับปุ่มที่สวยงาม
                        st.markdown("""
                        <style>
                        .user-action-buttons-container {
                            display: flex;
                            gap: 10px;
                            align-items: center;
                            justify-content: center;
                            margin: 1rem 0;
                            padding: 1rem;
                            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                            border-radius: 15px;
                            border: 1px solid rgba(0,0,0,0.1);
                            box-shadow: 0 4px 15px rgba(0,0,0,0.08);
                        }
                        .user-action-btn {
                            flex: 1;
                            min-height: 45px;
                            border-radius: 10px;
                            font-weight: 600;
                            transition: all 0.3s ease;
                            border: none;
                            cursor: pointer;
                            font-size: 0.95rem;
                        }
                        .user-action-btn:hover {
                            transform: translateY(-3px);
                            box-shadow: 0 6px 20px rgba(0,0,0,0.15);
                        }
                        </style>
                        """, unsafe_allow_html=True)
                        
                        # จัดเรียงปุ่มทั้ง 3 ปุ่มในแถวเดียวกันแบบสวยงาม
                        col1, col2, col3 = st.columns([1, 1, 1], gap="medium")
                        
                        # ปุ่มดูตัวอย่าง
                        preview_active = st.session_state.get(f"show_preview_{file_info['filename']}", False)
                        preview_button_text = "ปิด" if preview_active else "ดู"
                        preview_button_type = "secondary" if preview_active else "primary"
                        
                        with col1:
                            if st.button(preview_button_text, key=f"preview_{file_info['filename']}", help="คลิกเพื่อดูตัวอย่างเอกสาร", type=preview_button_type, use_container_width=True):
                                # Clear other preview and edit states for better UX
                                for key in list(st.session_state.keys()):
                                    if key.startswith("show_preview_") and key != f"show_preview_{file_info['filename']}":
                                        st.session_state[key] = False
                                st.session_state[f"show_preview_{file_info['filename']}"] = not preview_active
                                st.rerun()
                        
                        with col2:
                            # Download button with enhanced styling and feedback
                            try:
                                with open(file_info['path'], 'rb') as f:
                                    file_data = f.read()
                                    file_size = len(file_data) / (1024 * 1024)  # Size in MB
                                    
                                    st.download_button(
                                        "ดาวน์โหลด",
                                        file_data,
                                        file_name=file_info['filename'],
                                        key=f"download_{file_info['filename']}",
                                        help=f"คลิกเพื่อดาวน์โหลดเอกสาร {file_info['filename']} (ขนาด {file_size:.1f} MB)",
                                        use_container_width=True,
                                        type="primary"
                                    )
                            except Exception as e:
                                st.error(f"ไม่สามารถเตรียมไฟล์สำหรับดาวน์โหลดได้: {str(e)}")
                        
                        with col3:
                            # Delete button
                            if st.button("ลบ", key=f"delete_{file_info['filename']}", help="คลิกเพื่อลบเอกสารนี้", use_container_width=True, type="secondary"):
                                st.session_state[f"confirm_delete_{file_info['filename']}"] = True
                                st.rerun()
                            
                            # Delete confirmation dialog
                            if st.session_state.get(f"confirm_delete_{file_info['filename']}", False):
                                st.markdown("""
                                <div style="
                                    background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%);
                                    padding: 1rem;
                                    border-radius: 10px;
                                    border: 1px solid rgba(239, 68, 68, 0.3);
                                    margin: 0.5rem 0;
                                ">
                                    <p style="color: #dc2626; margin: 0; font-size: 0.9rem; text-align: center;">คุณแน่ใจหรือไม่ที่จะลบเอกสารนี้?</p>
                                </div>
                                """, unsafe_allow_html=True)
                                
                                col_confirm, col_cancel = st.columns(2)
                                with col_confirm:
                                    if st.button("ยืนยันลบ", key=f"confirm_delete_yes_{file_info['filename']}", use_container_width=True, type="primary"):
                                        try:
                                            os.remove(file_info['path'])
                                            st.session_state[f"confirm_delete_{file_info['filename']}"] = False
                                            st.success(f"ลบเอกสาร {file_info['filename']} เรียบร้อยแล้ว")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"เกิดข้อผิดพลาดในการลบเอกสาร: {str(e)}")
                                
                                with col_cancel:
                                    if st.button("ยกเลิก", key=f"confirm_delete_no_{file_info['filename']}", use_container_width=True):
                                        st.session_state[f"confirm_delete_{file_info['filename']}"] = False
                                        st.rerun()
                        
                        # Show preview if requested - moved outside columns for proper display
                        if st.session_state.get(f"show_preview_{file_info['filename']}", False):
                            if file_info['filename'].lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                                # Add padding and styling for image display
                                st.markdown("""
                                <div style="
                                    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                                    border-radius: 20px;
                                    margin: 1rem 0;
                                    padding: 1rem;
                                    box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                                ">
                                """, unsafe_allow_html=True)
                                
                                # Center the image using columns with more space
                                col1, col2, col3 = st.columns([0.5, 3, 0.5])
                                with col2:
                                    st.image(file_info['path'], caption=file_info['filename'], use_container_width=True)
                                
                                st.markdown("</div>", unsafe_allow_html=True)
                            elif file_info['filename'].lower().endswith('.pdf'):
                                # Center the PDF display using columns with more space (same as image)
                                col1, col2, col3 = st.columns([0.5, 3, 0.5])
                                with col2:
                                    # Display PDF using iframe with base64 encoding
                                    try:
                                        import base64
                                        with open(file_info['path'], "rb") as f:
                                            pdf_data = f.read()
                                        pdf_base64 = base64.b64encode(pdf_data).decode('utf-8')
                                        
                                        # Display PDF in iframe without padding
                                        st.markdown(f"""
                                        <iframe src="data:application/pdf;base64,{pdf_base64}" 
                                                width="100%" 
                                                height="600" 
                                                style="border: none; border-radius: 10px;">
                                        </iframe>
                                        """, unsafe_allow_html=True)
                                    except Exception as e:
                                        # Fallback with styled preview card (same as image style)
                                        st.markdown(f"""
                                        <div style="
                                            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                                            border-radius: 20px;
                                            text-align: center;
                                            padding: 2rem;
                                            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                                            border: 1px solid rgba(0,0,0,0.1);
                                        ">
                                            <div style="font-size: 3rem; margin-bottom: 1rem;"></div>
                                            <h4 style="color: #495057; margin: 0 0 1rem 0; font-size: 1.3rem; font-weight: 600;">{file_info['filename']}</h4>
                                            <p style="color: #6c757d; margin: 0; font-size: 1rem;">PDF Document</p>
                                            </div>
                                            """, unsafe_allow_html=True)
                    else:
                        # st.info("ไม่มีเอกสารที่อัพโหลด")
                        pass
                else:
                    # st.info("ไม่มีเอกสารที่อัพโหลด")
                    pass
        
            with tab3:
                st.subheader("ข้อมูลส่วนตัว")
                
                # Profile view/edit
                col1, col2 = st.columns([7, 1])
                
                with col2:
                    edit_mode = st.checkbox("แก้ไขข้อมูล")
                
                with col1:
                    if not edit_mode:
                        # Center container start
                        st.markdown('<div class="center-container">', unsafe_allow_html=True)
                        
                        # Profile Card Layout
                        st.markdown(f"""
                        <div style="
                            background: linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%);
                            padding: 2rem;
                            border-radius: 15px;
                            color: white;
                            margin-bottom: 1.5rem;
                            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                        ">
                            <div style="text-align: center; margin-bottom: 1rem;">
                                <div style="
                                    width: 80px;
                                    height: 80px;
                                    background: rgba(255,255,255,0.2);
                                    border-radius: 50%;
                                    margin: 0 auto 1rem;
                                    display: flex;
                                    align-items: center;
                                    justify-content: center;
                                    font-size: 2rem;
                                ">👤</div>
                                <h3 style="margin: 0; font-size: 1.5rem;">{user.get('title', '')} {user.get('first_name', '')} {user.get('last_name', '')}</h3>
                                <p style="margin: 0.5rem 0 0 0; opacity: 0.9;">@{user.get('username', '')}</p>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Information Cards - Full Width Layout
                        # Personal and Education Information in one wide card
                        st.markdown("""
                        <div style="
                            background: #f8f9fa;
                            padding: 2rem;
                            border-radius: 15px;
                            border-left: 4px solid #1e3a8a;
                            margin-bottom: 1.5rem;
                            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                        ">
                            <h4 style="color: #3b82f6; margin-bottom: 2rem; display: flex; align-items: center; font-size: 1.3rem;">
                                <span style="margin-right: 0.8rem; font-size: 1.4rem;">📋</span> ข้อมูลส่วนตัวและการศึกษา
                            </h4>
                        """, unsafe_allow_html=True)
                        
                        # Create two columns for better organization within the wide card
                        col_info, col_edu = st.columns([1.2, 1])
                        
                        with col_info:
                            st.markdown("""
                            <div style="margin-bottom: 1.5rem;">
                                <h5 style="color: #495057; margin-bottom: 1rem; font-size: 1.1rem; border-bottom: 2px solid #3b82f6; padding-bottom: 0.5rem; display: flex; align-items: center;">
                                    <span style="margin-right: 0.5rem; font-size: 1.2rem;"></span> ข้อมูลส่วนตัว
                                </h5>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            info_items = [
                                ("", "คำนำหน้า", user.get('title', 'ไม่ระบุ')),
                                ("", "ชื่อ", user.get('first_name', 'ไม่ระบุ')),
                                ("", "นามสกุล", user.get('last_name', 'ไม่ระบุ')),
                                ("", "เลขบัตรประชาชน", user.get('citizen_id', 'ไม่ระบุ')),
                                ("", "โทรศัพท์", user.get('phone', 'ไม่ระบุ')),
                                ("", "อีเมล", user.get('email', 'ไม่ระบุ'))
                            ]
                            
                            for icon, label, value in info_items:
                                st.markdown(f"""
                                <div style="
                                    display: flex;
                                    align-items: center;
                                    padding: 0.8rem 0;
                                    border-bottom: 1px solid #e9ecef;
                                    transition: background-color 0.2s;
                                ">
                                    <span style="margin-right: 0.8rem; font-size: 1.2rem;">{icon}</span>
                                    <strong style="min-width: 140px; color: #495057; font-size: 1rem;">{label}:</strong>
                                    <span style="color: #6c757d; font-size: 1rem;">{value}</span>
                                </div>
                                """, unsafe_allow_html=True)
                        
                        with col_edu:
                            st.markdown("""
                            <div style="margin-bottom: 1.5rem;">
                                <h5 style="color: #495057; margin-bottom: 1rem; font-size: 1.1rem; border-bottom: 2px solid #1e40af; padding-bottom: 0.5rem; display: flex; align-items: center;">
                                    <span style="margin-right: 0.5rem; font-size: 1.2rem;"></span> ข้อมูลการศึกษา
                                </h5>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            # Format GPAX to 2 decimal places if it exists
                            gpax_value = user.get('gpax')
                            if gpax_value and gpax_value != 'ไม่ระบุ':
                                try:
                                    gpax_display = f"{float(gpax_value):.2f}"
                                except (ValueError, TypeError):
                                    gpax_display = 'ไม่ระบุ'
                            else:
                                gpax_display = 'ไม่ระบุ'
                            
                            edu_items = [
                                ("", "สถาบันการศึกษาที่จบ", user.get('school_name', 'ไม่ระบุ')),
                                ("", "สาขาวิชาที่จบ", user.get('major', 'ไม่ระบุ')),
                                ("", "เกรดเฉลี่ย", gpax_display),
                                ("", "ปีที่จบ", user.get('graduation_year', 'ไม่ระบุ'))
                            ]
                            
                            for icon, label, value in edu_items:
                                st.markdown(f"""
                                <div style="
                                    display: flex;
                                    align-items: center;
                                    padding: 0.8rem 0;
                                    border-bottom: 1px solid #e9ecef;
                                    transition: background-color 0.2s;
                                ">
                                    <span style="margin-right: 0.8rem; font-size: 1.2rem;">{icon}</span>
                                    <strong style="min-width: 160px; color: #495057; font-size: 1rem;">{label}:</strong>
                                    <span style="color: #6c757d; font-size: 1rem;">{value}</span>
                                </div>
                                """, unsafe_allow_html=True)
                        
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Additional Information Cards - Full Padding
                        if user.get('address'):
                            st.markdown(f"""
                            <div style="
                                background: #f8f9fa;
                                padding: 2.5rem;
                                border-radius: 15px;
                                border-left: 4px solid #64748b;
                                margin: 1.5rem 0;
                                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                            ">
                                <h4 style="color: #64748b; margin-bottom: 1.5rem; display: flex; align-items: center; font-size: 1.2rem;">
                                    <span style="margin-right: 0.8rem; font-size: 1.3rem;"></span> ที่อยู่
                                </h4>
                                <div style="
                                    background: rgba(255,255,255,0.9);
                                    padding: 1.5rem;
                                    border-radius: 12px;
                                    border: 1px solid #e9ecef;
                                    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
                                ">
                                    <div style="
                                        display: flex;
                                        align-items: flex-start;
                                        padding: 1rem 0;
                                        border-bottom: 1px solid #f1f3f4;
                                        transition: background-color 0.2s;
                                    ">
                                        <div style="flex: 1;">
                                            <strong style="color: #495057; font-size: 1rem; display: block; margin-bottom: 0.5rem;">ที่อยู่ปัจจุบัน:</strong>
                                            <span style="color: #6c757d; font-size: 1rem; line-height: 1.6;">{user['address']}</span>
                                            {f'<br><strong style="color: #495057; font-size: 1rem; margin-top: 0.5rem; display: block;">จังหวัด:</strong><span style="color: #6c757d; font-size: 1rem;">{user["province"]}</span>' if user.get('province') else ''}
                                        </div>
                                    </div>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                        
                        if user.get('parent_name') or user.get('parent_phone'):
                            st.markdown(f"""
                            <div style="
                                background: #f8f9fa;
                                padding: 2.5rem;
                                border-radius: 15px;
                                border-left: 4px solid #1e3a8a;
                                margin: 1.5rem 0;
                                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                            ">
                                <h4 style="color: #1e40af; margin-bottom: 1.5rem; display: flex; align-items: center; font-size: 1.2rem;">
                                    <span style="margin-right: 0.8rem; font-size: 1.3rem;"></span> ข้อมูลผู้ปกครอง
                                </h4>
                                <div style="
                                    background: rgba(255,255,255,0.9);
                                    padding: 1.5rem;
                                    border-radius: 12px;
                                    border: 1px solid #e9ecef;
                                    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
                                    display: flex;
                                    align-items: center;
                                    gap: 2rem;
                                    flex-wrap: wrap;
                                ">
                                    {f'<div style="display: flex; align-items: center; gap: 0.5rem;"><strong style="color: #495057;">ชื่อผู้ปกครอง:</strong><span style="color: #6c757d;">{user["parent_name"]}</span></div>' if user.get('parent_name') else ''}
                                    {f'<div style="display: flex; align-items: center; gap: 0.5rem;"><strong style="color: #495057;">เบอร์โทรศัพท์:</strong><span style="color: #6c757d;">{user["parent_phone"]}</span></div>' if user.get('parent_phone') else ''}
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                        
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Close center container for personal info view
                        st.markdown('</div>', unsafe_allow_html=True)
                    
                    else:
                        # Center container start for edit mode
                        st.markdown('<div class="center-container">', unsafe_allow_html=True)
                        
                        # Edit mode
                        st.markdown(f"""
                        <div style="
                            background: linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%);
                            padding: 2rem;
                            border-radius: 15px;
                            color: white;
                            margin-bottom: 1.5rem;
                            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                        ">
                            <div style="text-align: center; margin-bottom: 1rem;">
                                <div style="
                                     width: 80px;
                                     height: 80px;
                                     background: rgba(255,255,255,0.2);
                                     border-radius: 50%;
                                     margin: 0 auto 1rem;
                                     display: flex;
                                     align-items: center;
                                     justify-content: center;
                                     font-size: 2rem;
                                 ">✏️</div>
                                <h3 style="margin: 0; font-size: 1.5rem;">แก้ไขข้อมูลส่วนตัว</h3>
                                <p style="margin: 0.5rem 0 0 0; opacity: 0.9;">@{user.get('username', '')}</p>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        with st.form("profile_edit_form"):
                            # ข้อมูลส่วนตัว Card
                            st.markdown("""
                            <div style="
                                background: #f8f9fa;
                                padding: 1.5rem;
                                border-radius: 10px;
                                border-left: 4px solid #1e3a8a;
                                margin-bottom: 1rem;
                                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                            ">
                                <h4 style="color: #1e3a8a; margin-bottom: 1rem; display: flex; align-items: center;">
                                    ข้อมูลส่วนตัว
                                </h4>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            col_a, col_b = st.columns(2)
                            with col_a:
                                # คำนำหน้า
                                current_title = user.get('title', '')
                                if current_title in THAI_TITLES:
                                    title_index = THAI_TITLES.index(current_title)
                                else:
                                    title_index = 0
                                new_title = st.selectbox("คำนำหน้า", THAI_TITLES, index=title_index)
                                
                                new_first_name = st.text_input("ชื่อ", value=user.get('first_name', ''))
                                new_last_name = st.text_input("นามสกุล", value=user.get('last_name', ''))
                            with col_b:
                                new_citizen_id = st.text_input("เลขบัตรประชาชน", value=user.get('citizen_id', ''), max_chars=13)
                                new_phone = st.text_input("โทรศัพท์", value=user.get('phone', ''), max_chars=10)
                                new_email = st.text_input("อีเมล", value=user.get('email', ''))
                            
                            # ข้อมูลการศึกษา Card
                            st.markdown("""
                            <div style="
                                background: #f8f9fa;
                                padding: 1.5rem;
                                border-radius: 10px;
                                border-left: 4px solid #1e40af;
                                margin: 1rem 0;
                                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                            ">
                                <h4 style="color: #1e3a8a; margin-bottom: 1rem; display: flex; align-items: center;">
                                    ข้อมูลการศึกษา
                                </h4>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            col_c, col_d = st.columns(2)
                            with col_c:
                                new_school_name = st.text_input("สถาบันการศึกษาที่จบ", value=user.get('school_name', ''))
                                new_major = st.text_input("สาขาวิชาที่จบ", value=user.get('major', ''))
                            with col_d:
                                # Format GPAX to 2 decimal places for display in edit form
                                gpax_value = user.get('gpax', '')
                                if gpax_value and gpax_value != '':
                                    try:
                                        gpax_formatted = f"{float(gpax_value):.2f}"
                                    except (ValueError, TypeError):
                                        gpax_formatted = str(gpax_value)
                                else:
                                    gpax_formatted = ''
                                new_gpax = st.text_input("เกรดเฉลี่ย", value=gpax_formatted)
                                new_graduation_year = st.selectbox(
                                    "ปีที่จบการศึกษา",
                                    options=list(range(2020, 2030)),
                                    index=list(range(2020, 2030)).index(user.get('graduation_year', 2024))
                                )

                            
                            # ที่อยู่และข้อมูลผู้ปกครอง Card
                            st.markdown("""
                            <div style="
                                background: #f8f9fa;
                                padding: 1.5rem;
                                border-radius: 10px;
                                border-left: 4px solid #64748b;
                                margin: 1rem 0;
                                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                            ">
                                <h4 style="color: #64748b; margin-bottom: 1rem; display: flex; align-items: center;">
                                    ที่อยู่และข้อมูลผู้ปกครอง
                                </h4>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            new_address = st.text_area("ที่อยู่(ที่สามารถติดต่อได้)", value=user.get('address', ''))
                            
                            # Set default index for province selectbox
                            current_province = user.get('province', '')
                            province_options = [""] + THAI_PROVINCES
                            province_index = 0
                            if current_province and current_province in THAI_PROVINCES:
                                province_index = province_options.index(current_province)
                            
                            new_province = st.selectbox("จังหวัด", options=province_options, index=province_index)
                            
                            col_e, col_f = st.columns(2)
                            with col_e:
                                new_parent_name = st.text_input("ชื่อผู้ปกครอง", value=user.get('parent_name', ''))
                            with col_f:
                                new_parent_phone = st.text_input("เบอร์ผู้ปกครอง", value=user.get('parent_phone', ''), max_chars=10)
                            
                            # เปลี่ยนรหัสผ่าน Card
                            st.markdown("""
                            <div style="
                                background: #f8f9fa;
                                padding: 1.5rem;
                                border-radius: 10px;
                                border-left: 4px solid #ef4444;
                                margin: 1rem 0;
                                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                            ">
                                <h4 style="color: #ef4444; margin-bottom: 1rem; display: flex; align-items: center;">
                                    เปลี่ยนรหัสผ่าน (ไม่บังคับ)
                                </h4>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            # Old password confirmation field
                            old_password = st.text_input("ยืนยันรหัสผ่านเดิม", type="password", help="กรุณากรอกรหัสผ่านปัจจุบันเพื่อยืนยันตัวตน")
                            
                            col_g, col_h = st.columns(2)
                            with col_g:
                                new_password = st.text_input("รหัสผ่านใหม่", type="password")
                            with col_h:
                                confirm_new_password = st.text_input("ยืนยันรหัสผ่านใหม่", type="password")
                            
                            submit_edit = st.form_submit_button("💾 บันทึกการเปลี่ยนแปลง", use_container_width=True)
                            
                            if submit_edit:
                                # Validation
                                errors = []
                                
                                # Validate required fields
                                if not all([new_first_name, new_last_name, new_citizen_id, new_phone, new_email, new_school_name, new_gpax]):
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
                                    
                                    # Validate citizen ID - check uniqueness only if changed
                                    if new_citizen_id != user.get('citizen_id'):
                                        is_valid, error_msg = Validator.validate_citizen_id_with_uniqueness(new_citizen_id, user.get('username'))
                                        if not is_valid:
                                            validations.append((is_valid, error_msg))
                                    else:
                                        # Just validate format if not changed
                                        is_valid, error_msg = Validator.validate_citizen_id(new_citizen_id)
                                        if not is_valid:
                                            validations.append((is_valid, error_msg))
                                    
                                    # Validate parent phone if provided
                                    if new_parent_phone and new_parent_phone.strip():
                                        is_valid, error_msg = Validator.validate_phone(new_parent_phone)
                                        if not is_valid:
                                            errors.append(f"เบอร์ผู้ปกครอง: {error_msg}")
                                    
                                    for is_valid, error_msg in validations:
                                        if not is_valid:
                                            errors.append(error_msg)
                                
                                # Password validation
                                if new_password:
                                    # Check if old password is provided and correct
                                    if not old_password:
                                        errors.append("กรุณากรอกรหัสผ่านเดิมเพื่อยืนยันตัวตน")
                                    elif AuthManager.hash_password(old_password) != user.get('password'):
                                        errors.append("รหัสผ่านเดิมไม่ถูกต้อง")
                                    elif new_password != confirm_new_password:
                                        errors.append("รหัสผ่านใหม่ไม่ตรงกัน")
                                    elif len(new_password) < 6:
                                        errors.append("รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร")
                                    elif old_password == new_password:
                                        errors.append("รหัสผ่านใหม่ต้องแตกต่างจากรหัสผ่านเดิม")
                                
                                if errors:
                                    for error in errors:
                                        st.error(error)
                                else:
                                    # Update user data
                                    updated_data = {
                                        'title': new_title,
                                        'first_name': new_first_name,
                                        'last_name': new_last_name,
                                        'citizen_id': new_citizen_id,
                                        'phone': new_phone,
                                        'email': new_email,
                                        'school_name': new_school_name,
                                        'major': new_major,
                                        'gpax': round(float(new_gpax), 2),
                                        'graduation_year': new_graduation_year,
                                        'address': new_address,
                                        'province': new_province,
                                        'parent_name': new_parent_name,
                                        'parent_phone': new_parent_phone
                                    }
                                    
                                    if new_password:
                                        updated_data['password'] = AuthManager.hash_password(new_password)
                                    
                                    success, message = UserManager.update_user(user['username'], updated_data)
                                    if success:
                                        # Show success notification with custom styling
                                        st.markdown("""
                                        <div style="
                                            background: linear-gradient(90deg, #1e40af 0%, #1e3a8a 100%);
                                            color: white;
                                            padding: 1rem;
                                            border-radius: 10px;
                                            text-align: center;
                                            margin: 1rem 0;
                                            box-shadow: 0 4px 15px rgba(30, 64, 175, 0.3);
                                            animation: slideIn 0.5s ease-out;
                                        ">
                                            <h4 style="margin: 0; display: flex; align-items: center; justify-content: center;">
                                                บันทึกข้อมูลสำเร็จ!
                                            </h4>
                                            <p style="margin: 0.5rem 0 0 0; opacity: 0.9;">ข้อมูลส่วนตัวของคุณได้รับการอัพเดทเรียบร้อยแล้ว</p>
                                        </div>
                                        """, unsafe_allow_html=True)
                                        
                                        # Update session user data
                                        st.session_state.current_user.update(updated_data)
                                        
                                        # Add a small delay to show the success message before rerun
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error(f"{message}")
                        
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Close center container for edit mode
                        st.markdown('</div>', unsafe_allow_html=True)

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; padding: 1rem;">
    <p>© 2025 มหาวิทยาลัยมหาสารคาม | ระบบอัพโหลดเอกสารสมัครเรียน</p>
    <p>พัฒนาด้วย Streamlit | เวอร์ชัน 1.0</p>
</div>
""", unsafe_allow_html=True)