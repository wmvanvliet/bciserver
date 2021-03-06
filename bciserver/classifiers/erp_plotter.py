import psychic
import numpy
import scipy

from classifier import Classifier
from ..bci_exceptions import ClassifierException

class ERPPlotter(Classifier):
    """ Implements a classifier that just plots the ERP.
    This class acts as a consumer to a Recorder
    """
    def __init__(self, engine, recorder, window=(0, 1.0), bandpass=[0.5, 15]):
        """ Constructor.

        Required parameters:
        recorder: The imec.Recorder object to read data from

        Keyword parameters (configures the classifier): 
        window: A pair (from, to) in samples of the window to extract around the stimulation onset
        bandpass: [lo, hi] cutoff frequencies for the bandpass filter to use on the data
        """
        assert len(window) == 2

        # Create pipeline
        self.bp_node = psychic.nodes.OnlineFilter( lambda s : scipy.signal.iirfilter(3, [bandpass[0]/(s/2.0), bandpass[1]/(s/2.0)]) )
        self.preprocessing = psychic.nodes.Chain([self.bp_node])

        self.window = window
        self.cl_lab = None
        self.format = 'png'

        Classifier.__init__(self, engine, recorder)

        self.logger.info('sample_rate: %d Hz' % recorder.sample_rate)
        self.logger.info('bandpass: %s' % bandpass)

    def _train(self, d):
        """ Trains on the data collected thus far. """

        if not d:
            raise ClassifierException('First collect some data before training.')

        # Save a snapshot of the training data to disk
        d.save('test_data.dat')

        # Do preprocessing
        self.preprocessing.train(d)
        d = self.preprocessing.apply(d)
        self.feat_lab = d.feat_lab

        mdict = {}
        for i in numpy.unique(d.labels):
            if i == 0:
                continue
            mdict[i] = 'target %02d' % i

        self.slice_node = psychic.nodes.OnlineSlice(mdict, self.window)
        d = self.slice_node.train_apply(d)

        # Send a debug plot to Unity
        self._send_debug_image(d)

        self.logger.info('Training complete')
        self.training_complete = True
        self.slice_node.reset()

    def _apply(self, d):
        """ Applies classifier to a dataset. """
        pass
    
    def _generate_debug_image(self, d):
        """ Generate image describing the training data. """
        d = psychic.DataSet(cl_lab=self.cl_lab, default=d)
        fig = psychic.plot_erp(d, enforce_equal_n=False)
        fig.set_size_inches(7, 11)
        return fig

    def set_parameter(self, name, value):
        if self.state != 'idle' or self.training_complete:
            raise ClassifierException('Can only change this parameter in idle mode, before training.')

        if name == 'bandpass':
            if len(value) < 2 or (type(value[0]) != float and type(value[1]) != int) or (type(value[1]) != float and type(value[1]) != int):
                raise ClassifierException('This parameter needs two numeric value.')

            self.bandpass = (value[0], value[1])
            return True

        elif name == 'window':
            if len(value) < 2 or (type(value[0]) != float and type(value[1]) != int) or (type(value[1]) != float and type(value[1]) != int):
                raise ClassifierException('This parameter needs two numeric value.')

            self.window = (value[0], value[1])
            return True

        elif name == 'cl_lab':
            self.cl_lab = value
            return True

        elif name == 'format':
            if len(value) < 1:
                raise ClassifierException('Missing value for format.')

            if not value[0] in ['png', 'jpg', 'pdf', 'svg']:
                raise ClassifierException('Invalid value for format.')

            self.format = value[0]
            return True

        return False

    def get_parameter(self, name):
        if name == 'window':
            return self.window
        elif name == 'bandpass':
            return self.bandpass
        elif name == 'cl_lab':
            return self.cl_lab
        elif name == 'format':
            return self.format
        else:
            return False
