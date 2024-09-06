# hilinksms2mqtt
send receive sms by mqtt with huawei e3372h-320


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
