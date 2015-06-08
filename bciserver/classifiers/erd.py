import matplotlib.pyplot as plt

import psychic
import numpy as np
import scipy

from classifier import Classifier
from ..bci_exceptions import ClassifierException

class ERD(Classifier):
    """ Implements an online ERD classifier. """
    def __init__(self, engine, recorder, window_size=2.0, window_step=0.5, ncomp=4, bandpass=[8, 15]):
        """ Constructor.

        Required parameters:
        recorder: The Recorder object to read data from

        Keyword parameters (configures the classifier): 
        window_size: The window size in seconds to use on the data
        window_step: The window step in seconds to use on the data
        ncomp: Number of ICA components to use
        bandpass: [lo, hi] cutoff frequencies for the bandpass filter to use on the data
        """
        self.window_size = window_size
        self.window_step = window_step
        self.ncomp = ncomp
        self.bandpass = bandpass
        self.pipeline = None
        self.target_sample_rate = 256
    
        Classifier.__init__(self, engine, recorder)

        self.logger.info("sample_rate: %f" % recorder.sample_rate)
        self.logger.info("window_size: %f" % window_size)
        self.logger.info("window_step: %f" % window_step)
        self.logger.info("ncomp: %d" % ncomp)
        self.logger.info("bandpass: %s" % bandpass)

    def _construct_pipeline(self):
        self.logger.info('Creating pipeline')

        self.classification = psychic.nodes.Chain([
            psychic.nodes.OnlineFilter( lambda s : scipy.signal.iirfilter(2, [self.bandpass[0]/(s/2.0), self.bandpass[1]/(s/2.0)]) ),
            psychic.nodes.Resample(self.target_sample_rate, max_marker_delay=1),
            psychic.nodes.OnlineSlidingWindow(int(self.window_size*self.target_sample_rate), int(self.window_step*self.target_sample_rate)),
            psychic.nodes.spatialfilter.CSP(self.ncomp),
            psychic.nodes.FeatMap(lambda x: np.log(np.var(x, axis=1))),
            psychic.nodes.LDA(),
        ])

    def _reset(self):
        """ Reset the classifier. Flushes all collected data."""
        super(ERD, self)._reset()

        if self.pipeline:
            self.window_node.reset()
            self.thres_node.reset()

    def _train(self):
        """ Train the classifier on a dataset. """

        d = self.recorder.read(block=False)
        if not d:
            raise ClassifierException('First collect some data before training.')

        # Save a snapshot of the training data to disk
        d.save('test_data.dat')

        # Convert markers to classes
        Y = np.zeros((3, d.ninstances), dtype=np.bool)

        Y[0,:] = (d.Y == 1)[0,:]
        Y[1,:] = (d.Y == 2)[0,:]
        Y[2,:] = (d.Y == 3)[0,:]

        d = psychic.DataSet(labels=Y, cl_lab=['on','off', 'sweep'], default=d)

        self._construct_pipeline()

        # Train the pipeline
        self.classification.train(d)
        self.logger.info('Training complete')

        # Send a debug plot to client
        self._send_debug_image(d)

        self.window_node.reset()
        self.thres_node.reset()

        self.training_complete = True

    def _apply(self, d):
        """ Apply the classifier on a dataset. """
        if d.ninstances == 0:
            return

        try:
            result = self.pipeline.apply(d)
            self.logger.debug('Result was: %s:%s at %s' % (result.data[:,0], result.labels[:,0], result.ids))
            # send result to client
            if self.engine != None:
                for i in range(0, result.labels.shape[0]):
                    self.engine.provide_result([result.data[i,0], int(result.labels[i,0])])
        except Exception as e:
            self.logger.warning('%s' % e.message)

    def _generate_debug_image(self, d):
        """ Send image describing the training data. """

        self.window_node.reset()
        d2 = self.pipeline.apply(d)
        fig = plt.figure()

        ax = fig.add_subplot(311)
        ax.plot(d.ids, d.xs[:,0])
        ax.set_ylabel('mV')
        ax.set_xlim([np.min(d.ids), np.max(d.ids)])
        ax.grid()

        ax = fig.add_subplot(312)
        ax.plot(d2.ids, d2.xs[:,0])
        ax.axhline(self.thres_node.hi, color='r')
        ax.axhline(self.thres_node.lo, color='g')
        ax.set_ylabel('mean(correlation)')
        ax.set_xlim([np.min(d2.ids), np.max(d2.ids)])
        ax.grid()

        ax = fig.add_subplot(313)
        ax.plot(d2.ids, d2.ys[:,0], '-r')
        ax.plot(d.ids, d.ys[:,0], '-b')
        ax.set_ylabel('fixating?')
        ax.set_xlabel('time (s)')
        ax.set_xlim([np.min(d2.ids), np.max(d2.ids)])
        ax.set_ylim([-0.2, 2])
        ax.grid()

        return fig

    def set_parameter(self, name, value):
        if name == 'thresholds':
            if len(value) < 2 or (type(value[0]) != float and type(value[1]) != int) or (type(value[1]) != float and type(value[1]) != int):
                raise ClassifierException('This parameter needs two numeric value.')

            if(self.state != 'application'):
                raise ClassifierException('Can only change this parameter in application mode, after training.')

            self.thres_node.hi = float(value[0])
            self.thres_node.lo = float(value[1])
            self.logger.info('Setting new thresholds to %f - %f' % (self.thres_node.hi, self.thres_node.lo))
            return True

        if self.state != 'idle' or self.training_complete:
            raise ClassifierException('Can only change this parameter in idle mode, before training.')

        parameter_set = False

        if name == 'window_size':
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
                raise ClassifierException('This parameter needs two numeric value.')

            self.bandpass = (value[0], value[1])
            parameter_set = True

        elif name == 'freq':
            if len(value) < 1 or (type(value[0]) != float and type(value[0]) != int):
                raise ClassifierException('Invalid value for stimulus frequency.')
            self.freq = float(value[0])
            parameter_set = True

        elif name == 'target_sample_rate':
            if type(value[0]) != int and type(value[0]) != float:
                raise ClassifierException('Value for target_sample_rate must be numeric.')

            self.target_sample_rate = value[0]
            self.target_window = (int(self.target_sample_rate*self.window[0]), int(self.target_sample_rate*self.window[1]))
            parameter_set = True

        return parameter_set

    def get_parameter(self, name):
        if name == 'thresholds':
            if not self.training_complete:
                raise ClassifierException('This parameter is only available after training.')
            return [self.thres_node.hi, self.thres_node.lo]

        elif name == 'window_step':
            return self.window_step
        elif name == 'window_size':
            return self.window_size
        elif name == 'target_sample_rate':
            return self.target_sample_rate
        elif name == 'bandpass':
            return self.bandpass
        elif name == 'freq':
            return self.freq
        else:
            return False
