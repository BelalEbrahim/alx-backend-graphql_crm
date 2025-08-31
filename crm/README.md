# CRM Project Setup Guide

This guide will walk you through setting up the CRM project, installing dependencies, running migrations, and starting background workers.

---

## 1. Install Redis and Dependencies

### On Ubuntu/Debian
```bash
sudo apt update
sudo apt install redis-server
```

Start and enable Redis:
```bash
sudo systemctl enable redis-server
sudo systemctl start redis-server
```

### On macOS (Homebrew)
```bash
brew install redis
brew services start redis
```

### Python Dependencies
Install required Python packages:
```bash
pip install -r requirements.txt
```

---

## 2. Run Migrations

Apply database migrations:
```bash
python manage.py migrate
```

---

## 3. Start Celery Worker

Run the Celery worker to process background tasks:
```bash
celery -A crm worker -l info
```

---

## 4. Start Celery Beat

Run the Celery Beat scheduler for periodic tasks:
```bash
celery -A crm beat -l info
```

---

## 5. Verify Logs

Celery task logs are written to:
```
/tmp/crm_report_log.txt
```

Use `tail` to monitor logs:
```bash
tail -f /tmp/crm_report_log.txt
```

---

