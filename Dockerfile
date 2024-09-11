# Utiliser une image Python officielle comme image de base
FROM python:3.9-slim-buster

# Définir le répertoire de travail dans le conteneur
WORKDIR /app

# Copier les fichiers de dépendances et les installer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le reste du code source de l'application
COPY . .

# Exposer le port si nécessaire (à ajuster selon vos besoins)
# EXPOSE 1883

# Commande pour exécuter l'application
CMD ["python", "huawei_sms_mqtt_bridge.py"]
