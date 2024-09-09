# Huawei SMS MQTT Bridge

Ce projet est un pont entre une clé LTE Huawei E3372-320 et un broker MQTT, permettant de recevoir et d'envoyer des SMS via MQTT.

## Fonctionnalités

- Réception des SMS de la clé Huawei et publication sur MQTT
- Envoi de SMS via MQTT
- Surveillance de la qualité du signal et des informations réseau

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

1. Clonez ce dépôt
2. Installez les dépendances : `pip install -r requirements.txt`
3. Configurez le fichier `.env`
4. Lancez le script : `python huawei_sms_mqtt_bridge.py`

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

## Licence

Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.
