import matplotlib
#matplotlib.use('Agg')

import classifiers
import eegdevices

from network import ClientHandler

import logging
import socket
import argparse

from bci_exceptions import *

class Engine:
    def __init__(self, port):
        self.classifier = None
        self.recorder = None
        self.logger = logging.getLogger('ENGINE')
        self.ch = None
        self.port = port
        self.running = False

    def run(self):
        # Wait for incoming TCP/IP connections
        self.running = True
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.server_socket.bind( ('', self.port) )

            self.logger.info('Awaiting network connection on port %d' % self.port)
            self.server_socket.settimeout(1)
            self.server_socket.listen(1)

            self.connected = False
            while self.running:
                try:
                    (client_socket, address) = self.server_socket.accept()
                    self.ch = ClientHandler(client_socket, self)
                    self.connected = True

                    self.ch.run()
                    self.connected = False

                    if self.classifier:
                        self.classifier.stop()
                        self.classifier = None
                    if self.recorder:
                        self.recorder.stop()
                        self.recorder = None

                except socket.timeout:
                    pass
                except KeyboardInterrupt:
                    break

        except Exception as e:
            self.logger.error('%s' % e)
            self.stop()
            raise

        self.stop()

    def stop(self):
        if self.classifier:
            self.classifier.stop()
        if self.recorder:
            self.recorder.stop()
        if self.server_socket:
            self.server_socket.close()
        self.running = False
        print 'Stopped.'

    def provide_devices(self):
        return eegdevices.available_devices.keys()

    def set_device(self, name):
        if not name in eegdevices.available_devices:
            raise EngineException(101, 'Recording device not available')

        try:
            if self.recorder:
                self.logger.info('Switching device.')
                self.recorder.stop()
            self.recorder = eegdevices.available_devices[name]()
            self.logger.info('Selected device: %s.' % name)
        except IOError as e:
            raise EngineException(202, e.strerror)

    def open_device(self):
        if not self.recorder:
            raise EngineException(102, 'Please specify a recording device first')
        self.logger.info('Opening device.')

        if not self.recorder.running:
            self.recorder.start()
        else:
            print 'Device already opened'

        if self.classifier and not self.classifier.running:
            self.classifier.start()

    def provide_classifiers(self):
        return classifiers.available_classifiers.keys()

    def set_classifier(self, name):
        if not self.recorder:
            raise EngineException(201, 'Please specify a recording device first')
        if not name in classifiers.available_classifiers:
            raise EngineException(202, 'Classifier not available')

        if self.classifier:
            self.logger.info('Switching classifier.')
            self.classifier.stop()

        self.logger.info('Loading classifier: ' + name)
        self.classifier = classifiers.available_classifiers[name](self, self.recorder)

        if self.recorder.running:
            self.classifier.start()

    def set_device_parameter(self, name, values):
        if not self.recorder:
            raise EngineException(301, 'Please specify a recording device first')

        if not self.recorder.set_parameter(name, values):
            raise EngineException(303, 'Unknown device parameter')

    def get_device_parameter(self, name):
        if not self.recorder:
            raise EngineException(301, 'Please specify a recording device first')

        value = self.recorder.get_parameter(name)
        if not value:
            raise EngineException(303, 'Unknown device parameter')
        return value

    def set_classifier_parameter(self, name, values):
        if not self.classifier:
            raise EngineException(302, 'Please specify a classifier first')

        if not self.classifier.set_parameter(name, values):
            raise EngineException(304, 'Unknown classifier parameter')

    def get_classifier_parameter(self, name):
        if not self.classifier:
            raise EngineException(302, 'Please specify a classifier first')

        value = self.classifier.get_parameter(name)
        if not value:
            raise EngineException(304, 'Unknown classifier parameter')
        return value

    def set_mode(self, mode):
        if mode != 'idle' and mode != 'data-collect' and mode != 'training' and mode != 'application':
            raise EngineException(401, 'Invalid mode requested')
        if not self.classifier:
            raise EngineException(402, 'Please specify a classifier first')

        self.classifier.change_state(mode)

    def get_mode(self):
        if not self.classifier:
            raise EngineException(402, 'Please specify a classifier first')
        return self.classifier.state

    def provide_mode(self, mode):
        if self.ch:
            self.ch.provide_mode(mode)

    def set_marker(self, code, type, timestamp):
        if not self.recorder:
            raise EngineException(301, 'Please specify a recording device first')

        self.recorder.set_marker(code, type, timestamp)

    def provide_result(self, result, timestamp=None):
        if self.ch:
            self.ch.provide_result(result, timestamp)

    def error(self, e):
        if self.ch:
            self.ch.error(e)

def main():
    class VAction(argparse.Action):
        def __call__(self, parser, args, values, option_string=None):
            if values==None:
                values='1'
            try:
                values=int(values)
            except ValueError:
                values=values.count('v')+1
            setattr(args, self.dest, values)

    print '''
K.U.Leuven BCI server -- Marijn van Vliet <marijn.vanvliet@med.kuleuven.be>
Copyright computational neuroscience group, K.U.Leuven (2013)
'''
    parser = argparse.ArgumentParser(description='BCI EEG data recorder and classifier')
    parser.add_argument('-p', '--network-port', metavar='N', type=int, default=9000, help='Set the port number on which the recorder will listen to incoming connections from Unity. [9000]')
    parser.add_argument('-l', '--log', metavar='File', help='Specify a file to write any log messages to.')
    parser.add_argument('-v', nargs='?', action=VAction, dest='verbose', help='Be more verbose. Repeat this argument to be even more verbose.')
    args = parser.parse_args()

    # Setup logging
    if args.log:
        ch = logging.FileHandler(args.log)
    else:
        ch = logging.StreamHandler()

    if args.verbose == None:
        ch.setLevel(logging.WARNING)
    elif args.verbose == 1:
        ch.setLevel(logging.INFO)
    else:
        ch.setLevel(logging.DEBUG)

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    ch.setFormatter(formatter)
    logger = logging.getLogger()

    if args.verbose == None:
        logger.setLevel(logging.WARNING)
    elif args.verbose == 1:
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.DEBUG)

    logger.addHandler(ch)

    # Check if all devices loaded properly
    for module, error in eegdevices.device_errors.items():
        logging.getLogger('EEG-Devices').debug('Device %s unavailable: %s' % (module, error.message))

    # Start engine
    e = Engine( int(args.network_port) )
    e.run()
