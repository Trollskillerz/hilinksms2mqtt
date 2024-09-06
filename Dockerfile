# Utiliser une image de base avec Python
FROM python:3.10-slim

# Définir le répertoire de travail
WORKDIR /app

# Copier le script et le fichier de configuration dans le conteneur
COPY lte2mqtt.py /app/
COPY .env /app/

# Installer les dépendances
RUN pip install --no-cache-dir paho-mqtt huawei-lte-api python-dotenv

# Commande pour exécuter le script
CMD ["python", "lte2mqtt.py"]
