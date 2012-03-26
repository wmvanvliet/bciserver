import matplotlib
#matplotlib.use('Agg')
import matplotlib.pyplot as plt

import golem, psychic
import logging, sys
import threading
import numpy
import scipy
import cStringIO
import base64

from ..bci_exceptions import ClassifierException

class Classifier(threading.Thread):
    """ Implements an online P300 classifier.
    This class acts as a consumer to a Recorder
    """
    def __init__(self, engine, recorder, window=(0.0, 1.0), bandpass=[0.5, 15]):
        """ Constructor.

        Required parameters:
        recorder: The imec.Recorder object to read data from

        Keyword parameters (configures the classifier): 
        window: A pair (from, to) in samples of the window to extract around the stimulation onset
        bandpass: [lo, hi] cutoff frequencies for the bandpass filter to use on the data
        """
        threading.Thread.__init__(self)

        assert len(window) == 2

        self.target_sample_rate = 128
        self.window = window
        self.window_samples = (int(recorder.sample_rate*window[0]), int(recorder.sample_rate*window[1]))
        self.target_window = (int(self.target_sample_rate*window[0]), int(self.target_sample_rate*window[1]))

        # Initialize event to signal the classifier to switch states
        self.state_event = threading.Event()

        # Initialize log system
        self.logger = logging.getLogger('ERP Plotter')

        # Create pipeline
        self.logger.info('Creating pipelines')
        self.bp_node = psychic.nodes.OnlineFilter( lambda s : scipy.signal.iirfilter(3, [bandpass[0]/(s/2.0), bandpass[1]/(s/2.0)]) )
        self.resample_node = psychic.nodes.Resample(self.target_sample_rate, max_marker_delay=1)
        self.preprocessing = golem.nodes.Chain([self.bp_node, self.resample_node])

        self.recorder = recorder
        self.engine = engine
        self.running = False
        self.cl_lab = None
        self.format = 'png'

        self.logger.info('sample_rate: %d Hz' % recorder.sample_rate)
        self.logger.info('bandpass: %s' % bandpass)
        self.logger.info('window: %s' % str(window))

        self._reset() 

    def _reset(self):
        """ Resets the classifier. Flushes all collected data."""
        self.processed_data = None
        self.state = 'idle'
        self.prev_state = self.state
        self.state_event.clear()
        self.training_complete = False

    def change_state(self, new_state):
        """ Changes the state of the classifier to one of:
        'idle', 'data-collect', 'training', 'application'
        """

        assert (new_state == 'idle' or
                new_state == 'data-collect' or
                new_state == 'training' or
                new_state == 'application')

        self.prev_state = self.state
        self.state = new_state
        self.state_event.set()
        self.logger.info('Changed state to %s' % new_state)

    def _train(self):
        """ Trains on the data collected thus far. """

        d = self.recorder.read(block=False)
        if not d:
            raise ClassifierException('First collect some data before training.')

        # Save a snapshot of the training data to disk
        d.save('test_data.dat')

        # Do preprocessing
        self.preprocessing.train(d)
        d = self.preprocessing.apply(d)
        self.feat_lab = d.feat_lab

        mdict = {}
        for i in numpy.unique(d.Y):
            if i == 0:
                continue
            mdict[i] = 'target %02d' % i

        self.slice_node = psychic.nodes.OnlineSlice(mdict, self.window)
        d = self.slice_node.train_apply(d,d)

        # Send a debug plot to Unity
        self._send_debug_image(d)

        self.logger.info('Training complete')
        self.training_complete = True
        self.slice_node.reset()

    def _apply(self, d):
        """ Applies classifier to a dataset. """
        pass
    
    def run(self):
        assert self.recorder.running
        
        self.running = True
        while(self.running and self.recorder.running):
            if self.state_event.is_set():
                self.state_event.clear()

            if self.state == 'idle':
                # Do nothing
                self.recorder.stop_capture()

                self.engine.provide_mode('idle')
                self.state_event.wait()

            elif self.state == 'data-collect':
                if self.prev_state != 'data-collect':
                    self.recorder.flush()

                self.recorder.calibrated_event.wait()

                # Start capturing training data
                self.recorder.start_capture()

                self.engine.provide_mode('data-collect')
                self.state_event.wait()

            elif self.state == 'training':
                # Stop capturing training data
                self.recorder.stop_capture()

                self.engine.provide_mode('training')

                # Train on the recorded data
                try:
                    self._train()
                except Exception as e:
                    self.engine.error(e)
                    raise

                # Turn back to idle state
                self.change_state('idle')

            elif self.state == 'application':
                self.state_event.wait()
            else:
                self.logger.warning('Classifier in invalid state: %s' % self.state)
                self.state_event.wait()

            self.prev_state = self.state

    def stop(self):
        """ Make the classifier stop collecting data. Works in training as well as application mode.
        This will terminate the thread, which cannot be restarted. If you want to continue collecting
        data at a later stage, use the pause() function instead.
        """
        self.logger.info('Stopping classifier')
        self.running = False
        self.change_state('idle')

        # Abort the threads waiting for data
        self.recorder.data_condition.acquire()
        self.recorder.data_condition.notifyAll()
        self.recorder.data_condition.release()

        if self.isAlive():
            self.join(1)
        self.logger.info('Classifier stopped')

    def _send_debug_image(self, d):
        """ Send a PNG image describing the training data to Unity. """

        self.logger.info('Sending debug plot to Unity')
        fig = psychic.plot_erp(d, self.target_sample_rate, feat_lab=self.feat_lab, cl_lab=self.cl_lab, enforce_equal_n=False)
        fig.set_size_inches(7,11)

        # Save a snapshot to disk
        fig.savefig('classifier_output.png', format='png')

        buf = cStringIO.StringIO()
        fig.savefig(buf, format='png')
        self.engine.provide_result( ['training-result', base64.b64encode(buf.getvalue())] )

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
            self.window_samples = (int(self.recorder.sample_rate*value[0]), int(self.recorder.sample_rate*value[1]))
            self.target_window = (int(self.target_sample_rate*value[0]), int(self.target_sample_rate*value[1]))
            return True

        elif name == 'target_sample_rate':
            if type(value[0]) != int and type(value[0]) != float:
                raise ClassifierException('Value for num_options must be numeric.')

            self.target_sample_rate = value[0]
            self.target_window = (int(self.target_sample_rate*self.window[0]), int(self.target_sample_rate*self.window[1]))
            return True

        elif name == 'cl_lab':
            self.cl_lab = value

        elif name == 'format':
            if len(value) < 1:
                raise ClassifierException('Missing value for format.')

            if not value[0] in ['png', 'jpg', 'pdf', 'svg']:
                raise ClassifierException('Invalid value for format.')

            self.format = value[0]

        return False

    def get_parameter(self, name):
        if name == 'window':
            return self.window
        elif name == 'target_sample_rate':
            return self.target_sample_rate
        elif name == 'bandpass':
            return self.bandpass
        elif name == 'cl_lab':
            return self.cl_lab
        elif name == 'format':
            return self.format
        else:
            return False
