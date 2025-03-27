import firebase_admin
from firebase_admin import credentials, firestore, storage
import os
import json
import base64
import logging
import time
from functools import lru_cache

# 配置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 設置緩存過期時間（秒）
CACHE_EXPIRATION = {
    'movies': 3600,  # 電影數據緩存1小時
    'users': 600,    # 用戶數據緩存10分鐘
    'rankings': 1800 # 排行榜緩存30分鐘
}

# 緩存字典，格式: {'collection:id': {'data': data, 'expire_at': timestamp}}
_cache = {}

def get_with_cache(collection, doc_id, timeout=None):
    """帶緩存功能的文檔獲取"""
    timeout = timeout or CACHE_EXPIRATION.get(collection, 300)
    cache_key = f"{collection}:{doc_id}"
    current_time = time.time()
    
    # 檢查緩存是否有效
    if cache_key in _cache and _cache[cache_key]['expire_at'] > current_time:
        logger.debug(f"緩存命中: {cache_key}")
        return _cache[cache_key]['data']
    
    # 從數據庫獲取
    db = initialize_firebase()
    doc = db.collection(collection).document(doc_id).get()
    
    if doc.exists:
        data = doc.to_dict()
        data['id'] = doc_id
        
        # 存入緩存
        _cache[cache_key] = {
            'data': data,
            'expire_at': current_time + timeout
        }
        
        return data
    
    return None

@lru_cache(maxsize=32)
def get_collection_cached(collection, limit=20, order_by=None, direction=None):
    """緩存集合查詢結果"""
    cache_key = f"collection:{collection}:limit:{limit}:order:{order_by}:{direction}"
    
    # 從數據庫查詢
    db = initialize_firebase()
    query = db.collection(collection).limit(limit)
    
    if order_by:
        direction_obj = firestore.Query.DESCENDING if direction == 'desc' else firestore.Query.ASCENDING
        query = query.order_by(order_by, direction=direction_obj)
    
    docs = query.get()
    result = [{'id': doc.id, **doc.to_dict()} for doc in docs]
    
    return result

def clear_cache(collection=None, doc_id=None):
    """清除特定集合或文檔的緩存，或全部緩存"""
    global _cache
    
    if collection and doc_id:
        cache_key = f"{collection}:{doc_id}"
        if cache_key in _cache:
            del _cache[cache_key]
    elif collection:
        # 清除特定集合的所有緩存
        keys_to_delete = [k for k in _cache.keys() if k.startswith(f"{collection}:")]
        for k in keys_to_delete:
            del _cache[k]
    else:
        # 清除所有緩存
        _cache = {}
    
    # 同時清除函數緩存
    get_collection_cached.cache_clear()

# 使用裝飾器標記需要在文檔變更時清除緩存的函數
def clear_cache_on_change(collection):
    def decorator(func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            # 執行後清除相關緩存
            clear_cache(collection)
            return result
        return wrapper
    return decorator

# 初始化Firebase (只需執行一次)
def initialize_firebase():
    """初始化 Firebase，如果未初始化則進行初始化"""
    try:
        firebase_admin.get_app()
    except ValueError:
        # 設定 Firebase 憑證路徑
        cred_path = os.environ.get('FIREBASE_CREDENTIALS', 'path/to/your/serviceAccountKey.json')
        if os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
        else:
            # 從環境變數加載憑證
            cred_dict = json.loads(base64.b64decode(os.environ.get('FIREBASE_CREDENTIALS_JSON', '')).decode('utf-8'))
            cred = credentials.Certificate(cred_dict)
        
        # 初始化 Firebase
        bucket_name = os.environ.get('FIREBASE_STORAGE_BUCKET', 'your-project-id.appspot.com')
        firebase_admin.initialize_app(cred, {
            'storageBucket': bucket_name
        })
    
    # 獲取 Firestore 資料庫實例
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

@clear_cache_on_change('likes')
def add_like(user_id, movie_id):
    """添加或刪除用戶對電影的喜歡"""
    try:
        db = initialize_firebase()
        # 檢查用戶是否已經喜歡這部電影
        likes = db.collection('likes').where('user_id', '==', user_id).where('movie_id', '==', movie_id).get()
        
        if len(list(likes)) > 0:
            # 如果已經喜歡，則刪除該記錄（取消喜歡）
            for like in likes:
                db.collection('likes').document(like.id).delete()
        else:
            # 如果還沒有喜歡，則添加記錄
            db.collection('likes').add({
                'user_id': user_id,
                'movie_id': movie_id,
                'created_at': firestore.SERVER_TIMESTAMP
            })
        return True
    except Exception as e:
        logger.error(f"添加喜歡操作失敗: {str(e)}")
        return False

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

def get_user_liked_movies(user_id):
    """獲取用戶喜歡的所有電影詳細資料"""
    db = initialize_firebase()
    
    # 1. 獲取用戶所有的喜歡記錄
    likes = db.collection('likes').where('user_id', '==', user_id).get()
    movie_ids = [like.to_dict()['movie_id'] for like in likes]
    
    # 2. 如果沒有喜歡的電影，返回空列表
    if not movie_ids:
        return []
    
    # 3. 批量獲取所有電影數據
    liked_movies = []
    # 由於 Firestore 批量獲取限制，分批處理
    batch_size = 10
    for i in range(0, len(movie_ids), batch_size):
        batch = movie_ids[i:i+batch_size]
        # 創建引用列表
        refs = [db.collection('movies').document(mid) for mid in batch]
        # 批量獲取文檔
        docs = db.get_all(refs)
        
        for doc in docs:
            if doc.exists:
                movie_data = doc.to_dict()
                movie_data['id'] = doc.id
                liked_movies.append(movie_data)
    
    # 4. 按評分排序
    liked_movies.sort(key=lambda x: float(x.get('rating', 0)), reverse=True)
    return liked_movies

def get_movie_recommendations(user_id, limit=6):
    """基於協同過濾的簡單電影推薦系統"""
    db = initialize_firebase()
    
    # 1. 獲取當前用戶喜歡的電影
    user_likes = db.collection('likes').where('user_id', '==', user_id).get()
    user_movie_ids = set(like.to_dict()['movie_id'] for like in user_likes)
    
    # 如果用戶沒有喜歡的電影，返回評分最高的電影
    if not user_movie_ids:
        top_movies = list(get_all_documents("movies"))
        top_movies.sort(key=lambda x: float(x.get('rating', 0)), reverse=True)
        return top_movies[:limit]
    
    # 2. 找到與當前用戶有相似品味的用戶
    similar_users = set()
    recommendations_score = {}
    
    # 對每部用戶喜歡的電影
    for movie_id in user_movie_ids:
        # 找出同樣喜歡這部電影的其他用戶
        movie_likes = db.collection('likes').where('movie_id', '==', movie_id).get()
        for like in movie_likes:
            other_user_id = like.to_dict()['user_id']
            if other_user_id != user_id:
                similar_users.add(other_user_id)
    
    # 3. 從相似用戶中獲取電影推薦
    for similar_user in similar_users:
        # 獲取相似用戶喜歡的電影
        similar_user_likes = db.collection('likes').where('user_id', '==', similar_user).get()
        for like in similar_user_likes:
            rec_movie_id = like.to_dict()['movie_id']
            # 排除用戶已經喜歡的電影
            if rec_movie_id not in user_movie_ids:
                # 將電影添加到推薦列表並增加分數
                recommendations_score[rec_movie_id] = recommendations_score.get(rec_movie_id, 0) + 1
    
    # 4. 如果沒有足夠的推薦，添加一些評分高的電影
    if len(recommendations_score) < limit:
        top_movies = list(get_all_documents("movies"))
        top_movies.sort(key=lambda x: float(x.get('rating', 0)), reverse=True)
        
        for movie in top_movies:
            movie_id = movie.get('id')
            if movie_id not in user_movie_ids and movie_id not in recommendations_score:
                recommendations_score[movie_id] = 0
                if len(recommendations_score) >= limit:
                    break
    
    # 5. 獲取推薦電影的詳細信息
    recommended_movie_ids = sorted(recommendations_score.keys(), 
                                   key=lambda x: recommendations_score[x], 
                                   reverse=True)[:limit]
    
    recommended_movies = []
    for movie_id in recommended_movie_ids:
        movie = get_document("movies", movie_id)
        if movie:
            recommended_movies.append(movie)
    
    return recommended_movies

def upload_user_avatar(user_id, file):
    """上傳用戶頭像到 Firebase Storage"""
    try:
        bucket = storage.bucket()
        blob = bucket.blob(f'avatars/{user_id}.jpg')
        
        # 設置內容類型
        blob.content_type = 'image/jpeg'
        
        # 上傳文件
        blob.upload_from_file(file)
        
        # 獲取公共URL
        blob.make_public()
        public_url = blob.public_url
        
        # 更新用戶資料
        db = initialize_firebase()
        db.collection('users').document(user_id).update({
            'avatar_url': public_url
        })
        
        return public_url
    except Exception as e:
        logger.error(f"上傳頭像失敗: {str(e)}")
        return None

def get_movie_comments(movie_id):
    """獲取電影的所有評論，按時間倒序排列"""
    db = initialize_firebase()
    comments = db.collection('movies').document(movie_id).collection('comments').order_by('created_at', direction=firestore.Query.DESCENDING).get()
    
    result = []
    for comment in comments:
        comment_data = comment.to_dict()
        comment_data['id'] = comment.id
        result.append(comment_data)
    
    return result

# ... 其他操作函數 ... 