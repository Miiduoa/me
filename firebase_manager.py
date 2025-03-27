import firebase_admin
from firebase_admin import credentials, firestore
import os
import json
import base64

# 初始化Firebase (只需執行一次)
def initialize_firebase():
    if not firebase_admin._apps:
        # 嘗試從環境變量讀取
        if 'FIREBASE_SERVICE_ACCOUNT' in os.environ:
            # 從 Base64 解碼並解析 JSON
            service_account_info = json.loads(
                base64.b64decode(os.environ.get('FIREBASE_SERVICE_ACCOUNT')).decode('utf-8')
            )
            cred = credentials.Certificate(service_account_info)
        else:
            # 從本地文件讀取（開發環境）
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
        data = doc.to_dict()
        data['id'] = doc_id  # 添加文檔ID到數據中
        return data
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
    return [{'id': doc.id, **doc.to_dict()} for doc in docs]  # 合併ID與數據

def add_like(user_id, movie_id):
    """添加用戶對電影的喜歡操作"""
    db = initialize_firebase()
    like_data = {
        'user_id': user_id,
        'movie_id': movie_id,
        'created_at': firestore.SERVER_TIMESTAMP
    }
    
    # 檢查用戶是否已經喜歡過這部電影
    likes = db.collection('likes').where('user_id', '==', user_id).where('movie_id', '==', movie_id).limit(1).get()
    
    if len(list(likes)) > 0:
        # 用戶已經喜歡過，可以選擇取消喜歡（刪除記錄）
        for like in likes:
            like.reference.delete()
        return False
    else:
        # 用戶還沒喜歡過，添加喜歡記錄
        add_document('likes', like_data)
        return True

def count_likes(movie_id):
    """計算電影獲得的喜歡數量"""
    db = initialize_firebase()
    likes = db.collection('likes').where('movie_id', '==', movie_id).get()
    return len(list(likes))

def check_user_liked(user_id, movie_id):
    """檢查用戶是否已經喜歡某電影"""
    db = initialize_firebase()
    likes = db.collection('likes').where('user_id', '==', user_id).where('movie_id', '==', movie_id).limit(1).get()
    return len(list(likes)) > 0

# ... 其他操作函數 ... 