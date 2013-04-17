import time, os, ctypes
import math
import socket
import select
import numpy as np
from psychopy import core, visual, event

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

# Open main window
window = visual.Window(screen_size, color=(-1,-1,-1), winType='pyglet', waitBlanking=True, fullscr=False)

# Connect to server
net = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
net.connect(('127.0.0.1', 9000))
net_file = net.makefile()

net.sendall('PING\r\n')
wait_for_message(net_file, 'PONG')

# Configure server
net.send('DEVICE SET emulator\r\n')
net.send('DEVICE PARAM SET bdf_file "test.bdf"\r\n')
net.send('CLASSIFIER SET ssvep\r\n')
net.send('DEVICE OPEN\r\n')
wait_for_message(net_file, 'MODE PROVIDE "idle"')

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
while running:
    if data_available(net):
        result = np.array(net.recv(1024).strip().split(' ')[2:]).astype(np.float)
        for stimulus, color in zip(stimuli, stimulus_colors):
            stimulus.setFillColor(color)
        stimuli[np.argmax(result)].setFillColor(stimulus_selected_color)

    now = clock.getTime() - T0

    for stimulus, freq, pos in zip(stimuli, stimulus_freqs, stimulus_pos):
        # Calculate alpha value
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
