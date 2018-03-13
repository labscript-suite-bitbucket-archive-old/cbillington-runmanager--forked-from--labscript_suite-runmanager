#####################################################################
#                                                                   #
# /batch_compiler_labscript.py                                      #
#                                                                   #
# Copyright 2013, Monash University                                 #
#                                                                   #
# This file is part of the program runmanager, in the labscript     #
# suite (see http://labscriptsuite.org), and is licensed under the  #
# Simplified BSD License. See the license.txt file in the root of   #
# the project for the full license.                                 #
#                                                                   #
#####################################################################

import sys
import traceback
from zprocess import setup_connection_with_parent
to_parent, from_parent, kill_lock = setup_connection_with_parent(lock = True)

try:
    from labscript_utils import check_version
except ImportError:
    raise ImportError('Require labscript_utils > 2.1.0')

check_version('labscript_utils', '2', '3')
check_version('labscript', '2.4', '3')
check_version('zprocess', '1.1.5', '3')

import labscript
import labscript_utils.excepthook
from labscript_utils.modulewatcher import ModuleWatcher

from runmanager.batch_compiler_base import BatchProcessorBase

class BatchProcessor(BatchProcessorBase):
    module_name = "labscript"
    
    def module_init(self, labscript_file, run_file):
        labscript.labscript_init(run_file, labscript_file=labscript_file)
        
    def module_cleanup(self, labscript_file, run_file):
        labscript.labscript_cleanup()
        
    def module_protected_global_names(self):
        return labscript.__dict__.keys()
                 
                   
if __name__ == '__main__':
    module_watcher = ModuleWatcher() # Make sure modified modules are reloaded
    batch_processor = BatchProcessor(to_parent,from_parent,kill_lock, module_watcher)
