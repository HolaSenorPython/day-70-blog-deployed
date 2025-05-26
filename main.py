from datetime import date
from flask import Flask, abort, render_template, redirect, url_for, flash, g
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import NoResultFound, MultipleResultsFound
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text, ForeignKey
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
# Import your forms from the forms.py
from forms import CreatePostForm, RegisterUserForm, LoginForm, CommentForm, ContactForm
import smtplib
import os

'''
Make sure the required packages are installed: 
Open the Terminal in PyCharm (bottom left). 

On Windows type:
python -m pip install -r requirements.txt

On MacOS type:
pip3 install -r requirements.txt

This will install the packages from the requirements.txt for this project.
'''

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_KEY')
ckeditor = CKEditor(app)
Bootstrap5(app)

# TODO: Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app=app)

# CREATE DATABASE
class Base(DeclarativeBase):
    pass
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DB_URI', 'sqlite:///posts.db')
db = SQLAlchemy(model_class=Base)
db.init_app(app)


# CONFIGURE TABLES
class BlogPost(db.Model):
    __tablename__ = "blog_posts"

    # Create Foreign Key, "users.id" the users refers to the tablename of User.
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("Users.id"))
    # Create reference to the User object. The "posts" refers to the posts property in the User class.
    author = relationship("User", back_populates="posts")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)

    # PARENT RELATION!
    comments = relationship("Comment", back_populates="parent_post")

# TODO: Create a User table for all your registered users. 
class User(db.Model, UserMixin):
    __allow_unmapped__ = True
    __tablename__ = "Users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    profile_pic: Mapped[str] = mapped_column(String(250), nullable=False)

    # This will act like a List of BlogPost objects attached to each User.
    # The "author" refers to the author property in the BlogPost class.
    posts = relationship("BlogPost", back_populates="author")
    comments = relationship("Comment", back_populates="author")

    def __init__(self, email: str, password: str, name: str, profile_pic: str):
        self.email = email
        self.password = password
        self.name = name
        self.profile_pic = profile_pic

# CREATE A COMMENT TABLE AND LINK IT to USER!!
class Comment(db.Model):
    __tablename__ = "Comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # OUR AUTHOR ID AND AUTHOR IS JUST GOING TO BE OUR USER'S ID AND USER
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("Users.id"))
    author = relationship("User", back_populates="comments")

    # ***************Child Relationship*************#
    post_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("blog_posts.id"))
    parent_post = relationship("BlogPost", back_populates="comments")
    text: Mapped[str] = mapped_column(Text, nullable=False)

with app.app_context():
    db.create_all()

# USER LOADER CALLBACK
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, user_id)

# SET-UP ADMIN CHECK FUNCTION/DECORATOR!!
def admin_only(function):
    @wraps(function)
    def admin_check(*args, **kwargs):
        if current_user is None:
            return redirect(url_for('login'))
        elif current_user.id == 1:
            return function(*args, **kwargs)
        else:
            return abort(403)
    return admin_check

# TODO: Use Werkzeug to hash the user's password when creating a new user.
@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterUserForm()

    if form.validate_on_submit(): # IF A POST REQUEST IS MADE...
        user_email = form.email.data
        user_pass = form.password.data
        user_name = form.name.data
        user_profile_pic = form.profile_pic.data
        # Search if there's already a user like this, try saving the user as a variable but if not (error) then user is none
        result = db.session.execute(db.select(User).where(User.email == user_email))
        user = result.scalar()

        if user:
            flash(f"There is already an account registered with the email {user_email}!")
            return redirect(url_for('login'))

        # Now if there ISN'T already a user, lets make one!
        salty_password = generate_password_hash(user_pass, "pbkdf2:sha256", salt_length=8)
        new_user = User(
            email=user_email,
            password=salty_password,
            name=user_name,
            profile_pic=user_profile_pic,
        )
        db.session.add(new_user)
        db.session.commit()

        login_user(new_user)
        flash(f"Successfully registered as {user_name}.")
        return redirect(url_for('get_all_posts', logged_in=current_user.is_authenticated, user=new_user))

    return render_template("register.html", form=form)


# TODO: Retrieve a user from the database based on their email. 
@app.route('/login', methods=['GET', 'POST'])
def login():
    login_form = LoginForm()

    if login_form.validate_on_submit(): # if a POST request is made
        email = login_form.email.data
        password = login_form.password.data

        # Check if the entered email needs to be registered or alr exists
        try:
            requested_user = db.session.execute(db.select(User).where(User.email == email)).scalar_one()
        except NoResultFound:
            flash("The requested user doesn't exist in our database! Maybe try registering instead?")
            return redirect(url_for('register'))
        except MultipleResultsFound:
            flash("Something is wrong: There are multiple accounts with the same email. Contact support for help!")
            return redirect(url_for('login'))

        password_check = check_password_hash(requested_user.password, password)

        if password_check:
            login_user(requested_user)
            flash(f"Successfully logged in as {requested_user.name}!")
            return redirect(url_for('get_all_posts', user=requested_user))
        else:
            flash("The password inputted is incorrect. 🤓☝️")
            return redirect(url_for('login'))

    return render_template("login.html", form=login_form)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    return render_template("index.html", all_posts=posts, logged_in=current_user.is_authenticated, user=current_user)


# TODO: Allow logged-in users to comment on posts
@app.route("/post/<int:post_id>", methods=['GET', 'POST'])
def show_post(post_id):
    requested_post = db.get_or_404(BlogPost, post_id)
    comments = db.session.execute(db.select(Comment).where(Comment.post_id == post_id)).scalars()
    com_form = CommentForm()
    if com_form.validate_on_submit(): # IF A COMMENT IS MADE...
        if not current_user.is_authenticated:
            flash("You must be LOGGED IN to post a comment! 🙂‍↔️🙂‍↔️")
            return redirect(url_for('login'))
        else:
            comment = Comment(
                parent_post=requested_post,
                text=com_form.comment.data,
                author=current_user,
            )
            db.session.add(comment)
            db.session.commit()
            return redirect(url_for('show_post', post_id=post_id))

    return render_template("post.html", post=requested_post, logged_in=current_user.is_authenticated, com_form=com_form, comments=comments, user=current_user)


# TODO: Use a decorator so only an admin user can create a new post
@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts", logged_in=current_user.is_authenticated))
    return render_template("make-post.html", form=form, logged_in=current_user.is_authenticated)


# TODO: Use a decorator so only an admin user can edit a post
@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id, logged_in=current_user.is_authenticated))
    return render_template("make-post.html", form=edit_form, is_edit=True, logged_in=current_user.is_authenticated)


# TODO: Use a decorator so only an admin user can delete a post
@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))

@app.route("/about")
def about():
    return render_template("about.html", logged_in=current_user.is_authenticated)

# THIS FUNCTION HANDLES THE CONTACT FORM AND SENDING ME MESSAGES
def send_email(name, email, message):
    my_email = os.environ.get('MY_EMAIL_FOR_USER')
    my_pass = os.environ.get('MY_PASS_FOR_USER')
    users_email = email
    users_msg = message
    users_name = name
    try:
        with smtplib.SMTP("smtp.gmail.com", port=587) as connection:
            connection.starttls()
            connection.login(user=my_email, password=my_pass)
            connection.sendmail(
                from_addr=my_email,
                to_addrs=my_email,
                msg=f"""Subject: You've got a contact form message from {users_name}!\n\n
Name: {users_name}
Email: {users_email}
            
User's message: {message}
"""
        )
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

@app.route("/contact", methods=['GET', 'POST'])
def contact():
    contact_form = ContactForm()
    if contact_form.validate_on_submit(): # If a POST request is made...
        user_name = contact_form.name.data
        user_email = contact_form.email.data
        user_msg = contact_form.message.data
        email_sent = send_email(user_name, user_email, user_msg) # DO THE SEND EMAIL function
        if email_sent:
            flash("Successfully sent email! Elisha will get back to you shortly. 😏🥳🎉", "success")
            return redirect(url_for('contact'))
        else:
            flash("Oops! Something went wrong while trying to send your email. 🥴😵‍💫", "error")
            return redirect(url_for('contact'))
    return render_template("contact.html", logged_in=current_user.is_authenticated, form=contact_form)

if __name__ == "__main__":
    app.run(debug=False)
