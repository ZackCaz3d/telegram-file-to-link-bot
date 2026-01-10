![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)
![Platform](https://img.shields.io/badge/platform-Telegram-blue)
![Python](https://img.shields.io/badge/python-3.13-blue)
![Framework](https://img.shields.io/badge/FastAPI-async-green)
![Deploy](https://img.shields.io/badge/deploy-Railway-purple)

# 📎 Telegram File Link Bot

A self-hosted **Telegram bot** that generates **secure, rate-limited download links** for uploaded files, with **time-based expiration (TTL)**, an **optional admin dashboard**, and **automatic cleanup**.

The project can run **locally**, on a **VPS**, or on any cloud platform.  
For the easiest setup, **Railway is recommended**.

---

## 🚀 Deployment (Railway – Recommended)

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/telegram-file-to-link-bot?referralCode=nIQTyp&utm_medium=integration&utm_source=template&utm_campaign=generic)

This repository is designed to be deployed **directly as a Railway template**.

### Why Railway?
- **Free public domain** (`*.railway.app`) included
- **Automatic HTTPS** (no SSL setup needed)
- **One-click PostgreSQL & Redis**
- **Easy environment variable management**
- **No server maintenance** or manual provisioning

### Steps
1. Click **Deploy on Railway**
2. Railway will create a new project from this template
3. Add PostgreSQL and Redis plugins
4. Set the required environment variables
5. Deploy

Your bot and download API will be live within minutes.

> You can still deploy this project locally or on any VPS.  

---

## ✨ Features

### 🤖 Telegram Bot
- Upload files via Telegram and receive a public download link
- Supports documents, videos, audio, photos, animations, voice, and video notes
- Preserves original file quality
- Optional private bot mode (allowed user IDs)
- Built with Pyrogram / Pyrofork

---

### 🔗 File Links
- Unique file IDs
- Direct downloads via FastAPI
- Correct filenames and headers
- Supports HTTP range requests (206 Partial Content)

---

### ⏳ Expiration (TTL Only)
- Optional expiration per file
- Time-based expiration only (no download limits)
- Unlimited downloads are always allowed
- Files expire automatically when TTL is reached

---

### 🔄 Upload Concurrency Control
- Limits how many file uploads are processed at the same time
- Prevents server overload and Telegram flood limits
- Extra uploads are automatically queued
- Fully configurable via environment variables

---

### ⚙️ Mode System (TTL Control)

TTL is controlled **per user** via Telegram commands.

Examples:
- `/mode ttl 30` → 30 minutes
- `/mode ttl 2h` → 2 hours
- `/mode ttl 1d` → 1 day
- `/mode ttl 0 or /mode reset` → Never expire

TTL is stored internally in **seconds**.

---

### 📊 Admin Dashboard (Optional)

Enabled only if `ADMIN_ENABLED=true`.

Features:
- Secure session-based login
- View total files, downloads, and active files
- Search files by name
- Disable files (expire immediately)
- Delete files
- View top downloads, recent uploads, and expiring files
- Light / Dark mode toggle

When enabled, the admin dashboard is available at:

```
https://your-domain.com/admin
```

> If `ADMIN_ENABLED=false`, the admin dashboard routes are not registered and the bot still works normally.

---

## 📸 Screenshots

### Admin Dashboard
![Admin Dashboard](docs/screenshots/admin-dashboard.jpg)

### Telegram Upload
![Telegram Upload](docs/screenshots/telegram-upload.jpg)

---

### 🧹 Automatic Cleanup
- Background task removes expired files
- Cleans database records and Redis cache
- Safe against partial failures

---

### 🚦 Rate Limiting
- Global per-IP rate limiting
- Redis-backed
- Proper `Retry-After` headers

---

## 🧱 Tech Stack
- Python **3.11+** (tested on 3.13)
- FastAPI
- Pyrogram / Pyrofork
- PostgreSQL (asyncpg)
- Redis
- Jinja2
- Vanilla HTML / CSS / JS

---

## 📁 Project Structure

```
.
├── admin/          # Admin routes, auth, and Jinja2 templates
├── api/            # Public download API endpoints
├── app/            # FastAPI core app & background cleanup tasks
├── bot/            # Telegram bot handlers (Pyrogram)
├── cache/          # Redis helper functions
├── db/             # Database connection & asyncpg schema
├── static/         # Admin dashboard CSS & JS
├── uploads/        # Local storage for files (gitignored)
├── config.py       # Environment variable parsing
└── main.py         # Application entry point
```

---

## ⚠️ Database Schema Management

This project automatically creates and maintains its database schema at startup.

Migrations are intentionally omitted to keep the template simple and easy to deploy.  
For larger or multi-tenant deployments, adding a migration system is recommended.

---

## ⚙️ Environment Variables

Create a `.env` file in the project root.
> Tip: Rename `.env.example` to `.env` and fill in your values.

### Telegram Bot
```env
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
```

### Upload Concurrency (Processing Control)
```env
MAX_CONCURRENT_TRANSFERS=3
```

### Database & Cache
```env
DATABASE_URL=postgresql://user:password@localhost:5432/filelink
REDIS_URL=redis://localhost:6379
```

### Public URL
```env
BASE_URL=https://your-public-domain.com
```

### Rate Limiting
```env
GLOBAL_RATE_LIMIT_REQUESTS=60
GLOBAL_RATE_LIMIT_WINDOW=10
```

### Access Control (Optional)
```env
ALLOWED_USER_IDS=123456789
```

### Admin Dashboard (Optional)
```env
ADMIN_ENABLED=true
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=change-me-now
SESSION_SECRET=change-me
```

---

## ▶️ Running Locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --log-level warning
```

Make sure a `.env` file exists before starting.

---

## 📝 Logs

You may see `socket.send() raised exception` during downloads.  
This is normal behavior caused by browser range requests or client disconnects.

---

## 🤝 Contributing

Contributions, bug reports, and feature suggestions are welcome.

If you plan to add a larger feature or architectural change, please open an issue first
to discuss it before submitting a pull request.

---

## ❓ FAQ

**Does this limit downloads per file?**  
No. Files have unlimited downloads until they expire.

**Can I disable expiration?**  
Yes. You can use either:
- `/mode ttl 0` — disable expiration explicitly  
- `/mode reset` — reset to default (no expiration)

**Is there a file size limit?**  
Yes. File size limits depend on **Telegram**, not this bot.
- Regular Telegram accounts: up to **2 GB**
- Telegram Premium accounts: up to **4 GB**

**Can I use my own domain?**  
Yes. Railway supports custom domains.

## 📜 License

Apache License 2.0

