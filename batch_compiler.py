#####################################################################
#                                                                   #
# /batch_compiler.py                                                #
#                                                                   #
# Copyright 2013, Monash University                                 #
#                                                                   #
# This file is part of the program runmanager, in the labscript     #
# suite (see http://labscriptsuite.org), and is licensed under the  #
# Simplified BSD License. See the license.txt file in the root of   #
# the project for the full license.                                 #
#                                                                   #
#####################################################################

import __builtin__
import keyword
import sys
import traceback

import runmanager
import labscript_utils.h5_lock, h5py
import labscript_utils.excepthook

import numpy

class GlobalNameError(Exception):
    pass

class BatchProcessorBase(object):
    module_name = "your module"
    def __init__(self, to_parent, from_parent, kill_lock, module_watcher):
        self.to_parent = to_parent
        self.from_parent = from_parent
        self.kill_lock = kill_lock
        self.module_watcher = module_watcher
        self.mainloop()
        
    def mainloop(self):
        while True:
            signal, data =  self.from_parent.get()
            if signal == 'compile':
                # Do not let the modulewatcher unload any modules whilst we're working:
                with self.kill_lock, self.module_watcher.lock:
                    success = self.compile(*data)
                self.to_parent.put(['done',success])
            elif signal == 'quit':
                sys.exit(0)
            else:
                raise ValueError(signal)
                 
    def module_init(self, labscript_file, run_file):
        raise NotImplementedError('You must subclass BatchProcessorBase and reimplement the module_init method')
        
    def module_cleanup(self, labscript_file, run_file):
        raise NotImplementedError('You must subclass BatchProcessorBase and reimplement the module_cleanup method')
    
    def module_protected_global_names(self):
        raise NotImplementedError('You must subclass BatchProcessorBase and reimplement the module_protected_global_names method')
        
    def load_globals(self, hdf5_filename, _builtins_dict):
        params = runmanager.get_shot_globals(hdf5_filename)
        for name in params.keys():
            if name in self.module_protected_global_names() or name in globals() or name in locals() or name in _builtins_dict:
                raise GlobalNameError('Error whilst parsing globals from %s. \'%s\''%(hdf5_filename,name) +
                                     ' is already a name used by Python or %s.'%self.module_name+
                                     ' Please choose a different variable name to avoid a conflict.')
            if name in keyword.kwlist:
                raise GlobalNameError('Error whilst parsing globals from %s. \'%s\''%(hdf5_filename,name) +
                                     ' is a reserved Python keyword.' +
                                     ' Please choose a different variable name.')
            try:
                assert '.' not in name
                exec(name + ' = 0')
                exec('del ' + name )
            except:
                raise GlobalNameError('ERROR whilst parsing globals from %s. \'%s\''%(hdf5_filename,name) +
                                     'is not a valid Python variable name.' +
                                     ' Please choose a different variable name.')
                                     
            # Workaround for the fact that numpy.bool_ objects dont 
            # match python's builtin True and False when compared with 'is':
            if type(params[name]) == numpy.bool_: # bool_ is numpy.bool_
                params[name] = bool(params[name])                         
            # 'None' is stored as an h5py null object reference:
            if isinstance(params[name], h5py.Reference) and not params[name]:
                params[name] = None
            _builtins_dict[name] = params[name]
                 
    def compile(self,labscript_file, run_file):
        # The namespace the labscript will run in:
        sandbox = {'__name__':'__main__'}
        # We need to backup the builtins as they are now, as well as have a
        # reference to the actual builtins dictionary (which will change as we
        # add globals and possibly other items to it)
        _builtins_dict = __builtin__.__dict__
        _existing_builtins_dict = _builtins_dict.copy()
        
        try:
            # load the globals
            self.load_globals(run_file, _builtins_dict)
            
            self.module_init(labscript_file, run_file)
            execfile(labscript_file,sandbox,sandbox)
            return True
        except:
            traceback_lines = traceback.format_exception(*sys.exc_info())
            del traceback_lines[1:2]
            message = ''.join(traceback_lines)
            sys.stderr.write(message)
            return False
        finally:
            # restore builtins
            for name in _builtins_dict.copy():
                if name not in _existing_builtins_dict:
                    del _builtins_dict[name]
                else:
                    _builtins_dict[name] = _existing_builtins_dict[name]
            self.module_cleanup(labscript_file, run_file)
                   
if __name__ == '__main__':
    module_watcher = ModuleWatcher() # Make sure modified modules are reloaded
    batch_processor = BatchProcessorBase(to_parent,from_parent,kill_lock, module_watcher)
