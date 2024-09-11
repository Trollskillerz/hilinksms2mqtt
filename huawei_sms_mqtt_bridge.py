import logging
import time
import os
import signal
import json
import asyncio
import pycurl
import paho.mqtt.client as mqtt
from datetime import datetime
from xml.etree import ElementTree as ET
from dotenv import load_dotenv
from queue import Queue
from io import BytesIO

class HuaweiSMSMQTTBridge:
    def __init__(self):
        self.load_config()
        self.setup_logging()
        self.running = True
        self.mqtt_client = None
        self.sms_queue = Queue()
        self.cookie = None
        self.token = None
        self.last_sms_time = 0
        self.sms_cooldown = 10  # Temps d'attente entre les SMS en secondes
        self.last_status_check = 0
        self.status_check_interval = 60  # 60 secondes entre chaque vérification
        self.old_status_info = {}
        self.last_signal_check = 0
        self.signal_check_interval = 60  # 60 secondes entre chaque vérification
        self.old_signal_info = {}
        self.last_network_check = 0
        self.network_check_interval = 60  # 60 secondes entre chaque vérification
        self.old_network_info = {}
        self.loop = None
        self.last_token_time = 0
        self.token_refresh_interval = 5  # 5 secondes, ou ajustez selon vos besoins        

    def setup_logging(self):
        numeric_level = getattr(logging, self.debug_level, None)
        if not isinstance(numeric_level, int):
            raise ValueError(f'Niveau de log invalide : {self.debug_level}')
        
        logging.basicConfig(level=numeric_level,
                            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger("HuaweiSMSMQTTBridge")
        self.logger.info(f"Niveau de logging configuré à : {self.debug_level}")

    @staticmethod
    def get_env(key, default=None):
        value = os.environ.get(key, default)
        if value is None:
            raise ValueError(f"La variable d'environnement '{key}' est requise mais n'est pas définie.")
        return value

    def load_config(self):
        if os.path.exists('.env'):
            load_dotenv()
        self.mqtt_prefix = self.get_env("MQTT_TOPIC")
        self.mqtt_host = self.get_env("MQTT_IP")
        self.mqtt_port = int(self.get_env("PORT", "1883"))
        self.mqtt_client_id = self.get_env("CLIENTID")
        self.mqtt_user = self.get_env("MQTT_ACCOUNT")
        self.mqtt_password = self.get_env("MQTT_PASSWORD")
        self.huawei_router_ip = self.get_env("HUAWEI_ROUTER_IP_ADDRESS")
        self.delay_second = int(self.get_env("DELAY_SECOND", "10"))
        self.signal_check_interval = int(self.get_env("SIGNAL_CHECK_INTERVAL", "60"))
        self.debug_level = os.environ.get("DEBUG_LEVEL", "INFO").upper()
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.debug_level not in valid_levels:
            raise ValueError(f"Niveau de debug invalide : {self.debug_level}. Les valeurs valides sont : {', '.join(valid_levels)}")
        
    def get_session_token(self):
        buffer = BytesIO()
        c = pycurl.Curl()
        c.setopt(c.URL, f"http://{self.huawei_router_ip}/api/webserver/SesTokInfo")
        c.setopt(c.WRITEDATA, buffer)
        c.perform()
        c.close()

        response = buffer.getvalue().decode('utf-8')
        root = ET.fromstring(response)
        self.cookie = root.find('.//SesInfo').text
        self.token = root.find('.//TokInfo').text

        self.logger.debug(f"Tokens mis à jour - Cookie: {self.cookie[:10]}... Token: {self.token[:10]}...")

    async def check_and_publish_received_sms(self):
        try:
            self.get_session_token()
            
            page_index = 1
            max_sms_per_check = 5  # Limite le nombre de SMS traités à chaque vérification
            sms_processed = 0

            while sms_processed < max_sms_per_check:
                buffer = BytesIO()
                c = pycurl.Curl()
                c.setopt(c.URL, f"http://{self.huawei_router_ip}/api/sms/sms-list")
                c.setopt(c.HTTPHEADER, [
                    f"Cookie: {self.cookie}",
                    f"__RequestVerificationToken: {self.token}",
                    "Content-Type: application/x-www-form-urlencoded; charset=UTF-8"
                ])
                data = f"""<?xml version='1.0' encoding='UTF-8'?><request><PageIndex>{page_index}</PageIndex><ReadCount>20</ReadCount><BoxType>1</BoxType><SortType>0</SortType><Ascending>0</Ascending><UnreadPreferred>1</UnreadPreferred></request>"""
                c.setopt(c.POSTFIELDS, data)
                c.setopt(c.WRITEDATA, buffer)
                c.perform()
                c.close()

                response = buffer.getvalue().decode('utf-8')
                root = ET.fromstring(response)

                unread_messages = root.findall('.//Message[Smstat="0"]')
                if not unread_messages:
                    break  # Pas de nouveaux messages non lus sur cette page

                for message in unread_messages:
                    if sms_processed >= max_sms_per_check:
                        break

                    sms_index = message.find('Index').text
                    phone = message.find('Phone').text
                    content = message.find('Content').text
                    date = message.find('Date').text

                    # Publier le SMS reçu
                    payload = {
                        "sender": phone,
                        "message": content,
                        "date_received": date
                    }
                    self.mqtt_client.publish(f"{self.mqtt_prefix}/received", json.dumps(payload))
                    self.logger.info(f"Nouveau SMS reçu de {phone} le {date}: {content[:20]}...")
                    # Marquer le SMS comme lu
                    await self.mark_sms_as_read(sms_index)

                    sms_processed += 1
                    await asyncio.sleep(0.5)  # Petit délai entre chaque traitement de SMS

                page_index += 1

        except Exception as e:
            self.logger.error(f"Erreur lors de la vérification des SMS reçus : {e}")

    async def mark_sms_as_read(self, sms_index):
        try:
            self.get_session_token()
            buffer = BytesIO()
            c = pycurl.Curl()
            c.setopt(c.URL, f"http://{self.huawei_router_ip}/api/sms/set-read")
            c.setopt(c.HTTPHEADER, [
                f"Cookie: {self.cookie}",
                f"__RequestVerificationToken: {self.token}",
                "Content-Type: application/x-www-form-urlencoded; charset=UTF-8"
            ])
            data = f"""<?xml version='1.0' encoding='UTF-8'?><request><Index>{sms_index}</Index></request>"""
            c.setopt(c.POSTFIELDS, data)
            c.setopt(c.WRITEDATA, buffer)
            c.perform()
            c.close()

            response = buffer.getvalue().decode('utf-8')
            self.logger.debug(f"Réponse pour marquer le SMS comme lu : {response}")

        except Exception as e:
            self.logger.error(f"Erreur lors du marquage du SMS comme lu : {e}")

    def send_sms(self, phone, content, retry=False, retry_count=0):
        self.get_session_token()
        current_time = time.time()
        if not retry and current_time - self.last_sms_time < self.sms_cooldown:
            wait_time = self.sms_cooldown - (current_time - self.last_sms_time)
            self.logger.info(f"Attente de {wait_time:.2f} secondes avant le prochain envoi")
            time.sleep(wait_time)
        self.logger.debug(f"Tentative d'envoi de SMS à {phone}")
        buffer = BytesIO()
        c = pycurl.Curl()
        c.setopt(c.URL, f"http://{self.huawei_router_ip}/api/sms/send-sms")
        c.setopt(c.HTTPHEADER, [
            f"Cookie: {self.cookie}",
            f"__RequestVerificationToken: {self.token}",
            "Content-Type: application/x-www-form-urlencoded; charset=UTF-8"
        ])
        data = f"""<?xml version='1.0' encoding='UTF-8'?><request><Index>-1</Index><Phones><Phone>{phone}</Phone></Phones><Sca></Sca><Content>{content}</Content><Length>{len(content)}</Length><Reserved>1</Reserved><Date>-1</Date></request>"""
        c.setopt(c.POSTFIELDS, data)
        c.setopt(c.WRITEDATA, buffer)
        c.perform()
        c.close()

        response = buffer.getvalue().decode('utf-8')
        success = "<response>OK</response>" in response
        status = "OK" if success else "Failed"
        self.logger.debug(f"Réponse du serveur pour l'envoi de SMS: {status}")
            
        # Préparer le payload pour la publication MQTT
        payload = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "success" if success else "failure",
            "recipient": phone,
            "message": content
        }
        # Publier le résultat sur MQTT
        self.mqtt_client.publish(f"{self.mqtt_prefix}/sent", json.dumps(payload))
        self.logger.debug(f"Réponse complète du serveur : {response}")
        
        if success:
            self.last_sms_time = time.time()
            self.logger.info(f"SMS envoyé avec succès à {phone}")
        else:
            self.logger.error(f"Échec de l'envoi du SMS à {phone}")
            if not retry and retry_count < 3:  # Limite à 3 tentatives
                self.logger.info(f"Planification d'une nouvelle tentative dans 30 secondes (tentative {retry_count + 1}/3)")
                self.loop.call_later(30, lambda: self.send_sms(phone, content, True, retry_count + 1))
        
        return success
    
    def retry_sms(self, phone, content):
        self.logger.info(f"Nouvelle tentative d'envoi de SMS à {phone}")
        success = self.send_sms(phone, content, retry=True)
        if not success:
            self.logger.error(f"Échec de la seconde tentative d'envoi de SMS à {phone}. Abandon de l'envoi.")

    def on_mqtt_connect(self, client, userdata, flags, rc, properties=None):
        self.logger.info("Connecté au serveur MQTT")
        client.publish(f"{self.mqtt_prefix}/connected", "1", 0, True)
        client.subscribe(f"{self.mqtt_prefix}/send")

    def on_mqtt_disconnect(self, client, userdata, rc, properties=None, reasonCode=None):
        self.logger.info("Déconnecté du serveur MQTT")

    def on_mqtt_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            if not isinstance(payload, dict) or 'number' not in payload or 'message' not in payload:
                self.logger.error(f"Format de payload invalide: {msg.payload.decode()}")
                return

            self.logger.info(f"Message reçu sur le topic '{msg.topic}': {payload}")
            if msg.topic == f"{self.mqtt_prefix}/send":
                number = payload['number']
                message = payload['message']
                self.send_sms(number, message)
        except json.JSONDecodeError as e:
            self.logger.error(f"Erreur de décodage JSON: {e}")
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement du message MQTT entrant sur le topic '{msg.topic}': {e}")

    async def process_sms_queue(self):
        if not self.sms_queue.empty():
            sms_request = self.sms_queue.get()
            number = sms_request.get('number')
            message = sms_request.get('message')
            if number and message:
                self.send_sms(number, message)

    async def check_and_publish_status_info(self):
        try:
            status_info = self.get_status_info()
            if status_info is not None:
                if status_info != self.old_status_info:
                    self.old_status_info = status_info
                    self.publish_status_info(status_info)
        except Exception as e:
            self.logger.error(f"Erreur lors de la vérification et de la publication des informations de statut : {e}")

    def get_status_info(self):
        try:
            self.get_session_token()  # Obtenir de nouveaux tokens avant la requête
            buffer = BytesIO()
            c = pycurl.Curl()
            c.setopt(c.URL, f"http://{self.huawei_router_ip}/api/monitoring/status")
            c.setopt(c.HTTPHEADER, [
                f"Cookie: {self.cookie}",
                f"__RequestVerificationToken: {self.token}",
            ])
            c.setopt(c.WRITEDATA, buffer)
            c.perform()
            c.close()

            response = buffer.getvalue().decode('utf-8')
            root = ET.fromstring(response)
            
            status_info = {}
            for element in root.iter():
                if element.tag != "response":
                    status_info[element.tag] = element.text

            return status_info
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des informations de statut : {e}")
            return None

    def publish_status_info(self, status_info):
        if status_info:
            self.mqtt_client.publish(f"{self.mqtt_prefix}/status", json.dumps(status_info), 0, True)
            self.logger.info(f"Nouvelles informations de statut publiées : ConnectionStatus={status_info.get('ConnectionStatus')}, SignalStrength={status_info.get('SignalIcon')}")

    async def get_signal_info(self):
        try:
            if time.time() - self.last_signal_check < self.signal_check_interval:
                return
            self.last_signal_check = time.time()

            self.get_session_token()  # Obtenir de nouveaux tokens avant la requête
            buffer = BytesIO()
            c = pycurl.Curl()
            c.setopt(c.URL, f"http://{self.huawei_router_ip}/api/device/signal")
            c.setopt(c.HTTPHEADER, [
                f"Cookie: {self.cookie}",
                f"__RequestVerificationToken: {self.token}",
            ])
            c.setopt(c.WRITEDATA, buffer)
            c.perform()
            c.close()

            response = buffer.getvalue().decode('utf-8')
            root = ET.fromstring(response)
            
            signal_info = {
                "rsrp": root.find(".//rsrp").text,
                "rsrq": root.find(".//rsrq").text,
                "rssi": root.find(".//rssi").text,
                "sinr": root.find(".//sinr").text,
                "cell_id": root.find(".//cell_id").text,
                "pci": root.find(".//pci").text,
                "ecio": root.find(".//ecio").text,
                "mode": root.find(".//mode").text,
            }

            if signal_info != self.old_signal_info:
                signal_payload = json.dumps(signal_info)
                self.mqtt_client.publish(f"{self.mqtt_prefix}/signal", signal_payload)
                self.old_signal_info = signal_info
                self.logger.info(f"Nouvelles informations de signal publiées : RSRP={signal_info['rsrp']}, RSRQ={signal_info['rsrq']}")
            else:
                self.logger.debug("Pas de changement dans les informations de signal")

        except Exception as e:
            self.logger.error(f"ERROR: Impossible de vérifier la qualité du signal : {e}")

    async def get_network_info(self):
        try:
            if time.time() - self.last_network_check < self.network_check_interval:
                return
            self.last_network_check = time.time()

            self.get_session_token()  # Obtenir de nouveaux tokens avant la requête
            buffer = BytesIO()
            c = pycurl.Curl()
            c.setopt(c.URL, f"http://{self.huawei_router_ip}/api/device/information")
            c.setopt(c.HTTPHEADER, [
                f"Cookie: {self.cookie}",
                f"__RequestVerificationToken: {self.token}",
            ])
            c.setopt(c.WRITEDATA, buffer)
            c.perform()
            c.close()

            response = buffer.getvalue().decode('utf-8')
            root = ET.fromstring(response)
            
            network_info = {}
            for element in root.iter():
                if element.tag != "response":
                    network_info[element.tag] = element.text

            if network_info != self.old_network_info:
                network_payload = json.dumps(network_info)
                self.mqtt_client.publish(f"{self.mqtt_prefix}/network", network_payload)
                self.old_network_info = network_info
                self.logger.info(f"Nouvelles informations réseau publiées : DeviceName={network_info['DeviceName']}, workmode={network_info['workmode']}, Mccmnc={network_info['Mccmnc']}, uptime={network_info['uptime']}")
            else:
                self.logger.debug("Pas de changement dans les informations réseau")

        except Exception as e:
            self.logger.error(f"ERROR: Impossible de vérifier les informations réseau : {e}")

    async def get_datetime(self):
        # Implémentez cette méthode si nécessaire
        pass

    async def main_loop(self):
        try:
            while self.running:
                current_time = time.time()
                # Traitement de la file d'attente SMS
                await self.process_sms_queue()
                # Vérification et publication du statut
                if current_time - self.last_status_check >= self.status_check_interval:
                    await self.check_and_publish_status_info()
                    self.last_status_check = current_time
                # Vérification et publication des informations de signal
                if current_time - self.last_signal_check >= self.signal_check_interval:
                    await self.get_signal_info()
                    self.last_signal_check = current_time
                # Vérification et publication des informations réseau
                if current_time - self.last_network_check >= self.network_check_interval:
                    await self.get_network_info()
                    self.last_network_check = current_time
                await self.check_and_publish_received_sms()
                # Petite pause pour éviter une utilisation excessive du CPU
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            self.logger.info("Boucle principale annulée")

    def run(self):
        self.logger.info("Démarrage du bridge")
        try:
            self.get_session_token()
            self.logger.info("Tokens de session obtenus")

            self.mqtt_client = mqtt.Client(client_id=self.mqtt_client_id)
            self.mqtt_client.username_pw_set(self.mqtt_user, self.mqtt_password)
            self.mqtt_client.on_connect = self.on_mqtt_connect
            self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
            self.mqtt_client.message_callback_add(f"{self.mqtt_prefix}/send", self.on_mqtt_message)
            self.logger.info("Tentative de connexion MQTT")
            self.mqtt_client.connect(self.mqtt_host, self.mqtt_port)
            self.mqtt_client.loop_start()
            self.logger.info("Boucle MQTT démarrée")

            self.loop = asyncio.get_event_loop()
            self.loop.add_signal_handler(signal.SIGINT, self.signal_handler)
            self.loop.add_signal_handler(signal.SIGTERM, self.signal_handler)
            self.logger.info("Démarrage de la boucle principale")
            self.loop.run_until_complete(self.main_loop())
        except Exception as e:
            self.logger.error(f"Erreur dans la méthode run : {e}")
        finally:
            self.force_shutdown()

    def signal_handler(self):
        self.logger.info("Signal reçu, arrêt en cours...")
        self.running = False
        for task in asyncio.all_tasks(self.loop):
            task.cancel()

    def force_shutdown(self):
        self.logger.info("Forçage de l'arrêt...")
        if self.mqtt_client:
            self.mqtt_client.publish(f"{self.mqtt_prefix}/connected", "0", 0, True)
            self.mqtt_client.disconnect()
            self.mqtt_client.loop_stop()
        if self.loop:
            self.loop.stop()
        self.logger.info("Arrêt terminé")

    async def shutdown(self):
        if not self.running:
            return
        self.logger.info("Arrêt gracieux...")
        self.running = False
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        [task.cancel() for task in tasks]
        await asyncio.gather(*tasks, return_exceptions=True)

if __name__ == "__main__":
    bridge = HuaweiSMSMQTTBridge()
    bridge.run()
