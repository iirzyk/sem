import subprocess
import re
import os
import uuid
import time
from tqdm import tqdm
import importlib


class SimulationRunner(object):
    """
    The class tasked with running simulations and interfacing with the ns-3
    system.
    """

    ##################
    # Initialization #
    ##################

    def __init__(self, path, script, optimized=True):
        """
        Initialization function.

        Args:
            path (str): absolute path to the ns-3 installation this Runner
                should lock on.
            script (str): ns-3 script that will be used by this Runner.
            optimized (bool): whether this Runner should build ns-3 with the
                optimized profile.
        """

        # Save member variables
        self.path = path
        self.script = script

        if optimized:
            # For old ns-3 installations, the library is in build, while for
            # recent ns-3 installations it's in build/lib. Both paths are
            # thus required to support all versions of ns-3.
            library_path = "%s:%s" % (
                os.path.join(path, 'build/optimized'),
                os.path.join(path, 'build/optimized/lib'))

            # We use both LD_ and DYLD_ to support Linux and Mac OS.
            self.environment = {
                'LD_LIBRARY_PATH': library_path,
                'DYLD_LIBRARY_PATH': library_path}
        else:
            library_path = "%s:%s" % (os.path.join(path, 'build'),
                                      os.path.join(path, 'build/lib'))
            self.environment = {
                'LD_LIBRARY_PATH': os.path.join(path, 'build'),
                'DYLD_LIBRARY_PATH': os.path.join(path, 'build')}

        # Configure and build ns-3
        self.configure_and_build(path, optimized=optimized)

        # ns-3's build status output is used to get the executable path for the
        # specified script.
        if optimized:
            build_status_path = os.path.join(path,
                                             'build/optimized/build-status.py')
        else:
            build_status_path = os.path.join(path,
                                             'build/build-status.py')

        # By importing the file, we can naturally get the dictionary
        try:  # This only works on Python >= 3.5
            spec = importlib.util.spec_from_file_location('build_status',
                                                          build_status_path)
            build_status = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(build_status)
        except (AttributeError):  # This happens in Python <= 3.4
            import imp
            build_status = imp.load_source('build_status', build_status_path)

        # Search is simple: we look for the script name in the program field.
        # Note that this could yield multiple matches, in case the script name
        # string is contained in another script's name.
        # matches contains [program, path] for each program matching the script
        matches = [{'name': program,
                    'path': os.path.abspath(os.path.join(path, program))} for
                   program in build_status.ns3_runnable_programs if self.script
                   in program]

        if not matches:
            raise ValueError("Cannot find %s script" % self.script)

        # To handle multiple matches, we take the 'better matching' option,
        # i.e., the one with length closest to the original script name.
        match_percentages = map(lambda x: {'name': x['name'],
                                           'path': x['path'],
                                           'percentage':
                                           len(self.script)/len(x['name'])},
                                matches)

        self.script_executable = max(match_percentages,
                                     key=lambda x: x['percentage'])['path']

    #############
    # Utilities #
    #############

    def configure_and_build(self, show_progress=True, optimized=True,
                            skip_configuration=False):
        """
        Configure and build the ns-3 code.

        Args:
            show_progress (bool): whether or not to display a progress bar
                during compilation.
            optimized (bool): whether to use an optimized build. If False, use
                a standard ./waf configure.
            skip_configuration (bool): whether to skip the configuration step,
                and only perform compilation.
        """

        # Only configure if necessary
        if not skip_configuration:
            configuration_command = ['./waf', 'configure', '--enable-examples',
                                     '--disable-gtk', '--disable-python']

            if optimized:
                configuration_command += ['--build-profile=optimized',
                                          '--out=build/optimized']
                # Check whether path points to a valid installation
                subprocess.call(configuration_command, cwd=self.path,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
            else:
                # Check whether path points to a valid installation
                subprocess.call(configuration_command, cwd=self.path,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)

        # Build ns-3
        build_process = subprocess.Popen(['./waf', 'build'], cwd=self.path,
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE)

        # Show a progress bar
        if show_progress:
            line_iterator = self.get_build_output(build_process)
            pbar = None
            try:
                [initial, total] = next(line_iterator)
                pbar = tqdm(line_iterator, initial=initial, total=total,
                            unit='file', desc='Building ns-3', smoothing=0)
                for current, total in pbar:
                    pbar.n = current
            except (StopIteration):
                if pbar is not None:
                    pbar.n = pbar.total
                pass
        else:  # Wait for the build to finish anyway
            build_process.communicate()

    def get_build_output(self, process):
        """
        Parse the output of the ns-3 build process to extract the information
        that is needed to draw the progress bar.

        Args:
            process: the subprocess instance to listen to.
        """

        while True:
            output = process.stdout.readline()
            if output == b'' and process.poll() is not None:
                if process.returncode > 0:
                    raise Exception("Compilation ended with an error"
                                    ".\nSTDERR\n%s\nSTDOUT\n%s" %
                                    (process.stderr.read(),
                                     process.stdout.read()))
                raise StopIteration
            if output:
                # Parse the output to get current and total tasks
                # This assumes the progress displayed by waf is in the form
                # [current/total]
                matches = re.search('\[\s*(\d+?)/(\d+)\].*',
                                    output.strip().decode('utf-8'))
                if matches is not None:
                    yield [int(matches.group(1)), int(matches.group(2))]

    def get_available_parameters(self):
        """
        Return a list of the parameters made available by the script.
        """

        # At the moment, we rely on regex to extract the list of available
        # parameters. This solution will break if the format of the output
        # changes, but this is the best option that is currently available.

        result = subprocess.check_output([self.script_executable,
                                          '--PrintHelp'], env=self.environment,
                                         cwd=self.path).decode('utf-8')

        # Isolate the list of parameters
        options = re.findall('.*Program\s(?:Options|Arguments):'
                             '(.*)General\sArguments.*',
                             result, re.DOTALL)

        # Get the single parameter names
        if len(options):
            args = re.findall('.*--(.*?):.*', options[0], re.MULTILINE)
            return args
        else:
            return []

    ######################
    # Simulation running #
    ######################

    def run_simulations(self, parameter_list, data_folder):
        """
        Run several simulations using a certain combination of parameters.

        Yields results as simulations are completed.

        Args:
            parameter_list (list): list of parameter combinations to simulate.
            data_folder (str): folder in which to save subfolders containing
                simulation output.
        """

        for idx, parameter in enumerate(parameter_list):

            current_result = {
                'params': {},
                'meta': {}
                }
            current_result['params'].update(parameter)

            command = [self.script_executable] + ['--%s=%s' % (param, value)
                                                  for param, value in
                                                  parameter.items()]

            # Run from dedicated temporary folder
            current_result['meta']['id'] = str(uuid.uuid4())
            temp_dir = os.path.join(data_folder, current_result['meta']['id'])
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)

            start = time.time()  # Time execution
            stdout_file_path = os.path.join(temp_dir, 'stdout')
            stderr_file_path = os.path.join(temp_dir, 'stderr')
            with open(stdout_file_path, 'w') as stdout_file, open(
                    stderr_file_path, 'w') as stderr_file:
                return_code = subprocess.call(command, cwd=temp_dir,
                                              env=self.environment,
                                              stdout=stdout_file,
                                              stderr=stderr_file)
            end = time.time()  # Time execution

            if return_code > 0:
                complete_command = [self.script]
                complete_command.extend(command[1:])
                complete_command = "./waf --run \"%s\"" % (
                    ' '.join(complete_command))

                with open(stdout_file_path, 'r') as stdout_file, open(
                        stderr_file_path, 'r') as stderr_file:
                    raise Exception(('Simulation exited with an error.\n'
                                     'Params: %s\n'
                                     '\nStderr: %s\n'
                                     'Stdout: %s\n'
                                     'Use this command to reproduce:\n'
                                     '%s'
                                     % (parameter, stderr_file.read(),
                                        stdout_file.read(), complete_command)))

            current_result['meta']['elapsed_time'] = end-start

            yield current_result
