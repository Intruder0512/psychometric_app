from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
import smtplib

app = Flask(__name__)

# ===== Database setup =====
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db = SQLAlchemy(app)

# ===== SMTP (Gmail example) =====
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'yourcompanyhr@gmail.com'
app.config['MAIL_PASSWORD'] = 'your_app_password_here'
mail = Mail(app)

# ===== DB model =====
class Candidate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120))
    score = db.Column(db.Integer)
    red_flags = db.Column(db.Integer)
    tier = db.Column(db.String(50))

db.create_all()

# ======= Scoring Key =======
scoring = {
    1: {'B':4}, 2:{'C':4,'B':1}, 3:{'C':4,'B':1,'D':1}, 4:{'C':4,'B':1},
    5:{'B':4}, 6:{'C':4}, 7:{'C':4}, 8:{'C':4,'D':1}, 9:{'A':4},
    10:{'C':4}, 11:{'B':4}, 12:{'C':4}, 13:{'A':4,'B':1}, 14:{'B':4,'C':2},
    15:{'A':4,'B':2}, 16:{'A':4,'C':1}, 17:{'B':4}, 18:{'B':4}, 19:{'B':4},
    20:{'B':4}, 21:{'B':4}, 22:{'A':4}, 23:{'A':4,'B':1,'D':1}, 24:{'B':4},
    25:{'B':4}, 26:{'B':4}, 27:{'B':4}, 28:{'B':4,'A':1}, 29:{'A':4,'B':3},
    30:{'A':4,'B':1}
}

red_flag_map = {
    1:['A','C','D'], 2:['A','D'], 3:['A'], 4:['A','D'], 5:['A','C','D'],
    6:['A','B','D'], 7:['A','B','D'], 8:['A','B'], 9:['B','C','D'],
    10:['A','B','D'], 11:['A','C','D'], 12:['A','B','D'], 13:['C','D'],
    14:['A','D'], 15:['C','D'], 16:['B','D'], 17:['A','C','D'], 18:['A','C','D'],
    19:['A','C','D'], 20:['A','C','D'], 21:['A','C','D'], 22:['B','C','D'],
    23:['C'], 24:['A','C','D'], 25:['A','C','D'], 26:['A','C','D'],
    27:['A','C','D'], 28:['C','D'], 29:['C','D'], 30:['C','D']
}

# ======= Helper: evaluate answers =======
def evaluate(answers):
    score, red_flags = 0, 0
    for q_num, ans in answers.items():
        qn = int(q_num.replace('q',''))
        score += scoring.get(qn, {}).get(ans, 0)
        if ans in red_flag_map.get(qn, []):
            red_flags += 1
    return score, red_flags

# ======= Routes =======
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit():
    name = request.form['name']
    email = request.form['email']
    answers = {k:v for k,v in request.form.items() if k.startswith('q')}
    score, red_flags = evaluate(answers)

    # Tier determination
    if red_flags >= 2 or score < 98 or any(
        answers.get(f'q{i}') in red_flag_map[i] for i in [1,10,15,30]
    ):
        tier = 'Rejected'
    elif score >= 105:
        tier = 'Tier 1'
    elif 98 <= score <= 104:
        tier = 'Tier 2'
    else:
        tier = 'Rejected'

    # Save result
    db.session.add(Candidate(name=name, email=email, score=score, red_flags=red_flags, tier=tier))
    db.session.commit()

    # Send emails
    send_email_to_hr(name, email, score, tier)
    send_email_to_candidate(name, email, score, tier)

    return redirect(url_for('thankyou'))

@app.route('/thankyou')
def thankyou():
    return render_template('thankyou.html')

# ======= Email helpers =======
def send_email_to_hr(name, email, score, tier):
    msg = Message(
        subject=f"New Psychometric Test Result: {name}",
        sender=app.config['MAIL_USERNAME'],
        recipients=['hrteam@yourcompany.com']
    )
    msg.body = f"""
Candidate: {name}
Email: {email}
Score: {score}/120
Tier: {tier}
"""
    mail.send(msg)

def send_email_to_candidate(name, email, score, tier):
    if tier == 'Rejected':
        subject = "Thank you for applying to Our Company"
        body = f"Dear {name},\n\nThank you for completing our assessment. Unfortunately, we will not proceed further.\n\nBest wishes,\nHR Team"
    elif tier == 'Tier 1':
        subject = "Congratulations! You're in the top 2%!"
        body = f"Dear {name},\n\nExcellent news! You scored {score}/120 placing you in the top 2%.\nWe'll reach out soon for next steps.\n\nHR Team"
    else:
        subject = "Next Steps for Your Application"
        body = f"Dear {name},\n\nYour score {score}/120 shows strong potential! We’ll schedule an interview shortly.\n\nHR Team"

    msg = Message(subject=subject, sender=app.config['MAIL_USERNAME'], recipients=[email])
    msg.body = body
    mail.send(msg)

if __name__ == '__main__':
    app.run(debug=True)
