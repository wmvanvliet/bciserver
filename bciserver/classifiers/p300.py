import psychic
import numpy
import scipy

import sklearn.svm
import sklearn.grid_search

from ..classifier import Classifier
from ..bci_exceptions import ClassifierException

class P300(Classifier):
    """ Implements an online P300 classifier. """
    def __init__(self, engine, recorder, classifications_needed=0, num_repetitions=10, num_options=7, window=(0.0, 1.0), bandpass=[0.5, 15]):
        """ Constructor.

        Required parameters:
        recorder: The Recorder object to read data from

        Keyword parameters (configures the classifier): 
        classifications_needed: Number of consistent classifications needed to make a desicion
        window: A pair (from, to) in samples of the window to extract around the stimulation onset
        bandpass: [lo, hi] cutoff frequencies for the bandpass filter to use on the data
        """

        assert len(window) == 2

        self.num_repetitions = num_repetitions
        self.num_options = num_options
        self.target_sample_rate = 128
        self.window = window
        self.window_samples = (int(recorder.sample_rate*window[0]), int(recorder.sample_rate*window[1]))
        self.target_window = (int(self.target_sample_rate*window[0]), int(self.target_sample_rate*window[1]))
        self.classifications_needed = classifications_needed

        self.mdict = {}
        for i in range(1,self.num_options+1):
            self.mdict[i] = 'target %02d' % i


        # Create pipeline
        self.bp_node = psychic.nodes.OnlineFilter( lambda s : scipy.signal.iirfilter(3, [bandpass[0]/(s/2.0), bandpass[1]/(s/2.0)]) )
        self.resample_node = psychic.nodes.Resample(self.target_sample_rate, max_marker_delay=1)
        self.svm_node = sklearn.grid_search.GridSearchCV(
            sklearn.svm.LinearSVC(),
            {'C': numpy.logspace(-3, 5, 10)},
            cv=5,
        )
        self.slice_node = psychic.nodes.OnlineSlice(self.mdict, window)
        self.preprocessing = psychic.nodes.Chain([self.bp_node, self.resample_node])
        self.classification = psychic.nodes.Chain([self.svm_node])

        Classifier.__init__(self, engine, recorder)

        self.logger.info('sample_rate: %d Hz' % recorder.sample_rate)
        self.logger.info('bandpass: %s' % bandpass)
        self.logger.info('window: %s' % str(window))
        self.logger.info('num_repetitions: %d' % num_repetitions)

    def _reset(self):
        """ Resets the classifier. Flushes all collected data."""
        super(P300, self)._reset()

        self.application_data_valid = True
        self.processed_data = None
        self.num_coherent_classifications = 0
        self.last_winner = -1
        self.last_repetitions_recorded = 0

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

        self.slice_node.train(d)

        # Extract trials
        d = self._extract_training_trials(d)
        d2 = psychic.nodes.Blowup(100).apply(d)
        d2 = psychic.nodes.Mean(axis=2).apply(d2)

        # Train classifier
        self.classification.train(d2)
        #if (numpy.any( numpy.isfinite(self.lda_node.means) ) or
        #    numpy.any( numpy.isfinite(self.lda_node.const) ) or
        #    numpy.any( numpy.isfinite(self.lda_node.S_is)  )):
        #    self.logger.error('Training FAILED')
        #    raise ClassifierException('Training failed')

        self.logger.info('Training complete')

        # Send a debug plot to client
        self._send_debug_image( psychic.nodes.Mean(axis=2).apply(d) )

        self.training_complete = True
        self.slice_node.reset()

    def _extract_training_trials(self, d):
        block_onsets = numpy.flatnonzero(d.Y > 100)
        num_blocks = len(block_onsets)
        if not num_blocks:
            raise ClassifierException('No blocks found in recording. Make sure the data is properly labeled.')

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
        feat_dim_lab = ['channels', 'samples', 'repetitions']
        feat_shape = (num_channels, self.target_window[1]-self.target_window[0], self.num_repetitions)
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
        return psychic.DataSet(data=X, labels=Y, ids=I,
                               feat_dim_lab=feat_dim_lab,
                               l_lab=['target', 'nontarget'])

    def _apply(self, d):
        """ Applies classifier to a dataset. """

        # Perform preprocessing
        d = self.preprocessing.apply(d)
        slices = self.slice_node.apply(d)
        if slices == None:
            return

        if self.application_data == None or not self.application_data_valid:
            self.application_data = slices
            self.application_data_valid = True
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
            result = self.classification.apply(d).data

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
            self.application_data_valid = False
            self.num_coherent_classifications = 0
            self.last_winner = -1
            self.last_repetitions_recorded = 0

        except ValueError as e:
            self.logger.error('Classification failed: %s' % e)
    
    def _generate_debug_image(self, d):
        """ Generate image describing the training data. """
        d = psychic.DataSet(cl_lab=self.cl_lab, default=d)
        fig = psychic.plot_erp(d, enforce_equal_n=False)
        fig.set_size_inches(7, 11)
        return fig

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
            self.application_data_valid = False
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
                raise ClassifierException('Value for target_sample_rate must be numeric.')

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
