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
    """ Implements an online SSVEP classifier.
    This class acts as a consumer to an imec.Recorder
    """
    def __init__(self, engine, recorder, window_size=1.0, window_step=0.5, freq=12.8, bandpass=[2, 45]):
        """ Constructor.

        Required parameters:
        recorder: The imec.Recorder object to read data from

        Keyword parameters (configures the classifier): 
        window_size: The window size in seconds to use on the data
        window_step: The window step in seconds to use on the data
        freq: The frequency in Hertz of the SSVEP stimulus to look for
        bandpass: [lo, hi] cutoff frequencies for the bandpass filter to use on the data
        """
        threading.Thread.__init__(self)

        # Initialize event to signal the classifier to switch states
        self.state_event = threading.Event()

        # Initialize log system
        self.logger = logging.getLogger('Classifier')

        self.recorder = recorder
        self.engine = engine
        self.window_size = window_size
        self.window_step = window_step
        self.freq = freq
        self.bandpass = bandpass
        self.running = False
        self.pipeline = None
        self.target_sample_rate = 128
    
        self._reset() 

        self.logger.info("freq: %f" % freq)
        self.logger.info("sample_rate: %f" % recorder.sample_rate)
        self.logger.info("window_size: %f" % window_size)
        self.logger.info("window_step: %f" % window_step)
        self.logger.info("bandpass: %s" % bandpass)

    def _construct_pipeline(self):
        self.logger.info('Creating pipeline')
        self.bp_node = psychic.nodes.OnlineFilter( lambda s : scipy.signal.iirfilter(4, [self.bandpass[0]/(s/2.0), self.bandpass[1]/(s/2.0)]) )
        self.resample_node = psychic.nodes.Resample(self.target_sample_rate, max_marker_delay=1)
        self.ica_node = golem.nodes.ICA()
        self.window_node = psychic.nodes.OnlineSlidingWindow(int(self.window_size*self.recorder.sample_rate), int(self.window_step*self.recorder.sample_rate))
        self.slic_node = psychic.nodes.Slic([self.freq], self.recorder.sample_rate)
        self.thres_node = golem.nodes.Threshold([0,1],feature=0)
        self.preprocessing = golem.nodes.Chain([self.bp_node, self.resample_node])
        self.classification = golem.nodes.Chain([self.window_node, self.slic_node, self.thres_node])
        self.pipeline = golem.nodes.Chain([self.preprocessing, self.ica_node, self.classification])

    def _reset(self):
        """ Reset the classifier. Flushes all collected data."""
        self.application_data = None
        self.state = 'idle'
        self.prev_state = self.state
        self.state_event.clear()
        self.training_complete = False

        if self.pipeline:
            self.window_node.reset()
            self.thres_node.reset()

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
        self.logger.info('Changing state to %s' % new_state)

    def _train(self):
        """ Train the classifier on a dataset. """

        d = self.recorder.read(block=False)
        if not d:
            raise ClassifierException('First collect some data before training.')

        # Save a snapshot of the training data to disk
        d.save('test_data.dat')

        # Convert markers to classes
        Y = numpy.zeros((3, d.ninstances), dtype=numpy.bool)

        Y[0,:] = (d.Y == 1)[0,:]
        Y[1,:] = (d.Y == 2)[0,:]
        Y[2,:] = (d.Y == 3)[0,:]

        d = golem.DataSet(Y=Y, cl_lab=['on','off', 'sweep'], default=d)

        self._construct_pipeline()

        # Train the pipeline
        d2 = self.preprocessing.train_apply(d,d)
        d2 = self.ica_node.train_apply(d.get_class(0), d2)
        self.classification.train(d2)
        self.logger.info('Training complete')

        # Send a debug plot to Unity
        self._send_debug_image(d)

        self.window_node.reset()
        self.thres_node.reset()

        self.training_complete = True

    def _apply(self, d):
        """ Apply the classifier on a dataset. """
        if d.ninstances == 0:
            return

        result = self.pipeline.apply(d)
        self.logger.debug('Result was: %s:%s at %s' % (result.xs[:,0], result.ys[:,0], result.ids))

        # send result to Unity
        if self.engine != None:
            for i in range(0, result.ys.shape[0]):
                self.engine.provide_result([result.xs[i,0], result.ys[i,0]])
    
    def pause_classifier(self):
        """ Pause the classifier while in application mode. To unpause, call
        either data-collect() or apply_classifier()."""
        self.recorder.stop_capture()


    def run(self):
        assert self.recorder.running

        self.running = True
        while(self.running and self.recorder.running):

            if self.state_event.is_set():
                self.state_event.clear()

            if self.state == 'idle':
                self.recorder.stop_capture()

                #if self.prev_state == 'application':
                #    # Take the time to retrain the ICA
                #    d = self.application_data[-60*self.recorder.sample_rate:]
                #    d = self.bp_node.apply(d)
                #    self.ica_node.train(d)
                
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
                    self.logger.error(e)
                    self.engine.error(e)

                # Turn back to idle state
                self.change_state('idle')

            elif self.state == 'application':
                if not self.training_complete:
                    self.logger.error('Cannot go into application state without'
                                      'proper training!')
                    self.change_state('idle')
                    continue

                # Flush previously stored application data
                if self.prev_state != 'application':
                    self.application_data = None
                    self.engine.provide_mode('application')

                while not self.state_event.is_set():
                    # Record data
                    self.recorder.start_capture()
                    d = self.recorder.read()

                    # Received data could be None for various reasons, recorder did not record
                    # anything yet, recorder was killed somewhere, etc.
                    if d == None:
                        continue

                    self.logger.info('Received data packet of length %d' % d.ninstances)

                    # Apply classifier to data
                    self._apply(d)

                    # Store data for later ICA-analysis
                    if self.application_data == None:
                        self.application_data = d
                    else:
                        self.application_data += d
            else:
                self.logger.warning('Classifier in invalid state: %s' % self.state)
                self.state_event.wait()

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
            self.join()
        self.logger.info('Classifier stopped')

    def _send_debug_image(self, d):
        """ Send a PNG image describing the training data to Unity. """

        self.window_node.reset()
        self.thres_node.reset()
        d2 = self.pipeline.apply(d)
        fig = plt.figure()

        ax = fig.add_subplot(311)
        ax.plot(d.ids, d.xs[:,0])
        ax.set_ylabel('mV')
        ax.set_xlim([numpy.min(d.ids), numpy.max(d.ids)])
        ax.grid()

        ax = fig.add_subplot(312)
        ax.plot(d2.ids, d2.xs[:,0])
        ax.axhline(self.thres_node.hi, color='r')
        ax.axhline(self.thres_node.lo, color='g')
        ax.set_ylabel('mean(correlation)')
        ax.set_xlim([numpy.min(d2.ids), numpy.max(d2.ids)])
        ax.grid()

        ax = fig.add_subplot(313)
        ax.plot(d2.ids, d2.ys[:,0], '-r')
        ax.plot(d.ids, d.ys[:,0], '-b')
        ax.set_ylabel('fixating?')
        ax.set_xlabel('time (s)')
        ax.set_xlim([numpy.min(d2.ids), numpy.max(d2.ids)])
        ax.set_ylim([-0.2, 2])
        ax.grid()

        # Save a snapshot to disk
        fig.savefig('last_result.png', format='png')

        buf = cStringIO.StringIO()
        fig.savefig(buf, format='png')
        self.engine.provide_result( ["training-result", base64.b64encode(buf.getvalue())] )

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
