# Telegram Music Downloader Bot

![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)
![pyrogram](https://img.shields.io/badge/pyrogram-MTProto-green?logo=telegram&logoColor=white)
![psy music](https://img.shields.io/badge/👾_psy-trance-blueviolet)

Телеграм-бот, который автоматически скачивает музыкальные релизы, пересланные из определённых каналов, и раскладывает их по папкам с обложками.

Бот парсит метаданные из постов Telegram, определяет информацию о релизе (артист, альбом, год, лейбл), скачивает аудиофайлы, загружает обложку и сохраняет всё в правильно названную папку.

---

## Возможности

- Автоматически парсит метаданные релиза из постов Telegram
- Поддерживает несколько исходных каналов с разными форматами текста
- Скачивает аудиофайлы с прогресс-баром
- Автоматически создаёт папки релизов
- Извлекает обложку из tg поста (Bandcamp как запасной вариант)
- Очищает и нормализует названия артиста, альбома и лейбла

---

## Поддерживаемые источники

Поддерживаемые tg-каналы (можно настроить и другие):

- `psymusicru`
- `radio_boga`

У каждого источника свои правила парсинга на основе регулярных выражений, заданных в `config.yaml`.

Пример поста Telegram:

```
Savupiippu-Ukko - Pariah Boogie EP [2026]
Label: #Hippie_Killer_Productions
Style: #Suomisaundi
Released: March 6, 2026
HQ: https://hippiekillerproductions.bandcamp.com/album/pariah-boogie-ep
```

Сгенерированная папка:

```
Savupiippu-Ukko - Pariah Boogie (Hippie Killer EP 2026)
```

---

## Как это работает

1. Пост из поддерживаемого канала пересылается боту.
2. Бот определяет исходный канал.
3. Из текста сообщения парсятся метаданные:
   - артист
   - альбом
   - год
   - лейбл
   - флаг EP
4. Создаётся папка релиза.
5. Скачиваются треки.
6. Сохраняется обложка (из Telegram или с Bandcamp).

Пример структуры папок:

```
DOWNLOAD_DIR/
└── Artist - Album (Label 2026)/
    ├── Cover.png
    ├── 01 Track.mp3
    ├── 02 Track.mp3
    └── 03 Track.mp3
```

---

## Установка

### 1. Клонировать репозиторий

```bash
git clone https://github.com/PSImera/Download_TG_Music.git
cd music-downloader-bot
```

---

### 2. Создать файл конфигурации окружения

Скопировать `.env.example` в `.env`:

```bash
# Linux / macOS
cp .env.example .env

# Windows (PowerShell)
Copy-Item .env.example .env
```

Открыть `.env` и заполнить свои данные:

```
API_ID=123456
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
```

**Где взять значения:**

- `API_ID` и `API_HASH` — на сайте [my.telegram.org](https://my.telegram.org):
  1. Войти через номер телефона.
  2. Перейти в **API development tools**.
  3. Создать приложение — получите `api_id` и `api_hash`.

- `BOT_TOKEN` — через [@BotFather](https://t.me/BotFather) в Telegram:
  1. Написать `/newbot`.
  2. Задать имя и юзернейм бота.
  3. Скопировать выданный токен.

> **Зачем нужны API_ID и API_HASH, если это бот?**
> Бот работает через библиотеку pyrogram, которая использует MTProto — низкоуровневый протокол Telegram.
> Именно он обеспечивает быстрое скачивание файлов напрямую с серверов Telegram, в отличие от медленного HTTP Bot API.
> Для MTProto-подключения всегда нужны `API_ID` и `API_HASH`, даже при работе от имени бота.

> **Безопасность:** никому не передавайте `API_ID`, `API_HASH` и `BOT_TOKEN`.
> `API_ID` и `API_HASH` привязаны к вашему аккаунту Telegram.
> `BOT_TOKEN` даёт полный контроль над ботом.

---

### 3. Настроить config.yaml

Файл `config.yaml` содержит настройки папки загрузки, паттерны источников и регулярные выражения. Отредактировать его под свои нужды перед запуском.

---

### 4. Создать и активировать виртуальное окружение

```bash
python -m venv .venv
```

**Linux / macOS:**
```bash
source .venv/bin/activate
```

**Windows (cmd):**
```bat
.venv\Scripts\activate
```

**Windows (PowerShell):**
```powershell
.venv\Scripts\Activate.ps1
```

---

### 5. Установить зависимости

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## Запуск

```bash
python download_tg_music.py
```

После запуска нужно просто пересылать боту посты из поддерживаемых Telegram-каналов. Бот сам распарсит метаданные и скачает релиз.

---

## Зависимости

Основные используемые библиотеки:

- `pyrogram`
- `aiohttp`
- `python-dotenv`
- `pyyaml`
- `tqdm`

---

## Примечания

- Аудиофайлы должны идти после поста с метаданными.
- Первое изображение в посте используется как обложка, если оно есть.
- Если обложка в Telegram отсутствует, бот пытается скачать обложку со страницы альбома на Bandcamp.

---

## Лицензия

MIT License
