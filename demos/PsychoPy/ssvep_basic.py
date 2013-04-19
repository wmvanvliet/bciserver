import math
import socket
import select
import numpy as np
import argparse
from psychopy import core, visual, event

parser = argparse.ArgumentParser(description='Basic SSVEP demo')
parser.add_argument('-p', '--port', metavar='N', type=int, default=9000, help='Set the port number on which the server is listening. [9000]')
parser.add_argument('-d', '--device', metavar='emulator/biosemi/epoc', default='emulator', help='Recording device to select [emulator]')
parser.add_argument('-b', '--bdf-file', metavar='File', default='basic_ssvep.bdf', help='BDF file to write data to [basic_ssvep.bdf]')
parser.add_argument('-t', '--training', action='store_true', default=False, help='Switch to training mode [not set]')
args = parser.parse_args()

# Below are two functions that are useful. Below that is the main script
def wait_for_message(net_file, message, ignore_others=False):
    '''
    Wait for the server to send a specific message.
    '''
    line = ''
    while line.lower() != message.lower():
        line = net_file.readline().strip()

        if line.lower() != message.lower() and not ignore_others:
            raise ValueError('Expected %s, but got %s' % (message, line))

def data_available(net):
    '''
    Non blocking test for data
    '''
    readable, _, _ = select.select([net], [], [], 0)
    return len(readable) > 0

# Main script

# Settings for window and stimuli
screen_width, screen_height = screen_size = 800, 600
stimulus_width, stimulus_height = stimulus_size = 0.8, 0.8
nstimuli = 4
stimulus_colors = [(1, 1, 1) for i in range(nstimuli)]
stimulus_selected_color =(-1, 1, -1)
stimulus_freqs = [60/4.0, 60/5.0, 60/6.0, 60/7.0]
stimulus_pos = [(-1+stimulus_width/2, 1-stimulus_height/2),
                (1-stimulus_width/2, 1-stimulus_height/2),
                (-1+stimulus_width/2, -1+stimulus_height/2),
                (1-stimulus_width/2, -1+stimulus_height/2)]

# Create training sequence
training_sequence = np.array([[0, 00.0], # Stimulus 0 at t=0
                              [1, 10.0], # Stimulus 1 at t=10
                              [2, 20.0],
                              [3, 30.0],
                              [0, 40.0],
                              [1, 50.0],
                              [2, 60.0],
                              [3, 70.0]])
training_length = 80

# Open main window
monitor = visual.monitors.getAllMonitors()[0]
window = visual.Window(screen_size, screen=1, monitor=monitor, color=(-1,-1,-1), winType='pyglet', waitBlanking=True, fullscr=False)

# Connect to server
net = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
net.connect(('127.0.0.1', args.port))
net_file = net.makefile()

net.sendall('PING\r\n')
wait_for_message(net_file, 'PONG')

# Configure server
if args.device == 'biosemi':
    net.send('DEVICE SET biosemi\r\n')
    net.send('DEVICE PARAM SET target_channels Oz O1 O2 Pz PO3 PO4\r\n')
    net.send('DEVICE PARAM SET reference_channels 33 34\r\n')
    net.send('DEVICE PARAM SET status_as_markers 1\r\n')
    net.send('DEVICE PARAM SET port LPT1\r\n')
if args.device == 'epoc':
    net.send('DEVICE SET epoc\r\n')
    net.send('DEVICE PARAM SET target_channels AF3 AF4 F3 F4 FC5 FC6\r\n')
else:
    net.send('DEVICE SET emulator\r\n')
    net.send('DEVICE PARAM SET nchannels 6\r\n')
    net.send('DEVICE PARAM SET sample_rate 2048\r\n')

net.send('DEVICE PARAM SET bdf_file "%s"\r\n' % args.bdf_file)

net.send('CLASSIFIER SET ssvep\r\n')
net.send('DEVICE OPEN\r\n')
wait_for_message(net_file, 'MODE PROVIDE "idle"')

if args.training:
    net.send('MODE SET "data-collect"\r\n')
    wait_for_message(net_file, 'MODE PROVIDE "data-collect"')
else :
    net.send('MODE SET "training"\r\n')
    wait_for_message(net_file, 'MODE PROVIDE "training"')
    wait_for_message(net_file, 'MODE PROVIDE "idle"')
    net.send('MODE SET "application"\r\n')
    wait_for_message(net_file, 'MODE PROVIDE "application"')
        
# Create stimuli
stimuli = []
for color,pos in zip(stimulus_colors, stimulus_pos):
    stimulus = visual.Rect(window, stimulus_width, stimulus_height,
                           pos=pos, fillColor=color)
    stimuli.append(stimulus)

# Create a clock
clock = core.Clock()
T0 = clock.getTime()

running = True
selected_stimulus = -1
prev_selected_stimulus = -1

while running:

    # Determine which stimulus is currently selected
    if args.training:
        # Do training sequence
        dt = clock.getTime() - T0
        i = np.searchsorted(training_sequence[:,1], dt, 'left')
        selected_stimulus = int(training_sequence[max(0, i-1),0])

        if selected_stimulus != prev_selected_stimulus:
            net.send('MARKER switch %d\r\n' % (selected_stimulus+1))
            prev_selected_stimulus = selected_stimulus

        if dt > training_length:
            running = False

    elif data_available(net):
        # Read current selected stimulus from server
        result = np.array(net.recv(1024).strip().split(' ')[2:]).astype(np.float)
        selected_stimulus = np.argmax(result)

    # Set the color for each stimulus
    for stimulus, color in zip(stimuli, stimulus_colors):
        stimulus.setFillColor(color)

    if selected_stimulus != -1:
        stimuli[selected_stimulus].setFillColor(stimulus_selected_color)

    # Calculate alpha value for each stimulus
    now = clock.getTime() - T0
    for stimulus, freq, pos in zip(stimuli, stimulus_freqs, stimulus_pos):
        stimulus.setOpacity(0.5 + math.cos(2*math.pi*freq*now)/2)
        stimulus.draw(window)

    window.flip()

    if len(event.getKeys()) > 0:
        running = False

# Cleanup
net.send('MODE SET "idle"\r\n')
wait_for_message(net_file, 'MODE PROVIDE "idle"', True)
window.close()
core.quit()
net.close()
