# Gigaschool AI-Quiz Bot

Telegram-бот для определения AI-профиля пользователя. Проводит тест из 6 вопросов, собирает email, отправляет результат в бот и на почту с подборкой AI-инструментов.

## Что делает бот

1. Пользователь нажимает `/start` → видит приветствие и кнопку **«Начать тест»**
2. Проходит 6 ситуационных вопросов (выбор A/B/C/D через инлайн-кнопки)
3. После теста бот просит ввести email
4. Результат отправляется:
   - **в чат бота** — архетип + баллы
   - **на email** — HTML-письмо с разбором профиля и 10 AI-инструментами
5. Данные сохраняются в SQLite (telegram_id, username, email, баллы, архетип)

### Система оценки

| Баллы | Профиль |
|-------|---------|
| 6–10 | 🔍 Наблюдатель |
| 11–15 | 🧪 Экспериментатор |
| 16–20 | ⚡ Практик |
| 21–24 | 🧠 AI-Ready |

### Команды

| Команда | Описание |
|---------|----------|
| `/start` | Начать / перезапустить тест |
| `/export` | Выгрузить CSV с данными пользователей (только для админа) |

---

## Настройка

### 1. Получить токен бота

1. Открыть Telegram → найти **@BotFather**
2. Написать `/newbot`, следовать инструкциям
3. Скопировать токен

### 2. Настроить почту (Яндекс)

1. Создать почтовый ящик на домене (например `quiz@gigaschool.ru`)
2. Зайти в [Яндекс ID](https://id.yandex.ru/) этого аккаунта
3. **Безопасность → Пароли приложений → Создать пароль** (тип: «Почта»)
4. Скопировать пароль приложения

### 3. Узнать свой Telegram ID (для /export)

Написать боту [@userinfobot](https://t.me/userinfobot) — он покажет ваш ID.

### 4. Создать файл `.env`

```env
BOT_TOKEN=7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SMTP_EMAIL=quiz@gigaschool.ru
SMTP_PASSWORD=пароль_приложения_яндекс
ADMIN_IDS=123456789,987654321
```

### 5. Установить зависимости

```bash
pip install -r requirements.txt
```

### 6. Запустить

```bash
python bot.py
```

---

## Деплой на Yandex Cloud (Ubuntu)

### Первоначальная настройка сервера

```bash
# Обновляем систему
sudo apt update && sudo apt upgrade -y

# Ставим Python и git
sudo apt install -y python3 python3-venv python3-pip git

# Клонируем репозиторий
git clone https://github.com/KillingNature/thQuiz.git
cd thQuiz

# Создаём виртуальное окружение
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Создаём .env
nano .env
# ← вставляем BOT_TOKEN, SMTP_EMAIL, SMTP_PASSWORD, ADMIN_IDS
```

### Настройка systemd (автозапуск)

```bash
sudo nano /etc/systemd/system/quizbot.service
```

Содержимое файла:

```ini
[Unit]
Description=Gigaschool AI-Quiz Telegram Bot
After=network.target

[Service]
User=ВАШ_ЮЗЕР
WorkingDirectory=/home/ВАШ_ЮЗЕР/thQuiz
ExecStart=/home/ВАШ_ЮЗЕР/thQuiz/venv/bin/python bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
# Включаем и запускаем
sudo systemctl daemon-reload
sudo systemctl enable quizbot
sudo systemctl start quizbot
```

### Полезные команды

| Действие | Команда |
|----------|---------|
| Статус бота | `sudo systemctl status quizbot` |
| Логи (live) | `journalctl -u quizbot -f` |
| Перезапуск | `sudo systemctl restart quizbot` |
| Остановка | `sudo systemctl stop quizbot` |

### Обновление бота (после правок)

**На своём компьютере:**

```bash
git add .
git commit -m "описание изменений"
git push
```

**На сервере:**

```bash
cd ~/thQuiz && git pull && sudo systemctl restart quizbot
```

Для удобства можно добавить алиас в `~/.bashrc`:

```bash
alias deploy='cd ~/thQuiz && git pull && sudo systemctl restart quizbot'
```

Тогда обновление = зайти на сервер и написать `deploy`.

---

## Бэкап базы данных

База хранится в файле `bot_data.db` рядом с ботом.

**Скачать на свой компьютер:**

```bash
scp user@сервер:~/thQuiz/bot_data.db ./backup/
```

**Или выгрузить CSV прямо из бота:**

Написать `/export` в бот (только для ADMIN_IDS).

---

## Структура проекта

```
thQuiz/
├── bot.py              # Основной файл бота
├── requirements.txt    # Python-зависимости
├── .env                # Токены и пароли (НЕ в git)
├── .gitignore          # Исключения для git
├── bot_data.db         # SQLite база (создаётся автоматически, НЕ в git)
└── README.md           # Этот файл
```
