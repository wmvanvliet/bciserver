import biosemi_reader
import logging
import numpy
import golem
import time

import wmi
import _winreg as reg
import struct

from . import Recorder, precision_timer, DeviceError, Marker

try:
    import ctypes
    lpt = ctypes.windll.inpout32
    lpt_error = None
except Exception as e:
    lpt = None
    lpt_error = e

class BIOSEMI(Recorder):
    """ 
    Class to record from a BIOSEMI device. For more information, see the generic
    Recorder class.
    """

    def __init__(self, buffer_size_seconds=0.5, status_as_markers=False, bdf_file=None, timing_mode='begin_read_relative', port='LPT1', reference_channels=[]):
        """ Open the BIOSEMI device

        Keyword arguments:

        buffer_size_seconds: The amount of seconds of data to read from the
                             BIOSEMI device before it will be decoded. Defaults
                             to 0.5 seconds.

        bdf_file:            Dump all recorded data (regardless whether the
                             device is in capture more or not) to a BDF file
                             with the given filename.
        """

        self.sample_rate = 2048
        self.nchannels = 40 
        self.calibration_time = 0 # Signal does not need to stabilize
        self.physical_min = -262144 
        self.physical_max = 262144
        self.digital_min = 0
        self.digital_max = 2**24
        self.gain = (self.physical_max-self.physical_min) / float(self.digital_max-self.digital_min)
        self.buffer_size_bytes = int(280 * 4 * (buffer_size_seconds+1) * self.sample_rate)
        self.status_as_markers = status_as_markers
        self.reference_channels = reference_channels
        self.nreference_channels = len(self.reference_channels)

        self.logger = logging.getLogger('BIOSEMI Recorder')

        self.feat_lab = [
            'Fp1', 'AF3', 'F7', 'F3', 'FC1', 'FC5', 'T7', 'C3',
            'CP1', 'CP5', 'P7', 'P3', 'Pz', 'PO3', 'O1', 'Oz',
            'O2', 'PO4', 'P4', 'P8', 'CP6', 'CP2', 'C4', 'T8',
            'FC6', 'FC2', 'F4', 'F8', 'AF4', 'Fp2', 'Fz', 'Cz',
            'EXG1', 'EXG2', 'EXG3', 'EXG4', 'EXG5', 'EXG6', 'EXG7', 'EXG8'
        ]
        
        if not self.status_as_markers:
            self.reader = biosemi_reader.BiosemiReader(
                buffersize=self.buffer_size_bytes,
                sync=True,
                pollInterval=1)
        else:
            if lpt == None:
                raise DeviceError('Could not open inpout32.dll: %s' % lpt_error)

            self.lpt_address = self._get_lpt_address(port)

            self.reader = biosemi_reader.BiosemiReader(
                buffersize=self.buffer_size_bytes)
            self.timing_mode = 'fixed'


        # Configuration of the generic recorder object
        Recorder.__init__(self, buffer_size_seconds, bdf_file, timing_mode)

        self._reset()

    def _reset(self):
        super(BIOSEMI, self)._reset()
        self.nsamples = 0
        self.begin_read_time = precision_timer()
        self.end_read_time = self.begin_read_time

    def _open(self):
        self.logger.debug('Opening BIOSEMI device...')
        try:
            self.reader.open()
        except Exception as e:
            raise DeviceError('Could not open BIOSEMI: %s' % e.message)

        self.driftlog = open('drift.log', 'w')
        self.driftlog.write('Now, Target, Obtained, Drift, Cycle\n')

        return self.reader.T0

    def stop(self):
        super(BIOSEMI, self).stop()
        self.reader.close()

    def _record_data(self):
        ''' Reads data from the BIOSEMI device and returns it as a Golem
        dataset. '''
        self.begin_read_time = self.end_read_time
        self.end_read_time = self.begin_read_time + self.buffer_size_seconds
        time_to_wait = max(0, self.end_read_time - precision_timer())
        time.sleep(time_to_wait)

        d = self.reader.read()
        now = self.reader.read_time
        diff = now - self.end_read_time
        self.end_read_time = now

        d = self._to_dataset(d)
        if d != None:
            self.nsamples += d.ninstances

        # Keep track of drift: the discrepancy between the number of
        # samples that should have been recorded by now and the number of
        # samples that actually were.
        target = int((self.end_read_time-self.T0) * self.sample_rate)
        drift = target - self.nsamples
        self.driftlog.write('%f, %d, %d, %d, %f\n' %
                            (now, target, self.nsamples, drift, diff))
        self.driftlog.flush()

        return d

    def _to_dataset(self, data):
        """ Converts the data recorded from the BIOSEMI device into a Golem dataset.
        """

        if data == None or data.size == 0:
            self.logger.warning('Data corrupt: no valid frames found in data packet')
            return None

        # Undo byte adding that the biosemi has done
        data = (data >> 8)

        # First channel is status channel
        if self.status_as_markers:
            Y = (data[:1,:] & 0x00ffff)
        else:
            Y = numpy.zeros((1, data.shape[1]))

        X = data[1:,:] + (2**23) # go from signed to unsigned

        if len(self.reference_channels) > 0:
            REF = X[self.reference_channels,:]

        X = X[self.target_channels,:]

        if len(self.reference_channels) > 0:
            X = X - numpy.tile(numpy.mean(REF, axis=0), (X.shape[0], 1))

        I = self._estimate_timing(X.shape[1])

        self.logger.debug('Number of samples parsed: %d' % X.shape[1])
        return golem.DataSet(X=X, Y=Y, I=I, feat_lab=self.feat_lab)

    def _flush_buffer(self):
        """ Flush data in BIOSEMI buffer """
        self.reader.read()
        self.begin_read_time = self.reader.read_time

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

            print lpt.Out32(self.lpt_address, code)
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
                self.timing_mode = 'begin_read_relative'
            return True

        elif name == 'reference_channels':
            if self.running:
                raise DeviceError('Cannot set parameter because the device is already opened.')

            reference_channels = []

            for channel_name in values:
                if type(channel_name) == str:
                    if not channel_name in self.feat_lab:
                        raise DeviceError('Channel %s is not a valid channel for this device.' % channel_name)

                    reference_channels.append( self.feat_lab.index(channel_name) )
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

