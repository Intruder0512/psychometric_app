import os
from io import BytesIO
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message

import pandas as pd  # for Excel export

# -------- Flask app --------
app = Flask(__name__)

# -------- Database (ephemeral on Render, OK for now) --------
# If you later add a disk, change this path to the mounted directory.
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL',
    'sqlite:///database.db'  # render ephemeral container FS
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# -------- SMTP via environment variables --------
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', '587'))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')  # required
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')  # required
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', app.config['MAIL_USERNAME'])
HR_EMAILS = [e.strip() for e in os.getenv('HR_EMAILS', 'hrteam@example.com').split(',') if e.strip()]

mail = Mail(app)

# -------- DB Model --------
class Candidate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ts = db.Column(db.DateTime, default=datetime.utcnow)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(200), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    red_flags = db.Column(db.Integer, nullable=False)
    tier = db.Column(db.String(50), nullable=False)
    # Store raw answers as a simple JSON-ish string for quick review (optional)
    answers_blob = db.Column(db.Text, nullable=False)

# Create tables with a proper app context (fixes your Render error)
with app.app_context():
    db.create_all()

# -------- Scoring maps --------
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

# -------- Helpers --------
def evaluate(answers_dict):
    score, red_flags = 0, 0
    for i in range(1, 30 + 1):
        ans = answers_dict.get(f'q{i}')
        score += scoring.get(i, {}).get(ans, 0)
        if ans in red_flag_map.get(i, []):
            red_flags += 1
    # Auto-reject critical integrity questions: Q1, Q10, Q15, Q30 if red flag chosen
    critical_fail = any(answers_dict.get(f'q{i}') in red_flag_map[i] for i in [1,10,15,30])
    if red_flags >= 2 or score < 98 or critical_fail:
        tier = 'Rejected'
    elif score >= 105:
        tier = 'Tier 1'
    elif 98 <= score <= 104:
        tier = 'Tier 2'
    else:
        tier = 'Rejected'
    return score, red_flags, tier

def make_excel_bytes(name, email, answers_dict, score, red_flags, tier):
    """
    Build a one-row Excel workbook in memory with all answers and metadata.
    """
    row = {
        'Timestamp (UTC)': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        'Candidate Name': name,
        'Candidate Email': email,
        'Score': score,
        'Red Flags': red_flags,
        'Tier': tier
    }
    for i in range(1, 31):
        row[f'Q{i}'] = answers_dict.get(f'q{i}', '')

    df = pd.DataFrame([row])
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Assessment', index=False)
    buf.seek(0)
    return buf

def send_email_to_hr(name, email, score, red_flags, tier, excel_bytes):
    subject = f"[Assessment] {name} | {tier} | {score}/120"
    body = (
        f"Candidate: {name}\n"
        f"Email: {email}\n"
        f"Score: {score}/120\n"
        f"Red Flags: {red_flags}\n"
        f"Tier: {tier}\n\n"
        "Excel file attached with full responses."
    )
    msg = Message(subject=subject, recipients=HR_EMAILS, body=body)
    # attach the Excel workbook
    msg.attach(
        filename=f"{name.replace(' ', '_')}_assessment.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        data=excel_bytes.read()
    )
    mail.send(msg)

def send_email_to_candidate(name, email, tier):
    # Candidate should NOT see score
    if tier == 'Rejected':
        subject = "Thank you for applying"
        body = (
            f"Dear {name},\n\n"
            "Thank you for completing our assessment and applying. "
            "At this time, we will not be moving forward.\n\n"
            "Best regards,\nHR Team"
        )
    elif tier == 'Tier 1':
        subject = "Next steps for your application"
        body = (
            f"Dear {name},\n\n"
            "Thank you for completing our assessment. We'd like to proceed to next steps.\n"
            "Our team will reach out to schedule a quick discussion.\n\n"
            "Best regards,\nHR Team"
        )
    else:  # Tier 2
        subject = "Next steps for your application"
        body = (
            f"Dear {name},\n\n"
            "Thank you for completing our assessment. "
            "We'd like to move forward with a 30-minute conversation.\n\n"
            "Best regards,\nHR Team"
        )
    msg = Message(subject=subject, recipients=[email], body=body)
    mail.send(msg)

# -------- Routes --------
@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()

    # Pull all q1..q30 answers
    answers = {f'q{i}': request.form.get(f'q{i}') for i in range(1, 31)}

    # Evaluate
    score, red_flags, tier = evaluate(answers)

    # Save to DB (ephemeral OK)
    c = Candidate(
        name=name,
        email=email,
        score=score,
        red_flags=red_flags,
        tier=tier,
        answers_blob=str(answers)
    )
    db.session.add(c)
    db.session.commit()

    # Build Excel in-memory and email HR + candidate
    xls_buf = make_excel_bytes(name, email, answers, score, red_flags, tier)
    send_email_to_hr(name, email, score, red_flags, tier, xls_buf)
    send_email_to_candidate(name, email, tier)

    # Show thank-you page only
    return redirect(url_for('thankyou'))

@app.route('/thankyou', methods=['GET'])
def thankyou():
    return render_template('thankyou.html')

if __name__ == '__main__':
    # For local testing only. On Render, gunicorn runs it.
    app.run(host='0.0.0.0', port=5000, debug=True)
