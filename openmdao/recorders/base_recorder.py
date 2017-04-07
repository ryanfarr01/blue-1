"""
Class definition for BaseRecorder, the base class for all recorders.
"""
from fnmatch import fnmatchcase
import sys

from six import StringIO

from openmdao.utils.generalized_dict import OptionsDictionary
from openmdao.utils.general_utils import warn_deprecation

import warnings


class BaseRecorder(object):
    """
    Base class for all case recorders and is not a functioning case recorder on its own.

    Options
    -------
    options['record_metadata'] :  bool(True)
        Tells recorder whether to record variable attribute metadata.
    options['record_outputs'] :  bool(True)
        Tells recorder whether to record the outputs vector.
    options['record_inputs'] :  bool(False)
        Tells recorder whether to record the inputs vector.
    options['record_residuals'] :  bool(False)
        Tells recorder whether to record the ressiduals vector.
    options['record_derivatives'] :  bool(True)
        Tells recorder whether to record derivatives that are requested by a `Driver`.
    options['includes'] :  list of strings
        Patterns for variables to include in recording.
    options['excludes'] :  list of strings
        Patterns for variables to exclude in recording (processed after includes).
    """

    def __init__(self):
        """
        initialize.
        """
        self.options = OptionsDictionary()
        # Options common to all objects
        self.options.declare('record_metadata', bool, 'Record metadata', True)
        self.options.declare('includes', list, 'Patterns for variables to include in recording',
                             ['*'])
        self.options.declare('excludes', list, 'Patterns for vars to exclude in recording '
                                               '(processed post-includes)', value=[])

        # Old options that will be deprecated
        self.options.declare('record_unknowns', bool, 'Deprecated option to record unknowns.',
                             False)
        self.options.declare('record_params', bool, 'Deprecated option to record params.', False)
        self.options.declare('record_resids', bool, 'Deprecated option to record residuals.',
                             False)
        self.options.declare('record_derivs', bool, 'Deprecated option to record derivatives.',
                             False)
        # System options
        self.options.declare('record_outputs', bool,
                             'Set to True to record outputs at the system level', True)
        self.options.declare('record_inputs', bool,
                             'Set to True to record inputs at the system level', True)
        self.options.declare('record_residuals', bool,
                             'Set to True to record residuals at the system level', True)
        self.options.declare('record_derivatives', bool,
                             'Set to True to record derivatives at the system level', False)
        # Driver options
        self.options.declare('record_desvars', bool, 'Set to True to record design variables at '
                                                     'the driver level', True)
        self.options.declare('record_responses', bool, 'Set to True to record responses at the '
                                                       'driver level', False)
        self.options.declare('record_objectives', bool, 'Set to True to record objectives at the '
                                                        'driver level', False)
        self.options.declare('record_constraints', bool, 'Set to True to record constraints at '
                                                         'the driver level', False)
        # Solver options
        self.options.declare('record_abs_error', bool, 'Set to True to record absolute error at '
                             'the solver level', True)
        self.options.declare('record_rel_error', bool, 'Set to True to record relative error at '
                             'the solver level', True)
        self.options.declare('record_output', bool, 'Set to True to record output at the '
                             'solver level', False)
        self.options.declare('record_solver_residuals', bool, 'Set to True to record residuals '
                             'at the solver level', False)

        self.out = None

        # global counter that is used in iteration coordinate
        self._counter = 0

    def startup(self):
        """
        Prepare for a new run.

        Args
        ----
        group : `Group`
            Group that owns this recorder.
        """
        myinputs = myoutputs = myresiduals = set()

        check = self._check_path
        incl = self.options['includes']
        excl = self.options['excludes']

        # Deprecated options here, but need to preserve backward compatibility if possible.
        if self.options['record_params']:
            warn_deprecation("record_params is deprecated, please use record_inputs.")
            # set option to what the user intended.
            self.options['record_inputs'] = True

        if self.options['record_unknowns']:
            warn_deprecation("record_ is deprecated, please use record_inputs.")
            # set option to what the user intended.
            self.options['record_outputs'] = True

        if self.options['record_resids']:
            warn_deprecation("record_params is deprecated, please use record_inputs.")
            # set option to what the user intended.
            self.options['record_residuals'] = True

        # Compute the inclusion lists for recording
        # if self.options['record_inputs']:
        #     myinputs = [n for n in group.inputs if check(n, incl, excl)]
        # if self.options['record_outputs']:
        #     myoutputs = [n for n in group.outputs if check(n, incl, excl)]
        #     if self.options['record_residuals']:
        #         myresiduals = myoutputs # outputs and residuals have same names
        # elif self.options['record_residuals']:
        #     myresiduals = [n for n in group.residuals if check(n, incl, excl)]
        #
        # self._filtered[group.pathname] = {
        #     'p': myinputs,
        #     'u': myoutputs,
        #     'r': myresiduals
        # }

    def _check_path(self, path, includes, excludes):
        """
        Return True if `path` should be recorded.
        """
        # First see if it's included
        for pattern in includes:
            if fnmatchcase(path, pattern):
                # We found a match. Check to see if it is excluded.
                for ex_pattern in excludes:
                    if fnmatchcase(path, ex_pattern):
                        return False
                return True

        # Did not match anything in includes.
        return False

    def _get_pathname(self, iteration_coordinate):
        """
        Convert iteration coord.

        Change coordinate to key to index _filtered to retrieve names of variables to be recorded.
        """
        return '.'.join(iteration_coordinate[5::2])

    def _filter_vector(self, vecwrapper, key, iteration_coordinate):
        """
        Return a dict that is a subset of the given vecwrapper to be recorded.
        """
        if not vecwrapper:
            return vecwrapper

        pathname = self._get_pathname(iteration_coordinate)
        return {n: vecwrapper[n] for n in self._filtered[pathname][key]}

    def record_metadata(self, group):
        """
        Write the metadata of the given group.

        Args
        ----
        group : `System`
            `System` containing vectors.
        """
        raise NotImplementedError()

    # TODO_RECORDER: change the signature to match what we decided to do with sqlite, hdf5,...
    def record_iteration(self, object_requesting_recording, metadata):
        """
        Write the provided data.

        Args
        ----
        inputs : dict
            Dictionary containing inputs.

        outputs : dict
            Dictionary containing outputs and states.

        residuals : dict
            Dictionary containing residuals.

        metadata : dict, optional
            Dictionary containing execution metadata (e.g. iteration coordinate).
        """
        self._counter += 1
        # raise NotImplementedError()

    def record_derivatives(self, derivs, metadata):
        """
        Write the metadata of the given group.

        Args
        ----
        derivs : dict
            Dictionary containing derivatives

        metadata : dict, optional
            Dictionary containing execution metadata (e.g. iteration coordinate).
        """
        raise NotImplementedError()

    def close(self):
        """
        Close `out` unless it's ``sys.stdout``, ``sys.stderr``, or StringIO.

        Note that a closed recorder will do nothing in :meth:`record`, and
        closing a closed recorder also does nothing.
        """
        # Closing a StringIO deletes its contents.
        if self.out not in (None, sys.stdout, sys.stderr):
            if not isinstance(self.out, StringIO):
                self.out.close()
            self.out = None