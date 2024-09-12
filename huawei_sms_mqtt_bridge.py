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

    def run(self):
        self.loop = asyncio.get_event_loop()
        self.loop.add_signal_handler(signal.SIGINT, self.signal_handler)
        self.loop.add_signal_handler(signal.SIGTERM, self.signal_handler)
        self.logger.info("Démarrage du bridge")
        try:
            self.loop.run_until_complete(self.run_async())
        except Exception as e:
            self.logger.error(f"Erreur dans la boucle principale : {e}")
        finally:
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
            self.logger.info("Tentative de connexion MQTT")
            self.mqtt_client.connect(self.mqtt_host, self.mqtt_port)
            self.mqtt_client.loop_start()
            self.logger.info("Boucle MQTT démarrée")

            # Démarrer la tâche de vérification de la connexion du routeur
            router_check_task = asyncio.create_task(self.check_router_connection())

            # Démarrer la boucle principale
            main_loop_task = asyncio.create_task(self.main_loop())

            self.logger.info("Démarrage de la boucle principale")
            # Attendre que l'une des tâches se termine
            await asyncio.wait([router_check_task, main_loop_task], return_when=asyncio.FIRST_COMPLETED)

        except Exception as e:
            self.logger.error(f"Erreur dans run_async : {e}")
        finally:
            await self.shutdown()

    def signal_handler(self):
        self.logger.info("Signal reçu, arrêt en cours...")
        self.running = False
        asyncio.create_task(self.shutdown())

    async def shutdown(self):
        self.logger.info("Arrêt gracieux...")
        if not self.running:
            return
        self.running = False
        
        # Annuler toutes les tâches en cours
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        [task.cancel() for task in tasks]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Arrêter le client MQTT
        if self.mqtt_client:
            self.mqtt_client.publish(f"{self.mqtt_prefix}/connected", "0", 0, True)
            self.mqtt_client.disconnect()
            self.mqtt_client.loop_stop()
        
        self.logger.info("Arrêt terminé")

if __name__ == "__main__":
    bridge = HuaweiSMSMQTTBridge()
    bridge.run()
