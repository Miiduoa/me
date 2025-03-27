from flask import Flask, render_template, request
from datetime import datetime
app = Flask(__name__)

@app.route("/")
def index():
    homepage = "<h1>顧晉瑋Python網頁</h1>"
    homepage += "<a href='/mis'>MIS</a><br>"
    homepage += "<a href='/today'>顯示日期時間</a><br>"
    homepage += "<a href='/welcome?nick=顧晦瑋'>傳送使用者暱稱</a><br>"
    homepage += "<a href='/account'>網頁表單傳值</a><br>"
    homepage += "<a href='/about'>顧晉瑋簡介網頁</a><br>"
    return homepage

@app.route("/mis")
def course():
    return "<h1>資訊管理導論</h1>"

@app.route("/today")
def today():
    now = datetime.now()
    return render_template("today.html", datetime=str(now))

@app.route("/welcome", methods=["GET", "POST"])
def welcome():
    user = request.values.get("nick")
    return render_template("welcome.html", name=user)

@app.route("/account", methods=["GET", "POST"])
def account():
    if request.method == "POST":
        user = request.form["user"]
        pwd = request.form["pwd"]
        result = "您輸入的帳號是：" + user + "; 密碼為：" + pwd 
        return result
    else:
        return render_template("account.html")

@app.route("/about")
def about():
    return "<h1>顧晉瑋簡介網頁</h1><p>這裡放個人簡介內容，例如個人網頁、聯絡資訊等。</p>"

if __name__ == "__main__":
    app.run(debug=True)