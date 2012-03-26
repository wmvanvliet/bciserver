import biosemi_reader
import logging
import numpy
import golem
import time

from . import Recorder, precision_timer, DeviceError

class BIOSEMI(Recorder):
    """ 
    Class to record from a BIOSEMI device. For more information, see the generic
    Recorder class.
    """

    def __init__(self, buffer_size_seconds=0.5, status_as_markers=True, bdf_file=None, timing_mode='fixed'):
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
            self.reader = biosemi_reader.BiosemiReader(
                buffersize=self.buffer_size_bytes)

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
        X = X[self.target_channels,:]
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
