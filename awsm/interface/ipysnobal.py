# -*- coding: utf-8 -*-
"""
ipysnobal: the Python implementation of iSnobal

This is not a replica of iSnobal but my interpretation and
porting to Python.  See pysnobal.exact for more direct
interpretation

Authors: Scott Havens, Micah Sandusky
"""

try:
    from pysnobal import snobal
except:
    print('pysnobal not installed, ignoring')

import ConfigParser
import sys, os
import numpy as np
import pandas as pd
from datetime import timedelta
import netCDF4 as nc
# import matplotlib.pyplot as plt
import progressbar
from copy import copy
from smrf import ipw
from smrf.utils import utils

try:
    from Queue import Queue, Empty, Full
except:
    from queue import Queue, Empty, Full
import threading
from time import time as _time
import logging
from awsm.interface import initialze_model as initmodel

# os.system("taskset -p 0xff %d" % os.getpid())

DEFAULT_MAX_Z_S_0 = 0.25
DEFAULT_MAX_H2O_VOL = 0.01

DATA_TSTEP = 0
NORMAL_TSTEP = 1
MEDIUM_TSTEP = 2
SMALL_TSTEP = 3

DEFAULT_NORMAL_THRESHOLD = 60.0
DEFAULT_MEDIUM_THRESHOLD = 10.0
DEFAULT_SMALL_THRESHOLD = 1.0
DEFAULT_MEDIUM_TSTEP = 15.0
DEFAULT_SMALL_TSTEP = 1.0

WHOLE_TSTEP = 0x1 # output when tstep is not divided
DIVIDED_TSTEP = 0x2  # output when timestep is divided

hrs2min = lambda x: x * 60
min2sec = lambda x: x * 60
SEC_TO_HR = lambda x: x / 3600.0
C_TO_K = 273.16
FREEZE = C_TO_K

# Kelvin to Celcius
K_TO_C = lambda x: x - FREEZE


def check_range(value, min_val, max_val, descrip):
    """
    Check the range of the value
    Args:
        value: value to check
        min_val: minimum value
        max_val: maximum value
        descrip: short description of input
    Returns:
        True if within range
    """
    if (value < min_val) or (value > max_val):
        raise ValueError("%s (%f) out of range: %f to %f", descrip, value, min_val, max_val);
    pass


def date_range(start_date, end_date, increment):
    '''
    Calculate a list between start and end date with
    an increment
    '''
    result = []
    nxt = start_date
    while nxt <= end_date:
        result.append(nxt)
        nxt += increment
    return np.array(result)


def get_args(myawsm):
    """
    Parse the configuration file

    Args:
        myawsm: AWSM instance

    Returns:
        options: options structure with defaults if not set

        options = {
            z: site elevation (m),
            t: time steps: data [normal, [,medium [,small]]] (minutes),
            m: snowcover's maximum h2o content as volume ratio,
            d: maximum depth for active layer (m),

            s: snow properties input data file,
            h: measurement heights input data file,
            p: precipitation input data file,
            i: input data file,
            I: initial conditions
            o: optional output data file,
            O: how often output records written (data, normal, all),
            c: continue run even when no snowcover,
            K: accept temperatures in degrees K,
            T: run timesteps' thresholds for a layer's mass (kg/m^2),
        }

    To-do: take all the rest of the defualt and check ranges for the
    input arguements, i.e. rewrite the rest of getargs.c
    """
    #------------------------------------------------------------------------------
    # these are the default options
    options = {
        'time_step': 60,
        'max-h2o': 0.01,
#         'max_z0': DEFAULT_MAX_Z_S_0,
        'c': True,
        'K': True,
        'mass_threshold': DEFAULT_NORMAL_THRESHOLD,
        'time_z': 0,
        'max_z_s_0': DEFAULT_MAX_Z_S_0,
        'z_u': 5.0,
        'z_t': 5.0,
        'z_g': 0.5,
        'relative_heights': True,
    }

    # make blank config and fill with corresponding sections
    config = {}
    config['time'] = {}
    config['output'] = {}
    config['time']['time_step'] = myawsm.time_step
    config['time']['start_date'] = myawsm.start_date
    config['time']['end_date'] = myawsm.end_date
    config['output']['frequency'] = myawsm.output_freq
    #config['output'] = myawsm.config['ipysnobal output']
    config['output']['location'] = myawsm.pathro
    config['output']['nthreads'] = int(myawsm.ipy_threads)
    config['constants'] = myawsm.config['ipysnobal constants']
    # read in the constants
    c = {}
    for v in myawsm.config['ipysnobal constants']:
        c[v] = float(myawsm.config['ipysnobal constants'][v])
    options.update(c) # update the defult with any user values

    config['constants'] = options

    #------------------------------------------------------------------------------
    # read in the time and ensure a few things
    # nsteps will only be used if end_date is not specified
    data_tstep_min = int(config['time']['time_step'])
    check_range (data_tstep_min, 1.0, hrs2min(60),"input data's timestep")
    if ((data_tstep_min > 60) and (data_tstep_min % 60 != 0)):
        raise ValueError("Data timestep > 60 min must be multiple of 60 min (whole hrs)")
    config['time']['time_step'] = data_tstep_min

    # add to constant sections for tstep_info calculation
    config['constants']['time_step'] = config['time']['time_step']


    # read in the start date and end date
    start_date = myawsm.start_date

    end_date = myawsm.end_date
    if end_date < start_date:
        raise ValueError('end_date is before start_date')
    nsteps = (end_date-start_date).total_seconds()/60  # elapsed time in minutes
    nsteps = int(nsteps / config['time']['time_step'])

    # create a date time vector
    dv = date_range(start_date, end_date,
                    timedelta(minutes=config['constants']['time_step']))

    if len(dv) != nsteps + 1:
        raise Exception('nsteps does not work with selected start and end dates')

    config['time']['start_date'] = start_date
    config['time']['end_date'] = end_date
    config['time']['nsteps'] = nsteps
    config['time']['date_time'] = dv

    # check the output section
    config['output']['frequency'] = int(config['output']['frequency'])

    # user has requested a point run from spatial data
    point_run = False

    config['output']['output_mode'] = 'data'
    config['output']['out_filename'] = None
    config['inputs'] = {}
    config['inputs']['point'] = None
    config['inputs']['input_type'] = myawsm.ipy_init_type
    config['inputs']['soil_temp'] = myawsm.soil_temp


    config['initial_conditions'] = {}
    config['initial_conditions']['file'] = os.path.abspath(myawsm.config['ipysnobal initial conditions']['init_file'])
    config['initial_conditions']['input_type'] = myawsm.config['ipysnobal initial conditions']['input_type'].lower()
    if 'restart' in myawsm.config['ipysnobal initial conditions']:
        config['initial_conditions']['restart'] = myawsm.config['ipysnobal initial conditions']['restart']
    else:
        config['initial_conditions']['restart'] = False

    # if 'mask_file' in myawsm.config['ipysnobal initial conditions']:
    #     if config['initial_conditions']['input_type'] == 'ipw' or config['initial_conditions']['input_type'] == 'ipw_out':
    #         config['initial_conditions']['mask_file'] = myawsm.config['ipysnobal initial conditions']['mask_file']
    #     elif config['initial_conditions']['input_type'] == 'netcdf':
    #         myawsm._logger.error('Mask should be in netcdf, not external file')
    if myawsm.mask_isnobal:
        if myawsm.topotype == 'ipw':
            config['initial_conditions']['mask_file'] = myawsm.fp_mask
        else:
            myawsm._logger.error('Mask should be ipw to run iPySnobal')

    return config, point_run


def get_tstep_info(options, config):
    """
    Parse the options dict, set the default values if not specified
    May need to divide tstep_info and params up into different
    functions
    """

    # intialize the time step info
    # 0 : data timestep
    # 1 : normal run timestep
    # 2 : medium  "     "
    # 3 : small   "     "

    tstep_info = []
    for i in range(4):
        t = {'level': i, 'output': False, 'threshold': None, 'time_step': None, 'intervals': None}
        tstep_info.append(t)


    # The input data's time step must be between 1 minute and 6 hours.
    # If it is greater than 1 hour, it must be a multiple of 1 hour, e.g.
    # 2 hours, 3 hours, etc.

    data_tstep_min = float(options['time_step'])
    tstep_info[DATA_TSTEP]['time_step'] = min2sec(data_tstep_min)

    norm_tstep_min = 60.0
    tstep_info[NORMAL_TSTEP]['time_step'] = min2sec(norm_tstep_min)
    tstep_info[NORMAL_TSTEP]['intervals'] = int(data_tstep_min / norm_tstep_min)

    med_tstep_min = DEFAULT_MEDIUM_TSTEP
    tstep_info[MEDIUM_TSTEP]['time_step'] = min2sec(med_tstep_min)
    tstep_info[MEDIUM_TSTEP]['intervals'] = int(norm_tstep_min / med_tstep_min)

    small_tstep_min = DEFAULT_SMALL_TSTEP
    tstep_info[SMALL_TSTEP]['time_step'] = min2sec(small_tstep_min)
    tstep_info[SMALL_TSTEP]['intervals'] = int(med_tstep_min / small_tstep_min)

    # output
    if config['output']['output_mode'] == 'data':
        tstep_info[DATA_TSTEP]['output'] = DIVIDED_TSTEP
    elif config['output']['output_mode'] == 'normal':
        tstep_info[NORMAL_TSTEP]['output'] = WHOLE_TSTEP | DIVIDED_TSTEP
    elif config['output']['output_mode'] == 'all':
        tstep_info[NORMAL_TSTEP]['output'] = WHOLE_TSTEP
        tstep_info[MEDIUM_TSTEP]['output'] = WHOLE_TSTEP
        tstep_info[SMALL_TSTEP]['output'] = WHOLE_TSTEP
    else:
        tstep_info[DATA_TSTEP]['output'] = DIVIDED_TSTEP
#     tstep_info[DATA_TSTEP]['output'] = DIVIDED_TSTEP

    # mass thresholds for run timesteps
    tstep_info[NORMAL_TSTEP]['threshold'] = DEFAULT_NORMAL_THRESHOLD
    tstep_info[MEDIUM_TSTEP]['threshold'] = DEFAULT_MEDIUM_THRESHOLD
    tstep_info[SMALL_TSTEP]['threshold'] = DEFAULT_SMALL_THRESHOLD


    # get the rest of the parameters
    params = {}

#     params['elevation'] = options['z']
    params['data_tstep'] = data_tstep_min
    params['max_h2o_vol'] = options['max-h2o']
    params['max_z_s_0'] = options['max_z_s_0']
#     params['sn_filename'] = options['s']
#     params['mh_filename'] = options['h']
#     params['in_filename'] = options['i']
#     params['pr_filename'] = options['p']
    params['out_filename'] = config['output']['out_filename']
    if params['out_filename'] is not None:
        params['out_file'] = open(params['out_filename'], 'w')
    params['stop_no_snow'] = options['c']
    params['temps_in_C'] = options['K']
    params['relative_heights'] = options['relative_heights']

    return params, tstep_info

def output_files(options, init):
    """
    Create the snow and em output netCDF file
    """

    # chunk size
    cs = (6,10,10)

    #------------------------------------------------------------------------------
    # EM netCDF
    m = {}
    m['name'] = ['net_rad','sensible_heat','latent_heat','snow_soil','precip_advected','sum_EB','evaporation','snowmelt','SWI','cold_content']
    m['units'] = ['W m-2','W m-2','W m-2','W m-2','W m-2','W m-2','kg m-2','kg m-2','kg or mm m-2','J m-2']
    m['description'] =['Average net all-wave radiation','Average sensible heat transfer','Average latent heat exchange','Average snow/soil heat exchange',
                     'Average advected heat from precipitation','Average sum of EB terms for snowcover','Total evaporation',
                     'Total snowmelt','Total runoff','Snowcover cold content']

    netcdfFile = os.path.join(options['output']['location'], 'em.nc')
    dimensions = ('time','y','x')

    em = nc.Dataset(netcdfFile, 'w')

    # create the dimensions
    em.createDimension('time',None)
    em.createDimension('y',len(init['y']))
    em.createDimension('x',len(init['x']))

    # create some variables
    em.createVariable('time', 'f', dimensions[0])
    em.createVariable('y', 'f', dimensions[1])
    em.createVariable('x', 'f', dimensions[2])

    setattr(em.variables['time'], 'units', 'hours since %s' % options['time']['start_date'])
    setattr(em.variables['time'], 'calendar', 'standard')
#     setattr(em.variables['time'], 'time_zone', time_zone)
    em.variables['x'][:] = init['x']
    em.variables['y'][:] = init['y']

    # em image
    for i,v in enumerate(m['name']):

#         em.createVariable(v, 'f', dimensions[:3], chunksizes=(6,10,10))
        em.createVariable(v, 'f', dimensions[:3], chunksizes=cs)
        setattr(em.variables[v], 'units', m['units'][i])
        setattr(em.variables[v], 'description', m['description'][i])

    options['output']['em'] = em

    #------------------------------------------------------------------------------
    # SNOW netCDF

    s = {}
    s['name'] = ['thickness','snow_density','specific_mass','liquid_water','temp_surf','temp_lower','temp_snowcover','thickness_lower','water_saturation']
    s['units'] = ['m','kg m-3','kg m-2','kg m-2','C','C','C','m','percent']
    s['description'] =['Predicted thickness of the snowcover','Predicted average snow density','Predicted specific mass of the snowcover',
                       'Predicted mass of liquid water in the snowcover','Predicted temperature of the surface layer',
                       'Predicted temperature of the lower layer','Predicted temperature of the snowcover',
                       'Predicted thickness of the lower layer', 'Predicted percentage of liquid water saturation of the snowcover']

    netcdfFile = os.path.join(options['output']['location'], 'snow.nc')
    dimensions = ('time','y','x')

    snow = nc.Dataset(netcdfFile, 'w')

    # create the dimensions
    snow.createDimension('time',None)
    snow.createDimension('y',len(init['y']))
    snow.createDimension('x',len(init['x']))

    # create some variables
    snow.createVariable('time', 'f', dimensions[0])
    snow.createVariable('y', 'f', dimensions[1])
    snow.createVariable('x', 'f', dimensions[2])

    setattr(snow.variables['time'], 'units', 'hours since %s' % options['time']['start_date'])
    setattr(snow.variables['time'], 'calendar', 'standard')
#     setattr(snow.variables['time'], 'time_zone', time_zone)
    snow.variables['x'][:] = init['x']
    snow.variables['y'][:] = init['y']

    # snow image
    for i,v in enumerate(s['name']):

        snow.createVariable(v, 'f', dimensions[:3], chunksizes=cs)
#         snow.createVariable(v, 'f', dimensions[:3])
        setattr(snow.variables[v], 'units', s['units'][i])
        setattr(snow.variables[v], 'description', s['description'][i])


    options['output']['snow'] = snow


def output_timestep(s, tstep, options):
    """
    Output the model results for the current time step
    """

    em_out = {'net_rad':'R_n_bar', 'sensible_heat':'H_bar', 'latent_heat': 'L_v_E_bar',
              'snow_soil': 'G_bar', 'precip_advected': 'M_bar',
              'sum_EB': 'delta_Q_bar', 'evaporation': 'E_s_sum',
              'snowmelt': 'melt_sum', 'SWI': 'ro_pred_sum',
              'cold_content': 'cc_s'}
    snow_out = {'thickness': 'z_s', 'snow_density': 'rho',
                'specific_mass': 'm_s', 'liquid_water': 'h2o',
                'temp_surf': 'T_s_0', 'temp_lower': 'T_s_l',
                'temp_snowcover': 'T_s', 'thickness_lower': 'z_s_l',
                'water_saturation': 'h2o_sat'}

    # preallocate
#     all_zeros = np.zeros(s['elevation'].shape)
#     em = {key: all_zeros for key in em_out.keys()}
#     snow = {key: all_zeros for key in snow_out.keys()}
    em = {}
    snow = {}


    # gather all the data together
#     for index, si in np.ndenumerate(s):
#
#         if si is not None:
    for key,value in em_out.iteritems():
        em[key] = copy(s[value])

    for key,value in snow_out.iteritems():
        snow[key] = copy(s[value])

    # convert from K to C
    snow['temp_snowcover'] -= FREEZE
    snow['temp_surf'] -= FREEZE
    snow['temp_lower'] -= FREEZE


    # now find the correct index
    # the current time integer
    times = options['output']['snow'].variables['time'] #- pd.to_timedelta(1, unit='h')
    t = nc.date2num(tstep.replace(tzinfo=None), times.units, times.calendar)

    if len(times) != 0:
        index = np.where(times[:] == t)[0]
        if index.size == 0:
            index = len(times)
        else:
            index = index[0]
    else:
        index = len(times)


    # insert the time
    options['output']['snow'].variables['time'][index] = t
    options['output']['em'].variables['time'][index] = t

    # insert the data
    for key in em_out:
        options['output']['em'].variables[key][index,:] = em[key]
    for key in snow_out:
        options['output']['snow'].variables[key][index,:] = snow[key]

    # sync to disk
    options['output']['snow'].sync()
    options['output']['em'].sync()


def initialize(params, tstep_info, init):
    """
    initialize
    """

    # create the OUTPUT_REC with additional fields and fill
    # There are a lot of additional terms that the original output_rec does not
    # have due to the output function being outside the C code which doesn't
    # have access to those variables
    sz = init['elevation'].shape
    flds = ['mask', 'elevation', 'z_0', 'rho', 'T_s_0', 'T_s_l', 'T_s', \
            'cc_s_0', 'cc_s_l', 'cc_s', 'm_s', 'm_s_0', 'm_s_l', 'z_s', 'z_s_0', 'z_s_l',\
            'h2o_sat', 'layer_count', 'h2o', 'h2o_max', 'h2o_vol','h2o_total',\
            'R_n_bar', 'H_bar', 'L_v_E_bar', 'G_bar', 'G_0_bar',\
            'M_bar', 'delta_Q_bar', 'delta_Q_0_bar', 'E_s_sum', 'melt_sum', 'ro_pred_sum',\
            'current_time', 'time_since_out']
    s = {key: np.zeros(sz) for key in flds} # the structure fields

    # go through each sn value and fill
    for key, val in init.items():
        if key in flds:
            s[key] = val

#     for key, val in mh.items():
#         if key in flds:
#             s[key] = val

    return s

################################################################
########### Functions for interfacing with smrf run ############
################################################################

def init_from_smrf(myawsm, mysmrf):
    """
    mimic the main.c from the Snobal model

    Args:
        myawsm: AWSM instance
        mysmrf: SMRF isntance
    """

    # parse the input arguments
    options, point_run = get_args(myawsm)

    # get the timestep info
    params, tstep_info = get_tstep_info(options['constants'], options)

    # open the files and read in data
    if myasm.config['isnobal restart']['restart_crash'] == False:
        init = initmodel.open_init_files(myawsm, options, mysmrf.topo.dem)
    # open restart files and zero small depths
    else:
        init = initmodel.open_restart_files(myawsm, options, mysmrf.topo.dem)
        # zero depths at correct location
        restart_var = initmodel.zero_crash_depths(myawsm,
                                                init['z_s'],
                                                init['rho'],
                                                init['T_s_0'],
                                                init['T_s_l'],
                                                init['T_s'],
                                                init['h2o_sat'])
        # put variables back in init dictionary
        for k, v in restart_var.items():
            init[k] = v

    output_rec = initialize(params, tstep_info, init)

    # create the output files
    output_files(options, init)

    return options, params, tstep_info, init, output_rec

class QueueIsnobal(threading.Thread):
    """
    Takes values from the queue and uses them to run iPySnobal
    """

    def __init__(self, queue, date_time, thread_variables,
                 options, params, tstep_info, init,
                 output_rec, nx, ny, soil_temp, logger, tzi):
        """
        Args:
            date_time: array of date_time
            queue: dict of the queue
        """

        threading.Thread.__init__(self, name='isnobal')
        self.queue = queue
        self.date_time = date_time
        self.thread_variables = thread_variables
        self.options = options
        self.params = params
        self.tstep_info = tstep_info
        self.init = init
        self.output_rec = output_rec
        self.nx = nx
        self.ny = ny
        self.soil_temp = soil_temp
        self.nthreads = self.options['output']['nthreads']
        self.tzinfo = tzi

        # get AWSM logger
        self._logger = logger
        self._logger.debug('Initialized iPySnobal thread')

    def run(self):
        """
        mimic the main.c from the Snobal model

        Args:
            configFile: path to configuration file
        """
        force_variables = ['thermal', 'air_temp', 'vapor_pressure', 'wind_speed',
                           'net_solar', 'soil_temp', 'precip', 'percent_snow',
                           'snow_density', 'dew_point']

        # loop through the input
        # do_data_tstep needs two input records so only go
        # to the last record-1

        data_tstep = self.tstep_info[0]['time_step']
        timeSinceOut = 0.0
        tmp_date = self.date_time[0].replace(tzinfo=self.tzinfo)
        wyhr = utils.water_day(tmp_date)[0] * 24.0
        start_step = wyhr # if restart then it would be higher if this were iSnobal
        # start_step = 0 # if restart then it would be higher if this were iSnobal
        step_time = start_step * data_tstep
        # step_time = start_step * 60.0

        self.output_rec['current_time'] = step_time * np.ones(self.output_rec['elevation'].shape)
        self.output_rec['time_since_out'] = timeSinceOut * np.ones(self.output_rec['elevation'].shape)

        # map function from these values to the ones requried by snobal
        map_val = {'air_temp': 'T_a', 'net_solar': 'S_n', 'thermal': 'I_lw',
                   'vapor_pressure': 'e_a', 'wind_speed': 'u',
                   'soil_temp': 'T_g', 'precip': 'm_pp',
                   'percent_snow': 'percent_snow', 'snow_density': 'rho_snow',
                   'dew_point': 'T_pp'}

        # get first timestep
        input1 = {}
        for v in force_variables:
            if v in self.queue.keys():

                data = self.queue[v].get(self.date_time[0], block=True, timeout=None)
                if data is None:
                    data = np.zeros((self.ny, self.nx))
                    self._logger.info('No data from smrf to iSnobal for {} in {}'.format(v, self.date_time[0]))
                    input1[map_val[v]] = data
                else:
                    input1[map_val[v]] = data
            elif v != 'soil_temp':
                self._logger.error('Value not in keys: {}'.format(v))

        # set ground temp
        input1['T_g'] = self.soil_temp*np.ones((self.ny, self.nx))

        input1['T_a'] += FREEZE
        input1['T_pp'] += FREEZE
        input1['T_g'] += FREEZE

        # tell queue we assigned all the variables
        self.queue['isnobal'].put([self.date_time[0], True])
        self._logger.info('Finished initializing first timestep for iPySnobal')

        #pbar = progressbar.ProgressBar(max_value=len(options['time']['date_time']))
        j = 1
        for tstep in self.date_time[1:]:
        #for tstep in options['time']['date_time'][953:958]:
        # get the output variables then pass to the function
            # this avoids zeroing of the energetics every timestep
            first_step = j
            input2 = {}
            for v in force_variables:
                if v in self.queue.keys():
                    # get variable from smrf queue
                    data = self.queue[v].get(tstep, block=True, timeout=None)
                    if data is None:

                        data = np.zeros((self.ny, self.nx))
                        self._logger.info('No data from smrf to iSnobal for {} in {}'.format(v, tstep))
                        input2[map_val[v]] = data
                    else:
                        input2[map_val[v]] = data
            # set ground temp
            input2['T_g'] = self.soil_temp*np.ones((self.ny, self.nx))
            # convert variables to Kelvin
            input2['T_a'] += FREEZE
            input2['T_pp'] += FREEZE
            input2['T_g'] += FREEZE

            self._logger.info('running PySnobal for timestep: {}'.format(tstep))
            rt = snobal.do_tstep_grid(input1, input2, self.output_rec,
                                      self.tstep_info, self.options['constants'],
                                      self.params, first_step, nthreads=self.nthreads)

            if rt != -1:
                self.logger.error('ipysnobal error on time step {}, pixel {}'.format(tstep, rt))
                break

            self._logger.info('Finished timestep: {}'.format(tstep))
            input1 = input2.copy()

            # output at the frequency and the last time step
            if ((j+1)*(data_tstep/3600.0) % self.options['output']['frequency'] == 0) or (j == len(self.options['time']['date_time'])):
                output_timestep(self.output_rec, tstep, self.options)
                self.output_rec['time_since_out'] = np.zeros(self.output_rec['elevation'].shape)

            j += 1
            #pbar.update(j)

            # put the value into the output queue so clean knows it's done
            self.queue['isnobal'].put([tstep, True])

            #self._logger.debug('%s iSnobal run from queues' % tstep)

        #pbar.finish()
