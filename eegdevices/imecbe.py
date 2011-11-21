import serial
import logging
import numpy
import golem
import struct
import time
import re
import os

from eegdevices import Recorder, precision_timer, DeviceError
from serial_reader import SerialReader

class IMECBE(Recorder):
    """ 
    Class to record from the IMEC-BE device. For more information, see the
    generic Recorder class.
    """
    def __init__(self, port=None, test=False, buffer_size_seconds=0.5, bdf_file=None, timing_mode='smoothed_sample_rate'):
        """ Open the IMEC-BE device on the given port.

        Keyword arguments:
        port:                On UNIX systems, a string containing the filename of the
                             serial port (e.g. '/dev/tty.usbserial-########') On
                             windows systems, a string in the form of COM# (e.g.
                             'COM1'). By default, autodetection of the port will be
                             attempted (which usually works).


        test:                Set this to true to make the IMEC device output a
                             test signal. Useful for debugging.

        buffer_size_seconds: The amount of seconds of data to read from the
                             IMEC device before it will be decoded. Defaults to
                             0.5 seconds.

        bdf_file:            Dump all recorded data (regardless whether the
                             device is in capture more or not) to a BDF file
                             with the given filename.
        """

        # Configuration of the device, this should not change often
        self.baudrate = 1000000
        self.sample_rate = 1000
        self.nchannels = 8
        self.samples_per_frame = 2
        self.bytes_per_frame = 27
        self.handshake_command = bytes("\xFF\xFF\xFF")
        self.handshake_response = bytes("\xEE\xEE")
        self.test_mode_command = bytes("\x41")
        self.start_measurement_command = bytes("\x20")
        self.calibration_time = 10 # Signal takes 60 seconds to stabilize
        self.physical_min = -625
        self.physical_max = 624
        self.digital_min = 0
        self.digital_max = 4094
        self.gain = ((self.physical_max-self.physical_min) /
                     float(self.digital_max-self.digital_min))
        self.feat_lab = ['Fz',
                         'FCz',
                         'Cz',
                         'CP1',
                         'CP2',
                         'P3',
                         'Pz',
                         'P4']

        self.port = port
        self.test = test

        self.reader = None
        self.serial = None

        # Configure logging
        self.logger = logging.getLogger('IMEC Recorder')

        # Configuration of the generic recorder object
        Recorder.__init__(self, buffer_size_seconds, bdf_file, timing_mode)

        self._reset()

    def _reset(self):
        super(IMECBE, self)._reset()
        self.last_frame = None
        self.remaining_data = bytes('')
        self.nsamples = 0

    def _open(self):
        self.buffer_size_samples = int(self.buffer_size_seconds * self.sample_rate)
        self.buffer_size_frames = int(self.buffer_size_samples / float(self.samples_per_frame))
        self.buffer_size = self.buffer_size_frames * self.bytes_per_frame
        
        # Open serial port and perform handshake
        self.logger.debug('Opening serial port...')

        if self.port == None:
            self.serial = self._find_device()

        else:
            if os.name == 'posix':
                ser = serial.serial_for_url(self.port,
                                            baudrate=self.baudrate,
                                            timeout=2*self.buffer_size_seconds)

                ser.flowControl(False)
            else:
                # Windows
                m = re.match(r"COM(\d+)", self.port)
                if m != None:
                    ser = serial.serialwin32.Win32Serial( int(m.group(1))-1,
                                                          baudrate=self.baudrate,
                                                          timeout=2*self.buffer_size_seconds)
                else:
                    raise DeviceError('Invalid format for port, should be COM#.')

            ser.write(self.handshake_command)
            if ser.read(len(self.handshake_response)) == self.handshake_response:
                self.logger.info('Found IMEC-BE wireless EEG-device on serial port'
                                 ' %s' % self.port)
                self.serial = ser
            else:
                ser.close()
                raise DeviceError('IMEC wireless EEG-device not found on port %s' % self.port)

        if self.test:
            # Put the device in test mode
            self.logger.info('Device in test mode')
            self.serial.write(self.test_mode_command)

        # Set up buffers to hold data
        buffers = [bytearray(b"\x00" * self.buffer_size) for n in xrange(4)]
        self.reader = SerialReader(self.serial, buffers)

        self.droppedframeslog = open('droppedframes.log', 'w')
        self.driftlog = open('drift.log', 'w')
        self.driftlog.write('Now, Target, Obtained, Drift, Cycle\n')

        # Start the measurement
        self.serial.write(self.start_measurement_command)

        # Drop the first 10 seconds of data. This will be garbage
        self._flush_buffer()
        togo = 5000 * self.bytes_per_frame
        while togo > 0 and self.running:
            togo -= len(self.serial.read(togo))
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
                                            timeout=0.5)
                except:
                    continue

                try:
                    ser.write(self.handshake_command)
                    if ser.read(len(self.handshake_response)) == self.handshake_response:
                        ser.timeout = 2*self.buffer_size_seconds
                        self.logger.info('Found IMEC-BE wireless EEG-device on serial port /dev/%s' % dev)
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
                    ser = serial.serialwin32.Win32Serial(i, baudrate=self.baudrate, timeout=0.5)
                except:
                    continue

                try:
                    ser.write(self.handshake_command)
                    if ser.read(len(self.handshake_response)) == self.handshake_response:
                        ser.timeout = 2*self.buffer_size_seconds
                        self.logger.info('Found IMEC-BE wireless EEG-device on serial port COM%d' % (i+1))
                        return ser
                    else:
                        ser.close()
                except:
                    ser.close()

        raise DeviceError('Could not find IMEC-BE device.')

    def stop(self):
        super(IMECBE, self).stop()

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

    def _raw_to_dataset(self, data):
        """ Decodes a string of raw data read from the IMEC device into a Golem
        dataset """
        num_bytes = len(data)
        self.logger.debug('Handling datapacket of length %d' % num_bytes)

        if num_bytes < self.bytes_per_frame:
            self.logger.warning('Data incomplete: read at least %d bytes before'
                                ' calling this function' % self.bytes_per_frame)
            return [None, bytes('')]

        #data = struct.unpack('%dB' % num_bytes, data_string)

        # Construct dataset from the raw data
        samples = []
        first_frame = True
        i = 0
        while i <= num_bytes-self.bytes_per_frame:
            # Search for the next frame. This frame should be right next to the
            # frame we just parsed. But sometimes, the device inserts some
            # bogus values between frames, which we need to skip
            frame_found = False
            frame_index = i
            for j in range(i, num_bytes-self.bytes_per_frame+1):
                # Data should begin with sync byte ('S' == 0x53)
                if data[j] != 0x53:
                    continue
                # Next frame should also begin with sync byte
                if (j < num_bytes-2*self.bytes_per_frame and
                   data[j+self.bytes_per_frame] != 0x53):
                    continue
                # Battery level should be between 120 and 165
                if data[j+2] < 120 or data[j+2] > 165:
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
                self.logger.debug('First frame found on index %d, seq number '
                                  '%d' % (i, data[i+1]))
                first_frame = False

            frame = self._decode_frame(data[i:i+self.bytes_per_frame])

            # Determine number of dropped frames. Note that if more than 255
            # frames are dropped, this does not work.
            if self.last_frame == None:
                dropped_frames = 0
            elif frame.seq > self.last_frame.seq:
                dropped_frames = (frame.seq-1) - self.last_frame.seq
            elif frame.seq < self.last_frame.seq:
                dropped_frames = (frame.seq+255) - self.last_frame.seq
            else:
                self.logger.warning('Data corrupt: duplicate frame number in '
                                    'data packet (%d = %d), i was %d' %
                                    (self.last_frame.seq, frame.seq, i))
                # don't use this frame
                i += self.bytes_per_frame

                # fix dropped frames when we restore accurate sequence numbers
                dropped_frames = 0
                continue 
            
            if dropped_frames > 0:
                self.logger.warning('Dropped %d frames' % dropped_frames)

                self.droppedframeslog.write('%f, %f, %d\n' %
                                   (precision_timer(), self.last_fixed_id, dropped_frames))
                self.droppedframeslog.flush()

            # Interpolate the dropped frames if possible
            for j in range(1, dropped_frames+1):
                if self.last_frame != None:
                    inter = ( self.last_frame.X[:,1] +
                              j * (frame.X[:,0]-self.last_frame.X[:,1]) /
                              float(dropped_frames+1) )
                    samples.append(numpy.vstack((inter, inter)).T)
                else:
                    samples.append(numpy.vstack((frame.X[:,0], frame.X[:,0])).T)

            # Append the current frame
            samples.append(frame.X)
            self.last_frame = frame

            i += self.bytes_per_frame

        if len(samples) == 0:
            return (None, data)

        X = numpy.hstack(samples)[self.target_channels,:]
        Y = numpy.zeros([1, X.shape[1]])
        I = self._estimate_timing(X.shape[1])

        self.logger.debug('Number of bytes parsed: %d' % i)
        d = golem.DataSet(X=X, Y=Y, I=I, feat_lab=self.feat_lab)

        return (d, data[i:])

    def _decode_frame(self, data):
        """ Decodes a single frame of data read from the IMEC device.
        """
        frame = Frame(seq=data[1], volt=data[2])

        i = 3
        X = []
        for sample in range(0, self.samples_per_frame):
            x = []
            for channel in range(8):
                    if channel % 2 == 0:
                        # even channels
                        x.append( (data[i] & 0xff) + ((data[i+1] << 4) & 0xf00) )# - 2048
                        i += 1
                    else:
                        # uneven channels
                        x.append( ((data[i] << 8) & 0x0f00) + (data[i+1] & 0xff) )# - 2048
                        i += 2
            X.append(x)

        frame.X = numpy.vstack(X).T
        return frame

    def _flush_buffer(self):
        """ Flush data in buffer """
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
        if super(IMECBE, self).set_parameter(name, values):
            return True

        if self.running:
            raise DeviceError('Cannot set parameter because the device is already opened.')

        if name == 'port':
            if len(values) < 1:
                raise DeviceError('missing value for port.')

            self.port = values[0]
            return True

        elif name == 'test':
            if len(values) < 1:
                raise DeviceError('missing value for test.')

            if values[0] != 1 and values[0] != 0:
                raise DeviceError('invalid value for test (1 or 0 allowed).')

            self.test = values[0] == 1
            return True

        else:
            return False

    def get_parameter(self, name):
        value = super(IMECBE, self).get_parameter(name)
        if value:
            return value

        if name == 'port':
            return self.port
        elif name == 'test':
            return self.test
        else:
            return False

class Frame:
    """ Contains information about a frame, recorded from the IMEC device.
    Frame.seq:  the sequence number % 255
    Frame.volt: the voltage of the battery (0 = 0V, 255 = 5.1V)
    Frame.X:    a (channels x samples) numpy array containing the data
    """
    def __init__(self, seq=-1, volt=-1, X=[]):
        self.seq = seq
        self.volt = volt
        self.X = X

    def __repr__(self):
        return 'Frame (%d)<volt: %d, X:%s>' % (self.seq, self.volt, self.X)
