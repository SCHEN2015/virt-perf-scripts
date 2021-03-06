#!/usr/bin/env python3
"""Generate flent Test Report.

# Interface between StoragePerformanceTest.py
# StoragePerformanceTest.py should do:
# 1. the flent outputs should be at least in json+ format
#    the "flent --group_reporting" must be used
# 2. save the flent outputs into *.flent
# 3. put all *.flent files into the spcified path
# 4. pass the additional information by "flent --description"
#    a) "driver" - frontend driver, such as SCSI or IDE
#    b) "format" - the disk format, such as raw or xfs
#    c) "round" - the round number, such as 1, 2, 3...
#    d) "backend" - the hardware which data image based on

History:
v0.1    2020-05-20  charles.shih  Init version.
v0.2    2020-07-02  charles.shih  Basic function completed.
"""

import json
import re
import os
import click
import pandas as pd


class FlentTestReporter():
    """Flent Test Reporter.

    This class used to generate the flent test report. As basic functions:
    1. It loads the raw data from *.flent log files;
    2. It analyse the raw data and extract performance KPIs from raw data;
    3. It generates the report DataFrame and dump to a CSV file;

    Attributes:
        raw_data_list: the list to store raw data.
        perf_kpi_list: the list to store performance KPI tuples.
        df_report: a DataFrame to store the test report.

    """

    # The list of raw data, the item is loaded from flent log file.
    # Each item is a full data source (raw data) in Python dict format.
    raw_data_list = []

    # The list of performance KPIs, which are extracted from the raw data.
    # Each item represents a single flent test results in Python dict format.
    perf_kpi_list = []

    # The DataFrame to store performance KPIs for reporting, which is powered
    # by Pandas.
    df_report = None

    def _byteify(self, inputs):
        """Convert unicode to utf-8 string.

        This function converts the unicode string to bytes.

        Args:
            inputs: the object which contain unicode.

        Returns:
            The byteify version of inputs.

        """
        if isinstance(inputs, dict):
            return {
                self._byteify(key): self._byteify(value)
                for key, value in inputs.items()
            }
        elif isinstance(inputs, list):
            return [self._byteify(element) for element in inputs]
        elif isinstance(inputs, str):
            return inputs.encode('utf-8')
        else:
            return inputs

    def _get_raw_data_from_flent_log(self, data_file):
        """Get the raw data from a specified flent log file.

        This function open a specified flent log file and read the json
        block. Then converts it into Python dict format and returns it.

        Args:
            data_file: string, the path to the flent log file.

        Returns:
            This function returns a tuple like (result, raw_data):
            result:
                0: Passed
                1: Failed
            raw_data:
                The raw data in Python dict format.

        Raises:
            1. Error while handling the new json file

        """
        # Parse required params
        if data_file == '':
            print('[ERROR] Missing required params: data_file')
            return (1, None)

        try:
            with open(data_file, 'r') as f:
                json_data = json.load(f)
                if '' == b'':
                    # Convert to byteify for Python 2
                    raw_data = self._byteify(json_data)
                else:
                    # Keep strings for Python 3
                    raw_data = json_data
        except Exception as err:
            print('[ERROR] Error while handling the new json file: %s' % err)
            return (1, None)

        return (0, raw_data)

    def load_raw_data_from_flent_logs(self, params={}):
        """Load raw data from flent log files.

        This function loads raw data from a sort of flent log files and stores
        the raw data (in Python dict format) into self.raw_data_list.

        Args:
            params: dict
                result_path: string, the path where flent log files located.

        Returns:
            0: Passed
            1: Failed

        Updates:
            self.raw_data_list: store all the raw data;

        """
        # Parse required params
        if 'result_path' not in params:
            print('[ERROR] Missing required params: params[result_path]')
            return 1

        # Load raw data from files
        for fname in os.listdir(params['result_path']):
            filename = params['result_path'] + os.sep + fname

            # Tarball support
            tmpfolder = '/tmp/flent-report.tmp'
            if filename.endswith('.tar.gz') and os.path.isfile(filename):
                os.system('mkdir -p {0}'.format(tmpfolder))
                os.system('tar xf {1} -C {0}'.format(tmpfolder, filename))
                filename = tmpfolder + os.sep + fname.replace(
                    '.tar.gz', '.flent')

            # Load raw data
            if filename.endswith('.flent') and os.path.isfile(filename):
                (result,
                 raw_data) = self._get_raw_data_from_flent_log(filename)
                if result == 0:
                    self.raw_data_list.append(raw_data)

            # Tarball support, cleanup
            os.system('[ -e {0} ] && rm -rf {0}'.format(tmpfolder))

        return 0

    def _get_kpis_from_raw_data(self, raw_data):
        """Get KPIs from a specified raw data.

        This function get the performance KPIs from a specified tuple of raw
        data. It converts the units and format the values so that people can
        read them easily.

        Args:
            raw_data: dict, the specified raw data.

        Returns:
            This function returns a tuple like (result, perf_kpi):
            result:
                0: Passed
                1: Failed
            perf_kpi:
                The performance KPIs in Python dict format.

        Raises:
            1. Error while extracting performance KPIs

        """
        # Parse required params
        if raw_data == '':
            print('[ERROR] Missing required params: raw_data')
            return (1, None)

        # Get the performance KPIs
        perf_kpi = {}

        try:
            series_meta = raw_data['metadata']['SERIES_META']
            for name in series_meta.keys():
                if name == 'Ping (ms) ICMP':
                    continue
                if name in ('TCP upload', 'TCP download'):
                    command = series_meta[name]['COMMAND']

                    # Test type
                    perf_kpi['type'] = re.search(r'\s-t\s(.*?)\s',
                                                 command).group(1)

                    # Bandwidth in "Mbits/s".
                    unit = series_meta[name]['UNITS']
                    if unit != 'Mbits/s':
                        raise Exception('Bandwidth unit is not "Mbits/s".')
                    perf_kpi['bw'] = series_meta[name]['MEAN_VALUE']

                    # Message size in "Kbits"
                    perf_kpi['msize'] = series_meta[name]['SEND_SIZE'] // 1024

            # Get additional information
            try:
                # perf_kpi.update(dict)
                pass
            except Exception as err:
                print(
                    '[ERROR] Error while parsing additional information: %s' %
                    err)

            if 'driver' not in perf_kpi:
                perf_kpi['driver'] = 'NaN'
            if 'format' not in perf_kpi:
                perf_kpi['format'] = 'NaN'
            if 'round' not in perf_kpi:
                perf_kpi['round'] = 'NaN'
            if 'backend' not in perf_kpi:
                perf_kpi['backend'] = 'NaN'

        except Exception as err:
            print('[ERROR] Error while extracting performance KPIs: %s' % err)
            return (1, None)

        return (0, perf_kpi)

    def calculate_performance_kpis(self, params={}):
        """Calculate performance KPIs.

        This function calculates performance KPIs from self.raw_data_list and
        stores the performance KPI tuples into self.perf_kpi_list.

        As data source, the following attributes should be ready to use:
        1. self.raw_data_list: the list of raw data (Python dict format)

        Args:
            params: dict
                None

        Returns:
            0: Passed
            1: Failed

        Updates:
            self.perf_kpi_list: store the performance KPI tuples.

        """
        # Calculate performance KPIs
        for raw_data in self.raw_data_list:
            (result, perf_kpi) = self._get_kpis_from_raw_data(raw_data)
            if result == 0:
                self.perf_kpi_list.append(perf_kpi)
            else:
                return 1

        return 0

    def _create_report_dataframe(self):
        """Create report DataFrame.

        This function creates the report DataFrame by reading the performance
        KPIs list.

        As data source, the following attributes should be ready to use:
        1. self.perf_kpi_list: the list of performance KPIs.

        Updates:
            self.df_report: the report DataFrame.

        """
        # Create report DataFrame from self.perf_kpi_list
        self.df_report = pd.DataFrame(self.perf_kpi_list,
                                      columns=[
                                          'backend', 'driver', 'format',
                                          'type', 'msize', 'round', 'bw'
                                      ])

        # Rename the columns of the report DataFrame
        self.df_report.rename(columns={
            'backend': 'Backend',
            'driver': 'Driver',
            'format': 'Format',
            'type': 'Type',
            'msize': 'MSize(Kbits)',
            'round': 'Round',
            'bw': 'BW(Mbits/s)'
        },
                              inplace=True)

        return None

    def _format_report_dataframe(self):
        """Format report DataFrame.

        This function sorts and formats the report DataFrame.

        As data source, the following attributes should be ready to use:
        1. self.df_report: the report DataFrame.

        Updates:
            self.df_report: the report DataFrame.

        """
        # Sort the report DataFrame and reset its index
        self.df_report = self.df_report.sort_values(by=[
            'Backend', 'Driver', 'Format', 'Type', 'MSize(Kbits)', 'Round'
        ])
        self.df_report = self.df_report.reset_index().drop(columns=['index'])

        # Format the KPI values
        self.df_report = self.df_report.round(4)

        return None

    def generate_report_dataframe(self):
        """Generate the report DataFrame.

        This function generates the report DataFrame by reading the
        performance KPIs list.

        As data source, the following attributes should be ready to use:
        1. self.perf_kpi_list: the list of performance KPIs.

        Updates:
            self.df_report: the report DataFrame.

        """
        # Create DataFrame
        self._create_report_dataframe()

        # Format DataFrame
        self._format_report_dataframe()

        return None

    def report_dataframe_to_csv(self, params={}):
        """Dump the report DataFrame to a csv file.

        As data source, the self.df_report should be ready to use.

        Args:
            params: dict
                report_csv: string, the csv file to dump report DataFrame to.

        Returns:
            0: Passed
            1: Failed

        Raises:
            1. Error while dumping to csv file

        """
        # Parse required params
        if 'report_csv' not in params:
            print('[ERROR] Missing required params: params[report_csv]')
            return 1

        # Write the report to the csv file
        try:
            print('[NOTE] Dumping data into csv file "%s"...' %
                  params['report_csv'])
            content = self.df_report.to_csv()
            with open(params['report_csv'], 'w') as f:
                f.write(content)
            print('[NOTE] Finished!')

        except Exception as err:
            print('[ERROR] Error while dumping to csv file: %s' % err)
            return 1

        return 0


def generate_flent_test_report(result_path, report_csv):
    """Generate flent test report."""
    flentreporter = FlentTestReporter()

    # Load raw data from *.flent files
    return_value = flentreporter.load_raw_data_from_flent_logs(
        {'result_path': result_path})
    if return_value:
        exit(1)

    # Caclulate performance KPIs for each test
    return_value = flentreporter.calculate_performance_kpis()
    if return_value:
        exit(1)

    # Convert the KPIs into Dataframe
    flentreporter.generate_report_dataframe()

    # Dump the Dataframe as CSV file
    return_value = flentreporter.report_dataframe_to_csv(
        {'report_csv': report_csv})
    if return_value:
        exit(1)

    exit(0)


@click.command()
@click.option('--result_path',
              type=click.Path(exists=True),
              help='Specify the path where *.flent files are stored in.')
@click.option('--report_csv',
              type=click.Path(),
              help='Specify the name of CSV file for flent test reports.')
def cli(result_path, report_csv):
    """Command Line Interface."""
    # Parse and check the parameters
    if not result_path:
        print('[ERROR] Missing parameter, use "--help" to check the usage.')
        exit(1)
    if not report_csv:
        print('[WARNING] No CSV file name (--report_csv) was specified. Will \
use "%s/flent_report.csv" instead.' % result_path)
        report_csv = result_path + os.sep + 'flent_report.csv'

    # Generate flent test report
    generate_flent_test_report(result_path, report_csv)


if __name__ == '__main__':
    cli()
