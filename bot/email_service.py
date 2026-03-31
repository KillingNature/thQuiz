import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, formataddr, make_msgid

from .config import SMTP_EMAIL, SMTP_PASSWORD, logger


def build_email_html(archetype_emoji: str, archetype_title: str, archetype_text: str, score: int) -> str:
    archetype_html = archetype_text.replace("\n", "<br>")
    tools_html = """
    <tr><td style="padding:20px 30px;">
      <h2 style="color:#1a1a2e;font-size:22px;margin:0 0 20px 0;">10 AI-инструментов</h2>
      <p style="color:#555;font-size:15px;margin:0 0 24px 0;">Которые чаще всего используют продакты, аналитики и маркетологи</p>
      <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;"><a href="https://chat.openai.com" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">1. ChatGPT (OpenAI)</a><p style="color:#555;font-size:14px;margin:6px 0 0 0;">Универсальный рабочий инструмент: анализ фидбека, генерация гипотез, подготовка PRD и брифов, работа с данными.</p></td></tr>
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;"><a href="https://claude.ai" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">2. Claude</a><p style="color:#555;font-size:14px;margin:6px 0 0 0;">Аналитика и работа с большими документами: исследования, структурирование информации, подготовка аргументов.</p></td></tr>
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;"><a href="https://perplexity.ai" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">3. Perplexity</a><p style="color:#555;font-size:14px;margin:6px 0 0 0;">AI-поисковик: быстрый ресёрч рынка, поиск статистики, анализ трендов.</p></td></tr>
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;"><a href="https://gemini.google.com" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">4. Gemini</a><p style="color:#555;font-size:14px;margin:6px 0 0 0;">AI-ассистент Google: анализ данных в Docs и Sheets, аналитические заметки, идеи для маркетинга.</p></td></tr>
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;"><a href="https://github.com/features/copilot" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">5. GitHub Copilot</a><p style="color:#555;font-size:14px;margin:6px 0 0 0;">AI для кода: проверка технических гипотез, скрипты, понимание кода продукта.</p></td></tr>
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;"><a href="https://replit.com" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">6. Replit AI</a><p style="color:#555;font-size:14px;margin:6px 0 0 0;">Быстрое создание прототипов: MVP, тестирование AI-идей, внутренние инструменты.</p></td></tr>
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;"><a href="https://chat.deepseek.com" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">7. DeepSeek</a><p style="color:#555;font-size:14px;margin:6px 0 0 0;">Аналитика и логические задачи: анализ данных, продуктовые гипотезы, структурирование решений.</p></td></tr>
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;"><a href="https://chat.qwen.ai" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">8. Qwen</a><p style="color:#555;font-size:14px;margin:6px 0 0 0;">Обработка больших массивов текста, анализ пользовательских запросов, AI-ассистенты.</p></td></tr>
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;"><a href="https://manus.ai" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">9. Manus</a><p style="color:#555;font-size:14px;margin:6px 0 0 0;">AI-агент для сложных многоступенчатых задач: ресёрч, аналитика, прототипирование без кода.</p><p style="color:#999;font-size:12px;margin:4px 0 0 0;font-style:italic;">* Компания Meta признана экстремистской и запрещена в РФ</p></td></tr>
        <tr><td style="padding:14px 0;"><a href="https://github.com/open-claude" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">10. OpenClaw</a><p style="color:#555;font-size:14px;margin:6px 0 0 0;">Open-source: внутренние AI-ассистенты, корпоративные документы, прототипирование без внешних API.</p></td></tr>
      </table>
    </td></tr>"""
    return f"""\
<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f4f4f7;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f7;padding:30px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
  <tr><td style="background:#1a1a2e;padding:30px;text-align:center;">
    <h1 style="color:#fff;font-size:24px;margin:0;font-weight:700;">Gigaschool</h1>
    <p style="color:#a0a0c0;font-size:14px;margin:8px 0 0 0;">Твой AI-профиль</p>
  </td></tr>
  <tr><td style="padding:30px 30px 10px 30px;">
    <div style="background:#f0f0ff;border-radius:10px;padding:24px;text-align:center;">
      <p style="font-size:40px;margin:0 0 8px 0;">{archetype_emoji}</p>
      <h2 style="color:#1a1a2e;font-size:22px;margin:0 0 6px 0;">{archetype_title}</h2>
      <p style="color:#4F46E5;font-size:15px;margin:0;font-weight:600;">{score} из 24 баллов</p>
    </div>
  </td></tr>
  <tr><td style="padding:10px 30px 30px 30px;"><p style="color:#333;font-size:15px;line-height:1.7;">{archetype_html}</p></td></tr>
  <tr><td style="padding:0 30px;"><hr style="border:none;border-top:2px solid #f0f0f0;margin:0;"></td></tr>
  {tools_html}
  <tr><td style="background:#1a1a2e;padding:24px 30px;text-align:center;">
    <p style="color:#a0a0c0;font-size:13px;margin:0;">Gigaschool &copy; {datetime.now().year}</p>
  </td></tr>
</table></td></tr></table></body></html>"""


def send_email(to_email: str, score: int, result: dict) -> bool:
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        logger.warning("SMTP not configured, skipping email")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Твой AI-профиль: {result['title']} — Gigaschool"
        msg["From"] = formataddr(("Gigaschool", SMTP_EMAIL))
        msg["To"] = to_email
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=SMTP_EMAIL.split("@")[-1])
        msg["Return-Path"] = SMTP_EMAIL
        msg["Reply-To"] = SMTP_EMAIL
        msg["X-Mailer"] = "Gigaschool Quiz Bot"
        msg["MIME-Version"] = "1.0"
        msg.attach(MIMEText(build_email_html(result["emoji"], result["title"], result["text"], score), "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.yandex.ru", 465, timeout=15) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
        logger.info(f"Email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False
