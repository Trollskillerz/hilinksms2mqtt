import logging
import time
import os
import signal
import json
import asyncio
import pycurl
import html
import urllib.parse
import threading
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
        self.check_interval = 60  # 60 secondes entre chaque vérification
        self.sms_check_interval = 30  # 30 secondes entre chaque vérification des SMS
        self.last_status_check = 0
        self.last_signal_check = 0
        self.last_network_check = 0
        self.last_sms_check = 0
        self.old_status_info = {}        
        self.old_signal_info = {}
        self.old_network_info = {}
        self.loop = None
        self.router_connected = True
        self.router_check_interval = 30  # Vérifier la connexion du routeur toutes les 30 secondes
        self.last_router_check = 0
        
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
        self.check_interval = int(self.get_env("CHECK_INTERVAL", "60"))
        self.sms_check_interval = int(self.get_env("SMS_CHECK_INTERVAL", "30"))
        self.debug_level = os.environ.get("DEBUG_LEVEL", "INFO").upper()
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.debug_level not in valid_levels:
            raise ValueError(f"Niveau de debug invalide : {self.debug_level}. Les valeurs valides sont : {', '.join(valid_levels)}")

    async def check_router_connection(self):
        failed_attempts = 0
        max_failed_attempts = 3  # Nombre maximal de tentatives avant l'arrêt

        while self.running:
            try:
                self.get_session_token()
                if not self.router_connected:
                    self.logger.info("Connexion au routeur rétablie")
                    self.router_connected = True
                    failed_attempts = 0  # Réinitialiser le compteur
                    self.mqtt_client.publish(f"{self.mqtt_prefix}/router_status", "connected", retain=True)
                await asyncio.sleep(self.router_check_interval)
            except asyncio.CancelledError:
                self.logger.info("Tâche de vérification de la connexion du routeur annulée")
                break
            except Exception as e:
                self.logger.error(f"Erreur de connexion au routeur : {e}")
                self.router_connected = False
                failed_attempts += 1
                self.mqtt_client.publish(f"{self.mqtt_prefix}/router_status", "disconnected", retain=True)
                
                if failed_attempts >= max_failed_attempts:
                    self.logger.critical(f"Échec de connexion au routeur après {max_failed_attempts} tentatives. Arrêt du script.")
                    self.running = False
                    break
                
                await asyncio.sleep(self.router_check_interval)

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

    def encode_sms_content(self, content):
        # Encode le contenu en UTF-8, puis le convertit en une chaîne URL-encodée
        return content.encode('utf-8')

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
        
        # S'assurer que le contenu est une chaîne de caractères
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        
        # Encoder le contenu en UTF-8
        encoded_content = html.escape(content).encode('utf-8')
        
        data = f"""<?xml version='1.0' encoding='UTF-8'?><request><Index>-1</Index><Phones><Phone>{phone}</Phone></Phones><Sca></Sca><Content>{content}</Content><Length>{len(encoded_content)}</Length><Reserved>1</Reserved><Date>-1</Date></request>"""
        c.setopt(c.POSTFIELDS, data.encode('utf-8'))
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

    def on_mqtt_message(self, client, userdata, message):
        try:
            payload_str = message.payload.decode('utf-8')
            self.logger.info(f"Message reçu sur le topic '{message.topic}': {payload_str}")
            payload = json.loads(payload_str)
            number = payload.get('number')
            text = payload.get('message')
            
            if number and text:
                encoded_text = self.encode_sms_content(text)
                self.send_sms(number, encoded_text)
            else:
                self.logger.warning("Message MQTT reçu sans numéro ou texte valide")
        except json.JSONDecodeError:
            self.logger.error(f"Erreur de décodage JSON pour le message reçu sur '{message.topic}'")
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement du message MQTT entrant sur le topic '{message.topic}': {str(e)}")
    
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
            if time.time() - self.last_signal_check < self.check_interval:
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
            if time.time() - self.last_network_check < self.check_interval:
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

    async def main_loop(self):
        try:
            while self.running:
                current_time = time.time()
                # Vérification et publication du statut
                if current_time - self.last_status_check >= self.check_interval:
                    await self.check_and_publish_status_info()
                    self.last_status_check = current_time
                # Vérification et publication des informations de signal
                if current_time - self.last_signal_check >= self.check_interval:
                    await self.get_signal_info()
                    self.last_signal_check = current_time
                # Vérification et publication des informations réseau
                if current_time - self.last_network_check >= self.check_interval:
                    await self.get_network_info()
                    self.last_network_check = current_time
                # Vérification et publication des SMS reçus
                if current_time - self.last_sms_check >= self.sms_check_interval:
                    await self.check_and_publish_received_sms()
                    self.last_sms_check = current_time
                # Petite pause pour éviter une utilisation excessive du CPU
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            self.logger.info("Boucle principale annulée")
        except Exception as e:
            self.logger.error(f"Erreur dans la boucle principale : {e}")
            self.running = False

    def run(self):
        self.loop = asyncio.get_event_loop()
        self.loop.add_signal_handler(signal.SIGINT, self.signal_handler)
        self.loop.add_signal_handler(signal.SIGTERM, self.signal_handler)
        self.logger.info("Démarrage du bridge")
        try:
            self.loop.run_until_complete(self.run_async())
        except KeyboardInterrupt:
            self.logger.info("Interruption clavier détectée")
        except Exception as e:
            self.logger.error(f"Erreur dans la boucle principale : {e}")
        finally:
            self.loop.run_until_complete(self.shutdown())
            self.loop.close()
            self.logger.info("Bridge arrêté")

    async def run_async(self):
        try:
            self.get_session_token()
            self.logger.info("Tokens de session obtenus")

            # Configuration MQTT
            self.mqtt_client = mqtt.Client(client_id=self.mqtt_client_id)
            self.mqtt_client.username_pw_set(self.mqtt_user, self.mqtt_password)
            self.mqtt_client.on_connect = self.on_mqtt_connect
            self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
            self.mqtt_client.message_callback_add(f"{self.mqtt_prefix}/send", self.on_mqtt_message)
            self.mqtt_client.will_set(f"{self.mqtt_prefix}/connected", "0", 0, True)            
            self.logger.info("Tentative de connexion MQTT")
            self.mqtt_client.connect(self.mqtt_host, self.mqtt_port)
            self.mqtt_client.loop_start()
            self.logger.info("Boucle MQTT démarrée")

            router_check_task = asyncio.create_task(self.check_router_connection())
            main_loop_task = asyncio.create_task(self.main_loop())

            self.logger.info("Démarrage de la boucle principale")
            done, pending = await asyncio.wait(
                [router_check_task, main_loop_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            for task in pending:
                task.cancel()

        except asyncio.CancelledError:
            self.logger.info("Tâches annulées")
        except Exception as e:
            self.logger.error(f"Erreur dans run_async : {e}")
        finally:
            self.running = False
            await self.shutdown()

    def signal_handler(self):
        self.logger.info("Signal reçu, arrêt en cours...")
        self.running = False
        if self.loop and self.loop.is_running():
            self.loop.create_task(self.shutdown())

    async def shutdown(self):
        if not self.running:
            return
        self.logger.info("Arrêt gracieux...")
        self.running = False
        
        # Annuler toutes les tâches en cours
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        
        # Attendre que toutes les tâches soient terminées
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Arrêter le client MQTT
        if self.mqtt_client:
            self.logger.info("Publication du statut déconnecté")
            self.mqtt_client.publish(f"{self.mqtt_prefix}/connected", "0", 0, True)
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        
        self.logger.info("Arrêt terminé")

if __name__ == "__main__":
    bridge = HuaweiSMSMQTTBridge()
    bridge.run()
