import socket
import logging
import re
from collections import deque

from bci_exceptions import *
from eegdevices import DeviceError, precision_timer

class ClientHandler:
    def __init__(self, socket, engine):
        self.socket = socket
        self.socket.settimeout(1)
        self.engine = engine
        self.running = False
        self.logger = logging.getLogger('Network')

        self.buffer = ''
        self.tokens = deque()

        self.tokenizer = re.compile(r'''
(?:                     # switch on different datatypes
    
    (
        [^-\d."][^\s$]+ # a single word (without quotes)
        (?:\s+|$)       # optional whitespace
    )

    |

        "               # a string, beginning with opening quote
        (               # start capture of group here
            (?:         # 
                \\.     # escaped character
                |       # 
                [^"\\]  # anything but ending quote
            )*
        )               # end capture of group
        "               # ending quote

        (?:\s+|$)       # optional whitespace

    |                

    (                   
        -?\d+           # an integer number
        (?:\s+|$)       # optional whitespace
    )               

    |               

    (                   
        -?\d*.\d+       # a floating point number
        (?:\s+|$)       # optional whitespace
    )               

)                       # end switch on datatypes
            ''', re.VERBOSE)

    def run(self):
        self.running = True
        self.logger.info('Connection established.')
        while self.running:
            try:
                data = self.socket.recv(1024)
                if not data:
                    self.logger.info('Connection lost.')
                    break

                self.buffer += data

                lines = self.buffer.split('\n')
                if len(lines) <= 1:
                    # No complete message received yet
                    continue

                for i in range(len(lines)-1):
                    self.lineReceived(lines[i])

                self.buffer = lines[-1]
            except socket.timeout:
                pass
            except Exception as e:
                print 'exception caught, trying to close down network connection'
                self.stop()
                self.socket.close()
                raise

        self.socket.close()

    def stop(self):
        self.running = False

    def sendLine(self, line):
        self.logger.debug('Sending message: %s' % line)
        self.socket.sendall(line + '\r\n')

    def lineReceived(self, line):
        self.logger.debug('Received message: %s' % line)

        # Tokenize line
        for token in self.tokenizer.findall(line):
            value = None
            if token[0]:
                # single word
                value = token[0].strip()
            elif token[1]:
                # string
                value = token[1].strip()
            elif token[2]:
                # integer
                value = int(token[2])
            elif token[3]:
                # float
                value = float(token[3])
            else:
                continue

            self.tokens.append(value)

        self._parse_message()

    def encode(self, value):
        if type(value) == list:
            return ' '.join([self.encode(x) for x in value])
        elif type(value) == int or type(value) == float:
            return str(value)
        elif type(value) == bool:
            return '1' if value else '0'
        else: 
            return '"' + str(value).replace('"', '\\"') + '"'

    def _parse_message(self):
        if len(self.tokens) == 0 or type(self.tokens[0]) != str:
            self.sendLine('ERROR 001: Please specify command category')
            self.tokens.clear()
            return

        category = self.tokens.popleft().lower()
        if category == 'ping':
            self.sendLine('PONG')
        else:
            try:
                if category == 'device':
                    self._parse_device()
                elif category == 'classifier':
                    self._parse_classifier()
                elif category == 'mode':
                    self._parse_mode()
                elif category == 'marker':
                    self._parse_marker()
                else:
                    self.sendLine('ERROR 001 "Unknown command category.')
            except EngineException as e:
                self.sendLine('ERROR %03d "%s"' % (e.code, e.msg))
                self.logger.error('ERROR %03d "%s"' % (e.code, e.msg))
            except BCIProtocolException as e:
                self.sendLine('ERROR %03d "%s"' % (e.code, e.msg))
                self.logger.error('ERROR %03d "%s"' % (e.code, e.msg))
            except ClassifierException as e:
                self.sendLine('ERROR 000 "%s"' % e)
                self.logger.error('ERROR 000 "%s"' % e)
            except DeviceError as e:
                self.sendLine('ERROR 000 "%s"' % e)
                self.logger.error('ERROR 000 "%s"' % e)
                raise
            except Exception as e:
                self.sendLine('ERROR 000 "%s"' % e)
                self.logger.error('ERROR 000 "%s"' % e)
                raise

        self.tokens.clear()

    def _parse_device(self):
        if len(self.tokens) == 0 or type(self.tokens[0]) != str:
            raise BCIProtocolException(2, 'Please specify command')

        command = self.tokens.popleft().lower()
        if command == 'get':
            # Provide a list of available classifiers
            self.sendLine('DEVICE PROVIDE ' +
                          self.encode( self.engine.provide_devices() ))

        elif command == 'set':
            # Load a device
            if len(self.tokens) == 0 or type(self.tokens[0]) != str:
                raise BCIProtocolException(102, 'Please specify device to set')

            name = self.tokens.popleft().lower()
            self.engine.set_device(name)

        elif command == 'param':
            if len(self.tokens) == 0 or type(self.tokens[0]) != str:
                raise BCIProtocolException(103, 'Please specify parameter operation')
            if len(self.tokens) == 1 or type(self.tokens[1]) != str:
                raise BCIProtocolException(104, 'Please specify parameter name')

            operation = self.tokens.popleft().lower()
            name = self.tokens.popleft().lower()

            if operation == 'set':
                if len(self.tokens) == 0:
                    raise BCIProtocolException(105, 'Please specify parameter value(s)')

                self.engine.set_device_parameter(name, list(self.tokens))

            elif operation == 'get':
                value = self.engine.get_device_parameter(name)
                self.sendLine('DEVICE PARAM PROVIDE "%s" %s' % (name, self.encode(value)))

        elif command == 'open':
            self.engine.open_device()

        else:
            raise BCIProtocolException(101, 'Unknown device command')

    def _parse_classifier(self):
        if len(self.tokens) == 0 or type(self.tokens[0]) != str:
            raise BCIProtocolException(2, 'Please specify command')

        command = self.tokens.popleft().lower()
        if command == 'get':
            # Provide a list of available classifiers
            self.sendLine('CLASSIFIER PROVIDE ' +
                          self.encode( self.engine.provide_classifiers() ))

        elif command == 'set':
            # Load a classifier
            if len(self.tokens) == 0 or type(self.tokens[0]) != str:
                raise BCIProtocolException(202, 'Please specify classifier to set')

            name = self.tokens.popleft().lower()
            self.engine.set_classifier(name)

        elif command == 'param':
            if len(self.tokens) == 0 or type(self.tokens[0]) != str:
                raise BCIProtocolException(203, 'Please specify parameter operation')
            if len(self.tokens) == 1 or type(self.tokens[1]) != str:
                raise BCIProtocolException(204, 'Please specify parameter name')

            operation = self.tokens.popleft().lower()
            name = self.tokens.popleft().lower()

            if operation == 'set':
                if len(self.tokens) == 0:
                    raise BCIProtocolException(205, 'Please specify parameter value(s)')

                self.engine.set_classifier_parameter(name, list(self.tokens))

            elif operation == 'get':
                value = self.engine.get_classifier_parameter(name)
                self.sendLine('CLASSIFIER PARAM PROVIDE "%s" %s' % (name, self.encode(value)))

            else:
                raise BCIProtocolException(201, 'Unknown classifier command')

        else:
            raise BCIProtocolException(201, 'Unknown classifier command')

    def _parse_mode(self):
        if len(self.tokens) == 0 or type(self.tokens[0]) != str:
            raise BCIProtocolException(2, 'Please specify command')

        command = self.tokens.popleft().lower()
        if command == 'set':
            if len(self.tokens) == 0 or type(self.tokens[0]) != str:
                raise BCIProtocolException(302, 'Please specify mode to set')

            mode = self.tokens.popleft().lower()
            self.engine.set_mode(mode) 

        elif command == 'get':
            self.sendLine('MODE PROVIDE "%s"' % self.engine.get_mode())

        else:
            raise BCIProtocolException(301, 'Unknown mode command')

    def provide_mode(self, mode):
        self.sendLine('MODE PROVIDE "%s"' % mode)

    def _parse_marker(self):
        if len(self.tokens) < 2:
            raise BCIProtocolException(401, 'Please specify both a marker code and type')

        marker_type = self.tokens.popleft()
        if marker_type != 'trigger' and marker_type != 'switch':
                raise BCIProtocolException(402, 'Invalid marker type')

        code = self.tokens.popleft()

        if len(self.tokens) > 0:
            timestamp = self.tokens.popleft()
            if type(timestamp) != float:
                raise BCIProtocolException(403, 'Invalid timestamp')
        else:
            timestamp = precision_timer()

        self.engine.set_marker(code, marker_type, timestamp)

    def provide_result(self, result, timestamp=None):
        if timestamp:
            self.sendLine('RESULT PROVIDE %s' % (self.encode(result), timestamp))
        else:
            self.sendLine('RESULT PROVIDE %s' % self.encode(result))

    def error(self, e):
        self.sendLine('ERROR 000: "%s"' % e)
