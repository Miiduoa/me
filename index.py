from flask import Flask, render_template, request, Blueprint, redirect, session, flash, jsonify, make_response, url_for
from datetime import datetime, timezone, timedelta
from firebase_manager import authenticate_user, check_email_exists, create_user, get_all_documents, add_like, get_document, count_likes, check_user_liked, get_user_liked_movies, get_movie_recommendations, upload_user_avatar, initialize_firebase, get_with_cache, get_collection_cached, get_movie_comments, create_post, get_posts
from web_crawler import crawl_movies
from forms import LoginForm, RegisterForm
from functools import wraps
import os
import secrets
import logging
import firebase_admin
from firebase_admin import firestore
from werkzeug.utils import secure_filename

app = Flask(__name__)

# 使用藍圖組織相關路由
auth_bp = Blueprint('auth', __name__)

# 從環境變量獲取密鑰，如果不存在則生成一個
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(16)

# 配置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 添加登入需求裝飾器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('請先登入', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        user = authenticate_user(email, password)
        if user:
            session['user_id'] = user.get('id')
            session['user_name'] = user.get('display_name')
            return redirect('/')
        else:
            form.email.errors.append('帳號或密碼不正確')
    return render_template('login.html', form=form)

@auth_bp.route('/logout')
def logout():
    # 清除session
    session.clear()
    return redirect('/')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        display_name = form.display_name.data
        email = form.email.data
        password = form.password.data
        
        # 檢查郵箱是否已存在
        if check_email_exists(email):
            form.email.errors.append('此電子郵件已被註冊')
            return render_template('register.html', form=form)
        
        # 創建新用戶
        user_id = create_user(email, password, display_name)
        if user_id:
            # 註冊成功，導向登入頁
            return redirect('/login')
        else:
            return render_template('register.html', form=form, error='註冊失敗，請稍後再試')
    
    return render_template('register.html', form=form)

@auth_bp.route('/verify-token', methods=['POST'])
def verify_token():
    try:
        id_token = request.json.get('idToken')
        if not id_token:
            return jsonify({'success': False, 'error': '未提供令牌'}), 400
        
        # 驗證令牌並獲取用戶信息
        auth = firebase_admin.auth
        decoded_token = auth.verify_id_token(id_token)
        
        # 獲取用戶ID和其他資訊
        uid = decoded_token['uid']
        email = decoded_token.get('email', '')
        display_name = decoded_token.get('name', '')
        
        # 檢查用戶是否已存在於資料庫
        db = initialize_firebase()
        user_ref = db.collection('users').document(uid)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            # 創建新用戶
            user_ref.set({
                'email': email,
                'display_name': display_name,
                'created_at': firestore.SERVER_TIMESTAMP
            })
        
        # 設置會話
        session['user_id'] = uid
        session['user_name'] = display_name
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"令牌驗證錯誤: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 400

# 註冊藍圖
app.register_blueprint(auth_bp)

@app.route('/')
def index():
    style = session.get('style', 'traditional')
    
    if style == 'social':
        return redirect(url_for('social_home'))
    elif style == 'threads':
        return redirect(url_for('threads_home'))
    
    # 傳統風格的主頁代碼...

@app.route("/today")
def today():
    # 設定時區為 UTC+8（臺灣）
    tz = timezone(timedelta(hours=+8))
    now = datetime.now(tz)
    return render_template("today.html", datetime=str(now))

@app.route("/about")
def about():
    # 顯示個人簡介網頁
    return render_template("about.html")

@app.route("/account", methods=["GET", "POST"])
def account():
    if request.method == "POST":
        # 取得使用者在表單中輸入的帳號與密碼
        user = request.form["user"]
        pwd = request.form["pwd"]
        result = f"您輸入的帳號是：{user}; 密碼為：{pwd}"
        return render_template("result.html", result=result)
    else:
        # GET 請求時，呈現表單頁面
        return render_template("account.html")

@app.route('/movies')
def movies():
    # 檢查用戶偏好的風格
    style = session.get('style', 'traditional')
    if style == 'social':
        return redirect(url_for('social_movies'))
    elif style == 'threads':
        return redirect(url_for('threads_movies'))
    
    # 以下是傳統風格的電影列表功能
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    sort_by = request.args.get('sort', 'rating')
    page = int(request.args.get('page', 1))
    per_page = 12
    
    # 獲取電影數據
    try:
        db = initialize_firebase()
        query = db.collection('movies')
        
        # 應用過濾器
        if search:
            query = query.where('title', '>=', search).where('title', '<=', search + '\uf8ff')
        if category:
            query = query.where('category', '==', category)
        
        # 應用排序
        if sort_by == 'rating':
            query = query.order_by('rating', direction=firestore.Query.DESCENDING)
        elif sort_by == 'date':
            query = query.order_by('date', direction=firestore.Query.DESCENDING)
        elif sort_by == 'likes':
            query = query.order_by('likes_count', direction=firestore.Query.DESCENDING)
        
        # 計算總文檔數量（警告：這在大型集合中效率低下）
        all_docs = list(query.get())
        total_docs = len(all_docs)
        total_pages = (total_docs + per_page - 1) // per_page
        
        # 分頁處理
        start_idx = (page - 1) * per_page
        end_idx = min(start_idx + per_page, total_docs)
        
        movies = []
        for doc in all_docs[start_idx:end_idx]:
            movie_data = doc.to_dict()
            movie_data['id'] = doc.id
            
            # 獲取喜歡數量
            movie_data['likes_count'] = count_likes(doc.id)
            
            # 如果用戶登入，標記用戶是否已喜歡
            user_id = session.get('user_id')
            if user_id:
                movie_data['user_liked'] = check_user_liked(user_id, doc.id)
            
            movies.append(movie_data)
        
        pagination = {
            'page': page, 
            'pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages
        }
        
        return render_template('movies.html', movies=movies, pagination=pagination)
    except Exception as e:
        # 記錄錯誤並顯示友好的錯誤頁面
        logger.error(f"電影列表錯誤: {str(e)}")
        return render_template('error.html', error=str(e)), 500

@app.route("/update_movies")
def update_movies():
    try:
        # 爬取最新電影數據
        movies = crawl_movies()
        return redirect("/movies")
    except Exception as e:
        logger.error(f"更新電影時發生錯誤: {str(e)}")
        return render_template('error.html', error='無法更新電影資料，請稍後再試'), 500

@app.route("/movie/<movie_id>/like", methods=["POST"])
def like_movie(movie_id):
    if 'user_id' not in session:
        return redirect('/login')
    
    try:
        # 添加用戶對電影的喜歡操作到 Firebase
        add_like(session['user_id'], movie_id)
        return redirect(f"/movie/{movie_id}")
    except Exception as e:
        logger.error(f"喜歡電影時發生錯誤: {str(e)}")
        # 提供友好的錯誤訊息而不是服務器崩潰
        return render_template('error.html', error='處理您的請求時出現問題，請稍後再試'), 500

@app.route("/movie/<movie_id>")
def movie_detail(movie_id):
    try:
        # 從Firebase獲取電影數據
        movie = get_with_cache('movies', movie_id)
        
        if not movie:
            return render_template('error.html', error='找不到此電影'), 404
        
        # 獲取此電影的喜歡數量
        likes_count = count_likes(movie_id)
        
        # 檢查當前用戶是否已喜歡此電影
        user_liked = False
        if 'user_id' in session:
            user_liked = check_user_liked(session['user_id'], movie_id)
        
        return render_template('movie_detail.html', movie=movie, likes_count=likes_count, user_liked=user_liked)
    except Exception as e:
        logger.error(f"顯示電影詳情時發生錯誤: {str(e)}")
        return render_template('error.html', error='載入電影詳情時出現問題'), 500

@app.route("/profile")
def profile():
    if 'user_id' not in session:
        return redirect('/login')
    
    try:
        # 獲取用戶資料
        user_id = session.get('user_id')
        user = get_document("users", user_id)
        
        if not user:
            return render_template('error.html', error='無法找到用戶資料'), 404
        
        # 獲取用戶喜歡的電影
        liked_movies = get_user_liked_movies(user_id)
        
        return render_template('profile.html', user=user, liked_movies=liked_movies)
    except Exception as e:
        logger.error(f"顯示用戶資料時發生錯誤: {str(e)}")
        return render_template('error.html', error='載入用戶資料時出現問題'), 500

@app.route("/profile/upload-avatar", methods=["POST"])
def upload_avatar():
    if 'user_id' not in session:
        return redirect('/login')
    
    try:
        if 'avatar' not in request.files:
            return redirect('/profile')
        
        avatar_file = request.files['avatar']
        if avatar_file.filename == '':
            return redirect('/profile')
        
        # 檢查文件類型
        if not avatar_file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
            flash('只支持圖片文件（PNG, JPG, JPEG, GIF）', 'error')
            return redirect('/profile')
        
        # 上傳頭像
        avatar_url = upload_user_avatar(session['user_id'], avatar_file)
        if avatar_url:
            flash('頭像上傳成功！', 'success')
        else:
            flash('頭像上傳失敗，請稍後再試', 'error')
        
        return redirect('/profile')
    except Exception as e:
        logger.error(f"上傳頭像時發生錯誤: {str(e)}")
        return render_template('error.html', error='上傳頭像時出現問題'), 500

@app.route("/movie/<movie_id>/comments", methods=["POST"])
def add_comment(movie_id):
    if 'user_id' not in session:
        return redirect('/login')
    
    try:
        comment_text = request.form.get('comment', '').strip()
        if not comment_text:
            flash('評論內容不能為空', 'error')
            return redirect(f'/movie/{movie_id}')
        
        # 添加評論到 Firebase
        user_id = session.get('user_id')
        user = get_document("users", user_id)
        
        comment_data = {
            'text': comment_text,
            'userId': user_id,
            'userName': user.get('display_name', '匿名用戶'),
            'created_at': firestore.SERVER_TIMESTAMP,
            'movie_id': movie_id
        }
        
        # 將評論添加為電影文檔的子集合
        db = initialize_firebase()
        db.collection('movies').document(movie_id).collection('comments').add(comment_data)
        
        flash('評論發布成功！', 'success')
        return redirect(f'/movie/{movie_id}')
    except Exception as e:
        logger.error(f"添加評論時發生錯誤: {str(e)}")
        return render_template('error.html', error='無法添加評論，請稍後再試'), 500

@app.route("/rankings")
def rankings():
    try:
        # 從Firebase獲取排行榜數據
        db = initialize_firebase()
        rankings_doc = db.collection('rankings').document('movies').get()
        
        if not rankings_doc.exists:
            flash('排行榜數據尚未生成', 'info')
            return render_template('rankings.html', movies=[])
        
        rankings_data = rankings_doc.to_dict()
        ranked_movies = rankings_data.get('movies', [])
        
        # 獲取完整電影信息
        movies_with_details = []
        for rank_data in ranked_movies:
            movie = get_document("movies", rank_data.get('id'))
            if movie:
                movie['rank_score'] = rank_data.get('score')
                movie['likes_count'] = rank_data.get('likes')
                movies_with_details.append(movie)
        
        return render_template('rankings.html', movies=movies_with_details)
    except Exception as e:
        logger.error(f"獲取排行榜時發生錯誤: {str(e)}")
        return render_template('error.html', error='載入排行榜時出現問題'), 500

@app.route("/admin/dashboard")
def admin_dashboard():
    if 'user_id' not in session:
        return redirect('/login')
    
    try:
        # 檢查用戶是否是管理員
        user_id = session.get('user_id')
        user = get_document("users", user_id)
        
        if not user or not user.get('isAdmin'):
            return render_template('error.html', error='您沒有權限訪問此頁面'), 403
        
        # 獲取最近7天的分析數據
        db = initialize_firebase()
        analytics_docs = []
        
        # 計算過去7天的日期
        for i in range(7):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            doc_id = f'daily_{date}'
            doc = db.collection('analytics').document(doc_id).get()
            if doc.exists:
                analytics_docs.append(doc.to_dict())
        
        # 按日期排序
        analytics_docs.sort(key=lambda x: x.get('date'))
        
        # 獲取總用戶數
        users_count = db.collection('users').count().get()[0][0].value
        
        # 獲取總電影數
        movies_count = db.collection('movies').count().get()[0][0].value
        
        # 獲取總喜歡數
        likes_count = db.collection('likes').count().get()[0][0].value
        
        return render_template('admin/dashboard.html', 
                               analytics=analytics_docs,
                               users_count=users_count,
                               movies_count=movies_count,
                               likes_count=likes_count)
    except Exception as e:
        logger.error(f"顯示管理員儀表板時發生錯誤: {str(e)}")
        return render_template('error.html', error='無法載入管理員儀表板'), 500

@app.route("/set_language", methods=["POST"])
def set_language():
    if 'user_id' not in session:
        # 未登入用戶使用Cookie存儲語言偏好
        language = request.form.get('language', 'zh-TW')
        response = make_response(redirect(request.referrer or '/'))
        response.set_cookie('preferred_language', language, max_age=365*24*60*60)
        return response
    
    try:
        # 登入用戶將語言偏好保存到Firebase
        user_id = session.get('user_id')
        language = request.form.get('language', 'zh-TW')
        
        db = initialize_firebase()
        db.collection('users').document(user_id).update({
            'preferred_language': language
        })
        
        # 同時設置Cookie
        response = make_response(redirect(request.referrer or '/'))
        response.set_cookie('preferred_language', language, max_age=365*24*60*60)
        return response
    except Exception as e:
        logger.error(f"設置語言偏好時發生錯誤: {str(e)}")
        return render_template('error.html', error='無法設置語言偏好'), 500

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', error='找不到頁面'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', error='伺服器內部錯誤'), 500

# 設置安全相關的頭部信息
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    # 添加 Content Security Policy
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; style-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; img-src 'self' data:;"
    
    return response

# 社群風格頁面路由
@app.route('/social')
def social_home():
    movies = get_collection_cached('movies', limit=6, order_by='rating', direction='desc')
    
    # 獲取推薦電影
    user_id = session.get('user_id')
    recommended_movies = []
    if user_id:
        recommended_movies = get_movie_recommendations(user_id, limit=6)
    else:
        # 未登入用戶顯示評分最高的另外6部電影
        recommended_movies = get_collection_cached('movies', limit=6, order_by='date', direction='desc')
    
    # 獲取用戶資訊（如果已登入）
    user = None
    if user_id:
        user = get_document('users', user_id)
    
    # 標記用戶已喜歡的電影
    if user_id:
        liked_movies = get_user_liked_movies(user_id)
        liked_ids = [movie['id'] for movie in liked_movies]
        
        for movie in movies:
            movie['user_liked'] = movie['id'] in liked_ids
    
    return render_template('index_social.html', movies=movies, recommended_movies=recommended_movies, user=user)

@app.route('/movies/social')
def social_movies():
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    sort_by = request.args.get('sort', 'rating')
    page = int(request.args.get('page', 1))
    per_page = 10
    
    # 獲取電影數據（這裡需要修改資料庫查詢以支援分頁）
    db = initialize_firebase()
    query = db.collection('movies')
    
    # 應用過濾器
    if search:
        query = query.where('title', '>=', search).where('title', '<=', search + '\uf8ff')
    if category:
        query = query.where('category', '==', category)
    
    # 應用排序
    if sort_by == 'rating':
        query = query.order_by('rating', direction=firestore.Query.DESCENDING)
    elif sort_by == 'date':
        query = query.order_by('date', direction=firestore.Query.DESCENDING)
    elif sort_by == 'likes':
        # 這需要預先計算的字段或改用 Cloud Function
        query = query.order_by('likes_count', direction=firestore.Query.DESCENDING)
    
    # 獲取總數量（用於分頁）
    total_docs = len(query.get())
    total_pages = (total_docs + per_page - 1) // per_page
    
    # 實現分頁
    offset = (page - 1) * per_page
    query = query.limit(per_page).offset(offset)
    
    movies = []
    for doc in query.get():
        movie_data = doc.to_dict()
        movie_data['id'] = doc.id
        
        # 獲取喜歡數量
        movie_data['likes_count'] = count_likes(doc.id)
        
        # 標記用戶是否已喜歡（如果已登入）
        user_id = session.get('user_id')
        if user_id:
            movie_data['user_liked'] = check_user_liked(user_id, doc.id)
        
        movies.append(movie_data)
    
    # 構建分頁信息
    pagination = {
        'page': page,
        'pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages
    }
    
    return render_template('movies_social.html', movies=movies, pagination=pagination)

@app.route('/movie/<movie_id>/social')
def social_movie_detail(movie_id):
    try:
        # 獲取電影詳情
        movie = get_document('movies', movie_id)
        if not movie:
            flash('找不到電影', 'danger')
            return redirect(url_for('social_movies'))
        
        # 獲取喜歡數量
        likes_count = count_likes(movie_id)
        
        # 獲取電影評論
        comments = get_movie_comments(movie_id)
        
        # 檢查用戶是否已喜歡
        user_id = session.get('user_id')
        user_liked = False
        user = None
        
        if user_id:
            user_liked = check_user_liked(user_id, movie_id)
            user = get_document('users', user_id)
            
            # 記錄觀看記錄
            db = initialize_firebase()
            db.collection('user_actions').add({
                'user_id': user_id,
                'movie_id': movie_id,
                'type': 'view',
                'timestamp': firestore.SERVER_TIMESTAMP
            })
        
        return render_template('movie_detail_social.html', movie=movie, likes_count=likes_count, 
                            user_liked=user_liked, comments=comments, user=user)
    except Exception as e:
        # 記錄錯誤並顯示友好的錯誤頁面
        logger.error(f"社交風格電影詳情錯誤: {str(e)}")
        return render_template('error.html', error=str(e)), 500

@app.route('/profile/social')
@login_required
def social_profile():
    user_id = session.get('user_id')
    user = get_document('users', user_id)
    
    if not user:
        flash('找不到用戶資料', 'danger')
        return redirect(url_for('index'))
    
    # 獲取用戶喜歡的電影
    liked_movies = get_user_liked_movies(user_id)
    
    return render_template('profile_social.html', user=user, liked_movies=liked_movies)

@app.route('/rankings/social')
def social_rankings():
    ranking_type = request.args.get('type', 'composite')
    
    # 獲取排行榜數據
    db = initialize_firebase()
    rankings_doc = db.collection('rankings').document('movies').get()
    
    movies = []
    if rankings_doc.exists:
        rankings_data = rankings_doc.to_dict()
        movies = rankings_data.get('movies', [])
        
        # 根據類型排序
        if ranking_type == 'rating':
            movies.sort(key=lambda x: float(x.get('rating', 0)), reverse=True)
        elif ranking_type == 'likes':
            movies.sort(key=lambda x: x.get('likes', 0), reverse=True)
        elif ranking_type == 'views':
            movies.sort(key=lambda x: x.get('views', 0), reverse=True)
        # 預設使用綜合評分
    
    return render_template('rankings_social.html', movies=movies, ranking_type=ranking_type)

@app.route('/switch-style')
def switch_style():
    current_style = session.get('style', 'traditional')
    
    # 循環切換三種風格: traditional -> social -> threads -> traditional
    if current_style == 'traditional':
        session['style'] = 'social'
    elif current_style == 'social':
        session['style'] = 'threads'
    else:
        session['style'] = 'traditional'
    
    # 重定向回當前頁面
    return redirect(request.referrer or url_for('index'))

# Threads 風格頁面路由
@app.route('/threads')
def threads_home():
    # 獲取貼文和電影
    posts = get_posts(limit=10)
    movies = get_all_documents('movies', 5, 'date', 'desc')
    
    # 標記用戶已喜歡的電影
    user_id = session.get('user_id')
    if user_id:
        liked_movies = get_user_liked_movies(user_id)
        liked_ids = [movie['id'] for movie in liked_movies]
        
        for movie in movies:
            movie['user_liked'] = movie['id'] in liked_ids
            # 獲取喜歡數量
            movie['likes_count'] = count_likes(movie['id'])
    
    # 獲取用戶資訊（如果已登入）
    user = None
    if user_id:
        user = get_document('users', user_id)
    
    return render_template('index_threads.html', movies=movies, posts=posts, user=user)

@app.route('/movies/threads')
def threads_movies():
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    sort_by = request.args.get('sort', 'date')
    page = int(request.args.get('page', 1))
    per_page = 20  # Threads風格應顯示更多項目
    
    # 獲取電影數據
    db = initialize_firebase()
    query = db.collection('movies')
    
    # 應用過濾器和排序
    if search:
        query = query.where('title', '>=', search).where('title', '<=', search + '\uf8ff')
    if category:
        query = query.where('category', '==', category)
    
    if sort_by == 'rating':
        query = query.order_by('rating', direction=firestore.Query.DESCENDING)
    elif sort_by == 'date':
        query = query.order_by('date', direction=firestore.Query.DESCENDING)
    elif sort_by == 'likes':
        query = query.order_by('likes_count', direction=firestore.Query.DESCENDING)
    
    # 分頁處理
    total_docs = len(query.get())
    total_pages = (total_docs + per_page - 1) // per_page
    offset = (page - 1) * per_page
    query = query.limit(per_page).offset(offset)
    
    movies = []
    for doc in query.get():
        movie_data = doc.to_dict()
        movie_data['id'] = doc.id
        movie_data['likes_count'] = count_likes(doc.id)
        
        # 標記用戶是否已喜歡
        user_id = session.get('user_id')
        if user_id:
            movie_data['user_liked'] = check_user_liked(user_id, doc.id)
        
        movies.append(movie_data)
    
    pagination = {
        'page': page, 
        'pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages
    }
    
    return render_template('movies_threads.html', movies=movies, pagination=pagination)

@app.route('/movie/<movie_id>/threads')
def threads_movie_detail(movie_id):
    try:
        # 獲取電影詳情
        movie = get_document('movies', movie_id)
        if not movie:
            flash('找不到電影', 'danger')
            return redirect(url_for('threads_movies'))
        
        # 獲取喜歡數量
        likes_count = count_likes(movie_id)
        
        # 獲取電影評論
        comments = get_movie_comments(movie_id)
        
        # 檢查用戶是否已喜歡
        user_id = session.get('user_id')
        user_liked = False
        user = None
        
        if user_id:
            user_liked = check_user_liked(user_id, movie_id)
            user = get_document('users', user_id)
            
            # 記錄觀看記錄
            db = initialize_firebase()
            db.collection('user_actions').add({
                'user_id': user_id,
                'movie_id': movie_id,
                'type': 'view',
                'timestamp': firestore.SERVER_TIMESTAMP
            })
        
        return render_template('movie_detail_threads.html', movie=movie, likes_count=likes_count, 
                            user_liked=user_liked, comments=comments, user=user)
    except Exception as e:
        # 記錄錯誤並顯示友好的錯誤頁面
        logger.error(f"Threads風格電影詳情錯誤: {str(e)}")
        return render_template('error.html', error=str(e)), 500

@app.route('/api/post', methods=['POST'])
@login_required
def post_api():
    try:
        data = request.json
        text = data.get('text', '').strip()
        movie_id = data.get('movie_id')
        image_url = data.get('image_url')
        
        if not text and not image_url:
            return jsonify({'success': False, 'error': '內容不能為空'})
        
        user_id = session.get('user_id')
        post = create_post(user_id, text, movie_id, image_url)
        
        if post:
            return jsonify({'success': True, 'post': post})
        else:
            return jsonify({'success': False, 'error': '發佈失敗，請稍後再試'})
    except Exception as e:
        logger.error(f"發佈貼文錯誤: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/upload-image', methods=['POST'])
@login_required
def upload_image():
    try:
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': '沒有圖片文件'})
        
        image = request.files['image']
        if image.filename == '':
            return jsonify({'success': False, 'error': '未選擇圖片'})
        
        # 允許的檔案類型
        if not image.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
            return jsonify({'success': False, 'error': '只支援PNG、JPG、JPEG或GIF圖片'})
        
        # 上傳到 Firebase Storage
        user_id = session.get('user_id')
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"posts/{user_id}/{timestamp}_{secure_filename(image.filename)}"
        
        # 使用您現有的上傳函數 (需要擴展 upload_user_avatar 函數或創建新函數)
        url = upload_to_firebase_storage(image, filename)
        
        if url:
            return jsonify({'success': True, 'url': url})
        else:
            return jsonify({'success': False, 'error': '圖片上傳失敗'})
    except Exception as e:
        logger.error(f"圖片上傳錯誤: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

if __name__ == "__main__":
    app.run(debug=True)