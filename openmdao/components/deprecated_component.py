"""Define a deprecated Component class for backwards compatibility."""

from __future__ import division

import numpy as np

from openmdao.core.component import Component as BaseComponent
from openmdao.utils.class_util import overrides_method
from openmdao.utils.general_utils import warn_deprecation
from openmdao.utils.name_maps import rel_name2abs_name


class Component(BaseComponent):
    """
    Component Class for backwards compatibility.

    Attributes
    ----------
    _state_names : [str, ...]
        list of names of the states (deprecated OpenMDAO 1.0 concept).
    _output_names : [str, ...]
        list of names of the outputs (deprecated OpenMDAO 1.0 concept).
    """

    def __init__(self, **kwargs):
        """
        Add a few more attributes.

        Parameters
        ----------
        **kwargs : dict of keyword arguments
            available here and in all descendants of this system.
        """
        super(Component, self).__init__(**kwargs)
        self._state_names = []
        self._output_names = []

        if overrides_method('apply_linear', self, Component):
            self.matrix_free = True

        warn_deprecation('Components should inherit from ImplicitComponent '
                         'or ExplicitComponent. This class provides '
                         'backwards compatibility with OpenMDAO <= 1.x as '
                         'this Component class is deprecated')

    def _setup_partials(self, recurse=True):
        super(Component, self)._setup_partials()

        abs2meta_out = self._var_abs2meta['output']
        abs2prom_out = self._var_abs2prom['output']

        # Note: These declare calls are outside of setup_partials so that users do not have to
        # call the super version of setup_partials. This is still post-setup.
        other_names = []
        for out_abs in self._var_abs_names['output']:
            meta = abs2meta_out[out_abs]
            out_name = abs2prom_out[out_abs]
            size = np.prod(meta['shape'])
            arange = np.arange(size)

            # Skip all states. The user declares those derivatives.
            if out_name in self._state_names:
                continue

            # No need to FD outputs wrt other outputs
            abs_key = (out_abs, out_abs)
            if abs_key in self._subjacs_info:
                if 'method' in self._subjacs_info[abs_key]:
                    del self._subjacs_info[abs_key]['method']

            # If our OpenMDAO Alpha component has any states at all, then even the non-state
            # outputs need to be flipped.
            if len(self._state_names) > 0:
                val = -1.0
            else:
                val = 1.0

            self._declare_partials(out_name, out_name, rows=arange, cols=arange, val=val)

            for other_name in other_names:
                self._declare_partials(out_name, other_name, dependent=False)
                self._declare_partials(other_name, out_name, dependent=False)
            other_names.append(out_name)

    def add_param(self, name, val=1.0, **kwargs):
        """
        Add an param variable to the component.

        Parameters
        ----------
        name : str
            name of the variable in this component's namespace.
        val : object
            The value of the variable being added.
        **kwargs : dict
            additional args, documented [INSERT REF].
        """
        self.add_input(name, val, **kwargs)

    def add_state(self, name, val=1.0, **kwargs):
        """
        Add a state variable to the component.

        Parameters
        ----------
        name : str
            name of the variable in this component's namespace.
        val : object
            The value of the variable being added.
        **kwargs : dict
            additional args, documented [INSERT REF].
        """
        if 'resid_scaler' in kwargs:
            kwargs['res_ref'] = kwargs['resid_scaler']
            del kwargs['resid_scaler']

        super(Component, self).add_output(name, val, **kwargs)
        self._state_names.append(name)

    def add_output(self, name, val=1.0, **kwargs):
        """
        Add an output variable to the component.

        Parameters
        ----------
        name : str
            name of the variable in this component's namespace.
        val : object
            The value of the variable being added.
        **kwargs : dict
            additional args, documented [INSERT REF].
        """
        if 'resid_scaler' in kwargs:
            kwargs['res_ref'] = kwargs['resid_scaler']

        super(Component, self).add_output(name, val, **kwargs)
        self._output_names.append(name)

    def _apply_nonlinear(self):
        """
        Compute residuals.
        """
        self._scale_vec(self._inputs, 'input', 'phys')
        self._scale_vec(self._outputs, 'output', 'phys')
        self._scale_vec(self._residuals, 'residual', 'phys')

        self.apply_nonlinear(self._inputs, self._outputs, self._residuals)

        self._scale_vec(self._inputs, 'input', 'norm')
        self._scale_vec(self._outputs, 'output', 'norm')
        self._scale_vec(self._residuals, 'residual', 'norm')

    def _solve_nonlinear(self):
        """
        Compute outputs.

        Returns
        -------
        boolean
            Failure flag; True if failed to converge, False is successful.
        float
            relative error.
        float
            absolute error.
        """
        super(Component, self)._solve_nonlinear()

        if self._nonlinear_solver is not None:
            self._nonlinear_solver.solve()
        else:
            self._scale_vec(self._inputs, 'input', 'phys')
            self._scale_vec(self._outputs, 'output', 'phys')
            self._scale_vec(self._residuals, 'residual', 'phys')

            self.solve_nonlinear(self._inputs, self._outputs, self._residuals)

            self._scale_vec(self._inputs, 'input', 'norm')
            self._scale_vec(self._outputs, 'output', 'norm')
            self._scale_vec(self._residuals, 'residual', 'norm')

    def _apply_linear(self, vec_names, mode, scope_out=None, scope_in=None):
        """
        Compute jac-vec product.

        Parameters
        ----------
        vec_names : [str, ...]
            list of names of the right-hand-side vectors.
        mode : str
            'fwd' or 'rev'.
        scope_out : set or None
            Set of absolute output names in the scope of this mat-vec product.
            If None, all are in the scope.
        scope_in : set or None
            Set of absolute input names in the scope of this mat-vec product.
            If None, all are in the scope.
        """
        for vec_name in vec_names:
            with self._matvec_context(vec_name, scope_out, scope_in, mode) as vecs:
                d_inputs, d_outputs, d_residuals = vecs

                with self.jacobian_context():
                    self._jacobian._apply(d_inputs, d_outputs, d_residuals,
                                          mode)

                with self._unscaled_context(
                        outputs=[self._outputs, d_outputs], residuals=[d_residuals]):

                    if len(self._state_names) == 0:
                        for name in d_inputs:
                            d_inputs[name] *= -1.0

                    self.apply_linear(self._inputs, self._outputs,
                                      d_inputs, d_outputs, d_residuals, mode)

                    if len(self._state_names) == 0:
                        for name in d_inputs:
                            d_inputs[name] *= -1.0

    def _solve_linear(self, vec_names, mode):
        """
        Apply inverse jac product.

        Parameters
        ----------
        vec_names : [str, ...]
            list of names of the right-hand-side vectors.
        mode : str
            'fwd' or 'rev'.

        Returns
        -------
        boolean
            Failure flag; True if failed to converge, False is successful.
        float
            relative error.
        float
            absolute error.
        """
        if self._linear_solver is not None:
            return self._linear_solver(vec_names, mode)
        else:
            for vec_name in vec_names:
                d_outputs = self._vectors['output'][vec_name]
                d_residuals = self._vectors['residual'][vec_name]

                self._scale_vec(d_outputs, 'output', 'phys')
                self._scale_vec(d_residuals, 'residual', 'phys')

            self.solve_linear(self._vectors['output'],
                              self._vectors['residual'],
                              vec_names, mode)

            for vec_name in vec_names:

                # skip for pure explicit components.
                if len(self._state_names) > 0:
                    for name in d_outputs:
                        if name in self._output_names:
                            if mode == 'fwd':
                                d_outputs[name] = d_residuals[name]
                            elif mode == 'rev':
                                d_residuals[name] = d_outputs[name]

                self._scale_vec(d_outputs, 'output', 'norm')
                self._scale_vec(d_residuals, 'residual', 'norm')

            return False, 0., 0.

    def _linearize(self, do_nl=False, do_ln=False):
        """
        Compute jacobian / factorization.

        Parameters
        ----------
        do_nl : boolean
            Flag indicating if the nonlinear solver should be linearized.
        do_ln : boolean
            Flag indicating if the linear solver should be linearized.
        """
        with self.jacobian_context() as J:
            with self._unscaled_context(
                    outputs=[self._outputs], residuals=[self._residuals]):

                # If we are a purely explicit component, then negate constant subjacs (and others
                # that will get overwritten) back to normal.
                if len(self._state_names) == 0:
                    self._negate_jac()

                J = self.linearize(self._inputs, self._outputs, self._residuals)
                if J is not None:
                    for k in J:
                        self._jacobian[k] = J[k]

                # Re-negate the jacobian, but only if we are totally explicit.
                if len(self._state_names) == 0:
                    self._negate_jac()

            if self._owns_assembled_jac or self._views_assembled_jac:
                J._update()

    def _negate_jac(self):
        """
        Negate this component's part of the jacobian.
        """
        if self._jacobian._subjacs:
            for res_name in self._var_abs_names['output']:
                for in_name in self._var_abs_names['input']:
                    abs_key = (res_name, in_name)
                    if abs_key in self._jacobian._subjacs:
                        self._jacobian._multiply_subjac(abs_key, -1.)

    def apply_nonlinear(self, params, unknowns, residuals):
        """
        Compute residuals given params and unknowns.

        Parameters
        ----------
        params : Vector
            unscaled, dimensional param variables read via params[key]
        unknowns : Vector
            unscaled, dimensional unknown variables read via unknowns[key]
        residuals : Vector
            unscaled, dimensional residuals written to via residuals[key]
        """
        residuals.set_vec(unknowns)
        self.solve_nonlinear(params, unknowns, residuals)
        residuals -= unknowns
        unknowns += residuals

    def solve_nonlinear(self, params, unknowns, residuals):
        """
        Compute unknowns given params.

        Parameters
        ----------
        params : Vector
            unscaled, dimensional param variables read via params[key]
        unknowns : Vector
            unscaled, dimensional unknown variables read via unknowns[key]
        residuals : Vector
            unscaled, dimensional residuals written to via residuals[key]
        """
        pass

    def apply_linear(self, params, unknowns,
                     d_params, d_unknowns, d_residuals, mode):
        r"""
        Compute jac-vector product.

        If mode is:
            'fwd': (d_params, unknowns) \|-> d_residuals

            'rev': d_residuals \|-> (d_params, unknowns)

        Parameters
        ----------
        params : Vector
            unscaled, dimensional param variables read via params[key]
        unknowns : Vector
            unscaled, dimensional unknown variables read via unknowns[key]
        d_params : Vector
            see params; product must be computed only if var_name in d_params
        d_unknowns : Vector
            see unknowns; product must be computed only if var_name in unknowns
        d_residuals : Vector
            see unknowns
        mode : str
            either 'fwd' or 'rev'
        """
        pass

    def solve_linear(self, d_unknowns_dict, d_residuals_dict, vec_names, mode):
        r"""
        Apply inverse jac product.

        If mode is:
            'fwd': d_residuals \|-> d_unknowns

            'rev': d_unknowns \|-> d_residuals

        Parameters
        ----------
        d_unknowns_dict : dict of <Vector>
            unscaled, dimensional quantities read via d_unknowns[key]
        d_residuals_dict : dict of <Vector>
            unscaled, dimensional quantities read via d_residuals[key]
        vec_names : [str, ...]
            list of right-hand-side vector names to perform solve linear on.
        mode : str
            either 'fwd' or 'rev'
        """
        pass

    def linearize(self, params, unknowns, residuals):
        """
        Compute jacobian.

        Parameters
        ----------
        params : Vector
            unscaled, dimensional param variables read via params[key]
        unknowns : Vector
            unscaled, dimensional unknown variables read via unknowns[key]
        residuals : Vector
            unscaled, dimensional residuals written to via residuals[key]

        Returns
        -------
        jacobian : dict or None
            Dictionary whose keys are tuples of the form ('unknown', 'param')
            and whose values are ndarrays. None if method is not imeplemented.
        """
        return None

    def _list_states(self):
        """
        Return list of all states at and below this system.

        Returns
        -------
        list
            List of all states.
        """
        return [rel_name2abs_name(self, name) for name in self._state_names]
