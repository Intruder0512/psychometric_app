from flask import Flask, render_template, request
from flask_mail import Mail, Message
from datetime import datetime
import pandas as pd
import os
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_url_path='/static')

# Mail settings
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')

mail = Mail(app)

HR_EMAIL = os.getenv('HR_EMAIL', 'hr@kampushr.com')
COMPANY_NAME = "Kampus HR"

# Scoring rules (same as before)
SCORES = {
    1: {'B': 4}, 2: {'C': 4, 'B': 1}, 3: {'C': 4, 'B': 1, 'D': 1},
    4: {'C': 4, 'B': 1}, 5: {'B': 4}, 6: {'C': 4}, 7: {'C': 4},
    8: {'C': 4, 'D': 1}, 9: {'A': 4}, 10: {'C': 4}, 11: {'B': 4},
    12: {'C': 4}, 13: {'A': 4, 'B': 1}, 14: {'B': 4, 'C': 2}, 15: {'A': 4, 'B': 2},
    16: {'A': 4, 'C': 1}, 17: {'B': 4}, 18: {'B': 4}, 19: {'B': 4}, 20: {'B': 4},
    21: {'B': 4}, 22: {'A': 4}, 23: {'A': 4, 'B': 1, 'D': 1}, 24: {'B': 4},
    25: {'B': 4}, 26: {'B': 4}, 27: {'B': 4}, 28: {'B': 4, 'A': 1},
    29: {'A': 4, 'B': 3}, 30: {'A': 4, 'B': 1}
}

RED_FLAGS = {
    1: ['A', 'C', 'D'], 2: ['A', 'D'], 4: ['A', 'D'], 5: ['A', 'C', 'D'],
    10: ['A', 'B', 'D'], 13: ['C', 'D'], 15: ['C', 'D'], 18: ['A', 'C', 'D'],
    19: ['A', 'C', 'D'], 20: ['A', 'C', 'D'], 22: ['B', 'C', 'D'],
    23: ['C'], 24: ['A', 'C', 'D'], 25: ['A', 'C', 'D'], 26: ['A', 'C', 'D'],
    27: ['A', 'C', 'D'], 28: ['C', 'D'], 29: ['C', 'D'], 30: ['C', 'D']
}

@app.route('/')
def index():
    return render_template('index.html', datetime=datetime, company=COMPANY_NAME)

@app.route('/submit', methods=['POST'])
def submit():
    name = request.form.get('name')
    email = request.form.get('email')
    position = request.form.get('position')
    answers, total_score, red_flags = {}, 0, 0

    for i in range(1, 31):
        ans = request.form.get(f'q{i}')
        answers[f'Q{i}'] = ans or "N/A"
        if ans in RED_FLAGS.get(i, []):
            red_flags += 1
        total_score += SCORES.get(i, {}).get(ans, 0)

    if red_flags >= 2 or total_score < 98:
        tier = "Rejected"
    elif total_score >= 105:
        tier = "Tier 1 (Elite)"
    else:
        tier = "Tier 2 (Strong)"

    df_summary = pd.DataFrame([{
        'Candidate Name': name, 'Email': email, 'Position': position,
        'Total Score': total_score, 'Red Flags': red_flags, 'Tier': tier
    }])
    df_answers = pd.DataFrame(list(answers.items()), columns=['Question', 'Answer'])

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_summary.to_excel(writer, index=False, sheet_name='Summary')
        df_answers.to_excel(writer, index=False, sheet_name='Answers')
    buffer.seek(0)

    # HR email
    msg_hr = Message(f"[{COMPANY_NAME}] Assessment – {name}",
                     sender=app.config['MAIL_USERNAME'],
                     recipients=[HR_EMAIL])
    msg_hr.body = f"""
Candidate: {name}
Email: {email}
Position: {position}
Total Score: {total_score}
Tier: {tier}
Red Flags: {red_flags}
"""
    msg_hr.attach(f"{name}_assessment.xlsx",
                  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                  buffer.read())
    mail.send(msg_hr)

    # Candidate acknowledgment
    msg_candidate = Message(f"Thank you for completing the assessment – {COMPANY_NAME}",
                            sender=app.config['MAIL_USERNAME'],
                            recipients=[email])
    msg_candidate.body = f"""
Dear {name},

Thank you for completing the {COMPANY_NAME} Psychometric Test.
Our HR team will review your results and contact you shortly.

Best regards,
HR Team
{COMPANY_NAME}
"""
    mail.send(msg_candidate)
    return render_template('thankyou.html', name=name, company=COMPANY_NAME, datetime=datetime)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
