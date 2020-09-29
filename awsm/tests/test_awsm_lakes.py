import os
from inicheck.tools import cast_all_variables

from awsm.framework.framework import run_awsm
from awsm.tests.awsm_test_case_lakes import AWSMTestCaseLakes


class TestStandardLakes(AWSMTestCaseLakes):
    """
    Testing using Lakes:
        - ipysnobal
        - initialize from snow.nc file
        - loading from netcdf
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.gold_dir = cls.basin_dir.joinpath('gold_hrrr')

        cls.gold_em = os.path.join(cls.gold_dir, 'em.nc')
        cls.gold_snow = os.path.join(cls.gold_dir, 'snow.nc')

        cls.output_path = cls.basin_dir.joinpath(
            'output/lakes/wy2020/lakes_gold/run20191001_20191001'
        )

        run_awsm(cls.config_file)

    def test_thickness(self):
        self.compare_netcdf_files('snow.nc', 'thickness')

    def test_snow_density(self):
        self.compare_netcdf_files('snow.nc', 'snow_density')

    def test_specific_mass(self):
        self.compare_netcdf_files('snow.nc', 'specific_mass')

    def test_liquid_water(self):
        self.compare_netcdf_files('snow.nc', 'liquid_water')

    def test_temp_surf(self):
        self.compare_netcdf_files('snow.nc', 'temp_surf')

    def test_temp_lower(self):
        self.compare_netcdf_files('snow.nc', 'temp_lower')

    def test_temp_snowcover(self):
        self.compare_netcdf_files('snow.nc', 'temp_snowcover')

    def test_thickness_lower(self):
        self.compare_netcdf_files('snow.nc', 'thickness_lower')

    def test_water_saturation(self):
        self.compare_netcdf_files('snow.nc', 'water_saturation')

    def test_net_rad(self):
        self.compare_netcdf_files('em.nc', 'net_rad')

    def test_sensible_heat(self):
        self.compare_netcdf_files('em.nc', 'sensible_heat')

    def test_latent_heat(self):
        self.compare_netcdf_files('em.nc', 'latent_heat')

    def test_snow_soil(self):
        self.compare_netcdf_files('em.nc', 'snow_soil')

    def test_precip_advected(self):
        self.compare_netcdf_files('em.nc', 'precip_advected')

    def test_sum_EB(self):
        self.compare_netcdf_files('em.nc', 'sum_EB')

    def test_evaporation(self):
        self.compare_netcdf_files('em.nc', 'evaporation')

    def test_snowmelt(self):
        self.compare_netcdf_files('em.nc', 'snowmelt')

    def test_SWI(self):
        self.compare_netcdf_files('em.nc', 'SWI')

    def test_cold_content(self):
        self.compare_netcdf_files('em.nc', 'cold_content')


class TestLakesSMRFiPysnobal(TestStandardLakes):
    """
    Testing using Lakes:
        - smrf_ipysnobal
        - initialize from snow.nc file
        - loading from netcdf
    """

    @classmethod
    def setUpClass(cls):
        cls.load_base_config()
        cls.create_output_dir()

        cls.gold_dir = cls.basin_dir.joinpath('gold_hrrr')

        cls.gold_em = os.path.join(cls.gold_dir, 'em.nc')
        cls.gold_snow = os.path.join(cls.gold_dir, 'snow.nc')

        cls.output_path = cls.basin_dir.joinpath(
            'output/lakes/wy2020/lakes_gold/run20191001_20191001'
        )

        config = cls.base_config_copy()
        config.raw_cfg['awsm master']['run_smrf'] = False
        config.raw_cfg['awsm master']['model_type'] = 'smrf_ipysnobal'
        config.raw_cfg['system']['threading'] = False

        config.apply_recipes()
        config = cast_all_variables(config, config.mcfg)

        run_awsm(config, testing=True)


class TestLakesSMRFiPysnobalThreaded(TestStandardLakes):
    """
    Testing using Lakes:
        - smrf_ipysnobal threaded
        - initialize from snow.nc file
    """

    @classmethod
    def setUpClass(cls):
        cls.load_base_config()
        cls.create_output_dir()

        cls.gold_dir = cls.basin_dir.joinpath('gold_hrrr')

        cls.gold_em = os.path.join(cls.gold_dir, 'em.nc')
        cls.gold_snow = os.path.join(cls.gold_dir, 'snow.nc')

        cls.output_path = cls.basin_dir.joinpath(
            'output/lakes/wy2020/lakes_gold/run20191001_20191001'
        )

        config = cls.base_config_copy()
        config.raw_cfg['awsm master']['run_smrf'] = False
        config.raw_cfg['awsm master']['model_type'] = 'smrf_ipysnobal'
        config.raw_cfg['system']['threading'] = True

        config.apply_recipes()
        config = cast_all_variables(config, config.mcfg)

        run_awsm(config, testing=True)
