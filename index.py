from flask import Flask, render_template, request, Blueprint, redirect, session, flash, jsonify, make_response
from datetime import datetime, timezone, timedelta
from firebase_manager import authenticate_user, check_email_exists, create_user, get_all_documents, add_like, get_document, count_likes, check_user_liked, get_user_liked_movies, get_movie_recommendations, upload_user_avatar, initialize_firebase
from web_crawler import crawl_movies
from forms import LoginForm, RegisterForm
import os
import secrets
import logging
import firebase_admin
from firebase_admin import firestore

app = Flask(__name__)

# 使用藍圖組織相關路由
auth_bp = Blueprint('auth', __name__)

# 從環境變量獲取密鑰，如果不存在則生成一個
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(16)

# 配置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

@app.route("/")
def index():
    # 獲取精選電影顯示在首頁
    all_movies = get_all_documents("movies")
    # 按評分排序，獲取前3部
    featured_movies = sorted(all_movies, key=lambda x: float(x.get('rating', 0)), reverse=True)[:3]
    
    # 獲取用戶推薦電影
    recommended_movies = []
    if 'user_id' in session:
        recommended_movies = get_movie_recommendations(session['user_id'], limit=3)
    
    return render_template("index.html", 
                           movies=featured_movies, 
                           recommended_movies=recommended_movies)

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

@app.route("/movies")
def movies():
    # 搜索功能
    search_query = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 9  # 每頁顯示的電影數量
    
    # 從Firebase獲取電影數據
    all_movies = get_all_documents("movies")
    
    # 如果有搜索查詢，過濾結果
    if search_query:
        all_movies = [movie for movie in all_movies if search_query.lower() in movie.get('title', '').lower()]
    
    # 簡單分頁實現
    total = len(all_movies)
    total_pages = (total + per_page - 1) // per_page
    
    if page < 1:
        page = 1
    elif page > total_pages and total_pages > 0:
        page = total_pages
    
    start = (page - 1) * per_page
    end = start + per_page
    movies = all_movies[start:end]
    
    return render_template(
        "movies.html", 
        movies=movies, 
        page=page, 
        total_pages=total_pages,
        search_query=search_query
    )

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
        movie = get_document("movies", movie_id)
        
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

if __name__ == "__main__":
    app.run(debug=True)