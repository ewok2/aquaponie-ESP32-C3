import time


def paris_time():
    t = time.gmtime()
    y, mo, d, h, mi, s = t[0], t[1], t[2], t[3], t[4], t[5]

    def _weekday(y, m, d):
        tab = [0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4]
        if m < 3:
            y -= 1
        return (y + y//4 - y//100 + y//400 + tab[m-1] + d) % 7  # 0=Sunday

    def _last_sunday(y, m):
        dims = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        if m == 2 and (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)):
            dims[2] = 29
        last = dims[m]
        return last - _weekday(y, m, last)

    dst_start = _last_sunday(y, 3)
    dst_end   = _last_sunday(y, 10)

    if mo > 3 and mo < 10:
        in_dst = True
    elif mo == 3:
        in_dst = d > dst_start or (d == dst_start and h >= 2)
    elif mo == 10:
        in_dst = not (d > dst_end or (d == dst_end and h >= 1))
    else:
        in_dst = False

    h += 2 if in_dst else 1
    if h >= 24:
        h -= 24
    return (y, mo, d, h, mi, s, t[6], t[7])


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
        return func(socketMessage, serialConnect, *args, **kwargs)
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
