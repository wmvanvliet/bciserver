import logging
import numpy
import golem
import psychic
import time
from . import Recorder, precision_timer, DeviceError

class Emulator(Recorder):
    """ Class that emulates EEG signals. Use this to build and test your
    application without an actual EEG device present. This class can also play
    back previously recorded .bdf files.

    For more information, see the documentation of the generic Recorder class.
    """


    def __init__(self, bdf_file=None, buffer_size_seconds=0.5,
                 bdf_playback_file=None, sample_rate=1000, nchannels=8):
        """ 
        Keyword arguments:

        bdf_playback_file:   File object or filename of BDF file to playback
                             data from.

        buffer_size_seconds: The size of the internal buffer (in seconds.) Data
                             will be generated in chunks of size
                             buffer_size_seconds * sample_rate. Do not use in
                             combination with bdf_playback_file. When playing
                             back BDF data, the record size noted in the BDF
                             file will be used.  Defaults to one second.

        sample_rate:          Samplerate (in Hz) at which data is generated. Do
                             not use in combination with bdf_playback_file.
                             When playing back BDF data, the sample_rate noted
                             in the BDF file will be used. Defaults to 1000.

        nchannels:           Number of channels of data to generate. Do not use
                             in combination with bdf_playback_file. When
                             playing back BDF data, the number of channels
                             noted in the BDF file will be used. Defaults to 8.

        bdf_file:            Dump all recorded data (regardless whether the
                             device is in capture more or not) to a BDF file
                             with the given filename.
        """

        # Configuration of the emulator
        self.sample_rate = sample_rate
        self.nchannels = nchannels
        self.calibration_time = 10 # We pretend that the signal takes 10
                                   # seconds to stabilise.
        self.physical_min = -625
        self.physical_max = 624
        self.digital_min = 0
        self.digital_max = 4094
        self.gain = ((self.physical_max-self.physical_min) /
                    float(self.digital_max-self.digital_min))
        self.channel_names = ['channel %02d' % x for x in range(self.nchannels)]
        self.feat_lab = list(self.channel_names)

        self.bdf_playback_file = bdf_playback_file
        self.file_input = False

        # Configure logging
        self.logger = logging.getLogger('Emulator')

        self.running = False
            
        # Configuration of the generic recorder object
        Recorder.__init__(self, buffer_size_seconds, bdf_file, 'fixed')

    def _reset(self):
        super(Emulator, self)._reset()
        self.begin_read_time = precision_timer()
        self.end_read_time = self.begin_read_time
        self.nsamples = 0
        self.remaining_frames_in_record = None

    def _open(self):
        # Open supplied BDF file for playback
        if self.bdf_playback_file != None:
            self.bdf_reader = psychic.BaseBDFReader(open(self.bdf_playback_file, 'rb'))
            self.header = h = self.bdf_reader.read_header()
            self.nchannels = h['n_channels']-1 # one status channel
            #self.buffer_size_seconds = h['record_length']
            self.sample_rate = h['n_samples_per_record'][0] / h['record_length']
            self.feat_lab = h['label']
            self.physical_min = h['physical_min'][0]
            self.physical_max = h['physical_max'][0]
            self.digital_min = h['digital_min'][0]
            self.digital_max = h['digital_max'][0]
            self.gain = ((self.physical_max-self.physical_min) /
                         float(self.digital_max-self.digital_min))
            self.file_input = True
        else:
            self.file_input = False

        T0 = precision_timer()
        self.end_read_time = T0
        return T0

    def stop(self):
        super(Emulator, self).stop()
        if self.file_input:
            self.bdf_reader.close()

    def _record_data(self):
        """ Either generates some random data or extracts a record from the BDF
        file. Returns result as a Golem dataset.
        """
        self.begin_read_time = self.end_read_time
        self.end_read_time = self.begin_read_time + self.buffer_size_seconds
        time_to_wait = max(0, self.end_read_time - precision_timer())
        time.sleep(time_to_wait)

        # Calculate the number of samples to generate
        target = int( (self.end_read_time - self.T0) * self.sample_rate )
        nsamples = target - self.nsamples

        if nsamples <= 0:
            return None

        if self.file_input:
            # Determine number of records to read
            samples_to_read = nsamples
            if self.remaining_frames_in_record != None:
                samples_to_read -= self.remaining_frames_in_record.shape[0]
            nrecords_to_read = int(numpy.ceil(samples_to_read / float(self.header['record_length']*self.sample_rate)))

            X = self.remaining_frames_in_record
            for i in range(nrecords_to_read):
                if X == None:
                    X = self.bdf_reader.read_record()
                else:
                    X = numpy.vstack((X, self.bdf_reader.read_record()))

            data_mask = [i for i, lab in enumerate(self.header['label'])
                        if lab != 'Status']
            status_mask = self.header['label'].index('Status')
            feat_lab = [self.header['label'][i] for i in data_mask]

            self.remaining_frames_in_record = X[nsamples:,:]
            Y = X[:nsamples, status_mask].reshape(1, -1).astype(numpy.int) & 0xffff
            X = X[:nsamples, data_mask].T
        else:
            X = numpy.random.random_integers(self.digital_min,
                                             self.digital_max,
                                             (self.nchannels, nsamples)
                                            )
            feat_lab = self.feat_lab

            Y = numpy.zeros((1, nsamples))

        I = self._estimate_timing(X.shape[1])
        d = golem.DataSet(X=X, Y=Y, I=I, feat_lab=feat_lab)
        self.nsamples += d.ninstances

        return d

    def _set_bdf_values(self):
        """ Set default values for the BDF Writer """
        self.bdf_writer.n_channels = self.nchannels
        self.bdf_writer.n_samples_per_record = [int(self.sample_rate*self.bdf_writer.record_length)
                                                for x in range(self.nchannels)]
        self.bdf_writer.transducer_type = ['Random noise' for x in range(self.nchannels)]
        self.bdf_writer.physical_min = [self.physical_min for x in range(self.nchannels)]
        self.bdf_writer.physical_max = [self.physical_max for x in range(self.nchannels)]
        self.bdf_writer.digital_min = [self.digital_min for x in range(self.nchannels)]
        self.bdf_writer.digital_max = [self.digital_max for x in range(self.nchannels)]
        self.bdf_writer.units = ['uV' for x in range(self.nchannels)]
        self.bdf_writer.prefiltering = ['' for x in range(self.nchannels)]
        self.bdf_writer.label = list(self.feat_lab)
        self.bdf_writer.reserved = ['' for x in range(self.nchannels)]
        self.bdf_writer.append_status_channel()

    def set_marker(self, code, type='trigger', timestamp=precision_timer()):
        """ Override to prevent a user from setting markers
        when playing back a BDF file """
        if self.file_input:
            self.logger.warning('Cannot set marker while playing back BDF file, marker ignored.')
            return
        else:
            super(Emulator, self).set_marker(code, type, timestamp)

    def set_parameter(self, name, values):
        if super(Emulator, self).set_parameter(name, values):
            return True

        parameter_set = False
        if self.running and self.file_output:
            raise DeviceError('cannot change parameters while writing to BDF file.')

        elif name == 'bdf_playback_file':
            if self.running:
                raise DeviceError('cannot change parameter: device is already opened.')

            if len(values) < 1:
                raise DeviceError('invalid value for bdf_playback_file.')

            self.bdf_playback_file = values[0]

        elif name == 'sample_rate':
            if self.file_input:
                raise DeviceError('cannot change sample rate when reading from BDF file.')
            if len(values) < 1 or (type(values[0]) != float and type(values[0]) != int):
                raise DeviceError('invalid value for sample rate.')
            self.sample_rate = values[0]
            parameter_set = True

        elif name == 'nchannels':
            if self.file_input:
                raise DeviceError('cannot change number of channels when reading from BDF file.')
            if len(values) < 1 or type(values[0]) != int or values[0] == 0:
                raise DeviceError('invalid value for number of channels.')
            self.nchannels = values[0]
            self.gain = ((self.physical_max-self.physical_min) /
                        float(self.digital_max-self.digital_min))
            self.feat_lab = ['channel %02d' % x for x in range(self.nchannels)]
            parameter_set = True

        # Rewrite the BDF header if necessary
        if parameter_set and self.file_output:
            self._set_bdf_values()
            self.bdf_writer.write_header()

        return parameter_set

    def get_parameter(self, name):
        value = super(Emulator, self).get_parameter(name)
        if value:
            return value

        if name == 'bdf_playback_file':
            return self.bdf_playback_file
        elif name == 'sample_rate':
            return self.sample_rate
        else:
            return False
