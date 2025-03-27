from flask import Flask, render_template, request, Blueprint, redirect, session
from datetime import datetime, timezone, timedelta
from firebase_manager import authenticate_user, check_email_exists, create_user, get_all_documents, add_like, get_document, count_likes, check_user_liked
from web_crawler import crawl_movies
from forms import LoginForm, RegisterForm
import os
import secrets

app = Flask(__name__)

# 使用藍圖組織相關路由
auth_bp = Blueprint('auth', __name__)

# 從環境變量獲取密鑰，如果不存在則生成一個
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(16)

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

# 註冊藍圖
app.register_blueprint(auth_bp)

@app.route("/")
def index():
    # 使用模板渲染首頁
    return render_template("index.html")

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
    # 爬取最新電影數據
    movies = crawl_movies()
    return redirect("/movies")

@app.route("/movie/<movie_id>/like", methods=["POST"])
def like_movie(movie_id):
    if 'user_id' not in session:
        return redirect('/login')
    
    # 添加用戶對電影的喜歡操作到 Firebase
    add_like(session['user_id'], movie_id)
    return redirect(f"/movie/{movie_id}")

@app.route("/movie/<movie_id>")
def movie_detail(movie_id):
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