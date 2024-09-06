import logging
import time
import os
import signal
import json
import paho.mqtt.client as mqtt
from huawei_lte_api.Client import Client
from huawei_lte_api.AuthorizedConnection import AuthorizedConnection
from huawei_lte_api.enums.sms import BoxTypeEnum
from huawei_lte_api.enums.client import ResponseEnum
import huawei_lte_api.exceptions
from dotenv import load_dotenv


# Variables globales
old_signal_info = ""
old_battery_charge = ""
old_network_info = ""
old_time = time.time()
last_signal_check = 0
signal_check_interval = 30  # seconds
running = True

# Callback MQTT lors de la connexion
def on_mqtt_connect(client, userdata, flags, rc, properties=None):
    logging.info("Connected to MQTT host")
    client.publish(f"{mqttprefix}/connected", "1", 0, True)
    client.subscribe(f"{mqttprefix}/send")

# Callback lors de la déconnexion MQTT
def on_mqtt_disconnect(client, userdata, rc, properties=None):
    logging.info("Disconnected from MQTT host")
    logging.info("Exit")
    shutdown()

# Fonction pour récupérer et publier les SMS via MQTT
def get_and_publish_sms():
    global client  # Utilisation de l'instance globale du client Huawei LTE
    global mqtt_client  # Utilisation de l'instance globale du client MQTT
    try:
        sms_list = client.sms.get_sms_list(1, BoxTypeEnum.LOCAL_INBOX, 1, 0, 0, 1)
        
        if sms_list['Messages'] is None:
            logging.info("No new SMS.")
            return

        # Vérification si 'Messages' est une liste
        messages = sms_list['Messages']['Message']
        if isinstance(messages, list):
            message = messages[0]  # Prendre le premier message
        else:
            message = messages  # Si un seul message

        # Si le SMS est lu, on l'ignore
        if int(message['Smstat']) == 1:
            logging.info(f"No new SMS to read: {message['Index']}")
            return

        # Récupération du SMS et publication sur MQTT
        sms = message
        payload = json.dumps({
            "datetime": sms['Date'],
            "number": sms['Phone'],
            "text": sms['Content']
        }, ensure_ascii=False)
        
        mqtt_client.publish(f"{mqttprefix}/received", payload)
        logging.info(f"SMS published: {payload}")

        # Marquer le SMS comme lu
        client.sms.set_read(int(sms['Index']))

    except Exception as e:
        logging.error(f"Failed to retrieve SMS: {e}")

# Fonction pour récupérer la qualité du signal (similaire à Gammu)
def get_signal_info():
    global old_signal_info, last_signal_check
    try:
        if time.time() - last_signal_check < signal_check_interval:
            return
        last_signal_check = time.time()
        
        signal_info = client.device.signal()
        if signal_info != old_signal_info:
            signal_payload = json.dumps(signal_info)
            mqtt_client.publish(f"{mqttprefix}/signal", signal_payload)
            old_signal_info = signal_info
    except Exception as e:
        logging.error(f"ERROR: Unable to check signal quality: {e}")

# Fonction pour obtenir les informations réseau
def get_network_info():
    global old_network_info
    try:
        network_info = client.device.information()
        if network_info != old_network_info:
            network_payload = json.dumps(network_info)
            mqtt_client.publish(f"{mqttprefix}/network", network_payload)
            old_network_info = network_info
    except Exception as e:
        logging.error(f"ERROR: Unable to check network info: {e}")

# Fonction pour obtenir l'heure
def get_datetime():
    global old_time
    try:
        now = time.time()
        if (now - old_time) > 60:
            mqtt_client.publish(f"{mqttprefix}/datetime", now)
            old_time = now
    except Exception as e:
        logging.error(f"ERROR: Unable to check datetime: {e}")

# Fonction de déconnexion propre
def shutdown(signum=None, frame=None):
    global running
    if running:
        logging.info("Shutting down gracefully...")
        mqtt_client.publish(f"{mqttprefix}/connected", "0", 0, True)
        mqtt_client.disconnect()
        running = False

# Callback MQTT lors de la réception d'un message
def on_mqtt_message(client, userdata, msg):
    try:
        # Décoder le payload JSON
        payload = json.loads(msg.payload.decode())
        
        logging.info(f"Received message on topic '{msg.topic}': {payload}")

        # Vérifier si le message est pour l'envoi de SMS
        if msg.topic == f"{mqttprefix}/send":
            logging.info(f"Processing SMS send request: {payload}")
            send_sms(payload)

    except Exception as e:
        logging.error(f"Error processing incoming MQTT message on topic '{msg.topic}': {e}")

# Fonction pour envoyer un SMS
def send_sms(payload):
    try:
        number = payload.get('number')
        message = payload.get('message')
        
        if not number or not message:
            logging.error("Invalid payload, 'number' or 'message' missing.")
            return

        # Envoi du SMS via l'API Huawei LTE
        response = client.sms.send_sms([number], message)  # Note que number est passé dans une liste
        if response == ResponseEnum.OK.value:
            logging.info(f"SMS sent to {number}: {message}")
            mqtt_client.publish(f"{mqttprefix}/sent", json.dumps({
                "status": "sent",
                "number": number,
                "message": message
            }))
        else:
            logging.error(f"Failed to send SMS: {response}")

    except Exception as e:
        logging.error(f"Failed to send SMS: {e}")

# Initialisation principale
if __name__ == "__main__":
    logging.basicConfig(format="%(asctime)s: %(message)s", level=logging.INFO, datefmt="%H:%M:%S")

    versionnumber = '1.0.0'
    logging.info(f'===== Huawei LTE to MQTT v{versionnumber} =====')
     
    # Charger les variables d'environnement depuis le fichier .env
    load_dotenv()

    # Charger les variables d'environnement
    mqttprefix = os.getenv("MQTT_TOPIC")
    mqtthost = os.getenv("MQTT_IP")
    mqttport = int(os.getenv("PORT", 1883))
    mqttclientid = os.getenv("CLIENTID")
    mqttuser = os.getenv("MQTT_ACCOUNT")
    mqttpassword = os.getenv("MQTT_PASSWORD")

    huawei_router_ip = os.getenv("HUAWEI_ROUTER_IP_ADDRESS")
    delay_second = int(os.getenv("DELAY_SECOND", 10))

    # Afficher les variables d'environnement pour vérification
    logging.info(f"Huawei Router IP Address: {huawei_router_ip}")
    logging.info(f"MQTT Host: {mqtthost}, Port: {mqttport}, Client ID: {mqttclientid}")

    # Connexion à l'API Huawei LTE
    try:
        url = f'http://{huawei_router_ip}/'
        logging.info(f"Connecting to Huawei LTE API at {url}")
        connection = AuthorizedConnection(url)
        client = Client(connection)
        logging.info('Huawei LTE API client initialized')
    except Exception as e:
        logging.error(f'Failed to initialize Huawei LTE API client: {e}')
        exit(1)
    
    # Connexion MQTT
    mqtt_client = mqtt.Client(client_id=mqttclientid, protocol=mqtt.MQTTv5)
    mqtt_client.username_pw_set(mqttuser, mqttpassword)
    mqtt_client.on_connect = on_mqtt_connect
    mqtt_client.on_disconnect = on_mqtt_disconnect
    mqtt_client.connect(mqtthost, mqttport)
    # Ajouter l'abonnement pour recevoir des SMS à envoyer
    mqtt_client.message_callback_add(f"{mqttprefix}/send", on_mqtt_message)

    # Gestion des signaux pour arrêt propre
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Boucle principale
    while running:
        time.sleep(delay_second)
        get_and_publish_sms()
        get_signal_info()
        get_network_info()
        get_datetime()
        mqtt_client.loop()
