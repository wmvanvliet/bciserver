import logging
import numpy
import time
import array
import struct
import psychic

import usb.core

from . import Recorder, precision_timer, DeviceError, Marker
from background_reader import BackgroundReader

try:
    import wmi
    import _winreg as reg
    import ctypes
    lpt = ctypes.windll.inpout32
    lpt_error = None
except Exception as e:
    lpt = None
    lpt_error = e

# Useful constants
SYNC_BV =      0xFFFFFF00 # 0xFFFFFF00
MK2_BV =       0x80000000 # bit 23/31
BATTERY_BV =   0x40000000 # bit 22/30
SPEED_BIT3 =   0x20000000 # bit 21/29
CMS_RANGE_BV = 0x10000000 # bit 20/28
SPEED_BIT2 =   0x08000000 # bit 19/27
SPEED_BIT1 =   0x04000000 # bit 18/26
SPEED_BIT0 =   0x02000000 # bit 17/25
EPOCH_BV =     0x01000000 # bit 16/24
numChannelsMk1 = [256, 128,  64,  32, 256, 138, 64, 32, 256]
numChannelsMk2 = [608, 608, 608, 608, 280, 152, 88, 56, 280]
CHUNK_SIZE = 1024

class BIOSEMI(Recorder):
    """ 
    Class to record from a BIOSEMI device. For more information, see the generic
    Recorder class.
    """

    def __init__(self, buffer_size_seconds=0.5, status_as_markers=False, bdf_file=None, timing_mode='smoothed_sample_rate', port='LPT1', reference_channels=range(32)):
        """ Open the BIOSEMI device

        Keyword arguments:

        buffer_size_seconds: The amount of seconds of data to read from the
                             BIOSEMI device before it will be decoded. Defaults
                             to 0.5 seconds.

        status_as_markers:   Set to True to use the parallel port trigger cable
                             as status channel.

        bdf_file:            Dump all recorded data (regardless whether the
                             device is in capture more or not) to a BDF file
                             with the given filename.

        lpt_port:            Name of the LPT port ('LPT#') to which the trigger
                             cable is connected. This parameter is ignored when
                             status_as_markers is set to False.

        reference_channels:  List of integer indices or channel names indicating
                             the channels to use as a reference. Defaults to
                             the first 32 channels (CAR referencing).
        """

        self.sample_rate = 2048
        self.nchannels = 40
        self.calibration_time = 0 # Signal does not need to stabilize
        self.physical_min = -262144 
        self.physical_max = 262144
        self.digital_min = 0
        self.digital_max = 2**24
        self.gain = (self.physical_max-self.physical_min) / float(self.digital_max-self.digital_min)
        self.bytes_per_sample = 280 * 4
        self.status_as_markers = status_as_markers

        self.logger = logging.getLogger('BIOSEMI Recorder')

        self.channel_names = [
            'Fp1', 'AF3', 'F7', 'F3', 'FC1', 'FC5', 'T7', 'C3',
            'CP1', 'CP5', 'P7', 'P3', 'Pz', 'PO3', 'O1', 'Oz',
            'O2', 'PO4', 'P4', 'P8', 'CP6', 'CP2', 'C4', 'T8',
            'FC6', 'FC2', 'F4', 'F8', 'AF4', 'Fp2', 'Fz', 'Cz',
            'EXG1', 'EXG2', 'EXG3', 'EXG4', 'EXG5', 'EXG6', 'EXG7', 'EXG8'
        ]

        self.reference_channels = []
        for ch in reference_channels:
            if type(ch) == str:
                self.reference_channels.append(self.channel_names.index(ch))
            elif type(ch) == int:
                self.reference_channels.append(ch)
            else:
                raise DeviceError('Use string or integers to indicate reference channels')

        self.nreference_channels = len(self.reference_channels)

        self.feat_lab = list(self.channel_names)
        
        if self.status_as_markers:
            if lpt == None:
                raise DeviceError('Could not open inpout32.dll: %s' % lpt_error)

            self.lpt_address = self._get_lpt_address(port)
            self.timing_mode = 'fixed'

        # Configuration of the generic recorder object
        Recorder.__init__(self, buffer_size_seconds, bdf_file, timing_mode)

        self._reset()

    def _reset(self):
        super(BIOSEMI, self)._reset()
        self.nsamples = 0
        self.begin_read_time = precision_timer()
        self.end_read_time = self.begin_read_time
        self.unfinished_frames = []

    def _open(self):
        self.logger.debug('Opening BIOSEMI device...')
        dev = usb.core.find(idVendor=0x0547, idProduct=0x21A1)
        if dev == None:
            dev = usb.core.find(idVendor=0x0547, idProduct=0x1005)

        if dev == None:
            raise DeviceError('Cannot find device: is the Biosemi ActiveTwo plugged in?')

        dev.set_configuration(1)
        interface = dev.get_active_configuration()[(0,0)]
        self.ep_out = interface[0]
        self.ep_in = interface[3]

        if self.status_as_markers:
            # Reset LPT pins to all zeros
            lpt.Out32(self.lpt_address, 0)

        # Instruct device to start recording
        try:
            buf = array.array('B', '\x00'*64)
            self.ep_in.write(buf)
            buf[0] = 0xFF
            self.ep_in.write(buf)
        except Exception as e:
            raise DeviceError('Cannnot open device: %s' % e)

        # Record some data to determine device properties
        try:
            data = array.array('B', [0] * CHUNK_SIZE)
            self.ep_out.readinto(data)
        except Exception as e:
            raise DeviceError('Cannnot read data: %s' % e)

        data = struct.unpack('<%dI' % (len(data)/4), data)

        # Analyze data to determine properties
        for i in range(len(data)-1):
            if data[i] == SYNC_BV and data[i+1] != SYNC_BV:
                data = data[i:]
                break
        else:
            raise DeviceError('Corrupted data.')

        status = data[1]
        self.isMk2 = bool(status & MK2_BV)
        self.speed_mode = 0;
        if bool(status & SPEED_BIT3): self.speed_mode += 8;
        if bool(status & SPEED_BIT2): self.speed_mode += 4;
        if bool(status & SPEED_BIT1): self.speed_mode += 2;
        if bool(status & SPEED_BIT0): self.speed_mode += 1;
        self.cmsInRange = bool(status & CMS_RANGE_BV)

        if self.speed_mode < 0 or self.speed_mode > 8:
            raise DeviceError('Unsupported speed mode discovered')

        if self.isMk2:
            maxNumChannels = numChannelsMk2[self.speed_mode]
        else:
            maxNumChannels = numChannelsMk1[self.speed_mode]

        numChannelsAIB = 32 if (self.speed_mode == 8) else 0
        self.stride = maxNumChannels + numChannelsAIB + 2
        
        if self.speed_mode in [0, 4, 8]:
                self.sample_rate = 2048
        elif self.speed_mode in [1, 5]:
                self.sample_rate = 4096
        elif self.speed_mode in [2, 6]:
                self.sample_rate = 8192
        elif self.speed_mode in [3, 7]:
                self.sample_rate = 16384

        # Set up buffers to hold data
        buffer_size = int(self.buffer_size_seconds * self.sample_rate) * self.bytes_per_sample
        buffer_size = numpy.ceil(buffer_size / float(CHUNK_SIZE)) * CHUNK_SIZE
        buffers = [array.array('B', [0] * (buffer_size/4)) for n in xrange(4)]

        # Start the background reader
        self.reader = BackgroundReader(self.ep_out, buffers)
        self._flush_buffer()
        T0 = self.begin_read_time
        self.reader.start()

        return T0

    def stop(self):
        super(BIOSEMI, self).stop()

        # Instruct device to stop recording
        try:
            buf = array.array('B', '\x00'*64)
            self.ep_in.write(buf)
        except:
            # Silently fail
            pass 

        try:
            self.reader.stop()
            self.reader.join(2*self.buffer_size_seconds)
        except AttributeError:
            pass

    def _record_data(self):
        ''' Reads data from the BIOSEMI device and returns it as a Psychic
        dataset. '''

        self.reader.data_condition.acquire()
        while len(self.reader.full_buffers) == 0 and self.running:
            self.reader.data_condition.wait()
        full_buffers = list(self.reader.full_buffers)
        self.reader.full_buffers.clear()
        self.reader.data_condition.release()

        recording = None
        for length, timestamp, buf in full_buffers:
            self.end_read_time = timestamp

            d = self._to_dataset(buf)
            if d != None:
                if recording == None:
                    recording = d
                else:
                    recording += d

            self.begin_read_time = self.end_read_time

        return recording

    def _to_dataset(self, data):
        """ Converts the data recorded from the BIOSEMI device into a Psychic dataset.
        """
        if data == None or len(data) == 0:
            return None

        # Convert data from little-endian 32-bit ints to python integers
        data = struct.unpack('<%dI' % (len(data)/4), data)
        
        # Prepend data recorded earlier that did not cover complete frames
        if len(self.unfinished_frames) > 0:
            data = self.unfinished_frames + data
            self.unfinished_frames = []

        # Check sync byte
        if data[0] != SYNC_BV:
            self.logger.warning('sync lost, trying to find it again')
            for i in range(len(data)-1):
                if data[i] == SYNC_BV and data[i+1] != SYNC_BV:
                    self.logger.warning('signal re-synced')
                    data = data[i:]
                    break
            else:
                self.logger.warning('unable to re-sync signal, discarding data')
                return None

        # Only keep complete frames
        samples_read = len(data) / self.stride
        self.unfinished_frames = data[self.stride * samples_read:]
        data = data[:self.stride * samples_read]

        frames = numpy.array(data, dtype=numpy.uint32).reshape(-1, self.stride).T

        # Test if sync markers line up,,
        if len(numpy.flatnonzero(frames[0,:] != SYNC_BV)) > 0:
            self.logger.warning('sync lost, discarding data')
            return None

        self.battery_low = len(numpy.flatnonzero(frames[1,:] & BATTERY_BV)) > 0
        self.cms_in_range = len(numpy.flatnonzero(frames[1,:] & CMS_RANGE_BV) == 0) > 0

        # Keep only first 32 channels + 8 external ones
        frames = frames[range(1,33) + range(257, 266),:]
        
        # Undo byte adding that the biosemi has done
        frames = (frames >> 8)

        # First channel is status channel
        if self.status_as_markers:
            Y = (frames[:1,:] & 0x00ffff)
        else:
            Y = numpy.zeros((1, frames.shape[1]))

        X = frames[1:,:] + (2**23) # go from signed to unsigned

        # Calculate reference signal
        if len(self.reference_channels) > 0:
            REF = X[self.reference_channels,:]

        X = X[self.target_channels,:]

        # Re-reference the signal to the chosen reference
        if len(self.reference_channels) > 0:
            X = X - numpy.tile(numpy.mean(REF, axis=0), (X.shape[0], 1))

        I = self._estimate_timing(X.shape[1])

        self.logger.debug('Number of samples parsed: %d' % X.shape[1])
        return psychic.DataSet(data=X, labels=Y, ids=I, feat_lab=self.feat_lab)

    def _flush_buffer(self):
        """ Flush data in BIOSEMI buffer """
        #self.ep_out.read(self.sample_rate*self.stride*4, timeout=0)
        self.begin_read_time = precision_timer()

    def _set_bdf_values(self):
        """ Set default values for the BDF Writer """
        self.bdf_writer.n_channels = self.nchannels
        self.bdf_writer.n_samples_per_record = [int(self.sample_rate*self.bdf_writer.record_length) for x in range(self.nchannels)]
        self.bdf_writer.transducer_type = ['Active electrode' for x in range(self.nchannels)]
        self.bdf_writer.physical_min = [self.physical_min for x in range(self.nchannels)]
        self.bdf_writer.physical_max = [self.physical_max for x in range(self.nchannels)]
        self.bdf_writer.digital_min = [self.digital_min for x in range(self.nchannels)]
        self.bdf_writer.digital_max = [self.digital_max for x in range(self.nchannels)]
        self.bdf_writer.units = ['uV' for x in range(self.nchannels)]
        self.bdf_writer.prefiltering = ['HP:DC LP:417Hz' for x in range(self.nchannels)]
        self.bdf_writer.label = list(self.feat_lab) # Make a copy of the list, don't just pass a reference
        self.bdf_writer.reserved = ['' for x in range(self.nchannels)]
        self.bdf_writer.append_status_channel()

    def _add_markers(self, d):
        if self.status_as_markers:
            return d
        else:
            return super(BIOSEMI, self)._add_markers(d)

    def set_marker(self, code, type='trigger', timestamp=precision_timer()):
        """ Label the data with a marker.

        code      - any integer value you wish to label the data with
        type      - 'trigger' meaning only one instance will be marked or
                    'switch' meaning all instances from now on will be marked
        timestamp - the exact timing at which the marker should be placed
                    (in seconds after epoch, floating point)
        """
        if self.status_as_markers:
            assert(type == 'switch' or type == 'trigger')

            self.marker_lock.acquire()

            lpt.Out32(self.lpt_address, code)
            delay = precision_timer() - timestamp

            if(type == 'trigger'):
                time.sleep(0.005)
                lpt.Out32(self.lpt_address, 0)
                
            m = Marker(code, type, timestamp)
            self.logger.info('Received marker %s, delay %.3f s' % (m, delay))
            self.marker_lock.release()
        else:
            super(BIOSEMI, self).set_marker(code, type, timestamp)

    def set_parameter(self, name, values):
        if name == 'port':
            if len(values) < 1:
                raise DeviceError('missing value for port.')
            self.lpt_address = self._get_lpt_address(values[0])
            return True

        elif name == 'status_as_markers':
            if len(values) < 1:
                raise DeviceError('missing value for status_as_markers.')
            if values[0]:
                if lpt == None:
                    raise DeviceError('Could not open inpout32.dll: %s' % lpt_error)
                self.status_as_markers = True
                self.timing_mode = 'fixed'
            else:
                self.status_as_markers = False
                self.timing_mode = 'smoothed_sample_rate'
            return True

        elif name == 'reference_channels':
            if self.running:
                raise DeviceError('Cannot set parameter because the device is already opened.')

            reference_channels = []

            for channel_name in values:
                if type(channel_name) == str:
                    if not channel_name in self.channel_names:
                        raise DeviceError('Channel %s is not a valid channel for this device.' % channel_name)

                    reference_channels.append( self.channel_names.index(channel_name) )
                elif type(channel_name) == float:
                    raise DeviceError('Invalid channel index or name: %f, please use integers or strings.' % channel_name)
                else:
                    reference_channels.append(channel_name)

            self.reference_channels = reference_channels
            self.nreference_channels = len(reference_channels)
            return True

        else:
            return super(BIOSEMI,self).set_parameter(name, values)

    def get_parameter(self, name):
        value = super(BIOSEMI, self).get_parameter(name)
        if value:
            return value

        if name == 'port':
            return self.port

        elif name == 'reference_channels':
            return self.reference_channels
        
        elif name == 'status_as_markers':
            return 1 if self.status_as_markers else 0

        else:
            return False

    def _get_lpt_ports(self):
        ''' Return a dictionary (name -> address) of available LPT ports
        on the system (Windows only). '''

        lpt_ports = {}

        lpt_devices = wmi.GetObject('WinMgmts://').InstancesOf('Win32_ParallelPort')
        for device in lpt_devices:
            id = device.PnpDeviceID
            key = reg.OpenKey(
                reg.HKEY_LOCAL_MACHINE, 
                'SYSTEM\\CurrentControlSet\\Enum\\' + id + '\\Device Parameters')
            portname = reg.QueryValueEx(key, 'PortName')[0]

            # Address can be stored in two places...
            try: 
                # For expansion cards
                key = reg.OpenKey(
                    reg.HKEY_LOCAL_MACHINE, 
                    'SYSTEM\\CurrentControlSet\\Enum\\' + id + '\\Control')
                conf = reg.QueryValueEx(key, 'AllocConfig')[0]

                # Decode data as signed integers (4 bytes each)
                conf_dec = struct.unpack('%di' % (len(conf)/4), conf)

                # Find the portaddress at the correct offset
                portaddress = conf_dec[6]

            except WindowsError:
                # For regular ports
                key = reg.OpenKey(
                    reg.HKEY_LOCAL_MACHINE, 
                    'SYSTEM\\CurrentControlSet\\Enum\\' + id + '\\LogConf')
                conf = reg.QueryValueEx(key, 'BasicConfigVector')[0]

                # Decode data as signed integers (4 bytes each)
                conf_dec = struct.unpack('%di' % (len(conf)/4), conf)

                # Find the portaddress at the correct offset
                portaddress = conf_dec[14]

            lpt_ports[portname] = portaddress

        return lpt_ports

    def _get_lpt_address(self, lpt_port='LPT1'):
        ''' Returns the address of the LPT port with the given name. Raises
        a DeviceError if the port is not available on the system.
        Use _get_lpt_ports() to determine which ports are available.
        Windows only. '''

        lpt_ports = self._get_lpt_ports()
        if not lpt_port in lpt_ports:
            raise DeviceError('%s port not found (available ports: %s)' %
                (lpt_port, lpt_ports.keys()))
        return lpt_ports[lpt_port]

