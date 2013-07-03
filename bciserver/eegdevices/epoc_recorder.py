import logging
import numpy
import golem
import usb.core
import usb.util
import array
from Crypto.Cipher import AES
from Crypto import Random

from . import Recorder, precision_timer, DeviceError
from background_reader import BackgroundReader

sensorBits = {
    'F3': [10, 11, 12, 13, 14, 15, 0, 1, 2, 3, 4, 5, 6, 7],
    'FC5': [28, 29, 30, 31, 16, 17, 18, 19, 20, 21, 22, 23, 8, 9],
    'AF3': [46, 47, 32, 33, 34, 35, 36, 37, 38, 39, 24, 25, 26, 27],
    'F7': [48, 49, 50, 51, 52, 53, 54, 55, 40, 41, 42, 43, 44, 45],
    'T7': [66, 67, 68, 69, 70, 71, 56, 57, 58, 59, 60, 61, 62, 63],
    'P7': [84, 85, 86, 87, 72, 73, 74, 75, 76, 77, 78, 79, 64, 65],
    'O1': [102, 103, 88, 89, 90, 91, 92, 93, 94, 95, 80, 81, 82, 83],
    'O2': [140, 141, 142, 143, 128, 129, 130, 131, 132, 133, 134, 135, 120, 121],
    'P8': [158, 159, 144, 145, 146, 147, 148, 149, 150, 151, 136, 137, 138, 139],
    'T8': [160, 161, 162, 163, 164, 165, 166, 167, 152, 153, 154, 155, 156, 157],
    'F8': [178, 179, 180, 181, 182, 183, 168, 169, 170, 171, 172, 173, 174, 175],
    'AF4': [196, 197, 198, 199, 184, 185, 186, 187, 188, 189, 190, 191, 176, 177],
    'FC6': [214, 215, 200, 201, 202, 203, 204, 205, 206, 207, 192, 193, 194, 195],
    'F4': [216, 217, 218, 219, 220, 221, 222, 223, 208, 209, 210, 211, 212, 213]
}

class EPOC(Recorder):
    """ 
    Class to record from the EPOC device. For more information, see the generic
    Recorder class.
    """

    def __init__(self, buffer_size_seconds=0.5, bdf_file=None, timing_mode='smoothed_sample_rate'):
        """ Open the EPOC device without using the EmoEngine.

        Keyword arguments:

        buffer_size_seconds: The amount of seconds of data to read from the
                             EPOC device before it will be decoded. Defaults to
                             0.2 seconds.

        bdf_file:            Dump all recorded data (regardless whether the
                             device is in capture more or not) to a BDF file
                             with the given filename.
        """

        self.sample_rate = 128
        self.bytes_per_sample = 32
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
        self.dataChannels = sensorBits.keys()

        # Configuration of the generic recorder object
        Recorder.__init__(self, buffer_size_seconds, bdf_file, timing_mode)

        self._reset()

    def _setup_crypto(self, sn):
        # Determine type: True = developer/research headset, False = consumer device
        type = 0 # feature[5]
        type &= 0xF
        type = 0

        # Construct the key using the serial number
        k = ['\0'] * 16
        k[0] = sn[-1]
        k[1] = '\0'
        k[2] = sn[-2]
        if type:
            k[3] = 'H'
            k[4] = sn[-1]
            k[5] = '\0'
            k[6] = sn[-2]
            k[7] = 'T'
            k[8] = sn[-3]
            k[9] = '\x10'
            k[10] = sn[-4]
            k[11] = 'B'
        else:
            k[3] = 'T'
            k[4] = sn[-3]
            k[5] = '\x10'
            k[6] = sn[-4]
            k[7] = 'B'
            k[8] = sn[-1]
            k[9] = '\0'
            k[10] = sn[-2]
            k[11] = 'H'
        k[12] = sn[-3]
        k[13] = '\0'
        k[14] = sn[-4]
        k[15] = 'P'

        key = ''.join(k)
        iv = Random.new().read(AES.block_size)
        self._cipher = AES.new(key, AES.MODE_ECB, iv)


    def _reset(self):
        super(EPOC, self)._reset()
        self.begin_read_time = precision_timer()
        self.end_read_time = self.begin_read_time

    def _open(self):
        self.logger.debug('Opening EPOC device...')
        dev = usb.core.find(idVendor=0x1234)
        if dev == None:
            dev = usb.core.find(idVendor=0x21A1)
        if dev == None:
            raise DeviceError('Cannot find device: is the EPOC dongle inserted?')
        serial_number = usb.util.get_string(dev, 256, dev.iSerialNumber)
        self._setup_crypto(serial_number)

        cfg = dev.get_active_configuration()[(1,0)]
        self.ep = cfg[0]

        # Set up buffers to hold data
        buffers = [array.array('B', " " * int(self.buffer_size_seconds * self.sample_rate) * self.bytes_per_sample) for n in xrange(4)]

        # Create reader
        self.reader = BackgroundReader(self.ep, buffers)

        # Start the background reader
        self._flush_buffer()
        T0 = self.begin_read_time
        self.reader.start()

        return T0

    def stop(self):
        super(EPOC, self).stop()
        try:
            self.reader.stop()
            self.reader.join(2*self.buffer_size_seconds)
        except AttributeError:
            pass

    def _record_data(self):
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

    def _get_level(self, data, bits):
        level = 0
        for i in range(13, -1, -1):
            level <<= 1
            b, o = (bits[i] / 8) + 1, bits[i] % 8
            level |= (ord(data[b]) >> o) & 1
        return level

    def _to_dataset(self, data):
        """ Converts the data recorded from the EPOC device into a Golem dataset.
        """
        if data == None or len(data) == 0:
            return None

        X = []
        for i in range(0, len(data)/self.bytes_per_sample):
            packet = data[i*self.bytes_per_sample:(i+1)*self.bytes_per_sample]
            raw_data = self._cipher.decrypt(packet[:16]) + self._cipher.decrypt(packet[16:])
            X.append([self._get_level(raw_data, bits) for bits in sensorBits.values()])

        X = numpy.array(X).T
        Y = numpy.zeros((1, X.shape[1]))
        I = self._estimate_timing(X.shape[1])

        self.logger.debug('Number of samples parsed: %d' % X.shape[1])
        return golem.DataSet(X=X, Y=Y, I=I, feat_lab=self.feat_lab)


    def _flush_buffer(self):
        """ Flush data in EPOC buffer """
        self.ep.read(10*32, timeout=0)
        self.begin_read_time = precision_timer()

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
