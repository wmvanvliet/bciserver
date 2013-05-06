from matplotlib import pyplot as plt
from matplotlib import animation
import cProfile
import bciserver
import time
import numpy as np
import scipy.signal
import psychic

class ERPPlotter():

    def __init__(self, r, time_range=8, vspace=500):
        self.r = r
        self.time = np.arange(int(time_range * r.sample_rate)) / float(r.sample_rate)
        self.fig, ax = plt.subplots()
        self.bases = np.arange(r.nchannels) * vspace
        self.ani = animation.FuncAnimation(self.fig, self.update, init_func=self.setup)
        plt.ylim(-vspace, r.nchannels * vspace)
        ax.set_yticks(self.bases)
        ax.set_yticklabels(self.r.channel_names)
        ax.yaxis.grid(True)
        plt.title('EEG signal')

        self.filt = psychic.nodes.OnlineFilter(None)
        self.filt.fs = r.sample_rate
        self.filt.filter = scipy.signal.iirfilter(3, [0.1/(r.sample_rate/2.0), 40/(r.sample_rate/2.0)])

    def setup(self):
        self.lines = []
        for ch, base in zip(range(self.r.nchannels), self.bases):
            self.lines.append(plt.plot(self.time, base + np.zeros(len(self.time)))[0])
        return self.lines

    def update(self, i):
        d = r.read(block=True)
        if d == None:
            return self.lines

        d = self.filt.apply(d)

        for ch, line in enumerate(self.lines):
            dat = line.get_ydata()
            new_dat = np.zeros(len(dat))
            new_dat[:-d.ninstances] = dat[d.ninstances:]
            new_dat[-d.ninstances:] = d.X[ch,:] + self.bases[ch]
            line.set_ydata(new_dat)

        return self.lines

    def show(self):
        plt.show()

r = bciserver.eegdevices.Emulator(buffer_size_seconds=0.1, nchannels=32)
r.start_capture()
p = ERPPlotter(r)

cProfile.run('p.show()', 'eegplotter_stats')

r.stop()
