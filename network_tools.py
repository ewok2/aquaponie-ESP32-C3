import network, socket, ntptime
import time
from secrets import secrets
from utils import logPrint


def connect_wifi(socketMessage, serialConnect):
    SSID = secrets['ssid']
    PASSWORD = secrets['pw']
    network.hostname("esp32-C3-aqua")
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(SSID, PASSWORD)
        timeout = 10
        start = time.time()
        while not wlan.isconnected():
            if time.time() - start > timeout:
                logPrint("Connexion timeout.", serialConnect)
                break
            time.sleep(1)
    else:
        logPrint("Deja connecte a %s" % SSID, serialConnect)
    if wlan.isconnected():
        logPrint("Connecte ! IP : %s" % wlan.ifconfig()[0], serialConnect)
    else:
        logPrint("Non connecte", serialConnect)
        return None
    ntptime.host = secrets['ntp_host']
    ntptime.settime()
    logPrint("NTP synchronise", serialConnect)
    return wlan


def disconnect_wifi(socketMessage, serialConnect, wlan):
    if wlan is None:
        return
    wlan.disconnect()
    time.sleep_ms(100)
    wlan.active(False)
    logPrint("Deconnexion du Wifi", serialConnect)
    time.sleep_ms(100)


def pushToSocket(socketMessage, serialConnect):
    hostname = secrets['socket_host']
    portnum  = secrets['socket_port']
    homeSocket = socket.socket()
    homeSocket.settimeout(10)
    homeSocket.connect((hostname, portnum))
    homeSocket.send(str(socketMessage).encode())
    logPrint("Message sent : %s" % str(socketMessage), serialConnect)
    homeSocket.close()
