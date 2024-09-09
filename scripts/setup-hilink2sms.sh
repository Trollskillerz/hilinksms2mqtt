#!/bin/bash

# Mise à jour du système
echo "Mise à jour du système..."
apt-get update && apt-get upgrade -y

# Installation des dépendances
echo "Installation des dépendances..."
apt-get install -y python3-full python3-venv git

# Création d'un répertoire pour l'application
echo "Création du répertoire de l'application..."
mkdir -p /opt/huawei_sms_mqtt_bridge
chown $USER:$USER /opt/huawei_sms_mqtt_bridge

# Clonage du dépôt (remplacez l'URL par celle de votre dépôt si nécessaire)
echo "Clonage du dépôt..."
git clone https://github.com/Trollskillerz/hilinksms2mqtt.git /opt/huawei_sms_mqtt_bridge

# Création d'un environnement virtuel
echo "Création de l'environnement virtuel..."
python3 -m venv /opt/huawei_sms_mqtt_bridge/venv

# Activation de l'environnement virtuel et installation des dépendances
echo "Installation des dépendances Python..."
source /opt/huawei_sms_mqtt_bridge/venv/bin/activate
/opt/huawei_sms_mqtt_bridge/venv/bin/pip install --upgrade pip setuptools wheel
/opt/huawei_sms_mqtt_bridge/venv/bin/pip install -r /opt/huawei_sms_mqtt_bridge/requirements.txt

# Demande des valeurs des variables d'environnement
echo "Configuration des variables d'environnement..."
read -p "MQTT_TOPIC: " mqtt_topic
read -p "MQTT_IP: " mqtt_ip
read -p "PORT: " port
read -p "CLIENTID: " clientid
read -p "MQTT_ACCOUNT: " mqtt_account
read -p "MQTT_PASSWORD: " mqtt_password
read -p "HUAWEI_ROUTER_IP_ADDRESS: " huawei_router_ip
read -p "DELAY_SECOND: " delay_second
read -p "SIGNAL_CHECK_INTERVAL: " signal_check_interval

# Écriture des variables dans le fichier .env
echo "Écriture des variables dans le fichier .env..."
cat > /opt/huawei_sms_mqtt_bridge/.env <<EOL
MQTT_TOPIC=$mqtt_topic
MQTT_IP=$mqtt_ip
PORT=$port
CLIENTID=$clientid
MQTT_ACCOUNT=$mqtt_account
MQTT_PASSWORD=$mqtt_password
HUAWEI_ROUTER_IP_ADDRESS=$huawei_router_ip
DELAY_SECOND=$delay_second
SIGNAL_CHECK_INTERVAL=$signal_check_interval
EOL

# Création du fichier de service systemd
echo "Création du service systemd..."
tee /etc/systemd/system/huawei_sms_mqtt_bridge.service > /dev/null <<EOT
[Unit]
Description=Huawei SMS MQTT Bridge
After=network.target

[Service]
ExecStart=/opt/huawei_sms_mqtt_bridge/venv/bin/python /opt/huawei_sms_mqtt_bridge/huawei_sms_mqtt_bridge.py
WorkingDirectory=/opt/huawei_sms_mqtt_bridge
User=$USER
Group=$USER
Restart=always

[Install]
WantedBy=multi-user.target
EOT

# Rechargement de systemd
echo "Rechargement de systemd..."
systemctl daemon-reload

# Activation et démarrage du service
echo "Activation et démarrage du service..."
systemctl enable huawei_sms_mqtt_bridge.service
systemctl start huawei_sms_mqtt_bridge.service

echo "Installation terminée. Le service Huawei SMS MQTT Bridge est maintenant actif et démarré."
echo "Vous pouvez vérifier son statut avec la commande : systemctl status huawei_sms_mqtt_bridge.service"
