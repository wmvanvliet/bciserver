import threading
import logging
import cStringIO
import base64

class Classifier(threading.Thread):
    '''
    Base class for classifiers. A classifier acts as a consumer of the data
    produced by a Recorder class. It has 4 states:

      'idle': classifier does absolutely nothing. Begin state.
      'data-collect': classifier is quietly collecting data without acting on
                      it. This state is used for collecting training data.
      'training': classifier is performing demanting computations on the
                  training data collected in the 'data-collect' state.
      'application': classifier is consuming new data and producing
                     classifiication results.

    The method change_state() is called whenever a state change is requested.
    The classifier calls Engine.provide_mode() to inform the engine whenever
    the classifier changes states. One typical use of these functions is the
    engine first calling change_state('training'), to which the classifier
    almost immediately responds with Engine.provide_mode('training') to indicate
    the classifier has begun the classifier training. When training is complete
    the classifier will call Engine.provide_mode('idle') to inform the engine
    it has finished and is now in 'idle' mode. This functionality is provided
    by this base class.

    When implementing a new classifier subclass, three methods need to be
    implemented:

      __init__: The class constructor. Make sure to call Classifier.__init__
                from within this constructor to initialize the base class.
                Initialize your classifier pipeline here.
      _train: Called when the classifier switched to 'training' mode. Call
              the train() method of the classifier pipeline here.
      _apply: Called when the classifier is in 'application' mode and some new
              data just arrived ready for classification. Call
              Engine.provide_classifier_result here to pass classification
              results to the engine, which in turn shall pass it on to the
              client.
      set_parameter: Called whenever the client is setting parameters of the
                     classifier.
      get_parameter: Called whenever the client is requesting parameters from
                     the classifier.
    '''

    def __init__(self, engine, recorder):
        threading.Thread.__init__(self)

        # Initialize event to signal the classifier to switch states
        self.state_event = threading.Event()

        # Initialize log system
        self.logger = logging.getLogger('Classifier')

        self.recorder = recorder
        self.engine = engine
        self.running = False

        self._reset() 

    def _reset(self):
        """ Reset the classifier. Flushes all collected data."""
        self.application_data = None
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
        self.logger.info('Changing state to %s' % new_state)

    def _train(self):
        """ Train the classifier on a dataset. """
        pass

    def _apply(self, d):
        """ Apply the classifier on a dataset. """
        pass

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
                    d = self.recorder.read(block=False)
                    self._train(d)
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
            else:
                self.logger.warning('Classifier in invalid state: %s' % self.state)
                self.state_event.wait()

    def stop(self):
        """
        Make the classifier stop collecting data. Works in training as well as
        application mode.  This will terminate the thread, which cannot be
        restarted. If you want to continue collecting data at a later stage,
        use the pause() function instead.
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
        """ Send a PNG image describing the training data to client. """
        fig = self._generate_debug_image(d)

        # Save a snapshot to disk
        fig.savefig('classifier_output.png', format='png')

        buf = cStringIO.StringIO()
        fig.savefig(buf, format='png')
        self.engine.provide_result( ['training-result', base64.b64encode(buf.getvalue())] )

    def set_parameter(self, name, value):
        return False

    def get_parameter(self, name):
        return False
