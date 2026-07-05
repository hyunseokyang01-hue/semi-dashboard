"""
send_email_semi.py — 반도체 대시보드 HTML을 Gmail로 첨부 발송 (Step C)
설계: krx-automation/send_email.py와 동일 패턴
자격증명: 이 폴더 .env → 없으면 krx-automation/.env 순서로 로드
"""
import os
import smtplib
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

BASE = os.path.dirname(os.path.abspath(__file__))

try:
    from dotenv import load_dotenv
    local_env = os.path.join(BASE, ".env")
    krx_env = r"C:\Users\user\dev\krx-automation\.env"
    load_dotenv(dotenv_path=local_env if os.path.exists(local_env) else krx_env)
except ImportError:
    pass

GMAIL_USER = os.getenv("GMAIL_ADDRESS") or os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

HTML_PATH = os.path.join(BASE, "index.html")


def send_semi_email(html_path=HTML_PATH, to=None):
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        raise RuntimeError("GMAIL_ADDRESS(또는 GMAIL_USER) / GMAIL_APP_PASSWORD 환경변수가 없습니다.")

    if not os.path.exists(html_path):
        raise FileNotFoundError(f"HTML 파일 없음: {html_path}")

    to = to or GMAIL_USER
    today = datetime.datetime.now().strftime("%Y%m%d")
    subject = f"반도체 투자 대시보드 {today}"

    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(f"{subject} 첨부파일을 확인하세요.", "plain", "utf-8"))

    with open(html_path, "rb") as f:
        part = MIMEBase("text", "html")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition",
        "attachment",
        filename=("utf-8", "", f"반도체_대시보드_{today}.html"),
    )
    msg.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, to, msg.as_string())

    print(f"[Step C] 이메일 발송 완료 → {to} / 제목: {subject}")


if __name__ == "__main__":
    send_semi_email()
