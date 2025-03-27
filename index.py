from flask import Flask, render_template, request, Blueprint, redirect, session, flash, jsonify, make_response, url_for, g
from datetime import datetime, timezone, timedelta
from firebase_manager import authenticate_user, check_email_exists, create_user, get_all_documents, add_like, get_document, count_likes, check_user_liked, get_user_liked_movies, get_movie_recommendations, like_post, mark_all_notifications_as_read, upload_user_avatar, initialize_firebase, get_with_cache, get_collection_cached, get_movie_comments, create_post, get_posts, upload_to_firebase_storage, get_active_users, get_recommended_posts, get_following_posts
from web_crawler import crawl_movies, get_sample_movies
from forms import LoginForm, RegisterForm
from functools import wraps
import os
import secrets
import logging
import firebase_admin
from firebase_admin import firestore
from werkzeug.utils import secure_filename
import jinja2
import time

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
    try:
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
                flash('註冊成功！請登入', 'success')
                return redirect(url_for('auth.login'))
            else:
                flash('註冊失敗，請稍後再試', 'danger')
                return render_template('register.html', form=form)
        
        return render_template('register.html', form=form)
    except Exception as e:
        logger.error(f"註冊頁面錯誤: {str(e)}")
        flash('發生錯誤，請稍後再試', 'danger')
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
    """網站首頁 - 社交風格"""
    try:
        # 設定時區為 UTC+8（臺灣）
        tz = timezone(timedelta(hours=+8))
        now = datetime.now(tz)
        formatted_date = now.strftime("%Y年%m月%d日 %H:%M:%S")
        
        # 獲取當前用戶ID（如果已登入）
        user_id = session.get('user_id')
        
        # 使用新的推薦貼文函數
        posts = get_recommended_posts(user_id=user_id, limit=10) or []
        
        # 獲取熱門電影
        trending_movies = get_all_documents('movies', 5, 'rating', 'desc') or []
        
        # 獲取活躍用戶
        active_users = get_active_users(limit=5) or []
        
        # 獲取通知數量
        notification_count = 0
        
        # 獲取當前用戶信息
        user = None
        if user_id:
            user = get_document('users', user_id)
            # 這裡應該獲取用戶的通知數量
            # notification_count = get_user_notification_count(user_id)
        
        logger.info(f"渲染社交風格首頁: {len(posts)} 貼文, {len(trending_movies)} 電影, {len(active_users)} 活躍用戶")
        
        return render_template('index.html', 
                              posts=posts, 
                              user=user, 
                              trending_movies=trending_movies,
                              active_users=active_users,
                              notification_count=notification_count,
                              now=formatted_date)
    except Exception as e:
        logger.error(f"首頁錯誤: {str(e)}")
        return render_template('error.html', error=f"載入首頁時發生錯誤: {str(e)}"), 500

@app.route("/today")
def today():
    # 設定時區為 UTC+8（臺灣）
    tz = timezone(timedelta(hours=+8))
    now = datetime.now(tz)
    return render_template("today.html", datetime=str(now))

@app.route('/about')
def about():
    """關於我頁面"""
    try:
        # 設定時區為 UTC+8（臺灣）
        tz = timezone(timedelta(hours=+8))
        now = datetime.now(tz)
        formatted_date = now.strftime("%Y年%m月%d日 %H:%M:%S")
        
        return render_template('about.html', now=formatted_date)
    except Exception as e:
        logger.error(f"關於頁面錯誤: {str(e)}")
        return render_template('error.html', error=str(e)), 500

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
    """電影頁面 - 顯示所有電影"""
    try:
        # 獲取所有電影
        movies = get_all_documents('movies') or []
        
        # 獲取熱門電影
        trending_movies = get_all_documents('movies', 4, 'rating', 'desc') or []
        
        # 確保電影數據格式一致
        for movie in movies:
            if 'title' not in movie:
                movie['title'] = '未知標題'
        
        return render_template('movies.html', 
                               movies=movies, 
                               trending_movies=trending_movies)
    except Exception as e:
        logger.error(f"電影頁面錯誤: {str(e)}")
        return render_template('error.html', error=f"載入電影頁面時發生錯誤: {str(e)}"), 500

@app.route('/crawl-movies', methods=['POST'])
# 暫時移除登錄要求，方便測試
# @login_required
def crawl_movies_route():
    """爬取電影資料的API端點"""
    try:
        # 添加日誌
        logger.info("開始處理電影爬取請求")
        
        movies = crawl_movies()
        
        if movies:
            # 將爬取的電影數據保存到數據庫
            db = initialize_firebase()
            movies_collection = db.collection('movies')
            
            added_count = 0
            for movie in movies:
                # 檢查電影是否已存在（通過標題簡單比較）
                existing = movies_collection.where('title', '==', movie['title']).get()
                
                if not len(list(existing)):
                    # 添加創建時間
                    movie['created_at'] = firestore.SERVER_TIMESTAMP
                    movies_collection.add(movie)
                    added_count += 1
            
            logger.info(f"成功添加 {added_count} 部新電影")
            
            return jsonify({
                'success': True,
                'message': f'成功爬取 {len(movies)} 部電影，新增 {added_count} 部'
            })
        else:
            logger.warning("未找到電影數據")
            return jsonify({
                'success': False,
                'error': '沒有找到電影數據'
            })
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"爬取電影錯誤: {str(e)}\n{error_details}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/add-movie', methods=['POST'])
@login_required
def add_movie():
    """手動添加電影"""
    try:
        # 獲取表單數據
        title = request.form.get('title')
        description = request.form.get('description', '')
        rating = int(request.form.get('rating', 0))
        release_date = request.form.get('release_date', '')
        poster_url = request.form.get('poster_url', '')
        
        if not title:
            flash('電影標題不能為空', 'danger')
            return redirect('/movies')
        
        # 創建電影數據
        movie_data = {
            'title': title,
            'description': description,
            'rating': rating,
            'release_date': release_date,
            'poster_url': poster_url,
            'created_at': firestore.SERVER_TIMESTAMP
        }
        
        # 保存到數據庫
        db = initialize_firebase()
        db.collection('movies').add(movie_data)
        
        flash('電影已成功添加', 'success')
        return redirect('/movies')
    except Exception as e:
        logger.error(f"添加電影錯誤: {str(e)}")
        flash(f'添加電影失敗: {str(e)}', 'danger')
        return redirect('/movies')

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

@app.route('/movie/<movie_id>')
def movie_detail(movie_id):
    """電影詳情頁面"""
    try:
        # 獲取電影詳情
        movie = get_document('movies', movie_id)
        if not movie:
            return render_template('error.html', error='找不到此電影'), 404
        
        # 獲取電影評論
        comments = get_movie_comments(movie_id)
        
        # 獲取相關電影（同類型）
        related_movies = []
        if 'genre' in movie and movie['genre']:
            # 取第一個類型作為相關依據
            primary_genre = movie['genre'][0]
            all_movies = get_all_documents('movies', 20)
            related_movies = [
                m for m in all_movies if 'genre' in m and m['genre'] and 
                primary_genre in m['genre'] and m['id'] != movie_id
            ][:4]  # 最多顯示4部相關電影
        
        # 計算點讚數
        movie['likes_count'] = count_likes(movie_id)
        
        # 檢查用戶是否已點讚
        user_id = session.get('user_id')
        if user_id:
            movie['user_liked'] = check_user_liked(user_id, movie_id)
        
        # 根據當前風格選擇模板
        template = get_template_for_style('movie_detail.html')
        
        # 準備額外數據（針對不同風格可能需要的其他數據）
        extra_data = {}
        style = session.get('style', 'traditional')
        if style == 'cinesocial':
            # 為 CineSocial 風格添加額外數據
            try:
                extra_data['trending_movies'] = get_all_documents('movies', 5, 'rating', 'desc') or []
                extra_data['active_users'] = get_active_users(limit=5) or []
            except Exception as e:
                logger.error(f"獲取額外數據錯誤: {str(e)}")
        
        return render_template(template, movie=movie, comments=comments, 
                              related_movies=related_movies, **extra_data)
    except Exception as e:
        logger.error(f"電影詳情頁面錯誤: {str(e)}")
        return render_template('error.html', error=str(e)), 500

@app.route("/profile")
@login_required
def profile():
    try:
        user_id = session.get('user_id')
        user = get_document('users', user_id)
        
        # 選擇合適的模板
        template = get_template_for_style('profile.html')
        
        # 準備額外數據（針對不同風格可能需要的其他數據）
        extra_data = {}
        style = session.get('style', 'traditional')
        if style == 'cinesocial':
            # 為 CineSocial 風格添加額外數據
            extra_data['liked_movies'] = get_user_liked_movies(user_id)
            
        return render_template(template, user=user, **extra_data)
    except Exception as e:
        logger.error(f"個人資料頁面錯誤: {str(e)}")
        return render_template('error.html', error=str(e)), 500

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

@app.route("/set_language", methods=['POST'])
def set_language():
    """設置用戶語言偏好"""
    language = request.form.get('language', 'zh-TW')
    session['language'] = language
    return redirect(request.referrer or url_for('index'))

@app.errorhandler(404)
def page_not_found(e):
    """404錯誤處理 - 頁面未找到"""
    return render_template('error.html', error="找不到請求的頁面。如果您確信此頁面應該存在，請與管理員聯繫。"), 404

@app.errorhandler(500)
def internal_server_error(e):
    """500錯誤處理 - 伺服器錯誤"""
    return render_template('error.html', error="伺服器內部錯誤。請稍後再試。"), 500

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
    """Social風格首頁"""
    try:
        # 簡單實現，可以根據需要擴展
        movies = get_all_documents('movies', 10, 'date', 'desc')
        return render_template('index_social.html', movies=movies)
    except Exception as e:
        logger.error(f"Social首頁錯誤: {str(e)}")
        return render_template('error.html', error=str(e)), 500

@app.route('/movies/social')
def social_movies():
    # 類似傳統風格的代碼，但使用social模板
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    sort_by = request.args.get('sort', 'rating')
    page = int(request.args.get('page', 1))
    per_page = 12
    
    try:
        # 獲取電影數據
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
        
        # 計算總文檔數量
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
        
        return render_template('movies_social.html', movies=movies, pagination=pagination)
    except Exception as e:
        logger.error(f"社交風格電影列表錯誤: {str(e)}")
        return render_template('error.html', error=str(e)), 500

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

@app.route('/set-style/<style>')
def set_style(style):
    """設置用戶介面風格偏好"""
    allowed_styles = ['traditional', 'social', 'cinesocial']
    if style in allowed_styles:
        previous_style = session.get('style', 'traditional')
        session['style'] = style
        logger.info(f"用戶風格變更: {previous_style} -> {style}")
        
        # 如果是 AJAX 請求，返回 JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True})
        
        # 直接重定向到首頁，讓首頁函數處理風格切換
        return redirect(url_for('index'))
    return redirect(url_for('index'))

# Threads 風格頁面路由
@app.route('/threads')
def threads_home():
    """Threads風格首頁"""
    try:
        # 獲取貼文列表
        posts = get_posts(limit=20)
        
        # 獲取用戶信息
        user = None
        user_id = session.get('user_id')
        if user_id:
            user = get_document('users', user_id)
        
        return render_template('index_threads.html', posts=posts, user=user)
    except Exception as e:
        logger.error(f"Threads首頁錯誤: {str(e)}")
        return render_template('error.html', error=str(e)), 500

@app.route('/movies/threads')
def threads_movies():
    try:
        search = request.args.get('search', '')
        category = request.args.get('category', '')
        sort_by = request.args.get('sort', 'rating')
        page = int(request.args.get('page', 1))
        per_page = 12
        
        # 獲取電影數據
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
        
        # 計算總文檔數量
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
        
        return render_template('movies_threads.html', movies=movies, pagination=pagination)
    except Exception as e:
        logger.error(f"Threads風格電影列表錯誤: {str(e)}")
        return render_template('error.html', error=str(e)), 500

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
        # 檢查請求
        if not request.is_json:
            return jsonify({'success': False, 'error': '需要 JSON 格式'}), 400
            
        data = request.json
        text = data.get('text', '').strip() if data else ''
        movie_id = data.get('movie_id') if data else None
        image_url = data.get('image_url') if data else None
        
        # 檢查內容
        if not text and not image_url:
            return jsonify({'success': False, 'error': '內容不能為空'}), 400
        
        # 檢查用戶會話
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': '請先登入'}), 401
            
        # 創建貼文
        post = create_post(user_id, text, movie_id, image_url)
        
        if not post:
            return jsonify({'success': False, 'error': '發佈失敗，請稍後再試'}), 500
            
        return jsonify({'success': True, 'post': post})
    except Exception as e:
        logger.error(f"發佈貼文錯誤: {str(e)}")
        return jsonify({'success': False, 'error': f'處理請求時出錯: {str(e)}'}), 500

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

@app.route('/debug')
def debug_info():
    """顯示調試信息的頁面"""
    try:
        db = initialize_firebase()
        firebase_status = "Firebase連接正常"
    except Exception as e:
        firebase_status = f"Firebase錯誤: {str(e)}"
    
    info = {
        "app": str(app),
        "firebase": firebase_status,
        "routes": [str(rule) for rule in app.url_map.iter_rules()],
        "session": {k: session[k] for k in session}
    }
    
    return render_template('debug.html', info=info)

@app.route('/test')
def test_page():
    """測試頁面，驗證系統基本功能"""
    try:
        # 測試 Firebase 連接
        db = initialize_firebase()
        firebase_ok = True
    except Exception as e:
        firebase_ok = False
        logger.error(f"Firebase 連接測試失敗: {str(e)}")
    
    # 返回測試結果
    return render_template('test.html', 
                          firebase_ok=firebase_ok,
                          session_data=dict(session))

@app.route('/system-check')
def system_check():
    """全面系統檢查，檢測所有可能的錯誤來源"""
    results = {
        'firebase': {'status': 'unknown', 'details': ''},
        'routes': {'status': 'unknown', 'details': []},
        'templates': {'status': 'unknown', 'details': []},
        'session': {'status': 'unknown', 'details': {}}
    }
    
    # 1. 檢查 Firebase 連接
    try:
        db = initialize_firebase()
        # 嘗試一個簡單的讀取操作
        db.collection('users').limit(1).get()
        results['firebase'] = {'status': 'ok', 'details': '連接成功'}
    except Exception as e:
        results['firebase'] = {'status': 'error', 'details': str(e)}
    
    # 2. 檢查關鍵路由
    key_routes = ['index', 'movies', 'threads_home', 'threads_movies', 'set_style']
    for route in key_routes:
        try:
            url = url_for(route)
            results['routes']['details'].append({'route': route, 'url': url, 'status': 'ok'})
        except Exception as e:
            results['routes']['details'].append({'route': route, 'error': str(e), 'status': 'error'})
    
    results['routes']['status'] = 'ok' if all(r['status'] == 'ok' for r in results['routes']['details']) else 'error'
    
    # 3. 檢查關鍵模板
    key_templates = ['base.html', 'base_threads.html', 'index.html', 'index_threads.html', 'movies_threads.html']
    for template in key_templates:
        template_path = os.path.join(app.root_path, 'templates', template)
        if os.path.exists(template_path):
            results['templates']['details'].append({'template': template, 'status': 'ok'})
        else:
            results['templates']['details'].append({'template': template, 'status': 'missing'})
    
    results['templates']['status'] = 'ok' if all(t['status'] == 'ok' for t in results['templates']['details']) else 'error'
    
    # 4. 檢查 session
    results['session']['details'] = dict(session)
    results['session']['status'] = 'ok' if session else 'empty'
    
    # 5. 檢查靜態文件
    static_files = ['css/style.css', 'css/threads.css', 'js/main.js']
    results['static'] = {'status': 'unknown', 'details': []}
    
    for file in static_files:
        file_path = os.path.join(app.root_path, 'static', file)
        if os.path.exists(file_path):
            results['static']['details'].append({'file': file, 'status': 'ok'})
        else:
            results['static']['details'].append({'file': file, 'status': 'missing'})
    
    results['static']['status'] = 'ok' if all(f['status'] == 'ok' for f in results['static']['details']) else 'error'
    
    return render_template('system_check.html', results=results)

@app.route('/check-movies')
def check_movies():
    """檢查電影資料的頁面"""
    try:
        # 嘗試直接從Firebase獲取電影資料
        db = initialize_firebase()
        movies_ref = db.collection('movies').order_by('date', direction=firestore.Query.DESCENDING).limit(5)
        movies_raw = movies_ref.get()
        
        # 檢查原始資料
        movies_direct = []
        for doc in movies_raw:
            movie_data = doc.to_dict()
            movie_data['id'] = doc.id
            movies_direct.append(movie_data)
        
        # 使用現有函數獲取
        movies_function = get_all_documents('movies', 5, 'date', 'desc')
        
        return render_template('check_movies.html', 
                               movies_direct=movies_direct, 
                               movies_function=movies_function)
    except Exception as e:
        logger.error(f"電影資料檢查錯誤: {str(e)}")
        return render_template('error.html', error=str(e)), 500

@app.route('/add-test-movies')
def add_test_movies():
    """添加測試電影數據"""
    try:
        db = initialize_firebase()
        
        # 測試電影數據
        test_movies = [
            {
                'title': '測試電影 1',
                'description': '這是一部測試電影，用於檢查網站功能',
                'date': '2023-12-01',
                'image_url': 'https://via.placeholder.com/300x450?text=電影1',
                'genre': ['動作', '冒險'],
                'rating': 8.5
            },
            {
                'title': '測試電影 2',
                'description': '另一部測試電影，用於檢查網站功能',
                'date': '2023-11-15',
                'image_url': 'https://via.placeholder.com/300x450?text=電影2',
                'genre': ['喜劇', '家庭'],
                'rating': 7.8
            },
            {
                'title': '測試電影 3',
                'description': '第三部測試電影，用於檢查網站功能',
                'date': '2023-10-20',
                'image_url': 'https://via.placeholder.com/300x450?text=電影3',
                'genre': ['科幻', '驚悚'],
                'rating': 9.0
            }
        ]
        
        # 添加到 Firebase
        for movie in test_movies:
            db.collection('movies').add(movie)
        
        return jsonify({'success': True, 'message': '已添加3部測試電影'})
    except Exception as e:
        logger.error(f"添加測試電影錯誤: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

app.jinja_env.undefined = jinja2.Undefined  # 允許未定義的變量

@app.route('/cinesocial')
def cinesocial_home():
    """CineSocial風格首頁"""
    try:
        # 獲取貼文列表
        posts = get_posts(limit=20) or []
        
        # 獲取熱門電影
        try:
            trending_movies = get_all_documents('movies', 5, 'rating', 'desc') or []
        except Exception as e:
            logger.error(f"獲取熱門電影錯誤: {str(e)}")
            trending_movies = []
        
        # 獲取活躍用戶
        try:
            active_users = get_active_users(limit=5) or []
        except Exception as e:
            logger.error(f"獲取活躍用戶錯誤: {str(e)}")
            active_users = []
        
        # 獲取當前用戶信息
        user = None
        user_id = session.get('user_id')
        if user_id:
            user = get_document('users', user_id)
        
        logger.info(f"渲染 CineSocial 首頁: {len(posts)} 貼文, {len(trending_movies)} 電影, {len(active_users)} 活躍用戶")
        
        return render_template('index_cinesocial.html', 
                               posts=posts, 
                               user=user, 
                               trending_movies=trending_movies,
                               active_users=active_users)
    except Exception as e:
        logger.error(f"CineSocial首頁錯誤: {str(e)}")
        return render_template('error.html', error=f"載入 CineSocial 首頁時發生錯誤: {str(e)}"), 500

def get_template_for_style(base_template):
    """根據當前風格選擇正確的模板"""
    style = session.get('style', 'traditional')
    if style == 'cinesocial' and os.path.exists(f'templates/{base_template.replace(".html", "_cinesocial.html")}'):
        return base_template.replace('.html', '_cinesocial.html')
    elif style == 'social' and os.path.exists(f'templates/{base_template.replace(".html", "_social.html")}'):
        return base_template.replace('.html', '_social.html')
    return base_template

@app.route('/create-post', methods=['POST'])
@login_required
def create_new_post():
    """創建新貼文"""
    try:
        user_id = session.get('user_id')
        content = request.form.get('content', '').strip()
        
        if not content:
            flash('貼文內容不能為空', 'warning')
            return redirect(url_for('index'))
        
        # 處理圖片上傳
        image_url = None
        if 'image' in request.files:
            image_file = request.files['image']
            if image_file and image_file.filename:
                # 上傳圖片到 Firebase Storage
                image_url = upload_to_firebase_storage(image_file, f'post_images/{user_id}_{int(time.time())}')
        
        # 處理電影關聯（這裡假設有一個隱藏字段用於關聯電影）
        movie_id = request.form.get('movie_id')
        
        # 創建貼文
        post_id = create_post(user_id, content, image_url, movie_id)
        
        if post_id:
            flash('貼文已發布', 'success')
        else:
            flash('貼文發布失敗', 'danger')
            
        return redirect(url_for('index'))
    except Exception as e:
        logger.error(f"創建貼文錯誤: {str(e)}")
        flash('發生錯誤，請稍後再試', 'danger')
        return redirect(url_for('index'))

@app.route('/like-post/<post_id>', methods=['POST'])
@login_required
def like_post_route(post_id):
    """點讚或取消點讚貼文"""
    try:
        user_id = session.get('user_id')
        result = like_post(user_id, post_id)
        
        return jsonify({'success': True, 'liked': result})
    except Exception as e:
        logger.error(f"點讚操作錯誤: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/explore')
def explore():
    """探索頁面 - 發現熱門內容"""
    try:
        # 獲取熱門電影
        trending_movies = get_all_documents('movies', 8, 'rating', 'desc') or []
        
        # 獲取熱門貼文
        popular_posts = get_posts(limit=10, sort_by='likes_count') or []
        
        # 獲取推薦用戶
        recommended_users = get_active_users(limit=5) or []
        
        # 獲取當前用戶信息
        user = None
        user_id = session.get('user_id')
        if user_id:
            user = get_document('users', user_id)
        
        # 明確使用「explore.html」模板
        return render_template('explore.html', 
                              trending_movies=trending_movies,
                              popular_posts=popular_posts,
                              recommended_users=recommended_users,
                              user=user)
    except Exception as e:
        # 記錄詳細錯誤以便調試
        logger.error(f"探索頁面錯誤: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        # 返回錯誤頁面
        return render_template('error.html', error=f"載入探索頁面時發生錯誤: {str(e)}"), 500

@app.route('/notifications')
@login_required
def notifications():
    """通知頁面"""
    try:
        user_id = session.get('user_id')
        
        # 這裡應該獲取用戶的通知
        # notifications = get_user_notifications(user_id)
        notifications = []  # 暫時使用空列表
        
        # 模擬一些通知數據
        sample_notifications = [
            {
                'id': '1',
                'type': 'like',
                'user_name': '王大明',
                'user_avatar': '/static/images/default-avatar.png',
                'content': '喜歡了你的貼文',
                'time_ago': '1小時前',
                'is_read': False
            },
            {
                'id': '2',
                'type': 'comment',
                'user_name': '李小華',
                'user_avatar': '/static/images/default-avatar.png',
                'content': '評論了你的貼文: "這部電影真的很棒!"',
                'time_ago': '3小時前',
                'is_read': True
            },
            {
                'id': '3',
                'type': 'follow',
                'user_name': '張小明',
                'user_avatar': '/static/images/default-avatar.png',
                'content': '關注了你',
                'time_ago': '1天前',
                'is_read': True
            }
        ]
        
        notifications = sample_notifications
        
        return render_template('notifications.html', notifications=notifications)
    except Exception as e:
        logger.error(f"通知頁面錯誤: {str(e)}")
        return render_template('error.html', error=str(e)), 500

@app.route('/mark-all-notifications-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """將所有通知標記為已讀"""
    try:
        user_id = session.get('user_id')
        success = mark_all_notifications_as_read(user_id)
        
        return jsonify({'success': success})
    except Exception as e:
        logger.error(f"標記所有通知為已讀錯誤: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.before_request
def set_global_variables():
    """設置所有頁面共用的變數"""
    # 排除靜態文件和API請求
    if not request.path.startswith('/static') and not request.path.startswith('/api'):
        # 獲取熱門電影
        g.trending_movies = get_all_documents('movies', 3, 'rating', 'desc') or []
        
        # 獲取活躍用戶
        g.active_users = get_active_users(limit=3) or []
        
        # 獲取當前用戶
        g.user = None
        user_id = session.get('user_id')
        if user_id:
            g.user = get_document('users', user_id)
            # 獲取未讀通知數量
            # g.notification_count = get_user_notification_count(user_id)

@app.route('/api/following-posts')
@login_required
def api_following_posts():
    """API: 獲取追蹤者的貼文"""
    try:
        user_id = session.get('user_id')
        offset = int(request.args.get('offset', 0))
        
        posts = get_following_posts(user_id, limit=10, offset=offset)
        
        return jsonify({
            'success': True,
            'posts': posts
        })
    except Exception as e:
        logger.error(f"獲取追蹤貼文API錯誤: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/add-sample-movies', methods=['POST'])
def add_sample_movies():
    """添加示例電影數據"""
    try:
        # 從 web_crawler 中獲取示例電影
        movies = get_sample_movies()
        
        if movies:
            # 將示例電影保存到數據庫
            db = initialize_firebase()
            movies_collection = db.collection('movies')
            
            added_count = 0
            for movie in movies:
                # 檢查電影是否已存在
                existing = movies_collection.where('title', '==', movie['title']).get()
                
                if not len(list(existing)):
                    movie['created_at'] = firestore.SERVER_TIMESTAMP
                    movies_collection.add(movie)
                    added_count += 1
            
            return jsonify({
                'success': True,
                'message': f'成功添加 {added_count} 部示例電影'
            })
        else:
            return jsonify({
                'success': False,
                'error': '沒有示例電影數據'
            })
    except Exception as e:
        logger.error(f"添加示例電影錯誤: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == "__main__":
    app.run(debug=True, port=5001)