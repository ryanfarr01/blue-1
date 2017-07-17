"""
Class definition for BaseRecorder, the base class for all recorders.
"""
from fnmatch import fnmatchcase
import sys
from six import StringIO

from openmdao.utils.options_dictionary import OptionsDictionary
from openmdao.utils.general_utils import warn_deprecation
from openmdao.core.system import System
from openmdao.core.driver import Driver
from openmdao.solvers.solver import Solver, NonlinearSolver


class BaseRecorder(object):
    """
    Base class for all case recorders and is not a functioning case recorder on its own.

    Options
    -------
    options['record_metadata'] :  bool(True)
        Tells recorder whether to record variable attribute metadata.
    options['record_outputs'] :  bool(True)
        Tells recorder whether to record the outputs of a System.
    options['record_inputs'] :  bool(False)
        Tells recorder whether to record the inputs of a System.
    options['record_residuals'] :  bool(False)
        Tells recorder whether to record the residuals of a System.
    options['record_derivatives'] :  bool(False)
        Tells recorder whether to record the derivatives of a System.
    options['record_desvars'] :  bool(True)
        Tells recorder whether to record the desvars of a Driver.
    options['record_responses'] :  bool(False)
        Tells recorder whether to record the responses of a Driver.
    options['record_objectives'] :  bool(False)
        Tells recorder whether to record the objectives of a Driver.
    options['record_constraints'] :  bool(False)
        Tells recorder whether to record the constraints of a Driver.
    options['record_abs_error'] :  bool(True)
        Tells recorder whether to record the absolute error of a Solver.
    options['record_rel_error'] :  bool(True)
        Tells recorder whether to record the relative error of a Solver.
    options['record_solver_output'] :  bool(False)
        Tells recorder whether to record the output of a Solver.
    options['record_solver_derivatives'] :  bool(False)
        Tells recorder whether to record the derivatives of a Solver.
    options['includes'] :  list of strings("*")
        Patterns for variables to include in recording.
    options['excludes'] :  list of strings('')
        Patterns for variables to exclude in recording (processed after includes).

    Attributes
    ----------
    out : StringIO
        Output to the recorder.
    _counter : int
        A global counter for execution order, used in iteration coordinate.
    _filtered_driver : dict
        Filtered subset of driver variables to record, based on includes/excludes.
    _filtered_solver : dict
        Filtered subset of solver variables to record, based on includes/excludes.
    _filtered_system : dict
        Filtered subset of system variables to record, based on includes/excludes.

    """

    def __init__(self):
        """
        initialize.
        """
        self.options = OptionsDictionary()
        # Options common to all objects
        self.options.declare('record_metadata', type_=bool, desc='Record metadata', default=True)
        self.options.declare('includes', type_=list, default=['*'],
                             desc='Patterns for variables to include in recording')
        self.options.declare('excludes', type_=list, default=[],
                             desc='Patterns for vars to exclude in recording '
                                  '(processed post-includes)')

        # Old options that will be deprecated
        self.options.declare('record_unknowns', type_=bool, default=False,
                             desc='Deprecated option to record unknowns.')
        self.options.declare('record_params', type_=bool, default=False,
                             desc='Deprecated option to record params.',)
        self.options.declare('record_resids', type_=bool, default=False,
                             desc='Deprecated option to record residuals.')
        self.options.declare('record_derivs', type_=bool, default=False,
                             desc='Deprecated option to record derivatives.')
        # System options
        self.options.declare('record_outputs', type_=bool, default=True,
                             desc='Set to True to record outputs at the system level')
        self.options.declare('record_inputs', type_=bool, default=True,
                             desc='Set to True to record inputs at the system level')
        self.options.declare('record_residuals', type_=bool, default=True,
                             desc='Set to True to record residuals at the system level')
        self.options.declare('record_derivatives', type_=bool, default=False,
                             desc='Set to True to record derivatives at the system level')
        # Driver options
        self.options.declare('record_desvars', type_=bool, default=True,
                             desc='Set to True to record design variables at the driver level')
        self.options.declare('record_responses', type_=bool, default=False,
                             desc='Set to True to record responses at the driver level')
        self.options.declare('record_objectives', type_=bool, default=False,
                             desc='Set to True to record objectives at the driver level')
        self.options.declare('record_constraints', type_=bool, default=False,
                             desc='Set to True to record constraints at the driver level')
        # Solver options
        self.options.declare('record_abs_error', type_=bool, default=True,
                             desc='Set to True to record absolute error at the solver level')
        self.options.declare('record_rel_error', type_=bool, default=True,
                             desc='Set to True to record relative error at the solver level')
        self.options.declare('record_solver_output', type_=bool, default=False,
                             desc='Set to True to record output at the solver level')
        self.options.declare('record_solver_residuals', type_=bool, default=False,
                             desc='Set to True to record residuals at the solver level')

        self.out = None

        # global counter that is used in iteration coordinate
        self._counter = 0

        # dicts in which to keep the included items for recording
        self._filtered_driver = {}
        self._filtered_system = {}
        self._filtered_solver = {}

    def startup(self, object_requesting_recording):
        """
        Prepare for a new run and calculate inclusion lists.

        Parameters
        ----------
        object_requesting_recording :
            Object to which this recorder is attached.
        """
        self._counter = 0

        # Deprecated options here, but need to preserve backward compatibility if possible.
        if self.options['record_params']:
            warn_deprecation("record_params is deprecated, please use record_inputs.")
            # set option to what the user intended.
            self.options['record_inputs'] = True

        if self.options['record_unknowns']:
            warn_deprecation("record_ is deprecated, please use record_outputs.")
            # set option to what the user intended.
            self.options['record_outputs'] = True

        if self.options['record_resids']:
            warn_deprecation("record_params is deprecated, please use record_residuals.")
            # set option to what the user intended.
            self.options['record_residuals'] = True

        # Compute the inclusion/exclusion lists

        if (isinstance(object_requesting_recording, System)):
            myinputs = myoutputs = myresiduals = set()
            incl = self.options['includes']
            excl = self.options['excludes']

            if self.options['record_inputs']:
                if object_requesting_recording._inputs:
                    myinputs = {n for n in object_requesting_recording._inputs._names
                                if self._check_path(n, incl, excl)}
            if self.options['record_outputs']:
                if object_requesting_recording._outputs:
                    myoutputs = {n for n in object_requesting_recording._outputs._names
                                 if self._check_path(n, incl, excl)}
                if self.options['record_residuals']:
                    myresiduals = myoutputs  # outputs and residuals have same names
            elif self.options['record_residuals']:
                if object_requesting_recording._residuals:
                    myresiduals = {n for n in object_requesting_recording._residuals._names
                                   if self._check_path(n, incl, excl)}

            self._filtered_system = {
                'i': myinputs,
                'o': myoutputs,
                'r': myresiduals
            }

        if (isinstance(object_requesting_recording, Driver)):
            mydesvars = myobjectives = myconstraints = myresponses = set()
            incl = self.options['includes']
            excl = self.options['excludes']

            if self.options['record_desvars']:
                mydesvars = {n for n in object_requesting_recording._designvars
                             if self._check_path(n, incl, excl)}

            if self.options['record_objectives']:
                myobjectives = {n for n in object_requesting_recording._objs
                                if self._check_path(n, incl, excl)}

            if self.options['record_constraints']:
                myconstraints = {n for n in object_requesting_recording._cons
                                 if self._check_path(n, incl, excl)}

            if self.options['record_responses']:
                myresponses = {n for n in object_requesting_recording._responses
                               if self._check_path(n, incl, excl)}

            self._filtered_driver = {
                'des': mydesvars,
                'obj': myobjectives,
                'con': myconstraints,
                'res': myresponses
            }

        if (isinstance(object_requesting_recording, Solver)):
            myoutputs = myresiduals = set()
            incl = self.options['includes']
            excl = self.options['excludes']

            if self.options['record_solver_residuals']:
                if isinstance(object_requesting_recording, NonlinearSolver):
                    residuals = object_requesting_recording._system._residuals
                else:  # it's a LinearSolver
                    residuals = object_requesting_recording._system._vectors['residual']['linear']
                myresiduals = {n for n in residuals
                               if self._check_path(n, incl, excl)}

            if self.options['record_solver_output']:
                if isinstance(object_requesting_recording, NonlinearSolver):
                    outputs = object_requesting_recording._system._outputs
                else:  # it's a LinearSolver
                    outputs = object_requesting_recording._system._vectors['output']['linear']
                myoutputs = {n for n in outputs
                             if self._check_path(n, incl, excl)}

            self._filtered_solver = {
                'out': myoutputs,
                'res': myresiduals
            }

    def _check_path(self, path, includes, excludes):
        """
        Calculate whether `path` should be recorded.

        Parameters
        ----------
        path : str
            path proposed to be recorded
        includes : list
            list of things to be included in recording list.
        excludes : list
            list of things to be excluded from recording list.

        Returns
        -------
        boolean
            True if path should be recorded, False if it's been excluded.
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

    def record_metadata(self, object_requesting_recording):
        """
        Write the metadata of the given object.

        Parameters
        ----------
        object_requesting_recording :
            System, Solver, Driver in need of recording.
        """
        raise NotImplementedError()

    def record_iteration(self, object_requesting_recording, metadata, **kwargs):
        """
        Write the provided data.

        Parameters
        ----------
        object_requesting_recording : object
            System, Solver, Driver in need of recording.
        metadata : dict, optional
            Dictionary containing execution metadata (e.g. iteration coordinate).
        **kwargs : keyword args
            Some implementations of record_iteration need additional args.
        """
        self._counter += 1

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
