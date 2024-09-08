# Huawei SMS MQTT Bridge

Ce projet est un pont entre un routeur Huawei et un broker MQTT, permettant de recevoir et d'envoyer des SMS via MQTT.

## Fonctionnalités

- Réception des SMS du routeur Huawei et publication sur MQTT
- Envoi de SMS via MQTT
- Surveillance de la qualité du signal et des informations réseau
- Gestion robuste des déconnexions

## Prérequis

- Python 3.7+
- Docker (optionnel)

## Configuration

Copiez le fichier `.env.example` en `.env` et modifiez les valeurs selon votre configuration :
```
MQTT_TOPIC=huawei/sms
MQTT_IP=192.168.1.100
PORT=1883
CLIENTID=huawei_sms_bridge
MQTT_ACCOUNT=user
MQTT_PASSWORD=password
HUAWEI_ROUTER_IP_ADDRESS=192.168.8.1
DELAY_SECOND=10
SIGNAL_CHECK_INTERVAL=60
```

## Installation

### Sans Docker

1. Clonez ce dépôt
2. Installez les dépendances : `pip install -r requirements.txt`
3. Configurez le fichier `.env`
4. Lancez le script : `python huawei_sms_mqtt_bridge.py`

### Avec Docker

1. Clonez ce dépôt
2. Configurez le fichier `.env`
3. Construisez et lancez le conteneur :
   ```
   docker-compose up -d
   ```

## Utilisation

Le bridge publiera les SMS reçus sur le topic `{MQTT_TOPIC}/received` et écoutera les commandes d'envoi de SMS sur `{MQTT_TOPIC}/send`.

Pour envoyer un SMS, publiez un message JSON sur le topic `{MQTT_TOPIC}/send` avec le format suivant :
```
json
{
"number": "+33612345678",
"message": "Votre message ici"
}
```
## Contribution

Les contributions sont les bienvenues ! N'hésitez pas à ouvrir une issue ou une pull request.

## Licence

Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.
