from flask import Flask, render_template, request, redirect, url_for
from flask_mail import Mail, Message
from datetime import datetime
import pandas as pd
import os
from io import BytesIO
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Mail configuration from .env
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')

mail = Mail(app)

# HR & Company details
HR_EMAIL = os.getenv('HR_EMAIL')
COMPANY_NAME = os.getenv('COMPANY_NAME', 'Your Company')

# ---------- QUESTION SCORING ----------
SCORES = {
    1: {'B': 4},
    2: {'C': 4, 'B': 1},
    3: {'C': 4, 'B': 1, 'D': 1},
    4: {'C': 4, 'B': 1},
    5: {'B': 4},
    6: {'C': 4},
    7: {'C': 4},
    8: {'C': 4, 'D': 1},
    9: {'A': 4},
    10: {'C': 4},
    11: {'B': 4},
    12: {'C': 4},
    13: {'A': 4, 'B': 1},
    14: {'B': 4, 'C': 2},
    15: {'A': 4, 'B': 2},
    16: {'A': 4, 'C': 1},
    17: {'B': 4},
    18: {'B': 4},
    19: {'B': 4},
    20: {'B': 4},
    21: {'B': 4},
    22: {'A': 4},
    23: {'A': 4, 'B': 1, 'D': 1},
    24: {'B': 4},
    25: {'B': 4},
    26: {'B': 4},
    27: {'B': 4},
    28: {'B': 4, 'A': 1},
    29: {'A': 4, 'B': 3},
    30: {'A': 4, 'B': 1}
}

RED_FLAGS = {
    1: ['A', 'C', 'D'],
    2: ['A', 'D'],
    4: ['A', 'D'],
    5: ['A', 'C', 'D'],
    10: ['A', 'B', 'D'],
    13: ['C', 'D'],
    15: ['C', 'D'],
    18: ['A', 'C', 'D'],
    19: ['A', 'C', 'D'],
    20: ['A', 'C', 'D'],
    22: ['B', 'C', 'D'],
    23: ['C'],
    24: ['A', 'C', 'D'],
    25: ['A', 'C', 'D'],
    26: ['A', 'C', 'D'],
    27: ['A', 'C', 'D'],
    28: ['C', 'D'],
    29: ['C', 'D'],
    30: ['C', 'D']
}

# ---------- ROUTES ----------
@app.route('/')
def index():
    # Pass datetime for footer year
    return render_template('index.html', datetime=datetime)

@app.route('/submit', methods=['POST'])
def submit():
    candidate_name = request.form.get('name')
    candidate_email = request.form.get('email')
    position = request.form.get('position')

    answers = {}
    total_score = 0
    red_flag_count = 0

    # Evaluate all 30 questions
    for i in range(1, 31):
        ans = request.form.get(f'q{i}')
        answers[f'Q{i}'] = ans if ans else "N/A"

        if ans in RED_FLAGS.get(i, []):
            red_flag_count += 1
        total_score += SCORES.get(i, {}).get(ans, 0)

    # Tier classification
    if red_flag_count >= 2 or total_score < 98 or SCORES.get(1, {}).get(answers['Q1'], 0) == 0 or SCORES.get(10, {}).get(answers['Q10'], 0) == 0 or SCORES.get(15, {}).get(answers['Q15'], 0) == 0 or SCORES.get(30, {}).get(answers['Q30'], 0) == 0:
        tier = "Rejected"
    elif total_score >= 105:
        tier = "Tier 1 (Elite)"
    elif 98 <= total_score < 105:
        tier = "Tier 2 (Strong)"
    else:
        tier = "Rejected"

    # Create Excel report for HR
    data = {
        'Candidate Name': [candidate_name],
        'Email': [candidate_email],
        'Position': [position],
        'Total Score': [total_score],
        'Red Flags': [red_flag_count],
        'Tier': [tier]
    }
    df = pd.DataFrame(data)
    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Summary')
        ans_df = pd.DataFrame(list(answers.items()), columns=['Question', 'Answer'])
        ans_df.to_excel(writer, index=False, sheet_name='Answers')
    excel_buffer.seek(0)

    # Send email to HR
    msg_hr = Message(
        subject=f"[{COMPANY_NAME}] Psychometric Assessment - {candidate_name}",
        sender=app.config['MAIL_USERNAME'],
        recipients=[HR_EMAIL]
    )
    msg_hr.body = f"""Candidate Name: {candidate_name}
Email: {candidate_email}
Position: {position}
Total Score: {total_score}
Tier: {tier}
Red Flags: {red_flag_count}
"""
    msg_hr.attach(f"{candidate_name}_Assessment.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", excel_buffer.read())
    mail.send(msg_hr)

    # Send acknowledgment email to candidate
    msg_candidate = Message(
        subject=f"Thank you for completing the assessment – {COMPANY_NAME}",
        sender=app.config['MAIL_USERNAME'],
        recipients=[candidate_email]
    )
    msg_candidate.body = f"""Dear {candidate_name},

Thank you for completing the {COMPANY_NAME} Psychometric Assessment.

Our HR team will review your responses and contact you soon regarding next steps.

Best regards,
HR Team
{COMPANY_NAME}
"""
    mail.send(msg_candidate)

    return render_template('thankyou.html', name=candidate_name, datetime=datetime)

# ---------- MAIN ----------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
