#!/bin/bash

# Arrêt et suppression du service
echo "Arrêt et suppression du service Huawei SMS MQTT Bridge..."
sudo systemctl stop huawei_sms_mqtt_bridge.service
sudo systemctl disable huawei_sms_mqtt_bridge.service
sudo rm /etc/systemd/system/huawei_sms_mqtt_bridge.service

# Rechargement de systemd
echo "Rechargement de systemd..."
sudo systemctl daemon-reload

# Suppression du répertoire de l'application
echo "Suppression du répertoire de l'application..."
sudo rm -rf /opt/huawei_sms_mqtt_bridge

# Nettoyage des paquets installés (optionnel, à utiliser avec précaution)
# echo "Nettoyage des paquets installés..."
# sudo apt-get remove -y python3 python3-pip python3-venv git
# sudo apt-get autoremove -y

echo "Désinstallation terminée. Le service Huawei SMS MQTT Bridge a été supprimé."
