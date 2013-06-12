'''
Support for various EEG devices
Copyright (c) 2011 Marijn van Vliet
'''
import os,time
import ctypes
import logging


def precision_timer():
    # Even Python suffers under OS inconsistancies
    if os.name == 'posix':
        return time.time()
    else:
        ticks = ctypes.c_int64()
        freq = ctypes.c_int64()
        ctypes.windll.Kernel32.QueryPerformanceFrequency(ctypes.byref(freq))
        ctypes.windll.Kernel32.QueryPerformanceCounter(ctypes.byref(ticks))

        return float(ticks.value) / float(freq.value)

from recorder import Recorder
from recorder import Marker
from recorder import DeviceError
from emulator import Emulator
available_devices = {'emulator':Emulator}

device_errors = {}

try:
    from epoc_recorder import EPOC
    available_devices['epoc'] = EPOC
except ImportError as e:
    device_errors['epoc'] = e

try:
    import biosemi as bs
    from biosemi import BIOSEMI
    available_devices['biosemi'] = BIOSEMI
except ImportError as e:
    device_errors['biosemi'] = e

try:
    from imecbe import IMECBE
    available_devices['imec-be'] = IMECBE
except ImportError as e:
    device_errors['imec-be'] = e

try:
    from imecnl import IMECNL
    available_devices['imec-nl'] = IMECNL
except ImportError as e:
    device_errors['imec-nl'] = e

