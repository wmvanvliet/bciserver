'''
Collection of BCI classifiers
'''
from ssvep import Classifier as SSVEP
from p300 import Classifier as P300
from erp_plotter import Classifier as ERPPlotter
available_classifiers = {'ssvep-slic':SSVEP, 'p300':P300, 'erp-plotter':ERPPlotter}
