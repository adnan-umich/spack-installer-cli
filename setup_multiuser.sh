#!/bin/bash
# Setup script for multi-user Spack Installer Server

set -e

echo "Setting up Spack Installer Multi-User Server..."

# Create system directories
echo "Creating system directories..."
sudo mkdir -p /var/lib/spack_installer
sudo mkdir -p /var/log/spack_installer
sudo mkdir -p /etc/spack_installer

# Set permissions for multi-user access
echo "Setting permissions..."
sudo chmod 755 /var/lib/spack_installer
sudo chmod 755 /var/log/spack_installer
sudo chmod 755 /etc/spack_installer

# Create group for spack installer users
echo "Creating spack-installer group..."
sudo groupadd -f spack-installer

# Create configuration file
echo "Creating server configuration..."
sudo tee /etc/spack_installer/server.conf > /dev/null << 'EOF'
# Spack Installer Server Configuration

# Database settings (for multi-user mode)
SPACK_INSTALLER_DB_TYPE=json
SPACK_INSTALLER_MULTI_USER_DB=/var/lib/spack_installer/jobs.json

# Server settings
SPACK_INSTALLER_SERVER_HOST=localhost
SPACK_INSTALLER_SERVER_PORT=8080
SPACK_INSTALLER_SERVER_SOCKET=/tmp/spack_installer.sock
SPACK_INSTALLER_USE_UNIX_SOCKET=true

# Spack configuration
SPACK_SETUP_SCRIPT=/opt/spack/setup-env.sh

# Worker settings
WORKER_CHECK_INTERVAL=10.0
WORKER_HEARTBEAT_INTERVAL=30.0
JOB_TIMEOUT_MULTIPLIER=2.0
MAX_WORKER_HEARTBEAT_AGE=60.0
EOF

# Create systemd service file
echo "Creating systemd service..."
sudo tee /etc/systemd/system/spack-installer-worker.service > /dev/null << 'EOF'
[Unit]
Description=Spack Installer Multi-User Worker Daemon
After=network.target

[Service]
Type=simple
User=root
Group=spack-installer
WorkingDirectory=/var/lib/spack_installer
Environment=PYTHONPATH=/home/adnanzai/spack-installer-api
EnvironmentFile=-/etc/spack_installer/server.conf
ExecStart=/usr/bin/python3 /home/adnanzai/spack-installer-api/spack_installer/worker_daemon.py --log-file /var/log/spack_installer/worker.log
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Create wrapper script for easy server management
echo "Creating worker management script..."
sudo tee /usr/local/bin/spack-installer-worker > /dev/null << 'EOF'
#!/bin/bash
# Spack Installer Worker Management Script

# Load configuration
if [ -f /etc/spack_installer/server.conf ]; then
    source /etc/spack_installer/server.conf
fi

case "$1" in
    start)
        echo "Starting Spack Installer Worker..."
        sudo systemctl start spack-installer-worker
        ;;
    stop)
        echo "Stopping Spack Installer Worker..."
        sudo systemctl stop spack-installer-worker
        ;;
    restart)
        echo "Restarting Spack Installer Worker..."
        sudo systemctl restart spack-installer-worker
        ;;
    status)
        sudo systemctl status spack-installer-worker
        ;;
    enable)
        echo "Enabling Spack Installer Worker to start on boot..."
        sudo systemctl enable spack-installer-worker
        ;;
    disable)
        echo "Disabling Spack Installer Worker from starting on boot..."
        sudo systemctl disable spack-installer-worker
        ;;
    logs)
        sudo journalctl -u spack-installer-worker -f
        ;;
    validate)
        echo "Validating worker setup..."
        sudo /home/adnanzai/spack-installer-api/spack_installer/worker_daemon.py --validate-setup
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|enable|disable|logs|validate}"
        exit 1
        ;;
esac
EOF

sudo chmod +x /usr/local/bin/spack-installer-worker

# Create user script for client access
sudo tee /usr/local/bin/spack-installer > /dev/null << 'EOF'
#!/bin/bash
# Spack Installer Client Script

# Load system configuration
if [ -f /etc/spack_installer/server.conf ]; then
    export $(grep -v '^#' /etc/spack_installer/server.conf | xargs)
fi

# Override database path to use system-wide database for multi-user support
export SPACK_INSTALLER_DB_PATH="$SPACK_INSTALLER_MULTI_USER_DB"

# Run the client CLI
python3 -m spack_installer.cli "$@"
EOF

sudo chmod +x /usr/local/bin/spack-installer

echo ""
echo "✓ Multi-user Spack Installer Server setup complete!"
echo ""
echo "Next steps:"
echo "1. Update the SPACK_SETUP_SCRIPT path in /etc/spack_installer/server.conf"
echo "2. Add users to the spack-installer group:"
echo "   sudo usermod -a -G spack-installer <username>"
echo "3. Validate the worker setup:"
echo "   sudo spack-installer-worker validate"
echo "4. Start the worker:"
echo "   sudo spack-installer-worker start"
echo "5. Enable auto-start on boot:"
echo "   sudo spack-installer-worker enable"
echo ""
echo "Users can then submit jobs with:"
echo "   spack-installer submit <package-name>"
echo ""
echo "Worker management commands:"
echo "   sudo spack-installer-worker {start|stop|restart|status|logs|validate}"
echo ""
