# -*- coding: utf-8 -*-

"""Main module."""

import awsf
from datetime import datetime
import sys

start = datetime.now()

configFile = '../test_data/AWSF_test_config_tuol.ini'
if len(sys.argv) > 1:
    configFile = sys.argv[1]


#===============================================================================
# Initialize and run basin
#===============================================================================
#

# 1. initialize
# try:
with awsf.framework.framework.AWSF(configFile) as a:

    if not a.config['isnobal restart']['restart_crash']:
    # distribute data by running smrf
        if a.do_smrf:
            a.runSmrf()

        # convert smrf output to ipw for iSnobal
        if a.do_isnobal:
            a.nc2ipw('smrf')
            # run iSnobal
            a.run_isnobal()
            # convert ipw back to netcdf for processing
            a.ipw2nc('smrf')
    # if restart
    else:
        if a.do_isnobal:
            # restart iSnobal from crash
            a.restart_crash_image()
            # convert ipw back to netcdf for processing
            a.ipw2nc('smrf')

    # perform same operations using gridded WRF data
    if a.do_wrf:
        if 'forecast' in a.config:
            if a.config['forecast']['forecast_flag']:
                if a.do_smrf:
                    a.runSmrf_wrf()
                if a.do_isnobal:
                    a.nc2ipw('wrf')

                    a.run_isnobal_forecast()

                    a.ipw2nc('wrf')

    # Run iPySnobal from SMRF in memory
    if a.do_smrf_ipysnobal:
        a.run_smrf_ipysnobal()

    a._logger.info(datetime.now() - start)
