from flask import Flask, request, render_template, redirect, url_for, flash, send_file
import spacy
from pymongo import MongoClient
from gridfs import GridFS
from bson import ObjectId
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, EqualTo, Email
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'random_key'

# Initialize the LoginManager and MongoDB client
login_manager = LoginManager(app)
login_manager.login_view = 'login'
client = MongoClient("mongodb://localhost:27017")  # Replace with your actual MongoDB URL

# User model
class User(UserMixin):
    def __init__(self, email, user_type):
        self.id = email
        self.user_type = user_type

@login_manager.user_loader
def load_user(email):
    db = client["login"]
    user_data = db.users.find_one({"email": email})
    if user_data:
        return User(email=user_data["email"], user_type=user_data["user_type"])

# Login form
class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

# Registration form
class RegistrationForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    user_type = StringField('User Type (candidate or company)', validators=[DataRequired()])
    submit = SubmitField('Register')

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        db = client["login"]
        user = db.users.find_one({"email": form.email.data})
        
        if user and check_password_hash(user['password'], form.password.data):
            user_obj = User(email=user["email"], user_type=user["user_type"])
            login_user(user_obj)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
    return render_template('login.html', title='Login', form=form)

@app.route("/register", methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data, method='pbkdf2:sha256')
        new_user = {
            "email": form.email.data,
            "password": hashed_password,
            "user_type": form.user_type.data.lower()
        }
        db = client["login"]
        db.users.insert_one(new_user)
        flash('Account created successfully', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/upload_form')
@login_required
def upload_form():
    if current_user.user_type != 'candidate':
        flash('You do not have access to this page', 'danger')
        return redirect(url_for('dashboard'))
    return render_template('upload.html')

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.user_type == 'candidate':
        return redirect(url_for('upload_form'))
    elif current_user.user_type == 'company':
        return render_template('job_request.html')
    else:
        flash('Unauthorized user type', 'danger')
        return redirect(url_for('logout'))

@app.route('/match', methods=['POST'])
def match_resumes():
    user_input = request.form.get('job_description')
    nlp = spacy.load("model_upgrade")  # Ensure model path is correct
    doc = nlp(user_input)
    technology_names = [ent.text.lower() for ent in doc.ents if ent.label_ in ["ORG", "TECHNOLOGY", "TECH"]]

    db = client["candidates"]
    users = db["candidates"]
    user_data = list(users.aggregate([
        {"$match": {"skills": {"$in": technology_names}}},
        {"$addFields": {"matchedSkills": {"$size": {"$setIntersection": ["$skills", technology_names]}}}},
        {"$sort": {"matchedSkills": -1}}
    ]))

    return render_template('view_resumes.html', user_data=user_data, technology_names=technology_names)

@app.route("/upload", methods=["POST"])
@login_required
def upload():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        skills = request.form["skills"]
        resume_file = request.files["resume"]

        # Check if the file is in the correct format
        if not resume_file.filename.lower().endswith(('.doc', '.docx')):
            flash("Only Word documents (.doc, .docx) are allowed.", "danger")
            return redirect(url_for('upload_form'))

        db = client["candidates"]
        fs = GridFS(db)
        
        # Format skills into a list
        skills = list(set(skill.strip().lower() for skill in skills.split(',') if skill.strip()))

        # Save the resume to GridFS
        if resume_file:
            resume_id = fs.put(resume_file, filename=resume_file.filename)
            user_data = {"name": name, "email": email, "skills": skills, "resume_id": resume_id}
            db.candidates.insert_one(user_data)
            flash('Resume Uploaded Successfully', 'success')
            return redirect(url_for('upload_form'))
    return redirect(url_for('home'))

@app.route('/fetch_resume/<resume_id>')
def fetch_resume(resume_id):
    db = client["candidates"]
    fs = GridFS(db)
    resume_file = fs.get(ObjectId(resume_id))
    return send_file(resume_file, mimetype='application/msword', as_attachment=True, download_name=f"{resume_id}.docx")

if __name__ == '__main__':
    app.run(debug=True)
