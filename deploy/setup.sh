#!/bin/bash
# Server setup script for OJ Tracker
set -e

echo "=== OJ Tracker Server Setup ==="

# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3 python3-pip python3-venv nginx supervisor certbot python3-certbot-nginx git

# Create app directory
sudo mkdir -p /opt/oj-tracker
sudo mkdir -p /var/log/oj-tracker

# Clone repository (update URL)
# git clone https://github.com/YOUR_USER/oj-tracker.git /opt/oj-tracker

# Setup Python venv
cd /opt/oj-tracker
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Copy config
cp .env.production .env
echo ">>> Please edit /opt/oj-tracker/.env with your actual configuration <<<"

# Initialize database
export FLASK_ENV=production
flask db upgrade
python seed_data.py

# Setup Nginx
sudo cp deploy/nginx.conf /etc/nginx/sites-available/oj-tracker
sudo ln -sf /etc/nginx/sites-available/oj-tracker /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Setup Supervisor
sudo cp deploy/supervisor.conf /etc/supervisor/conf.d/oj-tracker.conf
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start oj-tracker

echo "=== Setup complete ==="
echo "Don't forget to:"
echo "1. Edit /opt/oj-tracker/.env"
echo "2. Setup SSL: sudo certbot --nginx -d your-domain.com"
echo "3. Update deploy/nginx.conf with your domain"
