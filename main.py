import machine
import time
from sensor import (flash_led, connect_wifi, disconnect_wifi, logPrint,
                    dht22Get, tempWaterGet, pumpLogic, pushToSocket,
                    lire_tensions, update_boot_counter, capacityGet,
                    safe_call, errorNumSet, computeTimeAndPump)
from secrets import secrets

led_out_green = machine.Pin(0, machine.Pin.OUT)
led_out_red   = machine.Pin(1, machine.Pin.OUT)

socketMessage = {}
socketMessage["aquaErrorNum"]    = 0
socketMessage["aquaPumpVal"]     = 0
socketMessage["aquaPumpTime"]    = 0
socketMessage["dht22AquaTemp"]   = 0
socketMessage["dht22AquaValid"]  = 0
socketMessage["waterAquaValid"]  = 0
socketMessage["aquaBatt1Valid"]  = 0
socketMessage["aquaSolar1Valid"] = 0

monthTable = [1, 4, 7, 10, 12]
timeTable  = [0, 6, 9, 12, 15, 18, 24]

sleepTable = [[30, 22, 30, 22, 30],
              [22, 15, 20, 15, 22],
              [15, 10,  5, 10, 15],
              [ 7,  5,  5,  5,  7],
              [15, 10,  5, 10, 15],
              [22, 15, 10, 15, 22],
              [30, 22, 15, 22, 30]]

pumpTable = [1,  3,  4,  3,  1]

pumpDuration  = 120
deepSleepTime = 15
timeOfDay     = 0
pumpTime      = []
rtc = machine.RTC()
serialConnect = True

ERR_WIFI     = 6
ERR_DHT22    = 7
ERR_WATER    = 8
ERR_TENSION  = 9
ERR_CAPACITY = 10
ERR_INTERP   = 11
ERR_PUMP     = 12
ERR_PUSH     = 13
ERR_DISC     = 14

boot_count = update_boot_counter(rtc)
socketMessage["aquaBootCount"] = boot_count
logPrint("Script start", serialConnect)
flash_led(3, led_out_green)

wlan = safe_call(connect_wifi,   ERR_WIFI,     socketMessage, serialConnect, serialConnect)
safe_call(dht22Get,              ERR_DHT22,    socketMessage, serialConnect, socketMessage, serialConnect)
safe_call(tempWaterGet,          ERR_WATER,    socketMessage, serialConnect, socketMessage, serialConnect)
safe_call(lire_tensions,         ERR_TENSION,  socketMessage, serialConnect, socketMessage, serialConnect)
safe_call(capacityGet,           ERR_CAPACITY, socketMessage, serialConnect, socketMessage, serialConnect)

result = safe_call(computeTimeAndPump, ERR_INTERP, socketMessage, serialConnect,
                   socketMessage, serialConnect, timeTable, monthTable, sleepTable, pumpTable)
if result is not None:
    deepSleepTime, timeOfDay, pumpTime = result

safe_call(pumpLogic,       ERR_PUMP, socketMessage, serialConnect,
          socketMessage, pumpTime, pumpDuration, timeOfDay, rtc, serialConnect)
safe_call(pushToSocket,    ERR_PUSH, socketMessage, serialConnect, socketMessage, serialConnect)
safe_call(disconnect_wifi, ERR_DISC, socketMessage, serialConnect, wlan, serialConnect)

logPrint("Going to sleep for : %s min" % deepSleepTime, serialConnect)
flash_led(3, led_out_red)

machine.deepsleep(int(deepSleepTime * 60 * 1_000))

