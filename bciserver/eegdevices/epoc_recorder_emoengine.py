import epoc
import logging
import numpy
import golem
import time

from . import Recorder, precision_timer, DeviceError

class EPOC(Recorder):
    """ 
    Class to record from the EPOC device. For more information, see the generic
    Recorder class.
    """

    def __init__(self, composer=False, buffer_size_seconds=0.5, bdf_file=None, timing_mode='smoothed_sample_rate'):
        """ Open the EPOC device or connect to EmoComposer

        Keyword arguments:

        test:                Set this to true to connect to a locally running
                             EmoComposer instead. Useful for debugging.

        buffer_size_seconds: The amount of seconds of data to read from the
                             EPOC device before it will be decoded. Defaults to
                             0.2 seconds.

        bdf_file:            Dump all recorded data (regardless whether the
                             device is in capture more or not) to a BDF file
                             with the given filename.
        """

        self.sample_rate = 128
        self.nchannels = 14 
        self.calibration_time = 0 # Signal does not need to stabilize
        self.physical_min = 0
        self.physical_max = 16000
        self.digital_min = 0
        self.digital_max = 16000
        self.gain = 1.0


        self.logger = logging.getLogger('EPOC Recorder')

        self.channel_names = ['AF3', 'AF4', 'F3', 'F4', 'F7', 'F8', 'FC5', 'FC6', 'P7', 'P8', 'T7', 'T8', 'O1', 'O2']
        self.feat_lab = list(self.channel_names)
        self.dataChannels = numpy.array([
            epoc.channel.AF3,
            epoc.channel.AF4,
            epoc.channel.F3,
            epoc.channel.F4,
            epoc.channel.F7,
            epoc.channel.F8,
            epoc.channel.FC5,
            epoc.channel.FC6,
            epoc.channel.P7,
            epoc.channel.P8,
            epoc.channel.T7,
            epoc.channel.T8,
            epoc.channel.O1,
            epoc.channel.O2,
        ])

        self.composer = composer
        
        # Configuration of the generic recorder object
        Recorder.__init__(self, buffer_size_seconds, bdf_file, timing_mode)

        self._reset()

    def _reset(self):
        super(EPOC, self)._reset()
        self.begin_read_time = precision_timer()
        self.end_read_time = self.begin_read_time

    def _open(self):
        self.logger.debug('Opening EPOC device...')
        if self.composer:
            self.logger.debug('Connecting to composer.')
            epoc.EngineRemoteConnect('127.0.0.1', 1726)
        else:
            epoc.EngineConnect()

        epoc.DataChannelSelect(self.dataChannels[self.target_channels])

        self.driftlog = open('drift.log', 'w')
        self.driftlog.write('Now, Target, Obtained, Drift, Cycle\n')

        # Busy wait for the first data
        T0 = None
        data_available = False
        while T0 == None:
            e = epoc.EngineGetNextEvent()
            if e == None:
                continue

            elif e.type == epoc.event.UserAdded:
                # Start the measurement
                self.userId = e.userId;
                epoc.DataSetBufferSizeInSec(self.buffer_size_seconds+1)
                epoc.DataAcquisitionEnable(self.userId, True)
                data_available = True

            elif e.type == epoc.event.EmoStateUpdated and data_available:
                # First data available, this is T0
                T0 = precision_timer()
                self.end_read_time = T0

        return T0

    def stop(self):
        super(EPOC, self).stop()
        epoc.EngineDisconnect()

    def _record_data(self):
        self.begin_read_time = self.end_read_time
        self.end_read_time = self.begin_read_time + self.buffer_size_seconds
        time_to_wait = max(0, self.end_read_time - precision_timer())
        time.sleep(time_to_wait)

        e = epoc.EngineGetNextEvent()
        if e == None:
            return None

        elif e.type == epoc.event.EmulatorError:
            self.logger.error('Emulator error (maybe it disconnected?)')
            self.stop()

        elif e.type == epoc.event.EmoStateUpdated:
            d = epoc.DataGet(self.userId)
            d = self._to_dataset(d)
            return d

    def _to_dataset(self, data):
        """ Converts the data recorded from the EPOC device into a Golem dataset.
        """

        if data == None or data.size == 0:
            self.logger.warning('Data corrupt: no valid frames found in data packet')
            return None

        X = data
        Y = numpy.zeros((1, X.shape[1]))
        I = self._estimate_timing(X.shape[1])

        self.logger.debug('Number of samples parsed: %d' % X.shape[1])
        return golem.DataSet(X=X, Y=Y, I=I, feat_lab=self.feat_lab)

    def _flush_buffer(self):
        """ Flush data in EPOC buffer """
        self.begin_read_time = precision_timer()
        epoc.DataGet(self.userId)

    def _set_bdf_values(self):
        """ Set default values for the BDF Writer """
        self.bdf_writer.n_channels = self.nchannels
        self.bdf_writer.n_samples_per_record = [int(self.sample_rate*self.bdf_writer.record_length) for x in range(self.nchannels)]
        self.bdf_writer.transducer_type = ['active salt-water electrode' for x in range(self.nchannels)]
        self.bdf_writer.physical_min = [self.physical_min for x in range(self.nchannels)]
        self.bdf_writer.physical_max = [self.physical_max for x in range(self.nchannels)]
        self.bdf_writer.digital_min = [self.digital_min for x in range(self.nchannels)]
        self.bdf_writer.digital_max = [self.digital_max for x in range(self.nchannels)]
        self.bdf_writer.units = ['uV' for x in range(self.nchannels)]
        self.bdf_writer.prefiltering = ['HP:0.2 Hz LP:52-274Hz' for x in range(self.nchannels)]
        self.bdf_writer.label = list(self.feat_lab) # Make a copy of the list, don't just pass a reference
        self.bdf_writer.reserved = ['' for x in range(self.nchannels)]
        self.bdf_writer.append_status_channel()
