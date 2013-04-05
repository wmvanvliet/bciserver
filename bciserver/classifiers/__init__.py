'''
Collection of BCI classifiers
'''
from ssvep import SSVEP
from ssvep_single import SSVEPSingle
from p3002 import P300
from erp_plotter import ERPPlotter
available_classifiers = {'ssvep':SSVEP, 'ssvep-single':SSVEPSingle, 'p300':P300, 'erp-plotter':ERPPlotter}
