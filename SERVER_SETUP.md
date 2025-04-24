# Server Setup Guide

This guide explains how to deploy the Trading Charts Analysis service on your server.

## Prerequisites

1. Python 3.8 or higher (you already have this in your myenv)
2. Git
3. Systemd (for service management)

## Installation Steps

1. **Navigate to the project directory**:
```bash
cd /home/ken/AI/hei_chart
```

2. **Pull the latest changes**:
```bash
git pull origin main
```

3. **Set up the environment**:
```bash
# Run the deployment script
chmod +x deploy.sh
./deploy.sh
```

4. **Configure the environment**:
- Edit the `.env` file with your settings:
  ```bash
  nano .env
  ```
- Add your `credentials.json` file to the project directory

5. **Set up the systemd service**:
```bash
# Copy the service file
sudo cp trading-charts.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start the service
sudo systemctl enable trading-charts
sudo systemctl start trading-charts
```

## Monitoring

- Check service status:
  ```bash
  sudo systemctl status trading-charts
  ```

- View logs:
  ```bash
  sudo journalctl -u trading-charts -f
  ```

## Updating

To update the service with the latest code:

1. Stop the service:
```bash
sudo systemctl stop trading-charts
```

2. Pull the latest changes:
```bash
cd /home/ken/AI/hei_chart
git pull origin main
```

3. Run the deployment script:
```bash
./deploy.sh
```

4. Restart the service:
```bash
sudo systemctl start trading-charts
```

## Troubleshooting

1. If the service fails to start:
   - Check the logs: `sudo journalctl -u trading-charts -n 50`
   - Verify permissions: `ls -l run.sh`
   - Check Python environment: `source myenv/bin/activate && python -V`

2. If charts aren't being generated:
   - Check the `charts` directory permissions
   - Verify Google Sheets credentials
   - Check the `.env` configuration

3. If Telegram messages aren't being sent:
   - Verify bot token in `.env`
   - Check internet connectivity
   - Verify bot permissions in the group 