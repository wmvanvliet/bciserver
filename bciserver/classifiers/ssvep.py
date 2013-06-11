import matplotlib.pyplot as plt

import golem, psychic
import scipy
import scipy.signal
import traceback
import numpy as np

from classifier import Classifier
from ..bci_exceptions import ClassifierException

class SSVEP(Classifier):
    """
    Implements an online SSVEP classifier that can desinguish between flickering
    stimuli. Based on the Minimum Energy Combination method.

    Chumerin, N., Manyakov, N. V, Combaz, A., Robben, A., van Vliet, M., Van
    Hulle, M. M., Manyakov, N., et al. (2011). Steady state visual evoked
    potential based computer gaming - The Maze. The 4th International ICST
    Conference on Intelligent Technologies for Interactive Entertainment
    (INTETAIN). Genoa, Italy, May 25-27, in press.
    """
    def __init__(self, engine, recorder, window_size=2.0, window_step=0.5, freqs=[60/4., 60/5., 60/6., 60/7.], bandpass=[2, 45], cl_type='MNEC', nharmonics=3):
        """ Constructor.

        Required parameters:
        recorder: The Recorder object to read data from

        Keyword parameters (configures the classifier): 
        window_size: The window size in seconds to use on the data
        window_step: The window step in seconds to use on the data
        freqs: The frequencies in Hertz of the SSVEP stimuli to look for.
        bandpass: [lo, hi] cutoff frequencies for the bandpass filter to use on the data
        """
        self.window_size = window_size
        self.window_step = window_step
        self.freqs = freqs
        self.bandpass = bandpass
        self.nharmonics = nharmonics
        self.pipeline = None
        self.cl_type = cl_type

        # Figure out a sane target sample rate, using only a decimation factor
        self.target_sample_rate = np.floor(recorder.sample_rate / np.max([1, np.floor(recorder.sample_rate / 200)]))
    
        Classifier.__init__(self, engine, recorder)

    def _construct_pipeline(self):
        self.logger.info('Creating pipeline')
        self.logger.info("cl_type: %s" % self.cl_type)
        self.logger.info("freqs: %s" % self.freqs)
        self.logger.info("device sample_rate: %f" % self.recorder.sample_rate)
        self.logger.info("target sample_rate: %f" % self.target_sample_rate)
        self.logger.info("window_size: %f" % self.window_size)
        self.logger.info("window_step: %f" % self.window_step)
        self.logger.info("bandpass: %s" % str(self.bandpass))
        self.logger.info("nharmonics: %s" % self.nharmonics)

        self.bp_node = psychic.nodes.OnlineFilter(None)
        self.resample_node = psychic.nodes.Resample(self.target_sample_rate, max_marker_delay=1)
        self.window_node = psychic.nodes.OnlineSlidingWindow(int(self.window_size*self.target_sample_rate), int(self.window_step*self.target_sample_rate), ref_point=1.0)

        if self.cl_type.lower() == 'mnec':
            self.classifier_node = psychic.nodes.MNEC(self.target_sample_rate, self.freqs, self.nharmonics, nsamples=int(self.window_size*self.target_sample_rate, ))
        elif self.cl_type.lower() == 'canoncorr':
            self.classifier_node = psychic.nodes.CanonCorr(self.target_sample_rate, self.freqs, self.nharmonics, nsamples=int(self.window_size*self.target_sample_rate))
        else:
            raise ClassifierException(0, "Classifier type must be one of: ['MNEC', 'canoncorr'], not %s" % self.cl_type)

        # Go over the nodes and initialize them (to avoid having to train later)
        self.bp_node.filter = scipy.signal.iirfilter(4, [self.bandpass[0]/(self.target_sample_rate/2.0), self.bandpass[1]/(self.target_sample_rate/2.0)])
        self.resample_node.old_samplerate = self.recorder.sample_rate
        self.classifier_node.train_(None)
        
        self.pipeline = golem.nodes.Chain([self.bp_node, self.resample_node, self.window_node, self.classifier_node])

    def _reset(self):
        """ Reset the classifier. Flushes all collected data."""
        super(SSVEP, self)._reset()

        if self.pipeline:
            self.window_node.reset()

    def _train(self, d):
        """ Construct and initialize pipeline, which can take some time. """
        self._construct_pipeline()

        if d:
            d.save('test_data.dat')

        self.logger.info('Training complete')
        self.training_complete = True

    def _apply(self, d):
        """ Apply the classifier on a dataset. """
        if d.ninstances == 0:
            return

        try:
            result = self.pipeline.apply(d)
            self.logger.debug('Result was: %s at %s' % (result.X.ravel(), result.I))
            # send result to client
            if self.engine != None:
                for i in range(0, result.ninstances):
                    self.engine.provide_result(result.X[:,i].ravel().tolist())
        except Exception as e:
            self.logger.warning('%s' % e.message)
            traceback.print_exc()

    def set_parameter(self, name, value):
        if self.state != 'idle' or self.training_complete:
            raise ClassifierException('Can only change this parameter in idle mode, before training.')

        parameter_set = False

        if name == 'cl_type':
            if value[0].lower() != 'mnec' and value[0].lower() != 'canoncorr':
                raise ClassifierException(0, "cl_type must be one of: ['MNEC', 'canoncorr'].");

            self.cl_type = value[0]
            parameter_set = True

        elif name == 'window_size':
            if len(value) < 1 or (type(value[0]) != float and type(value[0]) != int):
                raise ClassifierException('Invalid value for window size.')
            self.window_size = float(value[0])
            parameter_set = True

        elif name == 'window_step':
            if len(value) < 1 or (type(value[0]) != float and type(value[0]) != int):
                raise ClassifierException('Invalid value for window step.')
            self.window_step = float(value[0])
            parameter_set = True

        elif name == 'bandpass':
            if len(value) < 2 or (type(value[0]) != float and type(value[1]) != int) or (type(value[1]) != float and type(value[1]) != int):
                raise ClassifierException('Bandpass parameter needs two numeric values.')

            self.bandpass = (value[0], value[1])
            parameter_set = True

        elif name == 'freqs':
            if len(value) < 1:
                raise ClassifierException('No value given for stimulus frequencies.')

            self.freqs = []
            for freq in value:
                if type(freq) != float and type(freq) != int:
                    raise ClassifierException('Invalid value for stimulus frequency: %s' % freq)
                self.freqs.append(float(freq))

            parameter_set = True

        elif name == 'nharmonics':
            if len(value) < 1:
                raise ClassifierException('No value given for nharmonics.')

            if type(value[0]) != int:
                raise ClassifierException('Number of harmonics should be an int value.')

            self.nharmonics = value[0]
            parameter_set = True

        elif name == 'target_sample_rate':
            if type(value[0]) != int and type(value[0]) != float:
                raise ClassifierException('Value for target_sample_rate must be numeric.')

            self.target_sample_rate = value[0]
            parameter_set = True

        return parameter_set

    def get_parameter(self, name):
        if name == 'cl_type':
            return self.cl_type
        elif name == 'window_step':
            return self.window_step
        elif name == 'window_size':
            return self.window_size
        elif name == 'target_sample_rate':
            return self.target_sample_rate
        elif name == 'bandpass':
            return self.bandpass
        elif name == 'freqs':
            return self.freqs
        elif name == 'nharmonics':
            return self.nharmonics
        else:
            return False
