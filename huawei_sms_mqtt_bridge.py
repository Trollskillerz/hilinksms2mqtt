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
from typing import Dict, Any
import asyncio
import aiohttp

class ConnectionLostError(Exception):
    pass

class HuaweiSMSMQTTBridge:
    def __init__(self):
        self.load_config()
        self.setup_logging()
        self.running = True
        self.old_signal_info: Dict[str, Any] = {}
        self.last_signal_check = 0
        self.old_network_info: Dict[str, Any] = {}
        self.old_time = 0
        self.huawei_client = None
        self.mqtt_client = None
        self.loop = None

    def load_config(self):
        load_dotenv()
        self.mqtt_prefix = os.getenv("MQTT_TOPIC")
        self.mqtt_host = os.getenv("MQTT_IP")
        self.mqtt_port = int(os.getenv("PORT", 1883))
        self.mqtt_client_id = os.getenv("CLIENTID")
        self.mqtt_user = os.getenv("MQTT_ACCOUNT")
        self.mqtt_password = os.getenv("MQTT_PASSWORD")
        self.huawei_router_ip = os.getenv("HUAWEI_ROUTER_IP_ADDRESS")
        self.delay_second = int(os.getenv("DELAY_SECOND", 10))
        self.signal_check_interval = int(os.getenv("SIGNAL_CHECK_INTERVAL", 60))

    def setup_logging(self):
        logging.basicConfig(
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            level=logging.INFO,
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        self.logger = logging.getLogger("HuaweiSMSMQTTBridge")

    async def initialize_huawei_client(self):
        url = f'http://{self.huawei_router_ip}/'
        for attempt in range(5):
            try:
                self.logger.info(f"Connecting to Huawei LTE API at {url}")
                connection = AuthorizedConnection(url)
                self.huawei_client = Client(connection)
                return
            except Exception as e:
                self.logger.error(f'Attempt {attempt + 1} failed to connect to Huawei LTE API: {e}')
                await asyncio.sleep(5)
        self.logger.error('All attempts to initialize Huawei LTE API client failed.')
        raise Exception("Failed to initialize Huawei LTE API client")

    async def check_connection(self):
        try:
            await asyncio.wait_for(asyncio.to_thread(self.huawei_client.device.information), timeout=10)
        except (asyncio.TimeoutError, Exception) as e:
            self.logger.error(f"Connection to Huawei router lost: {e}")
            raise ConnectionLostError("Connection to Huawei router lost")

    def on_mqtt_connect(self, client, userdata, flags, rc, properties=None):
        self.logger.info("Connected to MQTT host")
        client.publish(f"{self.mqtt_prefix}/connected", "1", 0, True)
        client.subscribe(f"{self.mqtt_prefix}/send")

    def on_mqtt_disconnect(self, client, userdata, rc, properties=None, reasonCode=None):
        self.logger.info("Disconnected from MQTT host")
        self.shutdown()

    def on_mqtt_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            if not isinstance(payload, dict) or 'number' not in payload or 'message' not in payload:
                self.logger.error(f"Invalid payload format: {msg.payload.decode()}")
                return

            self.logger.info(f"Received message on topic '{msg.topic}': {payload}")
            if msg.topic == f"{self.mqtt_prefix}/send":
                self.logger.info(f"Processing SMS send request: {payload}")
                asyncio.run_coroutine_threadsafe(self.send_sms(payload), self.loop)
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decoding error: {e}")
        except Exception as e:
            self.logger.error(f"Error processing incoming MQTT message on topic '{msg.topic}': {e}")

    async def get_and_publish_sms(self):
        try:
            await self.check_connection()
            sms_list = self.huawei_client.sms.get_sms_list(1, BoxTypeEnum.LOCAL_INBOX, 1, 0, 0, 1)
            messages = sms_list.get('Messages', {}).get('Message', [])
            if not messages:
                self.logger.info("No new SMS.")
                return

            if isinstance(messages, dict):
                messages = [messages]

            for message in messages:
                if int(message.get('Smstat', 1)) == 1:
                    self.logger.info(f"No new SMS to read: {message.get('Index')}")
                    continue

                payload = json.dumps({
                    "datetime": message.get('Date'),
                    "number": message.get('Phone'),
                    "text": message.get('Content')
                }, ensure_ascii=False)
                self.mqtt_client.publish(f"{self.mqtt_prefix}/received", payload)
                self.logger.info(f"SMS published: {payload}")
                self.huawei_client.sms.set_read(int(message.get('Index')))
        except ConnectionLostError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to retrieve SMS: {e}")
            await self.reset_huawei_connection()

    async def get_signal_info(self):
        try:
            await self.check_connection()
            if time.time() - self.last_signal_check < self.signal_check_interval:
                return
            self.last_signal_check = time.time()
            signal_info = self.huawei_client.device.signal()
            if not isinstance(signal_info, dict):
                raise ValueError("Invalid signal info format")
            
            if signal_info != self.old_signal_info:
                signal_payload = json.dumps(signal_info)
                self.mqtt_client.publish(f"{self.mqtt_prefix}/signal", signal_payload)
                self.old_signal_info = signal_info
        except ConnectionLostError:
            raise
        except Exception as e:
            self.logger.error(f"ERROR: Unable to check signal quality: {e}")
            await self.reset_huawei_connection()

    async def get_network_info(self):
        try:
            await self.check_connection()
            network_info = self.huawei_client.device.information()
            if not isinstance(network_info, dict):
                raise ValueError("Invalid network info format")
            
            if network_info != self.old_network_info:
                network_payload = json.dumps(network_info)
                self.mqtt_client.publish(f"{self.mqtt_prefix}/network", network_payload)
                self.old_network_info = network_info
        except ConnectionLostError:
            raise
        except Exception as e:
            self.logger.error(f"ERROR: Unable to check network info: {e}")
            await self.reset_huawei_connection()

    async def get_datetime(self):
        try:
            now = time.time()
            if (now - self.old_time) > 60:
                self.mqtt_client.publish(f"{self.mqtt_prefix}/datetime", now)
                self.old_time = now
        except Exception as e:
            self.logger.error(f"ERROR: Unable to check datetime: {e}")

    def shutdown(self, signum=None, frame=None):
        if self.running:
            self.logger.info("Shutting down gracefully...")
            self.running = False
            if self.loop and self.loop.is_running():
                self.loop.create_task(self.force_shutdown())

    async def force_shutdown(self):
        self.logger.info("Forcing shutdown...")
        self.running = False
        if self.mqtt_client:
            self.mqtt_client.publish(f"{self.mqtt_prefix}/connected", "0", 0, True)
            self.mqtt_client.disconnect()
        if self.loop:
            for task in asyncio.all_tasks(self.loop):
                if task is not asyncio.current_task():
                    task.cancel()
        # Arrêter le script
        os._exit(0)

    async def send_sms(self, payload):
        try:
            await self.check_connection()
            number = payload.get('number')
            message = payload.get('message')
            
            if not number or not message:
                self.logger.error("Invalid payload, 'number' or 'message' missing.")
                return

            response = self.huawei_client.sms.send_sms([number], message)
            if response == ResponseEnum.OK.value:
                self.logger.info(f"SMS sent to {number}: {message}")
                self.mqtt_client.publish(f"{self.mqtt_prefix}/sent", json.dumps({
                    "status": "sent",
                    "number": number,
                    "message": message
                }))
            else:
                self.logger.error(f"Failed to send SMS. Response code: {response}")
        except ConnectionLostError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to send SMS: {e}")
            await self.reset_huawei_connection()

    async def reset_huawei_connection(self):
        self.logger.info("Resetting Huawei connection...")
        try:
            await self.initialize_huawei_client()
        except Exception:
            self.logger.error("Failed to reset Huawei connection. Shutting down...")
            await self.force_shutdown()

    async def run(self):
        self.loop = asyncio.get_running_loop()
        try:
            await self.initialize_huawei_client()
        except Exception:
            self.logger.error("Failed to initialize Huawei client. Exiting...")
            return

        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.mqtt_client_id)
        self.mqtt_client.username_pw_set(self.mqtt_user, self.mqtt_password)
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
        self.mqtt_client.message_callback_add(f"{self.mqtt_prefix}/send", self.on_mqtt_message)
        self.mqtt_client.connect(self.mqtt_host, self.mqtt_port)
        self.mqtt_client.loop_start()

        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

        try:
            while self.running:
                try:
                    await asyncio.gather(
                        self.get_and_publish_sms(),
                        self.get_signal_info(),
                        self.get_network_info(),
                        self.get_datetime()
                    )
                    await asyncio.sleep(self.delay_second)
                except ConnectionLostError:
                    self.logger.error("Connection lost. Shutting down...")
                    break
                except asyncio.CancelledError:
                    self.logger.info("Tasks cancelled")
                    break
                except Exception as e:
                    self.logger.error(f"Error in main loop: {e}")
                    await asyncio.sleep(5)  # Attendre un peu avant de réessayer
        except asyncio.CancelledError:
            self.logger.info("Main loop cancelled")
        except Exception as e:
            self.logger.error(f"Unexpected error in main loop: {e}")
        finally:
            self.mqtt_client.loop_stop()
            await self.force_shutdown()

if __name__ == "__main__":
    bridge = HuaweiSMSMQTTBridge()
    asyncio.run(bridge.run())
    
