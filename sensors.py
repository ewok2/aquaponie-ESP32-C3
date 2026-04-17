import machine, onewire, ds18x20, dht, time
import struct
from utils import logPrint, interpolate2D, interpolate3D, paris_time


def dht22Get(socketMessage, serialConnect, pin_dht):
    dht22 = dht.DHT22(machine.Pin(pin_dht))
    dht22.measure()
    socketMessage["dht22AquaTemp"]  = dht22.temperature()
    socketMessage["dht22AquaHum"]   = dht22.humidity()
    socketMessage["dht22AquaValid"] = 1
    logPrint("Temperature air : %4.1f C ; Humidity : %4.1f %%" % (
        socketMessage["dht22AquaTemp"], socketMessage["dht22AquaHum"]), serialConnect)


def tempWaterGet(socketMessage, serialConnect, pin_thermo):
    waterPin = machine.Pin(pin_thermo)
    waterSensor = ds18x20.DS18X20(onewire.OneWire(waterPin))
    if waterSensor.scan() == []:
        raise OSError("no DS18X20 device found")
    waterSensor.convert_temp()
    time.sleep_ms(750)
    socketMessage["waterAquaTemp"]  = waterSensor.read_temp(b'(\xff,R\xc0\x17\x01\xc1')
    socketMessage["waterAquaValid"] = 1
    logPrint("Temperature eau : %4.1f C" % socketMessage["waterAquaTemp"], serialConnect)


def read_adc(ch, pin_scl, pin_sda):
    i2c = machine.I2C(0, scl=machine.Pin(pin_scl), sda=machine.Pin(pin_sda))
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


def lire_tensions(socketMessage, serialConnect, pin_scl, pin_sda):
    v0 = read_adc(0, pin_scl, pin_sda) * 2.0
    v1 = read_adc(1, pin_scl, pin_sda) * 9.33333
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


def computeTimeAndPump(socketMessage, serialConnect, timeTable, monthTable, sleepTable, pumpTable):
    t         = paris_time()
    timeOfDay = t[3] + t[4] / 60
    month     = t[1]
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


def pumpLogic(socketMessage, serialConnect, pin_pump, pumpTime, pumpDuration, timeOfDay, rtc):
    pump = machine.Pin(pin_pump, machine.Pin.OUT)
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
