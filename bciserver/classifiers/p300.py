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
    def __init__(self, engine, recorder, classifications_needed=0, num_repetitions=10, num_options=7, window=(0.0, 1.0), bandpass=[0.5, 15]):
        """ Constructor.

        Required parameters:
        recorder: The imec.Recorder object to read data from

        Keyword parameters (configures the classifier): 
        classifications_needed: Number of consistent classifications needed to make a desicion
        window: A pair (from, to) in samples of the window to extract around the stimulation onset
        bandpass: [lo, hi] cutoff frequencies for the bandpass filter to use on the data
        """
        threading.Thread.__init__(self)

        assert len(window) == 2

        self.num_repetitions = num_repetitions
        self.num_options = num_options
        self.target_sample_rate = 128
        self.window = window
        self.window_samples = (int(recorder.sample_rate*window[0]), int(recorder.sample_rate*window[1]))
        self.target_window = (int(self.target_sample_rate*window[0]), int(self.target_sample_rate*window[1]))
        self.classifications_needed = classifications_needed

        # Initialize event to signal the classifier to switch states
        self.state_event = threading.Event()

        # Initialize log system
        self.logger = logging.getLogger('P300 Classifier')

        self.mdict = {}
        for i in range(1,self.num_options+1):
            self.mdict[i] = 'target %02d' % i

        # Create pipeline
        self.logger.info('Creating pipelines')
        self.bp_node = psychic.nodes.OnlineFilter( lambda s : scipy.signal.iirfilter(3, [bandpass[0]/(s/2.0), bandpass[1]/(s/2.0)]) )
        self.resample_node = psychic.nodes.Resample(self.target_sample_rate, max_marker_delay=1)
        #self.feat_node = golem.nodes.AUCFilter()
        self.lda_node = golem.nodes.LDA()
        self.svm_node = golem.nodes.SVM(c=2)
        self.slice_node = psychic.nodes.OnlineSlice(self.mdict, window)

        self.preprocessing = golem.nodes.Chain([self.bp_node, self.resample_node])
        #self.classification = golem.nodes.Chain([self.feat_node, self.lda_node])
        self.classification = golem.nodes.Chain([self.svm_node])
        self.recorder = recorder
        self.engine = engine
        self.running = False

        self.logger.info('sample_rate: %d Hz' % recorder.sample_rate)
        self.logger.info('bandpass: %s' % bandpass)
        self.logger.info('window: %s' % str(window))
        self.logger.info('num_repetitions: %d' % num_repetitions)

        self._reset() 

    def _reset(self):
        """ Resets the classifier. Flushes all collected data."""
        self.application_data = None
        self.processed_data = None
        self.num_coherent_classifications = 0
        self.last_winner = -1
        self.last_repetitions_recorded = 0
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

        self.slice_node.train(d)

        # Extract trials
        d = self._extract_training_trials(d)
        d2 = psychic.nodes.Blowup(1000).apply(d)
        d2 = psychic.nodes.Mean(axis=2).apply(d2)

        # Train classifier
        self.classification.train(d2)
        #if (numpy.any( numpy.isfinite(self.lda_node.means) ) or
        #    numpy.any( numpy.isfinite(self.lda_node.const) ) or
        #    numpy.any( numpy.isfinite(self.lda_node.S_is)  )):
        #    self.logger.error('Training FAILED')
        #    raise ClassifierException('Training failed')

        self.logger.info('Training complete')

        # Send a debug plot to Unity
        self._send_debug_image( psychic.nodes.Mean(axis=2).apply(d) )

        self.training_complete = True
        self.slice_node.reset()

    def _extract_training_trials(self, d):
        block_onsets = numpy.flatnonzero(d.Y > 100)
        num_blocks = len(block_onsets)
        if not num_blocks:
            raise ClassifierException('No blocks found in recording. Make sure the data is properly labeled.')

        target_window_length = self.target_window[1] - self.target_window[0]
        block_lengths = numpy.hstack( (numpy.diff(block_onsets), d.ninstances-block_onsets[-1]) )
        targets = d.Y[0,block_onsets] - 100
        options = numpy.unique(targets)
        num_options = len(options)
        num_instances = num_blocks * num_options
        num_channels = d.nfeatures

        mdict = {}
        for target in sorted(numpy.unique(targets)):
            mdict[target] = 'target %02d' % target

        # Allocate memory for the blocks
        feat_dim_lab = ['samples', 'channels', 'repetitions']
        feat_shape = (self.target_window[1]-self.target_window[0], num_channels, self.num_repetitions)
        X = numpy.zeros(feat_shape + (num_instances,))
        Y = numpy.zeros((2,num_instances))
        I = numpy.arange(num_instances)

        # Extract each block
        for block_num,block_onset,block_length,target in zip(range(num_blocks), block_onsets, block_lengths, targets):
            block = d[block_onset : block_onset+block_length+self.target_sample_rate]
            block = psychic.slice(block, mdict, self.target_window)
            #block = psychic.baseline(block, (0, 10))

            # Extract each option within a block
            for option_num in range(block.nclasses):
                if block.get_class(option_num).ndX.shape[2] < self.num_repetitions:
                    self.logger.warning('could not extract all repetitions of option %d in block %d' % (option_num+1, block_num))
                    continue
                instance = block_num*num_options+option_num
                X[:,:,:,instance] = block.get_class(option_num).ndX[:,:,:self.num_repetitions]
                Y[0,instance] = (option_num == (target-1)) # target trial
                Y[1,instance] = (option_num != (target-1)) # nontarget trial

        # Build new dataset containing the trials
        return golem.DataSet(X=X.reshape(-1, num_instances), Y=Y, I=I, feat_shape=feat_shape, feat_dim_lab=feat_dim_lab,cl_lab=['target', 'nontarget'])

    def _apply(self, d):
        """ Applies classifier to a dataset. """

        # Perorm preprocessing
        d = self.preprocessing.apply(d)
        slices = self.slice_node.apply(d)
        if slices == None:
            return

        if self.application_data == None:
            self.application_data = slices
        else:
            self.application_data += slices

        repetitions_recorded = numpy.min(self.application_data.ninstances_per_class)
        if repetitions_recorded == self.last_repetitions_recorded:
            return

        self.logger.debug('Repetitions recorded: %d' % repetitions_recorded)
        self.last_repetitions_recorded = repetitions_recorded
        if repetitions_recorded < self.num_repetitions:
            return

        d = psychic.erp(self.application_data)

        # Perform actual classification
        try:
            result = self.classification.apply(d).X

            candidates = numpy.flatnonzero( numpy.argmax(result, axis=0) == 0 )
            if len(candidates) > 0:
                winner = candidates[ numpy.argmax( result[0, candidates] ) ]
            else:
                winner = numpy.argmax(result[0,:])

            if winner == self.last_winner:
                self.num_coherent_classifications += 1
            else:
                self.num_coherent_classifications = 0
                self.last_winner = winner

            self.logger.debug('Coherent classifications: %d' % self.num_coherent_classifications)
            if self.num_coherent_classifications < self.classifications_needed:
                self.engine.provide_result([list(result[0,:]), 0])
                return

            self.logger.info('classification result: %d' % winner)
            self.engine.provide_result([list(result[0,:]), winner+1])
            self.application_data = None
            self.num_coherent_classifications = 0
            self.last_winner = -1
            self.last_repetitions_recorded = 0

        except ValueError as e:
            self.logger.error('Classification failed: %s' % e)
    
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
                if not self.training_complete:
                    self.change_state('idle')
                    raise ClassifierException('Cannot go into application state'
                                              ' without proper training!')

                # Flush previously stored application data
                if self.prev_state != 'application':
                    self.application_data = None
                    self.slic_node.reset()
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
        fig = psychic.plot_erp(d, self.target_sample_rate, feat_lab=self.feat_lab, enforce_equal_n=False)
        fig.set_size_inches(7,11)

        # Save a snapshot to disk
        fig.savefig('classifier_output.png', format='png')

        buf = cStringIO.StringIO()
        fig.savefig(buf, format='png')
        self.engine.provide_result( ['training-result', base64.b64encode(buf.getvalue())] )

    def set_parameter(self, name, value):
        if name == 'num_repetitions':
            if type(value[0]) != int:
                raise ClassifierException('Value for num_repetitions must be of type int.')

            self.num_repetitions = value[0]
            return True

        elif name == 'classifications_needed':
            if type(value[0]) != int:
                raise ClassifierException('Value for classifications_needed must be of type int.')

            self.classifications_needed = value[0]
            return True

        elif name == 'num_options':
            if type(value[0]) != int:
                raise ClassifierException('Value for num_options must be of type int.')

            self.num_options = value[0]

            # Rebuild marker dictionary
            self.mdict.clear()
            for i in range(1,self.num_options+1):
                self.mdict[i] = 'target %02d' % i
            self.slice_node.reset()
            return True

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

        return False

    def get_parameter(self, name):
        if name == 'num_options':
            return self.num_options
        elif name == 'num_repetitions':
            return self.num_repetitions
        elif name == 'window':
            return self.window
        elif name == 'target_sample_rate':
            return self.target_sample_rate
        elif name == 'bandpass':
            return self.bandpass
        elif name == 'classifications_needed':
            return self.classifications_needed
        else:
            return False
