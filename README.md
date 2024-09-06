# hilinksms2mqtt
send receive sms by mqtt with huawei e3372h-320

```markdown
# Huawei LTE to MQTT

## Description

Ce projet est un script Python qui interagit avec un routeur Huawei LTE pour récupérer et publier des informations sur un broker MQTT. Il peut également envoyer des SMS via l'API du routeur Huawei LTE. Le script utilise Docker pour faciliter le déploiement.

## Fonctionnalités

- **Récupération des SMS** : Récupère les SMS non lus et les publie sur un broker MQTT.
- **Publication des Informations** : Publie les informations sur la qualité du signal et les informations réseau sur le broker MQTT.
- **Envoi de SMS** : Permet d'envoyer des SMS à un ou plusieurs numéros via MQTT.
- **Docker** : Conteneurisé pour une utilisation facile et reproductible.

## Prérequis

- Python 3.10+
- Docker
- Un routeur Huawei LTE avec accès à l'API
- Un broker MQTT

## Installation

### Cloner le Dépôt

```bash
git clone https://github.com/trollskillerz/huawei-lte-to-mqtt.git
cd huawei-lte-to-mqtt
```

### Configurer les Variables d'Environnement

Crée un fichier `.env` à la racine du projet avec les variables suivantes :

```env
HUAWEI_ROUTER_IP_ADDRESS=192.168.8.1
MQTT_TOPIC=hilinksms
MQTT_ACCOUNT=mqtt
MQTT_PASSWORD=mqtt
MQTT_IP=192.168.1.202
PREFIX=lteclient
DELAY_SECOND=10
LOCALE=en_US
PORT=1883
CLIENTID=lte2mqtt
```

### Construire l'Image Docker

```bash
docker build -t lte2mqtt .
```

### Exécuter le Conteneur Docker

```bash
docker run -d --name lte2mqtt_container --env-file .env lte2mqtt
```

## Utilisation

- **Envoyer un SMS** : Publie un message sur le topic MQTT configuré pour l'envoi de SMS (`<MQTT_TOPIC>/send`). Le message doit être au format JSON, par exemple :

```bash
mosquitto_pub -h <MQTT_HOST> -t "<MQTT_TOPIC>/send" -m '{"number": "+33612345678", "message": "Hello, this is a test!"}'
```

- **Consulter les Logs** : Vérifie les logs du conteneur pour les messages de débogage et les erreurs :

```bash
docker logs lte2mqtt_container
```

## Exemples

### Exemple de Message JSON pour Envoyer un SMS

```json
{
  "number": "+33612345678",
  "message": "Hello, this is a test!"
}
```

### Exemple de Publication de l'Information du Signal

Les informations sur la qualité du signal et les données réseau sont publiées automatiquement sur les topics MQTT configurés. Aucune action supplémentaire n'est nécessaire pour ces fonctionnalités.

## Débogage

Si le conteneur ne fonctionne pas correctement, voici quelques étapes de dépannage :

1. **Vérifier les Conteneurs** : Assure-toi que le conteneur est en cours d'exécution :

   ```bash
   docker container ls -a
   ```

2. **Vérifier les Logs** : Consulte les logs du conteneur pour identifier les erreurs :

   ```bash
   docker logs lte2mqtt_container
   ```

3. **Exécuter en Mode Interactif** : Pour un débogage plus approfondi, exécute le conteneur en mode interactif :

   ```bash
   docker run -it --entrypoint /bin/bash lte2mqtt
   ```

## Aide

Pour toute question ou problème, veuillez ouvrir une issue sur le dépôt GitHub ou contacter l'auteur.

## Contribuer

Les contributions sont les bienvenues ! Veuillez soumettre une pull request pour toute amélioration ou correction.

## Licence

Ce projet est sous la [Licence MIT](LICENSE).

```

### Points à Ajuster

Problème de route

L'ajout du dongle a eu un effet que je n'avais pas anticipé... Mon domoticz n'arrive plus a sortir sur le web...

Un accès web à google passe maintenant par le dongle... ce qui n'est pas souhaitable vue que je n'ai pas de forfait data...

$ wget www.google.com
--2020-06-15 10:59:49--  http://www.google.com/
Résolution de www.google.com (www.google.com)… 192.168.8.1
Connexion à www.google.com (www.google.com)|192.168.8.1|:80… connecté.
requête HTTP transmise, en attente de la réponse… 307 Temporary Redirect
Emplacement : http://192.168.8.1/html/index.html?url=www.google.com [suivant]
--2020-06-15 11:00:04--  http://192.168.8.1/html/index.html?url=www.google.com
Connexion à 192.168.8.1:80… connecté.

si l'on regarde les routes, on peut voir qu'il y a maintenant 2 chemins pour sortir du réseau local : eth1 et wlan0

$ route -n
Table de routage IP du noyau
Destination     Passerelle      Genmask         Indic Metric Ref    Use Iface
0.0.0.0         192.168.8.1     0.0.0.0         UG    204    0        0 eth1
0.0.0.0         192.168.1.1     0.0.0.0         UG    303    0        0 wlan0
192.168.1.0     0.0.0.0         255.255.255.0   U     303    0        0 wlan0
192.168.8.0     0.0.0.0         255.255.255.0   U     204    0        0 eth1

du coup il faut penser à supprimer la default gateway 192.168.8.1 puis rajouter la bonne

$ sudo ip route flush 0/0
$ sudo ip route add default via 192.168.1.1
