import network, socket, ntptime
import machine, onewire, ds18x20, dht, time
from secrets import secrets
import struct

PIN_DHT = 6
PIN_THERMO = 7
PIN_PUMP = 5
PIN_SCL = 21
PIN_SDA = 20


def flash_led(nb, led):
    for i in range(nb):
        led.toggle()
        time.sleep_ms(1)
        led.toggle()
        time.sleep_ms(199)
    led.off()


def logPrint(log, serialConnect=False):
    if serialConnect:
        print(log)


def safe_call(func, error_code, socketMessage, serialConnect, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception as e:
        logPrint('safe_call [err=%d] %s: %s' % (error_code, func.__name__, str(e)), serialConnect)
        socketMessage["aquaErrorNum"] = errorNumSet(error_code, socketMessage["aquaErrorNum"], serialConnect)
        return None


def errorNumSet(number, errorVal, serialConnect):
    prev = errorVal
    errorVal = errorVal | (1 << number)
    if prev != errorVal:
        logPrint('errorVal: %s -> %s' % (prev, errorVal), serialConnect)
    return errorVal


def errorNumReset(number, errorVal, serialConnect):
    prev = errorVal
    errorVal = errorVal & ~(1 << number)
    if prev != errorVal:
        logPrint('errorVal: %s -> %s' % (prev, errorVal), serialConnect)
    return errorVal


def connect_wifi(serialConnect):
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
    ntptime.host = "192.168.75.1"
    ntptime.settime()
    logPrint("NTP synchronise", serialConnect)
    return wlan


def disconnect_wifi(wlan, serialConnect):
    if wlan is None:
        return
    wlan.disconnect()
    time.sleep_ms(100)
    wlan.active(False)
    logPrint("Deconnexion du Wifi", serialConnect)
    time.sleep_ms(100)


def dht22Get(socketMessage, serialConnect):
    dht22 = dht.DHT22(machine.Pin(PIN_DHT))
    dht22.measure()
    socketMessage["dht22AquaTemp"]  = dht22.temperature()
    socketMessage["dht22AquaHum"]   = dht22.humidity()
    socketMessage["dht22AquaValid"] = 1
    logPrint("Temperature air : %4.1f C ; Humidity : %4.1f %%" % (
        socketMessage["dht22AquaTemp"], socketMessage["dht22AquaHum"]), serialConnect)


def tempWaterGet(socketMessage, serialConnect):
    waterPin = machine.Pin(PIN_THERMO)
    waterSensor = ds18x20.DS18X20(onewire.OneWire(waterPin))
    if waterSensor.scan() == []:
        raise OSError("no DS18X20 device found")
    waterSensor.convert_temp()
    time.sleep_ms(750)
    socketMessage["waterAquaTemp"]  = waterSensor.read_temp(b'(\xff,R\xc0\x17\x01\xc1')
    socketMessage["waterAquaValid"] = 1
    logPrint("Temperature eau : %4.1f C" % socketMessage["waterAquaTemp"], serialConnect)


def interpolate3D(x_points, y_points, z_table, x_val, y_val, serialConnect):
    nx = len(x_points)
    index_x = nx - 2
    for i in range(nx - 1):
        if x_points[i] <= x_val <= x_points[i + 1]:
            index_x = i
            break
    ny = len(y_points)
    index_y = ny - 2
    for i in range(ny - 1):
        if y_points[i] <= y_val <= y_points[i + 1]:
            index_y = i
            break
    x0, x1 = x_points[index_x], x_points[index_x + 1]
    y0, y1 = y_points[index_y], y_points[index_y + 1]
    z00 = z_table[index_x][index_y]
    z10 = z_table[index_x + 1][index_y]
    z01 = z_table[index_x][index_y + 1]
    z11 = z_table[index_x + 1][index_y + 1]
    return (z00 * (x1 - x_val) * (y1 - y_val) +
            z10 * (x_val - x0) * (y1 - y_val) +
            z01 * (x1 - x_val) * (y_val - y0) +
            z11 * (x_val - x0) * (y_val - y0)) / ((x1 - x0) * (y1 - y0))


def interpolate2D(x, colonne_x, colonne_y):
    n = len(colonne_x)
    ascending = colonne_x[-1] > colonne_x[0]
    if ascending:
        if x <= colonne_x[0]:
            return colonne_y[0]
        if x >= colonne_x[-1]:
            return colonne_y[-1]
        for i in range(n - 1):
            if colonne_x[i] <= x <= colonne_x[i + 1]:
                t = (x - colonne_x[i]) / (colonne_x[i + 1] - colonne_x[i])
                return colonne_y[i] + t * (colonne_y[i + 1] - colonne_y[i])
    else:
        if x >= colonne_x[0]:
            return colonne_y[0]
        if x <= colonne_x[-1]:
            return colonne_y[-1]
        for i in range(n - 1):
            if colonne_x[i + 1] <= x <= colonne_x[i]:
                t = (x - colonne_x[i]) / (colonne_x[i + 1] - colonne_x[i])
                return colonne_y[i] + t * (colonne_y[i + 1] - colonne_y[i])
    return colonne_y[-1]


def computeTimeAndPump(socketMessage, serialConnect, timeTable, monthTable, sleepTable, pumpTable):
    timeOfDay = time.gmtime()[3] + time.gmtime()[4] / 60
    month     = time.gmtime()[1]
    socketMessage["timeOfDay"] = timeOfDay
    socketMessage["month"]     = month

    deepSleepTime = int(interpolate3D(timeTable, monthTable, sleepTable, timeOfDay, month, serialConnect))
    pumpTimeNb    = int(round(interpolate2D(month, monthTable, pumpTable)))

    if socketMessage["dht22AquaTemp"] <= 2.0:
        pumpTimeNb = 0

    logPrint("deepSleepTime : %s" % deepSleepTime, serialConnect)
    logPrint("pumpTimeNb : %s" % pumpTimeNb, serialConnect)

    if pumpTimeNb == 4:
        pumpTime = [10, 12, 14, 16]
    elif pumpTimeNb == 3:
        pumpTime = [10, 12, 14]
    elif pumpTimeNb == 2:
        pumpTime = [12, 14]
    elif pumpTimeNb == 1:
        pumpTime = [12]
    else:
        pumpTime = []

    socketMessage["aquaSleepTime"] = deepSleepTime
    socketMessage["aquaPumpNb"]    = pumpTimeNb
    return deepSleepTime, timeOfDay, pumpTime


def pumpLogic(socketMessage, pumpTime, pumpDuration, timeOfDay, rtc, serialConnect):
    pump = machine.Pin(PIN_PUMP, machine.Pin.OUT)
    pump.value(0)

    heures  = int(timeOfDay)
    minutes = round((timeOfDay - heures) * 60)
    logPrint('current time is : %i:%02i' % (heures, minutes), serialConnect)

    flag = load_flag(rtc)

    if heures in pumpTime:
        if not flag:
            socketMessage["aquaPumpTime"] = timeOfDay
            socketMessage["aquaPumpVal"]  = pumpDuration
            pumpActivation = True
            save_flag(rtc, True)
        else:
            pumpActivation = False
            socketMessage["aquaPumpVal"] = 0
    else:
        socketMessage["aquaPumpVal"] = 0
        pumpActivation = False
        save_flag(rtc, False)

    if pumpActivation:
        pump.value(1)
        logPrint('pump Running', serialConnect)
        try:
            time.sleep(pumpDuration)
        finally:
            pump.value(0)
            logPrint('pump Stop', serialConnect)


def pushToSocket(socketMessage, serialConnect):
    hostname = '192.168.75.20'
    portnum  = 11222
    homeSocket = socket.socket()
    homeSocket.settimeout(10)
    homeSocket.connect((hostname, portnum))
    homeSocket.send(str(socketMessage).encode())
    logPrint("Message sent : %s" % str(socketMessage), serialConnect)
    homeSocket.close()


def capacityGet(socketMessage, serialConnect):
    if "aquaVoltBatt1" not in socketMessage:
        logPrint('capacityGet: aquaVoltBatt1 absent', serialConnect)
        return
    x1 = float(socketMessage["aquaVoltBatt1"])
    colonne_x = [4.15, 4.03, 3.93, 3.83, 3.74, 3.66, 3.62, 3.58, 3.55, 3.48, 3.4, 2.8]
    colonne_y = [ 100,   90,   81,   71,   62,   52,   42,   33,   23,   13,   4,   0]
    y1 = interpolate2D(x1, colonne_x, colonne_y)
    socketMessage["aquaCapaBatt1"] = y1
    logPrint('Battery1 capacity : %i%%' % y1, serialConnect)


def read_adc(ch):
    i2c = machine.I2C(0, scl=machine.Pin(PIN_SCL), sda=machine.Pin(PIN_SDA))
    MCP3426_ADDR = 0x68
    if ch == 0:
        ch_bits = 0b00 << 5
    elif ch == 1:
        ch_bits = 0b01 << 5
    else:
        raise ValueError("canal 0 ou 1 uniquement")
    config = (1 << 7) | ch_bits | (1 << 4) | (0b00 << 2) | 0b00
    i2c.writeto(MCP3426_ADDR, bytes([config]))
    time.sleep_ms(200)
    for _ in range(3):
        raw = i2c.readfrom(MCP3426_ADDR, 3)
        time.sleep_ms(10)
    val = int.from_bytes(raw[0:2], 'big')
    if val > 2047:
        val -= 4096
    return val * 2.048 / 2048


def lire_tensions(socketMessage, serialConnect):
    v0 = read_adc(0) * 2.0
    v1 = read_adc(1) * 9.33333
    if 0 <= v0 <= 5:
        socketMessage["aquaVoltBatt1"]  = v0
        socketMessage["aquaBatt1Valid"] = 1
    else:
        socketMessage["aquaVoltBatt1"]  = 0
        socketMessage["aquaBatt1Valid"] = 0
    if 0 <= v1 <= 25:
        socketMessage["aquaVoltSolar1"]  = v1
        socketMessage["aquaSolar1Valid"] = 1
    else:
        socketMessage["aquaVoltSolar1"]  = 0
        socketMessage["aquaSolar1Valid"] = 0
    logPrint("Batt1 : %4.1f V ; Solar1 : %4.1f V" % (v0, v1), serialConnect)


def update_boot_counter(rtc):
    data = rtc.memory()
    if data and len(data) >= 5:
        counter, flag = struct.unpack("IB", data)
    else:
        counter = 0
        flag    = 0
    counter += 1
    rtc.memory(struct.pack("IB", counter, flag))
    return counter


def save_flag(rtc, value):
    data = rtc.memory()
    if data and len(data) >= 5:
        counter, _ = struct.unpack("IB", data)
    else:
        counter = 0
    rtc.memory(struct.pack("IB", counter, 1 if value else 0))


def load_flag(rtc):
    data = rtc.memory()
    if data and len(data) >= 5:
        _, flag = struct.unpack("IB", data)
        return bool(flag)
    return None
