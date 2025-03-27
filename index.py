from flask import Flask, render_template, request, Blueprint, redirect, session
from datetime import datetime, timezone, timedelta
from firebase_manager import authenticate_user, check_email_exists, create_user, get_all_documents
from web_crawler import crawl_movies

app = Flask(__name__)

# 使用藍圖組織相關路由
auth_bp = Blueprint('auth', __name__)

# 在app初始化後添加
app.secret_key = 'your_secret_key'  # 在實際應用中使用安全的隨機字符串

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = authenticate_user(username, password)
        if user:
            # 使用session記錄登入狀態
            session['user_id'] = user.get('id')
            session['user_name'] = user.get('display_name')
            return redirect('/')
        else:
            return render_template('login.html', error='帳號或密碼不正確')
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    # 清除session
    session.clear()
    return redirect('/')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        display_name = request.form.get('display_name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # 表單驗證
        if password != confirm_password:
            return render_template('register.html', error='兩次輸入的密碼不一致')
        
        # 檢查郵箱是否已存在
        if check_email_exists(email):
            return render_template('register.html', error='此電子郵件已被註冊')
        
        # 創建新用戶
        user_id = create_user(email, password, display_name)
        if user_id:
            # 註冊成功，導向登入頁
            return redirect('/login')
        else:
            return render_template('register.html', error='註冊失敗，請稍後再試')
    
    return render_template('register.html')

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
    
    # 從Firebase獲取電影數據
    movies = get_all_documents("movies")
    
    # 如果有搜索查詢，過濾結果
    if search_query:
        movies = [movie for movie in movies if search_query.lower() in movie.get('title', '').lower()]
    
    return render_template("movies.html", movies=movies)

@app.route("/update_movies")
def update_movies():
    # 爬取最新電影數據
    movies = crawl_movies()
    return redirect("/movies")

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', error='找不到頁面'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', error='伺服器內部錯誤'), 500

if __name__ == "__main__":
    app.run(debug=True)