import datetime
import time


def current():
    return time.strftime('%Y-%m-%d', time.localtime(time.time()))


def is_valid(date_text):
    try:
        datetime.datetime.strptime(date_text, '%Y-%m-%d')
        return True
    except (ValueError, TypeError):
        return False


def str_time_prop(start, end, time_format, prop):
    stime = time.mktime(time.strptime(start, time_format))
    etime = time.mktime(time.strptime(end, time_format))
    ptime = stime + prop * (etime - stime)
    return time.strftime(time_format, time.localtime(ptime))


def random(start, end, prop):
    return str_time_prop(start, end, '%Y-%m-%d', prop)


def next_year(date):
    ptime = time.mktime(time.strptime(date, '%Y-%m-%d'))
    ptime += 31536000
    return time.strftime('%Y-%m-%d', time.localtime(ptime))


def back_in_months(months):
    ptime = time.time()
    ptime -= months * 2678400
    return time.strftime('%Y-%m-%d', time.localtime(ptime))
