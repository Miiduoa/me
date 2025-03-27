import firebase_admin
from firebase_admin import credentials, firestore, storage
import os
import json
import base64
import logging
import time
from functools import lru_cache
from datetime import datetime, timezone

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
    """初始化 Firebase 連接並返回 Firestore 數據庫實例"""
    try:
        # 檢查是否已初始化
        firebase_admin.get_app()
    except ValueError:
        # 未初始化，執行初始化
        if os.path.exists('serviceAccountKey.json'):
            cred = credentials.Certificate('serviceAccountKey.json')
        else:
            # 從環境變量獲取 Firebase 配置
            service_account_info = json.loads(base64.b64decode(os.environ.get('FIREBASE_CONFIG', '')))
            cred = credentials.Certificate(service_account_info)
        
        firebase_admin.initialize_app(cred, {
            'storageBucket': 'project-7332910669653362321.appspot.com'
        })
    
    return firestore.client()

# 基本CRUD操作
def add_document(collection, data):
    db = initialize_firebase()
    doc_ref = db.collection(collection).document()
    doc_ref.set(data)
    return doc_ref.id

def get_document(collection, doc_id):
    """獲取指定集合和ID的文檔"""
    try:
        db = initialize_firebase()
        doc = db.collection(collection).document(doc_id).get()
        if doc.exists:
            data = doc.to_dict()
            data['id'] = doc_id
            return data
        return None
    except Exception as e:
        logger.error(f"獲取文檔錯誤 ({collection}/{doc_id}): {e}")
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

def create_user(email, password, display_name):
    """創建新用戶，返回用戶ID"""
    try:
        # 初始化 Firebase
        db = initialize_firebase()
        
        # 使用 REST API 方式創建用戶
        # 這種方式避免直接使用 firebase_admin.auth 可能引起的問題
        user_data = {
            'email': email,
            'password': password,  # 加密會在 Firestore 處理
            'display_name': display_name,
            'created_at': firestore.SERVER_TIMESTAMP,
            'avatar_url': '',
            'bio': ''
        }
        
        # 存儲到 Firestore
        doc_ref = db.collection('users').document()
        doc_ref.set(user_data)
        user_id = doc_ref.id
        
        logger.info(f"成功創建用戶: {user_id}")
        return user_id
    except Exception as e:
        logger.error(f"創建用戶失敗: {str(e)}")
        return None

def check_email_exists(email):
    """檢查郵箱是否已存在"""
    try:
        auth = firebase_admin.auth
        try:
            # 嘗試通過郵箱查找用戶
            user = auth.get_user_by_email(email)
            return True  # 用戶存在
        except firebase_admin.auth.UserNotFoundError:
            return False  # 用戶不存在
    except Exception as e:
        logger.error(f"檢查郵箱存在性錯誤: {str(e)}")
        # 如果出現錯誤，假設郵箱不存在，讓用戶嘗試註冊
        return False

def get_all_documents(collection, limit=100, order_by=None, direction='desc'):
    """獲取集合中的所有文檔"""
    try:
        db = initialize_firebase()
        # 確保連接成功
        if not db:
            logger.error("Firebase初始化失敗")
            return []
            
        # 開始查詢
        query = db.collection(collection)
        
        # 添加排序
        if order_by:
            firestore_direction = firestore.Query.DESCENDING if direction == 'desc' else firestore.Query.ASCENDING
            query = query.order_by(order_by, direction=firestore_direction)
        
        # 添加限制
        if limit:
            query = query.limit(limit)
            
        # 執行查詢
        docs = query.get()
        
        # 處理結果
        results = []
        for doc in docs:
            data = doc.to_dict()
            if data:  # 確保不是空文檔
                data['id'] = doc.id
                results.append(data)
        
        logger.info(f"從 {collection} 獲取了 {len(results)} 個文檔")
        return results
    except Exception as e:
        logger.error(f"獲取文檔錯誤: {str(e)}")
        return []

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

def create_post(user_id, content, image_url=None, movie_id=None):
    """創建新貼文"""
    try:
        db = initialize_firebase()
        user = get_document('users', user_id)
        
        if not user:
            logger.error(f"創建貼文失敗：找不到用戶 {user_id}")
            return None
        
        # 計算貼文創建時間
        created_at = datetime.now(timezone.utc)
        
        post_data = {
            'user_id': user_id,
            'user_name': user.get('display_name', '未知用戶'),
            'user_avatar': user.get('avatar_url', ''),
            'text': content,
            'created_at': created_at,
            'likes_count': 0,
            'comments_count': 0
        }
        
        if image_url:
            post_data['image_url'] = image_url
            
        if movie_id:
            movie = get_document('movies', movie_id)
            if movie:
                post_data['movie_id'] = movie_id
                post_data['movie_title'] = movie.get('title', '')
                post_data['movie_poster'] = movie.get('image_url', '')
        
        # 添加到數據庫
        post_ref = db.collection('posts').add(post_data)
        post_id = post_ref[1].id
        
        logger.info(f"用戶 {user_id} 創建了新貼文 {post_id}")
        return post_id
    except Exception as e:
        logger.error(f"創建貼文錯誤: {str(e)}")
        return None

def get_posts(limit=10, user_id=None, sort_by='created_at', offset=None):
    """獲取貼文列表，可選按用戶過濾和排序"""
    try:
        db = initialize_firebase()
        posts_ref = db.collection('posts')
        
        if user_id:
            posts_ref = posts_ref.where('user_id', '==', user_id)
        
        # 預設按創建時間降序
        if sort_by == 'likes_count':
            posts_ref = posts_ref.order_by('likes_count', direction='desc')
        else:
            posts_ref = posts_ref.order_by('created_at', direction='desc')
            
        if offset:
            posts_ref = posts_ref.start_after(offset)
            
        posts_ref = posts_ref.limit(limit)
        posts_data = posts_ref.get()
        
        result = []
        for post in posts_data:
            post_dict = post.to_dict()
            post_dict['id'] = post.id
            
            # 計算貼文時間（例如：3小時前、2天前）
            if 'created_at' in post_dict:
                created_at = post_dict['created_at']
                if isinstance(created_at, (str, int, float)):
                    # 將字符串或數字轉換為datetime
                    if isinstance(created_at, str):
                        try:
                            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        except ValueError:
                            created_at = datetime.now(timezone.utc)
                    else:
                        created_at = datetime.fromtimestamp(created_at, tz=timezone.utc)
                
                now = datetime.now(timezone.utc)
                delta = now - created_at
                
                if delta.days > 365:
                    post_dict['time_ago'] = f"{delta.days // 365}年前"
                elif delta.days > 30:
                    post_dict['time_ago'] = f"{delta.days // 30}個月前"
                elif delta.days > 0:
                    post_dict['time_ago'] = f"{delta.days}天前"
                elif delta.seconds // 3600 > 0:
                    post_dict['time_ago'] = f"{delta.seconds // 3600}小時前"
                elif delta.seconds // 60 > 0:
                    post_dict['time_ago'] = f"{delta.seconds // 60}分鐘前"
                else:
                    post_dict['time_ago'] = "剛剛"
            
            result.append(post_dict)
        
        return result
    except Exception as e:
        logger.error(f"獲取貼文錯誤: {str(e)}")
        return []

def like_post(user_id, post_id):
    """點讚或取消點讚貼文，返回True表示點讚，False表示取消點讚"""
    try:
        db = initialize_firebase()
        
        # 檢查是否已點讚
        likes_ref = db.collection('post_likes')
        existing_like = likes_ref.where('user_id', '==', user_id).where('post_id', '==', post_id).get()
        
        if len(existing_like) == 0:
            # 創建新點讚記錄
            like_data = {
                'user_id': user_id,
                'post_id': post_id,
                'created_at': datetime.now(timezone.utc)
            }
            likes_ref.add(like_data)
            
            # 增加貼文的讚數
            post_ref = db.collection('posts').document(post_id)
            post = post_ref.get()
            if post.exists:
                post_data = post.to_dict()
                current_likes = post_data.get('likes_count', 0)
                post_ref.update({'likes_count': current_likes + 1})
            
            # 創建通知（如果點讚的不是自己的貼文）
            post = post_ref.get().to_dict()
            target_user_id = post.get('user_id')
            if target_user_id and target_user_id != user_id:
                user = get_document('users', user_id)
                create_notification(
                    target_user_id, 
                    'like', 
                    user.get('display_name', '未知用戶'), 
                    user.get('avatar_url', ''),
                    f"喜歡了你的貼文",
                    post_id
                )
            
            return True
        else:
            # 移除點讚
            for like in existing_like:
                like.reference.delete()
            
            # 減少貼文的讚數
            post_ref = db.collection('posts').document(post_id)
            post = post_ref.get()
            if post.exists:
                post_data = post.to_dict()
                current_likes = post_data.get('likes_count', 0)
                post_ref.update({'likes_count': max(0, current_likes - 1)})
            
            return False
    except Exception as e:
        logger.error(f"點讚操作錯誤: {str(e)}")
        return None

def upload_to_firebase_storage(file_obj, destination_path):
    """通用的 Firebase Storage 上傳函數"""
    try:
        bucket = storage.bucket()
        blob = bucket.blob(destination_path)
        
        # 設置內容類型
        content_type = file_obj.content_type
        blob.content_type = content_type
        
        # 上傳文件
        blob.upload_from_file(file_obj)
        
        # 生成可訪問的URL
        blob.make_public()
        return blob.public_url
    except Exception as e:
        print(f"Firebase Storage 上傳錯誤: {e}")
        return None

def get_active_users(limit=5):
    """獲取活躍用戶列表"""
    try:
        db = initialize_firebase()
        users_ref = db.collection('users')
        
        # 如果有活躍度字段，根據活躍度排序
        # 如果沒有，只獲取最近的用戶
        users = users_ref.limit(limit).get()
        
        result = []
        for user in users:
            user_data = user.to_dict()
            user_data['id'] = user.id
            
            # 確保數據格式一致
            if 'display_name' not in user_data:
                user_data['display_name'] = '使用者'
                
            if 'avatar_url' not in user_data:
                user_data['avatar_url'] = '/static/images/default-avatar.png'
                
            result.append(user_data)
            
        return result
    except Exception as e:
        logger.error(f"獲取活躍用戶錯誤: {str(e)}")
        # 返回空列表而不是None，確保模板可以安全遍歷
        return []

def create_notification(target_user_id, notification_type, user_name, user_avatar, content, related_id=None):
    """創建用戶通知
    
    參數:
        target_user_id: 接收通知的用戶ID
        notification_type: 通知類型 (like, comment, follow, etc.)
        user_name: 觸發通知的用戶名稱
        user_avatar: 觸發通知的用戶頭像URL
        content: 通知內容
        related_id: 相關聯的內容ID (如貼文ID)
    """
    try:
        db = initialize_firebase()
        
        notification_data = {
            'user_id': target_user_id,
            'type': notification_type,
            'user_name': user_name,
            'user_avatar': user_avatar,
            'content': content,
            'created_at': datetime.now(timezone.utc),
            'is_read': False
        }
        
        if related_id:
            notification_data['related_id'] = related_id
        
        # 添加到數據庫
        notification_ref = db.collection('notifications').add(notification_data)
        
        logger.info(f"為用戶 {target_user_id} 創建了新通知")
        return notification_ref[1].id
    except Exception as e:
        logger.error(f"創建通知錯誤: {str(e)}")
        return None

def get_user_notifications(user_id, limit=20, offset=None):
    """獲取用戶的通知列表"""
    try:
        db = initialize_firebase()
        
        query = db.collection('notifications') \
                .where('user_id', '==', user_id) \
                .order_by('created_at', direction='desc')
        
        if offset:
            query = query.start_after(offset)
            
        query = query.limit(limit)
        notifications = query.get()
        
        result = []
        for notification in notifications:
            notif_dict = notification.to_dict()
            notif_dict['id'] = notification.id
            
            # 計算通知時間（例如：3小時前、2天前）
            if 'created_at' in notif_dict:
                created_at = notif_dict['created_at']
                if isinstance(created_at, datetime):
                    now = datetime.now(timezone.utc)
                    delta = now - created_at
                    
                    if delta.days > 365:
                        notif_dict['time_ago'] = f"{delta.days // 365}年前"
                    elif delta.days > 30:
                        notif_dict['time_ago'] = f"{delta.days // 30}個月前"
                    elif delta.days > 0:
                        notif_dict['time_ago'] = f"{delta.days}天前"
                    elif delta.seconds // 3600 > 0:
                        notif_dict['time_ago'] = f"{delta.seconds // 3600}小時前"
                    elif delta.seconds // 60 > 0:
                        notif_dict['time_ago'] = f"{delta.seconds // 60}分鐘前"
                    else:
                        notif_dict['time_ago'] = "剛剛"
            
            result.append(notif_dict)
        
        return result
    except Exception as e:
        logger.error(f"獲取用戶通知錯誤: {str(e)}")
        return []

def get_user_notification_count(user_id, unread_only=True):
    """獲取用戶的通知數量，默認只計算未讀通知"""
    try:
        db = initialize_firebase()
        
        query = db.collection('notifications').where('user_id', '==', user_id)
        
        if unread_only:
            query = query.where('is_read', '==', False)
            
        notifications = query.get()
        return len(notifications)
    except Exception as e:
        logger.error(f"獲取用戶通知數量錯誤: {str(e)}")
        return 0

def mark_notification_as_read(notification_id, read=True):
    """標記通知為已讀或未讀"""
    try:
        db = initialize_firebase()
        
        notification_ref = db.collection('notifications').document(notification_id)
        notification_ref.update({'is_read': read})
        
        return True
    except Exception as e:
        logger.error(f"標記通知狀態錯誤: {str(e)}")
        return False

def mark_all_notifications_as_read(user_id):
    """標記用戶所有通知為已讀"""
    try:
        db = initialize_firebase()
        
        # 獲取用戶的所有未讀通知
        notifications = db.collection('notifications') \
                        .where('user_id', '==', user_id) \
                        .where('is_read', '==', False) \
                        .get()
        
        # 批量更新為已讀
        batch = db.batch()
        for notification in notifications:
            batch.update(notification.reference, {'is_read': True})
        
        batch.commit()
        
        return True
    except Exception as e:
        logger.error(f"標記所有通知為已讀錯誤: {str(e)}")
        return False

def get_recommended_posts(user_id=None, limit=10):
    """獲取推薦貼文，參考 Threads 演算法
    
    參數:
        user_id: 當前用戶ID（用於個性化推薦）
        limit: 返回貼文數量上限
    """
    try:
        db = initialize_firebase()
        posts_ref = db.collection('posts')
        
        # 獲取所有貼文
        all_posts = []
        posts = posts_ref.order_by('created_at', direction=firestore.Query.DESCENDING).limit(100).get()
        
        for post in posts:
            post_data = post.to_dict()
            post_data['id'] = post.id
            
            # 添加用戶信息
            if 'user_id' in post_data:
                user = get_document('users', post_data['user_id'])
                if user:
                    post_data['user_name'] = user.get('display_name', '未知用戶')
                    post_data['user_avatar'] = user.get('avatar_url', '')
            
            # 計算時間差
            if 'created_at' in post_data and post_data['created_at']:
                created_at = post_data['created_at']
                if isinstance(created_at, datetime):
                    now = datetime.now(timezone.utc)
                    diff = now - created_at
                    
                    if diff.days > 0:
                        post_data['time_ago'] = f"{diff.days} 天前"
                    elif diff.seconds // 3600 > 0:
                        post_data['time_ago'] = f"{diff.seconds // 3600} 小時前"
                    elif diff.seconds // 60 > 0:
                        post_data['time_ago'] = f"{diff.seconds // 60} 分鐘前"
                    else:
                        post_data['time_ago'] = "剛剛"
                else:
                    post_data['time_ago'] = "未知時間"
            
            # 獲取貼文點讚數（如果未設置則默認為0）
            post_data['likes_count'] = post_data.get('likes_count', 0)
            
            # 獲取貼文評論數
            post_data['comments_count'] = 0
            comments = db.collection('comments').where('post_id', '==', post.id).get()
            post_data['comments_count'] = len(comments)
            
            # 檢查當前用戶是否已點讚
            if user_id:
                post_data['user_liked'] = False
                likes = db.collection('post_likes').where('post_id', '==', post.id).where('user_id', '==', user_id).get()
                if len(likes) > 0:
                    post_data['user_liked'] = True
            
            all_posts.append(post_data)
        
        # Threads式推薦算法實現
        if all_posts:
            scored_posts = []
            
            # 如果用戶已登入，獲取用戶喜好和互動歷史
            user_interests = []
            user_interactions = []
            if user_id:
                # 獲取用戶喜歡的電影類別
                liked_movies = get_user_liked_movies(user_id)
                for movie in liked_movies:
                    if 'genres' in movie:
                        user_interests.extend(movie.get('genres', []))
                
                # 獲取用戶互動過的作者ID
                interactions = db.collection('post_likes').where('user_id', '==', user_id).get()
                for interaction in interactions:
                    data = interaction.to_dict()
                    if 'post_id' in data:
                        post = db.collection('posts').document(data['post_id']).get()
                        if post.exists and 'user_id' in post.to_dict():
                            user_interactions.append(post.to_dict()['user_id'])
            
            # 為每篇貼文計算分數
            current_time = datetime.now(timezone.utc)
            for post in all_posts:
                score = 0
                
                # 1. 參與度分數 (40%)
                engagement_score = post.get('likes_count', 0) * 1 + post.get('comments_count', 0) * 2
                score += engagement_score * 0.4
                
                # 2. 時效性分數 (30%)
                recency_score = 0
                if 'created_at' in post and isinstance(post['created_at'], datetime):
                    # 24小時內的貼文獲得加分
                    time_diff = (current_time - post['created_at']).total_seconds() / 3600  # 小時
                    if time_diff <= 24:
                        recency_score = 100 * (1 - (time_diff / 24))
                    elif time_diff <= 72:
                        recency_score = 30 * (1 - ((time_diff - 24) / 48))
                score += recency_score * 0.3
                
                # 3. 關係權重 (如果用戶已登入) (15%)
                if user_id:
                    if post.get('user_id') in user_interactions:
                        score += 100 * 0.15
                
                # 4. 興趣匹配 (如果用戶已登入且貼文關聯電影) (15%)
                if user_id and 'movie_id' in post:
                    movie = get_document('movies', post['movie_id'])
                    if movie and 'genres' in movie:
                        movie_genres = movie.get('genres', [])
                        common_interests = set(user_interests).intersection(set(movie_genres))
                        if common_interests:
                            score += (len(common_interests) / max(len(user_interests), 1)) * 100 * 0.15
                
                # 存儲貼文和其分數
                scored_posts.append((post, score))
            
            # 基於分數排序貼文
            scored_posts.sort(key=lambda x: x[1], reverse=True)
            
            # 選擇前N篇貼文，並添加多樣性
            top_posts = []
            users_added = set()  # 跟踪已添加的用戶
            
            # 首先添加得分最高的貼文
            if scored_posts:
                top_posts.append(scored_posts[0][0])
                if 'user_id' in scored_posts[0][0]:
                    users_added.add(scored_posts[0][0]['user_id'])
            
            # 接著添加其他貼文，同時確保多樣性
            for post, score in scored_posts[1:]:
                # 如果我們已經有足夠的貼文，就停止
                if len(top_posts) >= limit:
                    break
                
                # 如果用戶已有貼文，並且我們還有其他用戶的貼文可選，就跳過
                if 'user_id' in post and post['user_id'] in users_added:
                    # 每個用戶最多有2篇貼文
                    user_posts_count = sum(1 for p in top_posts if p.get('user_id') == post['user_id'])
                    if user_posts_count >= 2:
                        continue
                
                top_posts.append(post)
                if 'user_id' in post:
                    users_added.add(post['user_id'])
            
            return top_posts
        
        return all_posts[:limit]
    except Exception as e:
        logger.error(f"獲取推薦貼文錯誤: {str(e)}")
        return []

def get_following_posts(user_id, limit=10, offset=0):
    """獲取用戶關注的人發布的貼文
    
    參數:
        user_id: 當前用戶ID
        limit: 返回貼文數量上限
        offset: 分頁偏移量
    """
    try:
        if not user_id:
            return []
            
        db = initialize_firebase()
        
        # 獲取用戶關注的人列表
        following = []
        following_docs = db.collection('follows').where('follower_id', '==', user_id).get()
        for doc in following_docs:
            following_data = doc.to_dict()
            if 'following_id' in following_data:
                following.append(following_data['following_id'])
        
        if not following:
            return []
        
        # 獲取關注的人的貼文
        posts_ref = db.collection('posts')
        posts = posts_ref.where('user_id', 'in', following) \
                         .order_by('created_at', direction=firestore.Query.DESCENDING) \
                         .limit(limit) \
                         .offset(offset) \
                         .get()
        
        result = []
        for post in posts:
            post_data = post.to_dict()
            post_data['id'] = post.id
            
            # 添加用戶信息
            if 'user_id' in post_data:
                user = get_document('users', post_data['user_id'])
                if user:
                    post_data['user_name'] = user.get('display_name', '未知用戶')
                    post_data['user_avatar'] = user.get('avatar_url', '')
            
            # 計算時間差
            if 'created_at' in post_data and post_data['created_at']:
                created_at = post_data['created_at']
                if isinstance(created_at, datetime):
                    now = datetime.now(timezone.utc)
                    diff = now - created_at
                    
                    if diff.days > 0:
                        post_data['time_ago'] = f"{diff.days} 天前"
                    elif diff.seconds // 3600 > 0:
                        post_data['time_ago'] = f"{diff.seconds // 3600} 小時前"
                    elif diff.seconds // 60 > 0:
                        post_data['time_ago'] = f"{diff.seconds // 60} 分鐘前"
                    else:
                        post_data['time_ago'] = "剛剛"
                else:
                    post_data['time_ago'] = "未知時間"
            
            # 獲取貼文點讚數和評論數
            post_data['likes_count'] = post_data.get('likes_count', 0)
            
            comments = db.collection('comments').where('post_id', '==', post.id).get()
            post_data['comments_count'] = len(comments)
            
            # 檢查當前用戶是否已點讚
            post_data['user_liked'] = False
            likes = db.collection('post_likes').where('post_id', '==', post.id).where('user_id', '==', user_id).get()
            if len(likes) > 0:
                post_data['user_liked'] = True
            
            result.append(post_data)
        
        return result
    except Exception as e:
        logger.error(f"獲取追蹤貼文錯誤: {str(e)}")
        return []

# ... 其他操作函數 ... 