'''
Collection of BCI classifiers
'''
from ssvep import SSVEP
from p3002 import P300
from erp_plotter import ERPPlotter
available_classifiers = {'ssvep-slic':SSVEP, 'p300':P300, 'erp-plotter':ERPPlotter}
