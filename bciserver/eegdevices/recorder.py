import threading
import time
import golem
import psychic
import numpy
import logging
import collections

from . import precision_timer

class DeviceError(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg

class Marker:
    def __init__(self, code, type='trigger', timestamp=precision_timer()):
        self.code = code
        self.type = type
        self.timestamp = timestamp
        self.time_received = precision_timer()

    def __str__(self):
        return 'M:%d:%f:%s' % (self.code, self.timestamp, self.type)

class Recorder(threading.Thread):
    """
    Launches a separate thread that continuously reads data from a connected
    EEG device. After you have completed all your initialization and are ready
    to process the data, use start_capture() to make the recorder start
    offering the data as Golem datasets.

    Example usage:
    >>> r = Emulator(buffer_size_seconds=0.5)
    >>> r.start()
    >>> r.start_capture()
    >>> d = r.read()
    >>> r.stop()
    >>> d.ninstances
    500
    
    Some useful properties the subclasses implement are:
    nchannels  number of channels the device is recording from
    labels     a textual label for each channel (usually the 10-20 names)
    sample_rate the sample rate the device is recording at
    """

    def __init__(self, buffer_size_seconds=0.5, bdf_file=None, timing_mode='begin_read_relative'):
        """
        Opens an EEG recording device for reading. Use start() to spawn a new
        thread that reads data from the device. Data is not automatically
        captured, use start_capture() to start capturing data.

        buffer_size_seconds - Size of the internal buffer in seconds.
        bdf_file - Filename to write all incoming data in BDF format to.
        timing_mode - Timing mode to use ['fixed',
                                          'end_read_relative',
                                          'estimated_sample_rate',
                                          'smoothed_sample_rate',
                                          'begin_read_relative']
        """
        threading.Thread.__init__(self)
        self.deamon = True

        # Configure logging
        self.logger = logging.getLogger('Recorder')

        self.bdf_file = bdf_file
        # Set up locking mechanisms
        self.data_condition = threading.Condition()
        self.calibrated_event = threading.Event()
        self.marker_lock = threading.Lock()

        # Keep some debugging information related to markers
        self.markerlog = open('markers.log', 'w')
        self.markerlog.write('Timestamp, Received, Code, Y_index, Calculated,'
                             'Frame\n')

        # Timing mode
        self.timing_mode = timing_mode
        self.buffer_size_seconds = buffer_size_seconds

        # Channel selection
        self.target_channels = range(self.nchannels)

        self.file_output = False
        self.running = False
        self._reset()

    def _reset(self):
        """ Resets the recorder. Flushes all data and markers. """
        self.last_frame = None
        self.last_id = 0
        self.data = None
        self.capture_data = False

        self.marker_lock.acquire()
        self.markers = []
        self.current_marker = Marker(0, 0, 'switch')
        self.marker_lock.release()

    def read(self, block=True, flush=True):
        """
        Reads available data from the device. Returns a Golem dataset or null
        if no data is available at this time.

        block - whether to block until data is available
        flush - whether to flush the internal buffer afterwards
        """
        self.data_condition.acquire()

        if block:
            # Wait for data to become available
            while self.data == None and self.running:
                self.data_condition.wait()

        d = self.data

        if flush:    
            self.data = None

        self.data_condition.release()
        return d

    def flush(self):
        """ Flushes all data collected thus far. """
        self.data_condition.acquire()
        self.data = None
        self.data_condition.release()

    def stop(self):
        """
        Stop recording and close down the EEG device. This also shuts down the
        thread, so recording can not recommence.
        """
        self.logger.info('Stopping recorder')
        self.capture_data = False
        self.running = False

        # Notify any threads waiting for data
        self.data_condition.acquire()
        self.data_condition.notifyAll()
        self.data_condition.release()

        # Shut down recording thread
        if self.isAlive():
            self.join()

        if self.file_output:
            self.bdf_writer.close()

        self.markerlog.close()

        self.logger.info('Recorder stopped')

    def start_capture(self):
        """ (Re)start capturing data. Before this call, calls to read() and
        read_flush() will return null. Call this after you have completed all
        initialization and are ready to process data. """

        if self.capture_data:
            return

        self.logger.info('Starting data capture')
        self.capture_data = True
        if not self.running:
            self.start();

    def stop_capture(self):
        """ Stop capturing data. Subsequent calls to read() and read_flush()
        will return null, until start_capture() is called. """

        if not self.capture_data:
            return

        self.logger.info('Stopping data capture')
        self.capture_data = False

    def set_marker(self, code, type='trigger', timestamp=precision_timer()):
        """ Label the data with a marker.

        code      - any integer value you wish to label the data with
        type      - 'trigger' meaning only one instance will be marked or
                    'switch' meaning all instances from now on will be marked
        timestamp - the exact timing at which the marker should be placed
                    (in seconds after epoch, floating point)
        """
        assert(type == 'switch' or type == 'trigger')

        self.marker_lock.acquire()
        m = Marker(code, type, timestamp)
        self.markers.append(m)
        self.logger.info('Received marker %s' % (m))
        self.marker_lock.release()

    def run(self):
        """ Don't call this directly. Use start() and start_capture() to start
        reading data from the device. """

        self.running = True

        # We keep track of the last 10 seconds of estimations of the sample rate
        # of the device in a circular buffer.
        self.estimated_sample_rates = collections.deque(maxlen=numpy.ceil(10/float(self.buffer_size_seconds)))

        # Open BDF file output
        if self.bdf_file != None:
            self.bdf_writer = psychic.BDFWriter(self.bdf_file,
                                            self.sample_rate, self.nchannels)
            self._set_bdf_values()
            self.bdf_writer.write_header()
            self.file_output = True
        else:
            self.file_output = False

        # Perform initialization of the device driver, which returns the
        # timestamp of the first data packet
        self.T0 = self._open()

        self.last_id = 0

        while self.running:
            try:
                # Record some data
                d = self._record_data();

                # Check whether the decoding of the data succeeded
                if d == None:
                    continue

                # Add markers to the data
                d = self._add_markers(d);

                # Write data without gain factor to file
                if self.file_output:
                    self.bdf_writer.write_raw(d)

                # Check whether calibration period is complete
                if precision_timer() > self.T0+self.calibration_time:
                    self.calibrated_event.set()

                if self.capture_data:
                    # Apply gain factor to data, producing values that
                    # correspond to actual voltage
                    d = golem.DataSet(X=d.X*self.gain+self.physical_min,
                                      default=d)

                    # Append the data to the buffer and notify
                    # any listeners (usually the classifier)
                    self.data_condition.acquire()
                    if self.data == None:
                        self.data = d
                    else:
                        self.data += d

                    self.data_condition.notify()
                    self.data_condition.release()
                
            except IOError, e:
                self.logger.error('I/O Error: %s' % e)
                raise

    def _estimate_timing(self, nsamples):
        """ Create timestamps for each sample, based on a number of timing
        schemes """

        dt = self.end_read_time - self.begin_read_time
        estimated_sample_rate = nsamples / dt
        self.estimated_sample_rates.append(estimated_sample_rate)
        smoothed_sample_rate = numpy.mean(self.estimated_sample_rates)

        relative_begin_read_time = self.begin_read_time - self.T0

        self.logger.debug('dt: %f, estimated sample rate: %f, smoothed sample rate: %f' % (dt, estimated_sample_rate, smoothed_sample_rate))

        I = numpy.atleast_2d( numpy.arange(1, nsamples+1, dtype=numpy.float ) )

        if self.timing_mode == 'fixed':
            t = I/float(self.sample_rate)
            t += self.last_id
            self.last_id = t[0,-1]

        elif self.timing_mode == 'end_read_relative':
            t = I/float(self.sample_rate)
            t += (self.end_read_time - t[0,-1]) - self.T0
            if t[0,0] <= self.last_id:
                t += 1/float(self.sample_rate)
            self.last_id = t[0,-1]

        elif self.timing_mode == 'smoothed_sample_rate':
            t = I/smoothed_sample_rate
            t += self.last_id
            self.last_id = t[0,-1]

        elif self.timing_mode == 'begin_read_relative':
            t = I/float(self.sample_rate)
            if relative_begin_read_time < self.last_id:
                relative_begin_read_time = self.last_id
            t += relative_begin_read_time
            self.last_id = t[0,-1]

        elif self.timing_mode == 'estimated_sample_rate':
            t = I/estimated_sample_rate
            if relative_begin_read_time < self.last_id:
                relative_begin_read_time = self.last_id
            t += relative_begin_read_time
            self.last_id = t[0,-1]

        else:
            self.logger.warning('Invalid timing mode, defaulting to begin_read_relative')
            t = I/float(self.sample_rate)
            t += relative_begin_read_time
            self.last_id = t[0,-1]

        return t

    def _add_markers(self, d):
        """ Label the data with markers. """

        self.marker_lock.acquire()

        if self.current_marker.type == 'trigger':
            Y = numpy.zeros((1, d.ninstances))
        else:
            Y = numpy.repeat([[self.current_marker.code]], d.ninstances, axis=1)

        future_markers = []
        for m in self.markers:
            # Determine the location of the marker in the datastream
            y_index = numpy.searchsorted(d.I[0,:], m.timestamp-self.T0)

            if y_index <= 0:
                # timestamp lies in the past, oh dear!
                # mark the first sample, the marker is delayed.
                self.current_marker = m
                if m.type == 'trigger':
                    Y[0,0] = m.code
                else:
                    Y[0,0:] = m.code

            elif y_index >= d.ninstances:
                # timestamp lies in the future, save for a later time
                future_markers += [m]
            else:
                # timestamp is present in current data segment
                self.current_marker = m
                if m.type == 'trigger':
                    Y[0,y_index] = m.code
                else:
                    Y[0,y_index:] = m.code

            # Write some debug info
            self.logger.debug('For marker %s, found y_index of %d, (T0=%f)' % (m, y_index, self.T0))
            if y_index < d.ninstances:
                self.markerlog.write('%f, %f, %d, %d, %f, %f\n' % (m.timestamp,
                                                                   m.time_received,
                                                                   m.code,
                                                                   y_index,
                                                                   m.timestamp-self.T0,
                                                                   d.I[0,0]))
            self.markerlog.flush()

        self.markers = future_markers

        self.marker_lock.release()

        return golem.DataSet(Y=Y, default=d)

    def set_parameter(self, name, values):
        if name == 'bdf_file':
            if len(values) < 1 or type(values[0]) != str:
                raise DeviceError('invalid value for BDF file.')

            self.bdf_file = values[0]
            return True

        elif name == 'timing_mode':
            if len(values) < 1:
                raise DeviceError('missing value for timing_mode.')
            
            if values[0] in ['fixed', 'end_read_relative', 'estimated_sample_rate', 'smoothed_sample_rate', 'begin_read_relative']:
                self.timing_mode = values[0]
                return True
            else:
                raise DeviceError('invalid timing_mode for device.')


        elif name == 'buffer_size_seconds':
            if self.running:
                raise DeviceError('Cannot set parameter because the device is already opened.')

            if len(values) < 1 or (type(values[0]) != float and type(values[0]) != int):
                raise DeviceError('invalid value for buffer size.')

            self.buffer_size_seconds = values[0]
            return True

        elif name == 'channel_names':
            if len(values) != self.nchannels:
                raise DeviceError('Number of channel names should be equal to number of (target) channels of the device (%d).' % self.nchannels)

            self.channel_names = values
            self.feat_lab = [self.channel_names[x] for x in self.target_channels]
            return True

        elif name == 'target_channels':
            if self.running:
                raise DeviceError('Cannot set parameter because the device is already opened.')

            if len(values) < 1:
                raise DeviceError('Specify at least one target channel.')

            target_channels = []

            for channel_name in values:
                if type(channel_name) == str:
                    if not channel_name in self.channel_names:
                        raise DeviceError('Channel %s is not a valid channel for this device.' % channel_name)

                    target_channels.append( self.channel_names.index(channel_name) )
                elif type(channel_name) == float:
                    raise DeviceError('Invalid channel index or name: %f, please use integers or strings.' % channel_name)
                else:
                    target_channels.append(channel_name)

            self.target_channels = target_channels
            self.nchannels = len(self.target_channels)
            self.feat_lab = [self.channel_names[x] for x in self.target_channels]
            return True
        else:
            return False

    def get_parameter(self, name):
        if name == 'bdf_file':
            return self.bdf_writer.f.name if self.file_output else '<none>'
        elif name == 'timing_mode':
            return self.timing_mode
        elif name == 'buffer_size_seconds':
            return self.buffer_size_seconds
        elif name =='nchannels':
            return self.nchannels
        elif name =='channel_names':
            return self.feat_lab
        elif name == 'target_channels':
            return self.target_channels
        else:
            return False
