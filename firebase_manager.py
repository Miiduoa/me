import firebase_admin
from firebase_admin import credentials, firestore
import os

# 初始化Firebase (只需執行一次)
def initialize_firebase():
    if not firebase_admin._apps:
        cred = credentials.Certificate('serviceAccountKey.json')
        firebase_admin.initialize_app(cred)
    return firestore.client()

# 基本CRUD操作
def add_document(collection, data):
    db = initialize_firebase()
    doc_ref = db.collection(collection).document()
    doc_ref.set(data)
    return doc_ref.id

def get_document(collection, doc_id):
    db = initialize_firebase()
    doc = db.collection(collection).document(doc_id).get()
    if doc.exists:
        return doc.to_dict()
    return None

# 添加到現有文件中
def authenticate_user(email, password):
    """模擬身份驗證功能，實際應用中應使用Firebase Auth"""
    db = initialize_firebase()
    users = db.collection('users').where('email', '==', email).limit(1).get()
    for user in users:
        user_data = user.to_dict()
        # 注意：實際應用中應使用加密比較密碼
        if user_data.get('password') == password:
            return user_data
    return None

def create_user(email, password, display_name=None):
    """創建新用戶"""
    user_data = {
        'email': email,
        'password': password,  # 實際應用中應加密儲存
        'display_name': display_name,
        'created_at': firestore.SERVER_TIMESTAMP
    }
    return add_document('users', user_data)

def check_email_exists(email):
    """檢查郵箱是否已被註冊"""
    db = initialize_firebase()
    users = db.collection('users').where('email', '==', email).limit(1).get()
    return len(list(users)) > 0

def get_all_documents(collection):
    """獲取集合中的所有文檔"""
    db = initialize_firebase()
    docs = db.collection(collection).get()
    return [doc.to_dict() for doc in docs]

# ... 其他操作函數 ... 