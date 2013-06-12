import serial
import logging
import numpy
import golem
import struct
import re
import os

from . import Recorder, precision_timer, DeviceError
from background_reader import BackgroundReader

class IMECNL(Recorder):
    """ 
    Class to record from the IMEC-NL device. For more information, see the
    generic Recorder class.
    """
    def __init__(self, port=None, buffer_size_seconds=0.5, bdf_file=None, timing_mode='begin_read_relative'):
        """ Open the IMEC-NL device on the given port.

        Keyword arguments:
        port:                On UNIX systems, a string containing the filename of the
                             serial port (e.g. '/dev/tty.usbserial-########') On
                             windows systems, a string in the form of COM# (e.g.
                             'COM1'). By default, autodetection of the port will be
                             attempted (which usually works).

        buffer_size_seconds: The amount of seconds of data to read from the
                             IMEC device before it will be decoded. Defaults to
                             0.5 seconds.

        bdf_file:            Dump all recorded data (regardless whether the
                             device is in capture more or not) to a BDF file
                             with the given filename.
        """

        # Configuration of the device, this should not change often
        self.baudrate = 1000000
        self.sample_rate = 1024
        self.nchannels = 8
        self.samples_per_frame = 1
        self.bytes_per_frame = 27
        self.calibration_time = 0 # Signal takes 0 seconds to stabilize
        self.physical_min = 0
        self.physical_max = 65535
        self.digital_min = 0
        self.digital_max = 65535
        self.gain = ((self.physical_max-self.physical_min) /
                     float(self.digital_max-self.digital_min))
        self.channel_names = ['Fz', 'Cz', 'CP1', 'CP2', 'P3', 'Pz', 'P4', 'Oz']
        self.feat_lab = list(self.channel_names)
        self.preamble = bytes('BAN')
        self.frame_struct = struct.Struct('<3s4B8HBcH')
        self.config_struct = struct.Struct('BBBxxBB14x')

        self.port = port

        self.reader = None
        self.serial = None

        # Configure logging
        self.logger = logging.getLogger('IMEC-NL Recorder')

        # Configuration of the generic recorder object
        Recorder.__init__(self, buffer_size_seconds, bdf_file, timing_mode)

        self._reset()

    def _reset(self):
        super(IMECNL, self)._reset()
        self.last_frame = None
        self.remaining_data = bytes('')
        self.nsamples = 0

    def _open(self):
        self.buffer_size_samples = int(self.buffer_size_seconds * self.sample_rate)
        self.buffer_size_frames = int(self.buffer_size_samples / float(self.samples_per_frame))
        self.buffer_size = int( self.buffer_size_seconds*self.bytes_per_frame*(self.sample_rate/self.samples_per_frame) )

        # Open serial port
        self.logger.debug('Opening serial port...')

        if self.port == None:
            self.serial = self._find_device()
        else:
            if os.name == 'posix':
                ser = serial.serial_for_url(self.port,
                                            baudrate=self.baudrate,
                                            timeout=0.5)

                ser.flowControl(False)
            else:
                # Windows
                m = re.match(r"COM(\d+)", self.port)
                if m != None:
                    ser = serial.serialwin32.Win32Serial( int(m.group(1))-1,
                                                          baudrate=self.baudrate,
                                                          timeout=0.5)
                else:
                    raise DeviceError('Invalid format for port, should be COM#.')

            # Check the data
            if self._detect_imecnl_data(ser):
                ser.close()
                raise DeviceError('This does not look like the IMEC-NL device.')
            self.serial = ser

        # Configure the device
        self.serial.write( self.config_struct.pack(1,255,2,0xFF,0x80) )

        # Set up buffers to hold data
        buffers = [bytearray(b"\x00" * self.buffer_size) for n in xrange(4)]
        self.reader = BackgroundReader(self.serial, buffers)

        self.droppedframeslog = open('droppedframes.log', 'w')
        self.driftlog = open('drift.log', 'w')
        self.driftlog.write('Now, Target, Obtained, Drift, Cycle\n')

        # Timestamp the beginning of the recording
        self._flush_buffer()
        T0 = self.begin_read_time

        # Start the serial reader
        self.reader.start()

        return T0

    def _find_device(self):
        if os.name == 'posix':
            # Get a listing of the available USB->SERIAL devices
            possible_devices = [dev for dev in os.listdir('/dev') if dev.startswith('tty.')]
            for dev in possible_devices:
                try:
                    ser = serial.serial_for_url('/dev/%s' % dev,
                                            baudrate=self.baudrate,
                                            timeout=2*self.buffer_size_seconds)
                except:
                    continue

                try:
                    if self._detect_imecnl_data(ser):
                        self.logger.info('Found IMEC-NL wireless EEG-device on serial port /dev/%s' % dev)
                        ser.flowControl(False)
                        return ser
                    else:
                        ser.close()
                except:
                    ser.close()

        else:
            # Try the first 10 COM ports
            for i in range(10):
                try:
                    ser = serial.serialwin32.Win32Serial(i, baudrate=self.baudrate, timeout=2*self.buffer_size_seconds)
                except Exception as e:
                    continue

                try:
                    if self._detect_imecnl_data(ser):
                        self.logger.info('Found IMEC-NL wireless EEG-device on serial port COM%d' % (i+1))
                        return ser
                    else:
                        ser.close()
                except Exception as e:
                    ser.close()
                    raise

        raise DeviceError('Could not find IMEC-NL device.')

    def stop(self):
        super(IMECNL, self).stop()

        try:
            self.reader.stop()
            self.reader.join(2*self.buffer_size_seconds)
        except AttributeError:
            pass

        try:
            self.serial.close()
        except AttributeError:
            pass

        try:
            self.droppedframeslog.close()
            self.driftlog.close()
        except AttributeError:
            pass

    def _record_data(self):
        """ Read data from the device and parse it. Returns a Golem dataset. """

        self.reader.data_condition.acquire()
        while len(self.reader.full_buffers) == 0 and self.running:
            self.reader.data_condition.wait()
        full_buffers = list(self.reader.full_buffers)
        self.reader.full_buffers.clear()
        self.reader.data_condition.release()

        recording = None
        for length, timestamp, buf in full_buffers:
            self.end_read_time = timestamp
            diff = self.end_read_time - self.begin_read_time

            data = self.remaining_data + buf[:length]

            # Decode as much data as possible, keep track of the data in the buffer
            # that still remains. That is left until the next iteration
            d, self.remaining_data = self._raw_to_dataset(data)

            if d != None:
                self.nsamples += d.ninstances
                self.logger.debug('dt: %.03f, samples: %d, timestamp: %.03f' % (diff, d.ninstances, timestamp))

                if recording == None:
                    recording = d
                else:
                    recording += d

            # Keep track of drift: the discrepancy between the number of samples
            # that should have been recorded by now and the number of samples that
            # actually were.
            now = self.end_read_time
            target = int((now-self.T0) * self.sample_rate)
            drift = target - self.nsamples
            self.driftlog.write('%f, %d, %d, %d, %f\n' %
                                (now, target, self.nsamples, drift, diff))
            self.driftlog.flush()
            self.logger.debug('Drift: %d' % drift)

            self.begin_read_time = self.end_read_time

        return recording

    def _detect_imecnl_data(self, serial):
        old_timeout = serial.timeout
        detected = False

        # Try to read 0.5 seconds of data
        serial.timeout = 0.5

        try:
            data = serial.read( int(0.5*self.samples_per_frame*self.bytes_per_frame*self.sample_rate) )
        except Exception as e:
            # If anything goes wrong, give up
            return False

        num_bytes = len(data)
        if num_bytes < self.bytes_per_frame:
            return False

        # Find frame markers
        frames_found = 0
        i = 0
        while i < num_bytes-self.bytes_per_frame:
            for j in range(i, num_bytes-self.bytes_per_frame):
                # Data should begin with preamble ('JEF')
                if data[j:j+3] != self.preamble:
                    continue

                # Next frame should also begin with preamble
                if j < num_bytes-2*self.bytes_per_frame and data[j+self.bytes_per_frame:j+self.bytes_per_frame+3] != self.preamble:
                    continue

                frames_found += 1

            i += j+self.bytes_per_frame

        if frames_found > 10:
            detected = True
            
        serial.timeout = old_timeout
        return detected

    def _raw_to_dataset(self, data_string):
        """ Decodes a string of raw data read from the IMEC-NL device into a
        Golem dataset """
        num_bytes = len(data_string)
        self.logger.debug('Handling datapacket of length %d' % num_bytes)

        if num_bytes < self.bytes_per_frame:
            self.logger.warning('Data incomplete: read at least %d bytes before'
                                'calling this function' % self.bytes_per_frame)
            return [None, data_string]

        #data = struct.unpack('%dB' % num_bytes, data_string)
        data = data_string

        # Construct dataset from the raw data
        samples = []
        first_frame = True
        i = 0
        while i < num_bytes-self.bytes_per_frame:
            # Search for the next frame. This frame should be right next to the frame
            # we just parsed. But sometimes, the device inserts some bogus values between
            # frames, which we need to skip
            frame_found = False
            frame_index = i
            for j in range(i, num_bytes-self.bytes_per_frame):
                # Data should begin with preamble ('JEF')
                if data[j:j+3] != self.preamble:
                    continue

                # Next frame should also begin with preamble
                if j < num_bytes-2*self.bytes_per_frame and data[j+self.bytes_per_frame:j+self.bytes_per_frame+3] != self.preamble:
                    continue

                frame_found = True
                frame_index = j
                break
            if frame_index - i > 0:
                self.logger.debug('garbage bytes: %d' % (frame_index - i))
            i = frame_index

            if not frame_found:
                # Done with this data packet
                break

            if first_frame:
                first_frame = False

            frame = self._decode_frame(data[i:i+self.bytes_per_frame])

            # Determine number of dropped frames
            if self.last_frame == None:
                dropped_frames = 0
            elif frame.seq > self.last_frame.seq:
                dropped_frames = (frame.seq-1) - self.last_frame.seq
            elif frame.seq < self.last_frame.seq:
                dropped_frames = (frame.seq+2**32) - self.last_frame.seq
            else:
                self.logger.warning('Data corrupt: duplicate sequence number in data packet (%d = %d), i was %d' % (self.last_frame.seq, frame.seq, i))
                # don't use this frame
                i += self.bytes_per_frame

                # fix dropped frames when we restore accurate sequence numbers
                dropped_frames = 0
                continue 
            
            if dropped_frames > 0:
                self.logger.warning('Dropped %d frames' % dropped_frames)

            # Interpolate the dropped frames if possible
            for j in range(1, dropped_frames+1):
                if self.last_frame != None:
                    inter = ( self.last_frame.X[:,0] +
                              j * (frame.X[:,0]-self.last_frame.X[:,0]) /
                              float(dropped_frames+1) )
                    samples.append(numpy.vstack((inter, inter)).T)
                else:
                    samples.append(numpy.vstack((frame.X[:,0], frame.X[:,0])).T)

            # Append the current frame
            samples.append(frame.X)
            self.last_frame = frame

            i += self.bytes_per_frame

        # Check whether any data has been decoded
        if len(samples) == 0:
            self.logger.warning('Data corrupt: no valid frames found in data packet')
            return (None, bytes(''))

        X = numpy.hstack(samples)[self.target_channels,:]
        Y = numpy.zeros([1, X.shape[1]])
        I = self._estimate_timing(X.shape[1])

        self.logger.debug('Number of bytes parsed: %d' % i)
        d = golem.DataSet(X=X, Y=Y, I=I, feat_lab=self.feat_lab)

        return (d, data_string[i:])

    def _decode_frame(self, data):
        """ Decodes a single frame of data read from the IMEC device.
        """
        preamble, seq1, seq2, seq3, seq4, chan1, chan2, chan3, chan4, chan5, chan6, chan7, chan8, mode, event, adc = self.frame_struct.unpack(bytes(data))
        seq = seq1 + 256*seq2 + 65536*seq3 + 16777216*seq4
        X = numpy.atleast_2d(numpy.array([chan1, chan2, chan3, chan4, chan5, chan6, chan7, chan8])).T

        return Frame(seq=seq, mode=mode, event=event, volt=8*adc/4095.0, X=X)

    def _flush_buffer(self):
        """ Flush data in EPOC buffer """
        self.begin_read_time = precision_timer()
        self.serial.flushInput()

    def _set_bdf_values(self):
        """ Set default values for the BDF Writer """
        self.bdf_writer.n_channels = self.nchannels
        self.bdf_writer.n_samples_per_record = [int(self.sample_rate*self.bdf_writer.record_length) for x in range(self.nchannels)]
        self.bdf_writer.transducer_type = ['active gel electrode' for x in range(self.nchannels)]
        self.bdf_writer.physical_min = [self.physical_min for x in range(self.nchannels)]
        self.bdf_writer.physical_max = [self.physical_max for x in range(self.nchannels)]
        self.bdf_writer.digital_min = [self.digital_min for x in range(self.nchannels)]
        self.bdf_writer.digital_max = [self.digital_max for x in range(self.nchannels)]
        self.bdf_writer.units = ['uV' for x in range(self.nchannels)]
        self.bdf_writer.prefiltering = ['HP:0.2 Hz LP:52-274Hz' for x in range(self.nchannels)]
        self.bdf_writer.label = list(self.feat_lab)
        self.bdf_writer.reserved = ['' for x in range(self.nchannels)]
        self.bdf_writer.append_status_channel()

    def set_parameter(self, name, values):
        if super(IMECNL, self).set_parameter(name, values):
            return True

        if self.running:
            raise DeviceError('Cannot set parameter because the device is already opened.')

        if name == 'buffer_size_seconds':
            if len(values) < 1 or (type(values[0]) != float and type(values[0]) != int):
                raise DeviceError('invalid value for buffer size.')
            self.buffer_size_seconds = values[0]
            return True

        elif name == 'timing_mode':
            if len(values) < 1:
                raise DeviceError('missing value for timing_mode.')
            
            if values[0] in ['fixed', 'end_read_relative', 'estimated_sample_rate', 'smoothed_sample_rate', 'begin_read_relative']:
                self.timing_mode = values[0]
                return True
            else:
                raise DeviceError('invalid value for timing_mode.')

        elif name == 'port':
            if len(values) < 1:
                raise DeviceError('missing value for port.')

            self.port = values[0]
            return True

        else:
            return False

    def get_parameter(self, name):
        value = super(IMECNL, self).get_parameter(name)
        if value:
            return value

        if name == 'port':
            return self.port
        else:
            return False

class Frame:
    """ Contains information about a frame, recorded from the IMEC-NL device.
    Frame.seq:  the sequence number 
    Frame.mode: the voltage of the battery (0 = 0V, 255 = 5.1V)
    Frame.event: event related byte ('0' or '1')
    Frame.X:   a (channels x sample) numpy array containing the data
    """
    def __init__(self, seq=-1, mode=-1, event=-1, volt=0, X=[]):
        self.seq = seq
        self.mode = mode
        self.event = event
        self.volt = volt
        self.X = X

    def __repr__(self):
        return 'Frame (%d)<mode: %d, event: %s, volt: %.2f, X:%s>' % (self.seq, self.mode, self.event, self.volt, self.X)
