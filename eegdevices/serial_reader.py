import serial
import threading
import collections
import sys
import time

from eegdevices import precision_timer

class SerialReader(threading.Thread):
    def __init__(self, serial, buffers):
        """
        Required parameters:
        serial  - pyserial serial port object to read from
        buffers - list of equal size bytes() buffers
        """

        threading.Thread.__init__(self)
        self.deamon = True
        self.serial = serial
        self.buffers = buffers
        self.nbuffers = len(self.buffers)
        self.data_condition = threading.Condition()
        self.full_buffers = collections.deque(maxlen=self.nbuffers)
        self.running = False
        self.data = bytes()

    def stop(self):
        self.running = False

    def run(self):
        self.running = True

        # Cycle through all the buffers, reading data into them one
        # by one
        i = 0
        while(self.running):
            nbytes = self.serial.readinto(self.buffers[i])
            timestamp = precision_timer()

            self.data_condition.acquire()
            self.full_buffers.append( (nbytes, timestamp, self.buffers[i]) )
            self.data_condition.notifyAll()
            self.data_condition.release()

            i = (i+1) % self.nbuffers

if __name__ == '__main__':
    bytes_per_second = 13500
    buffer_size_seconds = 10

    # Open serial port
    ser = serial.serialwin32.Win32Serial(5, baudrate=1000000, timeout=2*buffer_size_seconds)

    handshake_command = bytes("\xFF\xFF\xFF")
    handshake_response = bytes("\xEE\xEE")
    start_measurement_command = bytes("\x20")

    ser.write(handshake_command)
    if ser.read(len(handshake_response)) == handshake_response:
        print 'Found IMEC-BE wireless EEG-device'
    else:
        ser.close()
        sys.exit(1)
    
    # Set up buffers to hold data
    buffers = [bytearray(b" " * int(buffer_size_seconds * bytes_per_second)) for n in xrange(4)]

    # Create reader
    reader = SerialReader(ser, buffers)

    # Start reading data
    ser.write(start_measurement_command)
    reader.start()

    T0 = precision_timer()
    prev_time = T0
    for i in range(100 / buffer_size_seconds):
        print i
        reader.data_condition.acquire()
        while len(reader.full_buffers) == 0:
            reader.data_condition.wait()
        full = list(reader.full_buffers)
        reader.full_buffers.clear()
        reader.data_condition.release()

        for length, timestamp, buf in full:
            dt = timestamp - prev_time
            prev_time = timestamp
            print '%.03f: Read %d bytes, Samplerate is %0.3f Hz' % (dt, length, (length/13.5) / dt)

    print 'Total time: %.03f' % (precision_timer() - T0)
    reader.running = False
    reader.join(3)
    print 'stopped'
    ser.close()

    

