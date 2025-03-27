from waitress import serve

if __name__ == "__main__":
    # app.run()
    serve(app, host='0.0.0.0', port=8080)
from datetime import datetime
app = Flask(__name__)

@app.route("/")
def index():
    return "Hello World!"

@app.route("/today")
def today():
    now = datetime.now()
    return render_template("today.html", datetime=str(now))

if __name__ == "__main__":
    app.run()
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