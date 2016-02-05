# -*- coding: utf-8 -*-
"""
Created on Tue Oct 20 17:40:07 2015

@author: casim
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import h5py
import re

from edi12.fitting_optimization import *
from edi12.peak_fitting import *
import shutil
from edi12.peak_fitting import cos_
from edi12.XRD_tools import XRD_tools


class XRD_analysis(XRD_tools):
    """
    Takes an un-processed .nxs file from the I12 EDXD detector and fits curves
    to all specified peaks for each detector. Calculates strain and details
    associated error. 
    """
   
    def __init__(self, file, q0, window, func = gaussian):
        """
        Extract and manipulate all pertinent data from the .nxs file. Takes 
        either one or multiple (list) q0s.
        """
        super(XRD_tools, self).__init__(file)
        scan_command = self.f['entry1/scan_command'][:]#.astype(str)#[0]
        print(scan_command)
        self.dims = re.findall(b'ss2_\w+', scan_command)
        self.slit_size = self.f['entry1/before_scan/s4/s4_xs'][0]
        group = self.f['entry1']['EDXD_elements']
        q, I = group['edxd_q'], group['data']
        
        # Convert int or float to list
        if type(q0) == int or type(q0) == float or type(q0) == np.float64:
            q0 = [q0]
        self.q0 = q0
        self.peak_windows = [[q - window/2, q + window/2] for q in q0]
        
        # Accept detector specific q0 2d-array
        if len(np.shape(q0)) == 2:
            q0_av = np.nanmean(q0, 0)
            self.peak_windows = [[q - window/2, q + window/2] for q in q0_av]
 
        # Iterate across q0 values and fit peaks for all detectors
        array_shape = I.shape[:-1] + (np.shape(q0)[-1],)
        self.peaks = np.nan * np.ones(array_shape)
        self.peaks_err = np.nan * np.ones(array_shape)
        for idx, window in enumerate(self.peak_windows):
            fit_data = array_fit(q, I, window, func)
            self.peaks[..., idx], self.peaks_err[..., idx] = fit_data
        self.strain = (self.q0 - self.peaks)/ self.q0
        self.strain_err = (self.q0 - self.peaks_err)/ self.q0
        
        self.strain_theta = None
        self.theta = None
        self.strain_fit()

    def strain_fit(self):
        """
        Fits a sin function to the 
        ***** Should ONLY Need this here - not in tools!
        """
        data_shape = self.strain.shape
        self.strain_param = np.nan * np.ones(data_shape[:-2] + \
                            (data_shape[-1], ) + (3, ))
        for idx in np.ndindex(data_shape[:-2] + (data_shape[-1],)):
            data = self.strain[idx[:-1]][:-1][..., idx[-1]]
            not_nan = ~np.isnan(data)
            angle = np.linspace(0, np.pi, 23)
            p0 = [np.nanmean(data), 3*np.nanstd(data)/(2**0.5), 0]
            try:
                a, b = curve_fit(cos_, angle[not_nan], data[not_nan], p0)
                self.strain_param[idx] = a
            except (TypeError, RuntimeError):
                print('Type or runtime error...')

    def save_to_nxs(self, fname = None):
        """
        Saves all data back into an expanded .nxs file. Contains all original 
        data plus q0, peak locations and strain.
        
        # fname:      File name/location - default is to save to parent 
                      directory (*_md.nxs) 
        """
        if fname == None:        
            fname = '%s_md.nxs' % self.filename[:-4]
        
        shutil.copy(self.filename, fname)
        with h5py.File(fname, 'r+') as f:
            data_ids = ('dims', 'slit_size', 'q0','peak_windows', 'peaks',  
                        'peaks_err', 'strain', 'strain_err', 'strain_param')
            data_array = (self.dims, self.slit_size, self.q0,  
                          self.peak_windows, self.peaks, self.peaks_err,  
                          self.strain, self.strain_err, self.strain_param)
            
            for data_id, data in zip(data_ids, data_array):
                base_tree = 'entry1/EDXD_elements/%s'
                f.create_dataset(base_tree % data_id, data = data)