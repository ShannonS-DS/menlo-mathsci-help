from flask import render_template, flash, redirect, session, url_for, request, g
from flask.ext.login import login_user, logout_user, current_user, login_required
from app import app, db, lm
from forms import LoginForm
from models import User, Request, Subject, ROLE_USER, ROLE_ADMIN 
from bcrypt import hashpw, gensalt
from emails import send_email
from os import urandom
from datetime import datetime

PASSWORD_CHARS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+?'
NEW_PASSWORD_LENGTH = 13;
ISSUE_MAP = {'hw':'Homework', 'proj': 'Project', 'test': 'Test'}


@lm.user_loader
def load_user(id):
    return User.query.get(int(id))

@app.before_request
def before_request():
    g.user = current_user #current_user is a Flask-Login global, so we copy it into g.user so that all requests and HTML templates have access to it
    
@app.route('/')
@app.route('/index')
def index():
    return render_template('index.html',
        title = 'Home')

@app.route('/me')
@login_required
def me():
    return render_template('me.html',
        title="Me")

@app.route('/login', methods = ['GET', 'POST'])
def login():
    if g.user is not None and g.user.is_authenticated(): #The user is already logged in
        return redirect(url_for('me'))

    #They hit the submit button
    if request.method == 'POST':
        info = request.form
        email = info['email'] #Could try to smartly add an @menloschool.org
        password = info['password']
        remember_me = False
        if 'remember-me' in info:
            remember_me = info['remember-me'].data
        
        if email is None or email == "":
            flash('Invalid email. Please try again.')
            return redirect(url_for('login'))
        
        if password is None or password == "":
            flash('Invalid password. Please try again.')
            return redirect(url_for('login'))
        
        user = User.query.filter_by(email = email).first()
        if user is None:
            flash('The email "{0}" is not stored in our database.'.format(email))
            return redirect(url_for('login'))

        if not user.verify_password(password):
            flash('Incorrect password. Please try again.')
            return redirect(url_for('login'))
        
        now = datetime.utcnow()
        user.last_logged_in = now
        db.session.add(user)
        db.session.commit()
        login_user(user, remember = remember_me)
        return redirect(request.args.get('next') or url_for('me'))
    return render_template('login.html', 
        title = 'Sign In')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if g.user is not None and g.user.is_authenticated(): #The user is already logged in
        return redirect(url_for('me'))

    #They hit the submit button
    if request.method == 'POST':
        #Do verification here.
        info = request.form
        email = info['email'] + "@menloschool.org"
        hashed_password = hashpw(info['password'], gensalt())

        first_name = info['first_name']
        last_name = info['last_name']
        grade = int(info['grade'])

        now = datetime.utcnow()
        user = User(email=email, 
            hashed_password=hashed_password, 
            first_name=first_name,
            last_name=last_name,
            grade=grade,
            role=ROLE_USER,
            created=now,
            last_logged_in=now)

        tutoring_classes = info.getlist('tutor_science') + info.getlist('tutor_math') + info.getlist('tutor_cs_as')
        for cl in tutoring_classes:
            subj = Subject.query.filter_by(name=cl).first()
            if subj != None:
                user.tutor_subject(subj)

        learning_classes = info.getlist('learn_science') + info.getlist('learn_math') + info.getlist('learn_cs_as')
        for cl in learning_classes:
            subj = Subject.query.filter_by(name=cl).first()
            if subj != None:
                user.learn_subject(subj)

        db.session.add(user)
        db.session.commit()
        flash("Logged in successfully.")
        login_user(user)
        return redirect(url_for('me'))
    return render_template('signup.html')

@app.route('/edit', methods=['GET', 'POST'])
@login_required
def edit():
    return render_template('edit.html',
        title="Edit")

@app.route('/reset_password', methods = ['GET', 'POST'])
def reset_password():
    if g.user is not None and g.user.is_authenticated(): #The user is already logged in
        return redirect(url_for('me'))
    #They hit the submit button
    if request.method == 'POST':
        email = request.form['email']
        if len(email) == 0:
            flash("You didn't enter anything! Please enter an email.")
            return redirect(url_for('reset_password'))
        if not email.endswith("@menloschool.org"):
            email += "@menloschool.org"
        u = User.query.filter_by(email=email).first()
        if u is None: #email not in database
            flash("The email address '{0}' isn't in our database. Try again, and this time make sure you entered the email correctly. Alternatively, sign up for an account.".format(email))
            return redirect(url_for('reset_password'))
        try:
            new_pass = ''.join(PASSWORD_CHARS[ord(urandom(1)) % 64] for i in xrange(NEW_PASSWORD_LENGTH))
            send_email('Password Reset Notification', [email], 
                render_template('reset_password_email.txt', user = u, new_pass=new_pass),
                render_template('reset_password_email.html', user = u, new_pass=new_pass))
            hashed_password = hashpw(new_pass, gensalt())
            u.hashed_password = hashed_password
            db.session.add(u)
            db.session.commit()
            flash("Password Reset. Email sent successfully to '{0}'.".format(email))
            return redirect(url_for('index'))
        except Exception as e:
            flash("Uh oh! Looks like we couldn't send that email. Are you sure you entered the email address correctly?")
            flash("Specific error: {0}".format(repr(e)))
            return(redirect(url_for('reset_password')))
        
    return render_template('reset_password.html',
        title="Reset Password")

@app.route('/user/<int:user_id>')
def show_user(user_id=None):
    user = User.query.filter_by(id = user_id).first()
    return render_template('view_user.html',
        user=user)

@app.route('/learn', methods=['GET', 'POST'])
@login_required
def learn():
    if request.method=='POST': #Looking at the page
        info = request.form

        '''
        Server-side validation, in case bad data slips through
        Possible Errors:
            Invalid class selected
            'Other' issue selected but nothing filled in
            Nothing in the 'title' section
            Nothing in the 'specific challenge' section
        '''
        subj = Subject.query.filter_by(title=info['subj_title']).first()
        if subj == None:
            flash("Invalid subject selected. Please leave page source alone.");
            return redirect(url_for('learn'))
        else:
            now = datetime.utcnow()
            issue=info['issue']
            title=info['title']
            body=info['challenge']

            if issue == 'other':
                elaboration=info['elaboration']
                if elaboration == "" or elaboration == None:
                    flash("Somehow, a blank issue type elaboration bypassed client-side validation :( Please leave page source and JS alone.");
                    return redirect(url_for('learn'))
                issue_str = elaboration
            elif issue not in ISSUE_MAP:
                flash("Somehow, an invalid issue type bypassed client-side validation :( Please leave page source and JS alone.");
                return redirect(url_for('learn'))
            else:
                issue_str = ISSUE_MAP[issue]


            if title == "" or title == None: #Remember, different browsers handle blank strings differently
                flash("Somehow, an empty title bypassed client-side validation :( Please leave page source and JS alone.");
                return redirect(url_for('learn'))
            if body == "" or body == None:
                flash("Somehow, a blank body bypassed client-side validation :( Please leave page source and JS alone.");
                return redirect(url_for('learn'))

            req = Request(title=title,
                issue=issue_str,
                body=body,
                extra_requests=info['requests'],
                availability=info['availability'],
                additional=info['additional_comments'],
                timestamp=now)

            subj.add_request(req)
            g.user.make_request(req)

            db.session.add(req)
            db.session.commit()
            flash("Successfully requested help")
            return redirect(url_for('me'))
        flash("That request wasn't for a sensible subject")
        return redirect(url_for('learn'))
    return render_template('learn.html',
            title="Learn",
            user=g.user)

@app.route('/teach')
@login_required
def teach():
    requests = filter(lambda r: r.subject in g.user.tutoring, Request.query.all())
    return render_template('teach.html',
        title="Teach",
        user=g.user,
        requests=requests)

@app.route('/admin')
@login_required
def admin():
    return render_template('admin.html',
        title="Administrator",
        users=User.query.all(),
        requests=Request.query.all(),
        subjects=Subject.query.all())

@app.route('/manage_users', methods=['GET', 'POST'])
@login_required
def manage_users():
    if request.method == 'POST':
        pass
    else:
        if g.user.role < 2:
            flash("You don't have the proper clearance to see this webpage.")
            return render_template('me.html',
                title="Me")
        return render_template('manage_users.html',
            users = User.query.all(),
            title="Manage Users")


@app.route('/termsconditions')
def terms_and_conditions():
    return render_template('termsconditions.html',
        title="Terms and Conditions")

#Handle Error Pages
@app.errorhandler(404) #404 = Page Not Found
def internal_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500) #500 = Internal server error
def internal_error(error):
    db.session.rollback() #Rollback the database in case a database error triggered the 500
    return render_template('500.html'), 500

# #Load pages
# @app.route('/')
# def main():
# 	return render_template('home.html')

# @app.route('/login', methods=['GET', 'POST'])
# def login():
#     error = None
#     if request.method == 'POST':
#         if request.form['username'] != 'admin' or \
#                 request.form['password'] != 'secret':
#             error = 'Invalid credentials'
#         else:
#             flash('You were successfully logged in')
#             return redirect(url_for('home'))
#     return render_template('login.html', error=error)

# #Note that this URL rule keeps 
# @app.route('/signup', methods=['GET', 'POST'])
# def signup():
# 	if request.method == 'POST':
# 		return render_template('home.html', console=request.form)
# 	return render_template('signup.html')


# @app.route('/learn')
# def learn():
# 	return render_template('learn.html')

# @app.route('/teach')
# def teach():
# 	return render_template('teach.html')

# @app.route('/show_all_requests')
# def show_all_requests():
# 	read = open(pickle_path, 'rb')
# 	current_requests = cp.load(read)
# 	read.close()
# 	return render_template('show_all_requests.html', requests=current_requests)

# @app.route('/feedback')
# def feedback():
# 	return render_template('feedback.html')

# @app.route('/view_messages')
# def view_messages():
# 	read = open(feedback_path, 'rb')
# 	all_messages = cp.load(read)
# 	read.close()
# 	return render_template('view_messages.html', messages=all_messages)

# #Set URL rules for modals (?!)
# @app.route('/modal_overview')
# def modal_overview():
# 	return render_template('modal_overview.html')

# #Respond to form requests
# @app.route('/submitLearner', methods=['POST'])
# def submitLearner():
# 	info = request.form

# 	params={}
# 	#User information
# 	params['first_name'] = info['first_name']
# 	params['last_name'] = info['last_name']
# 	params['grade'] = int(info['grade'])
# 	params['email'] = info['email'] + "@menloschool.org"

# 	#Classes
# 	sci_classes = info.getlist('science')
# 	math_classes = info.getlist('math')
# 	other_classes = info.getlist('cs_as')
# 	all_classes = []
# 	all_classes.extend(sci_classes)
# 	all_classes.extend(math_classes)
# 	all_classes.extend(other_classes)
# 	params['all_classes'] = filter(lambda x: x in classesMap, all_classes) #Will only store values that are in our class list
	
	
# 	#Type of issue
# 	issue = info['issue']
# 	params['issue'] = issue
# 	if issue in issue_map:
# 		params['issue_str'] = issue_map[issue]
# 	elif issue == 'other':
# 		params['issue_str'] = info['elaboration'].lower()
# 	else:
# 		params['issue_str'] = 'Invalid option'

# 	#Mandatory info
# 	params['title'] = info['title']
# 	params['challenge'] = info['challenge']
	
# 	#Optional info
# 	params['requests'] = info['requests']
# 	params['availability'] = info['availability']
# 	params['additional'] = info['additional_comments']

# 	#THIS IS BAD AND SLOW. CHANGE IT LATER. 
# 	req = Request(params)
# 	read = open(pickle_path, 'rb')
# 	current_requests = cp.load(read)
# 	read.close()
# 	current_requests = [req] + current_requests #I do it in this order so the requests display chronologically
# 	write = open(pickle_path, 'wb')
# 	cp.dump(current_requests, write)
# 	write.close()

# 	return render_template('show_all_requests.html', requests=current_requests)

# @app.route('/submitTeacher', methods=['POST'])
# def submitTeacher():
# 	info = request.form

# 	params={}

# 	#User information
# 	params['first_name'] = info['first_name']
# 	params['last_name'] = info['last_name']
# 	params['grade'] = int(info['grade'])
# 	params['email'] = info['email'] + "@menloschool.org"

# 	#Classes
# 	sci_classes = info.getlist('science')
# 	math_classes = info.getlist('math')
# 	other_classes = info.getlist('cs_as')
# 	all_classes = []
# 	all_classes.extend(sci_classes)
# 	all_classes.extend(math_classes)
# 	all_classes.extend(other_classes)
# 	params['all_classes'] = filter(lambda x: x in classesMap, all_classes) #Will only store values that are in our class list

# 	t = Tutor(params)
# 	read = open(pickle_path, 'rb')
# 	current_requests = cp.load(read)
# 	read.close()

# 	filtered_requests = []
# 	for req in current_requests:
# 		if matches(req, all_classes):
# 			filtered_requests.append(req)

# 	return render_template('show_all_requests.html', requests=filtered_requests, tutor=t)

# @app.route('/submitMessage', methods=['POST'])
# def submitMessage():
# 	info = request.form
# 	params = {}

# 	params['title'] = info['title']
# 	params['feedback'] = info['feedback']
# 	params['type'] = info['feedback_type']
	
# 	message = Message(params)

# 	read = open(feedback_path, 'rb')
# 	all_messages = cp.load(read)
# 	read.close()
	
# 	all_messages = [message] + all_messages
	
# 	write = open(feedback_path, 'wb')
# 	cp.dump(all_messages, write)
# 	write.close()

# 	return render_template('home.html', console="Thanks for submitting feedback!")