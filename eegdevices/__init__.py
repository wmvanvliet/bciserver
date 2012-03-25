'''
Support for various EEG devices
Copyright (c) 2011 Marijn van Vliet
'''
import os,time
import ctypes


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
from imecbe import IMECBE
from imecnl import IMECNL
from biosemi import BIOSEMI
available_devices = {'emulator':Emulator,
                     'imec-be':IMECBE,
                     'imec-nl':IMECNL}

try:
    import epoc
    from epoc_recorder import EPOC
    available_devices['epoc'] = EPOC
except ImportError:
    pass # silently fail when EPOC is not available

try:
    import biosemi as bs
    from biosemi import BIOSEMI
    available_devices['biosemi'] = BIOSEMI

except ImportError:
    pass # silently fail when BIOSEMI is not available
