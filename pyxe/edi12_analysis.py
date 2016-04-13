# -*- coding: utf-8 -*-
"""
Created on Tue Oct 20 17:40:07 2015

@author: casimp
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import h5py
import re
import shutil
import numpy as np
from scipy.optimize import curve_fit

from pyxe.fitting_tools import array_fit
from pyxe.fitting_functions import cos_
from pyxe.strain_tools import StrainTools
from pyxe.plotting import StrainPlotting
from pyxe.analysis_tools import dimension_fill, scrape_slits


class EDI12(StrainTools, StrainPlotting):
    """
    Takes an un-processed .nxs file from the I12 EDXD detector and fits curves
    to all specified peaks for each detector. Calculates strain and details
    associated error. 
    """
   
    def __init__(self, file, unused_detector=23, phi=None):
        """
        Extract useful data from raw .nxs file. Removes data from unused 
        detector. Allows definition of az_angle (phi) if the unused detector is
        not 23.
        """
        self.filename = file
        self.f = h5py.File(file, 'r') 
        self.ss2_x = dimension_fill(self.f, 'ss2_x')   
        self.ss2_y = dimension_fill(self.f, 'ss2_y')
        self.ss2_z = dimension_fill(self.f, 'ss2_z')
        self.co_ords = {b'ss2_x': self.ss2_x, b'ss2_y': self.ss2_y, 
                        b'ss2_z': self.ss2_z} 
        self.slit_size = scrape_slits(self.f)   
        scan_command = self.f['entry1/scan_command'][0]
        self.dims = re.findall(b'ss2_\w+', scan_command)
        self.q = self.f['entry1/EDXD_elements/edxd_q'][:]
        self.I = self.f['entry1/EDXD_elements/data'][:]
        self.I = np.delete(self.I, unused_detector, -2)
        if phi == None:
            self.phi = np.linspace(-np.pi, 0, 23)
        else:
            self.phi = phi
        
        
    def peak_fit(self, q0, window, func='gaussian', error_limit=10**-4,
                 progress = True): 
        
        self.q0 = [q0] if isinstance(q0, (int, float, np.float64)) else q0
        self.peak_windows = [[q_ - window/2, q_ + window/2] for q_ in self.q0]               
        if len(np.shape(self.q0)) == 2:
            q0_av = np.nanmean(self.q0, 0)
            self.peak_windows = [[q_ - window/2, q_ +window/2] for q_ in q0_av]
       
       # Iterate across q0 values and fit peaks for all detectors
        array_shape = self.I.shape[:-1] + (np.shape(self.q0)[-1],)
        data = [np.nan * np.ones(array_shape) for i in range(4)]
        self.peaks, self.peaks_err, self.fwhm, self.fwhm_err = data

        print('\nFile: %s - %s acquisition points\n' % 
             (self.filename, self.I[..., 0, 0].size))
        
        for idx, window in enumerate(self.peak_windows):
            fit = array_fit(self.q,self.I, window, func, error_limit, progress)
            self.peaks[..., idx], self.peaks_err[..., idx] = fit[0], fit[1]
            self.fwhm[..., idx], self.fwhm_err[..., idx] = fit[2], fit[3]
        
        self.strain = (self.q0 - self.peaks)/ self.q0
        self.strain_err = (self.q0 - self.peaks_err)/ self.q0
        self.full_ring_fit()
        

    def full_ring_fit(self):
        """
        Fits a sinusoidal curve to the strain information from each detector. 
        """
        data_shape = self.peaks.shape[:-2] + self.peaks.shape[-1:] + (3, )
        self.strain_param = np.nan * np.ones(data_shape)
        for idx in np.ndindex(data_shape[:-1]):
            data = self.strain[idx[:-1]][..., idx[-1]]
            not_nan = ~np.isnan(data)
            count = 0
            if self.phi[not_nan].size > 2:
                p0 = [np.nanmean(data), 3*np.nanstd(data)/(2**0.5), 0]
                try:
                    a, b = curve_fit(cos_,self.phi[not_nan], data[not_nan], p0)
                    self.strain_param[idx] = a
                except (TypeError, RuntimeError):
                    count += 1
            else:
                count += 1
        print('\nUnable to fit full ring data %i out of %i points'
              % (count, np.size(self.peaks[:, 0, 0])))
                
        

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
        data_ids = ('phi', 'dims', 'slit_size', 'q0','peak_windows', 'peaks',  
                    'peaks_err', 'fwhm', 'fwhm_err', 'strain', 'strain_err', 
                    'strain_param', 'q')
        data_array = (self.phi, self.dims, self.slit_size, self.q0,  
                      self.peak_windows, self.peaks, self.peaks_err, self.fwhm,
                      self.fwhm_err, self.strain, self.strain_err, 
                      self.strain_param, self.q)
        with h5py.File(fname, 'r+') as f:
            
            for data_id, data in zip(data_ids, data_array):
                base_tree = 'entry1/EDXD_elements/%s'
                f.create_dataset(base_tree % data_id, data = data)
                
                