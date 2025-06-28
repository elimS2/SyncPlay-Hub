# Production Deployment Guide

## 🚀 YouTube Playlist Downloader & Job Queue System

Complete guide for deploying the YouTube Playlist Downloader with Job Queue System to production environment.

---

## 📋 Prerequisites

### System Requirements
- **Python:** 3.8+ (Recommended: 3.11+)
- **Operating System:** Windows 10+, Linux, macOS
- **Memory:** 4GB RAM minimum, 8GB recommended
- **Storage:** 100GB+ for media files
- **Network:** Stable internet connection

### Required Software
- Git (for deployment)
- yt-dlp (installed via pip)
- FFmpeg (for media processing)

---

## 🔧 Production Environment Setup

### 1. Clone Repository
```bash
git clone <repository-url>
cd Youtube
```

### 2. Create Virtual Environment
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Create Data Directory Structure
```bash
mkdir -p /opt/youtube-downloader/{DB,Playlists,Logs}
# Windows: Create folders manually or use PowerShell
```

### 5. Configure Environment Variables
Create `.env` file in project root:
```env
# Database Configuration
DB_PATH=/opt/youtube-downloader/DB/tracks.db
ROOT_DIR=/opt/youtube-downloader
PLAYLISTS_DIR=/opt/youtube-downloader/Playlists
LOGS_DIR=/opt/youtube-downloader/Logs

# Security
SECRET_KEY=your-super-secret-production-key-here

# Performance
DB_CONNECTION_POOL_SIZE=10
MAX_CONCURRENT_WORKERS=5
MAX_CONCURRENT_DOWNLOADS=3
LOG_LEVEL=INFO

# Optional: Monitoring
PROMETHEUS_ENABLED=false
EMAIL_ALERTS_ENABLED=false
```

---

## 🗄️ Database Setup

### 1. Initialize Database
```bash
python migrate.py status
python migrate.py apply-all
```

### 2. Verify Database
```bash
python -c "
import sqlite3
conn = sqlite3.connect('$DB_PATH')
print('Tables:', [t[0] for t in conn.execute('SELECT name FROM sqlite_master WHERE type=\"table\"').fetchall()])
conn.close()
"
```

---

## ⚙️ Production Configuration

### 1. Security Settings
- **Change default secret key** in `.env`
- **Restrict file permissions** on database and logs
- **Configure firewall** for port 8000
- **Use HTTPS** in production (reverse proxy recommended)

### 2. Performance Optimization
- **Connection pooling:** Set `DB_CONNECTION_POOL_SIZE=10`
- **Worker limits:** Adjust `MAX_CONCURRENT_WORKERS` based on CPU cores
- **Download limits:** Set `MAX_CONCURRENT_DOWNLOADS` based on bandwidth
- **Log rotation:** Logs auto-rotate at 100MB

### 3. Monitoring Setup
```python
# Enable monitoring in production
from config.production import get_config
config = get_config()
print(config.export_summary())
```

---

## 🚀 Deployment Options

### Option 1: Direct Deployment
```bash
# Start production server
python app.py --host 0.0.0.0 --port 8000 --root /opt/youtube-downloader
```

### Option 2: Systemd Service (Linux)
Create `/etc/systemd/system/youtube-downloader.service`:
```ini
[Unit]
Description=YouTube Playlist Downloader
After=network.target

[Service]
Type=simple
User=youtube
WorkingDirectory=/opt/youtube-downloader
Environment=PATH=/opt/youtube-downloader/venv/bin
ExecStart=/opt/youtube-downloader/venv/bin/python app.py --host 0.0.0.0 --port 8000 --root /opt/youtube-downloader
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Start service:
```bash
sudo systemctl enable youtube-downloader
sudo systemctl start youtube-downloader
sudo systemctl status youtube-downloader
```

### Option 3: Docker Deployment
Create `Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["python", "app.py", "--host", "0.0.0.0", "--port", "8000", "--root", "/data"]
```

Build and run:
```bash
docker build -t youtube-downloader .
docker run -d -p 8000:8000 -v /opt/youtube-downloader:/data youtube-downloader
```

---

## 🔍 Production Testing

### 1. Run Integration Tests
```bash
python test_phase8_integration.py
```

### 2. Health Check
```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/jobs/queue/status
```

### 3. Performance Test
```bash
python test_phase7_performance.py
```

Expected results:
- ✅ All integration tests pass (>90% success rate)
- ✅ API endpoints respond within 100ms
- ✅ Job creation rate >100 jobs/second
- ✅ Database performance optimized

---

## 📊 Monitoring & Maintenance

### 1. Log Monitoring
```bash
# Monitor application logs
tail -f /opt/youtube-downloader/Logs/app.log

# Monitor job logs
ls /opt/youtube-downloader/logs/jobs/
```

### 2. Performance Monitoring
Access web interface:
- **Jobs Queue:** http://localhost:8000/jobs
- **System Logs:** http://localhost:8000/logs
- **Performance:** Check job completion rates

### 3. Database Maintenance
```bash
# Automatic maintenance runs daily
# Manual maintenance:
python -c "
from utils.database_optimizer import DatabaseOptimizer
optimizer = DatabaseOptimizer()
optimizer.perform_maintenance()
"
```

### 4. Backup Strategy
```bash
# Database backup
cp /opt/youtube-downloader/DB/tracks.db /backup/tracks_$(date +%Y%m%d).db

# Media backup (optional - large files)
rsync -av /opt/youtube-downloader/Playlists/ /backup/playlists/
```

---

## 🛡️ Security Considerations

### 1. File Permissions
```bash
chmod 750 /opt/youtube-downloader
chmod 640 /opt/youtube-downloader/.env
chmod 640 /opt/youtube-downloader/DB/tracks.db
```

### 2. Network Security
- **Firewall:** Restrict access to port 8000
- **Reverse Proxy:** Use nginx/Apache for HTTPS
- **Access Control:** Implement authentication if needed

### 3. Data Protection
- **Regular backups** of database and configuration
- **Secure storage** of API keys and secrets
- **Log rotation** to prevent disk space issues

---

## 🚨 Troubleshooting

### Common Issues

**Service won't start:**
```bash
# Check logs
journalctl -u youtube-downloader -f

# Check port availability
netstat -tulpn | grep :8000

# Check permissions
ls -la /opt/youtube-downloader/
```

**Database issues:**
```bash
# Check database integrity
sqlite3 /opt/youtube-downloader/DB/tracks.db "PRAGMA integrity_check;"

# Reset database if corrupted
python migrate.py rollback-all
python migrate.py apply-all
```

**Performance issues:**
```bash
# Check system resources
htop
df -h

# Monitor job queue
curl http://localhost:8000/api/jobs/queue/status
```

**Download failures:**
```bash
# Check yt-dlp
yt-dlp --version

# Update yt-dlp
pip install --upgrade yt-dlp

# Check logs
tail -f /opt/youtube-downloader/logs/jobs/job_*/job.log
```

---

## 🔄 Updates & Maintenance

### 1. Application Updates
```bash
# Stop service
sudo systemctl stop youtube-downloader

# Backup database
cp /opt/youtube-downloader/DB/tracks.db /backup/

# Update code
git pull origin main
pip install -r requirements.txt

# Run migrations
python migrate.py apply-all

# Start service
sudo systemctl start youtube-downloader
```

### 2. Dependency Updates
```bash
# Update yt-dlp regularly
pip install --upgrade yt-dlp

# Update other dependencies (carefully)
pip install --upgrade -r requirements.txt
```

### 3. Monitoring Updates
```bash
# Check system status
python test_phase8_integration.py

# Verify functionality
curl http://localhost:8000/api/health
```

---

## 📈 Scaling Considerations

### Horizontal Scaling
- **Multiple workers:** Increase `MAX_CONCURRENT_WORKERS`
- **Separate download server:** Dedicated server for downloads
- **Load balancing:** Multiple app instances behind load balancer

### Vertical Scaling
- **CPU:** More cores = more concurrent workers
- **Memory:** 8GB+ for large playlists
- **Storage:** SSD recommended for database performance

### Performance Tuning
- **Database:** Adjust connection pool size
- **Workers:** Tune based on CPU cores and I/O capacity
- **Downloads:** Balance with available bandwidth

---

## ✅ Production Checklist

Before going live:

- [ ] **Environment configured** (.env file with production values)
- [ ] **Database initialized** (migrations applied)
- [ ] **Security configured** (secret key, permissions, firewall)
- [ ] **Service configured** (systemd/docker)
- [ ] **Monitoring setup** (logs, health checks)
- [ ] **Backup strategy** implemented
- [ ] **Integration tests** passing (>90%)
- [ ] **Performance tests** passing
- [ ] **Documentation** reviewed
- [ ] **Support contacts** established

---

## 📞 Support

### Resources
- **Logs:** `/opt/youtube-downloader/Logs/`
- **Jobs Interface:** http://localhost:8000/jobs
- **API Documentation:** Built-in at runtime
- **Configuration:** `config/production.py`

### Emergency Procedures
1. **Service restart:** `sudo systemctl restart youtube-downloader`
2. **Database backup:** `cp tracks.db tracks_emergency.db`
3. **Clear job queue:** Access `/jobs` interface, cancel all jobs
4. **Reset system:** Stop service, backup data, restart from clean state

---

*Production Deployment Guide - Version 1.0*  
*YouTube Playlist Downloader & Job Queue System* 