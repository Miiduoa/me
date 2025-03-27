from flask import Flask, render_template, request, Blueprint, redirect
from datetime import datetime, timezone, timedelta
from firebase_manager import authenticate_user, check_email_exists, create_user, get_all_documents
from web_crawler import crawl_movies

app = Flask(__name__)

# 使用藍圖組織相關路由
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = authenticate_user(username, password)
        if user:
            # 這裡可以設置session或cookie來跟踪登入狀態
            return redirect('/')
        else:
            return render_template('login.html', error='帳號或密碼不正確')
    return render_template('login.html')

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
    # 從Firebase獲取電影數據
    movies = get_all_documents("movies")
    return render_template("movies.html", movies=movies)

@app.route("/update_movies")
def update_movies():
    # 爬取最新電影數據
    movies = crawl_movies()
    return redirect("/movies")

if __name__ == "__main__":
    app.run(debug=True)