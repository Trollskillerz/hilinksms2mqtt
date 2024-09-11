# Huawei SMS MQTT Bridge

Ce projet est un pont entre un routeur Huawei et un broker MQTT, permettant de gérer les SMS et de surveiller l'état du routeur.

## Fonctionnalités

- Envoi et réception de SMS via MQTT
- Surveillance de l'état du routeur (statut de connexion, force du signal, etc.)
- Publication des informations du routeur sur MQTT
- Configuration flexible via variables d'environnement

## Prérequis

- Python 3.9+
- Docker (optionnel)
- Un routeur Huawei compatible
- Un broker MQTT

## Installation

### Méthode standard

1. Clonez ce dépôt :
   ```
   git clone https://github.com/votre-nom/huawei-sms-mqtt-bridge.git
   cd huawei-sms-mqtt-bridge
   ```

2. Installez les dépendances :
   ```
   pip install -r requirements.txt
   ```

3. Configurez les variables d'environnement (voir section Configuration)

4. Lancez le script :
   ```
   python huawei_sms_mqtt_bridge.py
   ```

### Utilisation avec Docker

1. Construisez l'image Docker :
   ```
   docker build -t huawei-sms-mqtt-bridge .
   ```

2. Lancez le conteneur :
   ```
   docker run --env-file .env huawei-sms-mqtt-bridge
   ```

## Configuration

Créez un fichier `.env` à la racine du projet avec les variables suivantes :
```
MQTT_TOPIC=votre/topic/mqtt
MQTT_IP=adresse_ip_du_broker_mqtt
PORT=1883
CLIENTID=id_client_mqtt
MQTT_ACCOUNT=compte_mqtt
MQTT_PASSWORD=mot_de_passe_mqtt
HUAWEI_ROUTER_IP_ADDRESS=adresse_ip_du_routeur_huawei
CHECK_INTERVAL=60
SMS_CHECK_INTERVAL=30
DEBUG_LEVEL=INFO
```

Ajustez ces valeurs selon votre configuration.

## Utilisation

Une fois lancé, le bridge :
- Se connecte au broker MQTT spécifié
- Surveille les SMS entrants sur le routeur Huawei
- Publie les informations du routeur sur MQTT
- Écoute les commandes MQTT pour envoyer des SMS

## Contribution

Les contributions sont les bienvenues ! N'hésitez pas à ouvrir une issue ou à soumettre une pull request.

## Licence

[MIT License](LICENSE)
