from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo

class LoginForm(FlaskForm):
    email = StringField('電子郵件', validators=[DataRequired(), Email()])
    password = PasswordField('密碼', validators=[DataRequired()])
    submit = SubmitField('登入')

class RegisterForm(FlaskForm):
    display_name = StringField('顯示名稱', validators=[DataRequired(), Length(min=2, max=20)])
    email = StringField('電子郵件', validators=[DataRequired(), Email()])
    password = PasswordField('密碼', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('確認密碼', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('註冊') 