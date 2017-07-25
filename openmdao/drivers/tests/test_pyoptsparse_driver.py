""" Unit tests for the Pyoptsparse Driver."""

import unittest

import numpy as np

from openmdao.api import Problem, Group, IndepVarComp, ExecComp, AnalysisError, ExplicitComponent
from openmdao.devtools.testutil import assert_rel_error
from openmdao.test_suite.components.paraboloid import Paraboloid
from openmdao.test_suite.components.expl_comp_array import TestExplCompArrayDense
from openmdao.test_suite.components.sellar import SellarDerivativesGrouped
from openmdao.utils.general_utils import set_pyoptsparse_opt


# check that pyoptsparse is installed
# if it is, try to use SNOPT but fall back to SLSQP
OPT, OPTIMIZER = set_pyoptsparse_opt('SNOPT')

if OPTIMIZER:
    from openmdao.drivers.pyoptsparse_driver import pyOptSparseDriver


class ParaboloidAE(ExplicitComponent):
    """ Evaluates the equation f(x,y) = (x-3)^2 + xy + (y+4)^2 - 3
    This version raises an analysis error 50% of the time.
    The AE in ParaboloidAE stands for AnalysisError."""

    def __init__(self):
        super(ParaboloidAE, self).__init__()
        self.fail_hard = False

    def setup(self):
        self.add_input('x', val=0.0)
        self.add_input('y', val=0.0)

        self.add_output('f_xy', val=0.0)

        self.eval_iter_count = 0
        self.eval_fail_at = 3

        self.grad_iter_count = 0
        self.grad_fail_at = 100

    def compute(self, inputs, outputs):
        """f(x,y) = (x-3)^2 + xy + (y+4)^2 - 3
        Optimal solution (minimum): x = 6.6667; y = -7.3333
        """
        if self.eval_iter_count == self.eval_fail_at:
            self.eval_iter_count = 0

            if self.fail_hard:
                raise RuntimeError('This should error.')
            else:
                raise AnalysisError('Try again.')

        x = inputs['x']
        y = inputs['y']

        outputs['f_xy'] = (x-3.0)**2 + x*y + (y+4.0)**2 - 3.0
        self.eval_iter_count += 1

    def compute_partials(self, inputs, outputs, partials):
        """ Jacobian for our paraboloid."""

        if self.grad_iter_count == self.grad_fail_at:
            self.grad_iter_count = 0

            if self.fail_hard:
                raise RuntimeError('This should error.')
            else:
                raise AnalysisError('Try again.')

        x = inputs['x']
        y = inputs['y']

        partials['f_xy','x'] = 2.0*x - 6.0 + y
        partials['f_xy','y'] = 2.0*y + 8.0 + x
        self.grad_iter_count += 1


class TestPyoptSparse(unittest.TestCase):

    def setUp(self):
        if OPT is None:
            raise unittest.SkipTest("pyoptsparse is not installed")

        if OPTIMIZER is None:
            raise unittest.SkipTest("pyoptsparse is not providing SNOPT or SLSQP")

    def test_simple_paraboloid_upper(self):

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])
        model.add_subsystem('comp', Paraboloid(), promotes=['*'])
        model.add_subsystem('con', ExecComp('c = - x + y'), promotes=['*'])

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        if OPTIMIZER == 'SLSQP':
            prob.driver.opt_settings['ACC'] = 1e-9
        prob.driver.options['print_results'] = False

        model.add_design_var('x', lower=-50.0, upper=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0)
        model.add_objective('f_xy')
        model.add_constraint('c', upper=-15.0)

        prob.setup(check=False)
        prob.run_driver()

        # Minimum should be at (7.166667, -7.833334)
        assert_rel_error(self, prob['x'], 7.16667, 1e-6)
        assert_rel_error(self, prob['y'], -7.833334, 1e-6)

    def test_simple_paraboloid_upper_indices(self):

        prob = Problem()
        model = prob.model = Group()

        size = 3
        model.add_subsystem('p1', IndepVarComp('x', np.array([50.0]*size)))
        model.add_subsystem('p2', IndepVarComp('y', np.array([50.0]*size)))
        model.add_subsystem('comp', ExecComp('f_xy = (x-3.0)**2 + x*y + (y+4.0)**2 - 3.0',
                                             x=np.zeros(size), y=np.zeros(size),
                                             f_xy=np.zeros(size)))
        model.add_subsystem('con', ExecComp('c = - x + y',
                                            c=np.zeros(size), x=np.zeros(size),
                                            y=np.zeros(size)))

        model.connect('p1.x', 'comp.x')
        model.connect('p2.y', 'comp.y')
        model.connect('p1.x', 'con.x')
        model.connect('p2.y', 'con.y')

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        if OPTIMIZER == 'SLSQP':
            prob.driver.opt_settings['ACC'] = 1e-9
        prob.driver.options['print_results'] = False

        model.add_design_var('p1.x', indices=[1], lower=-50.0, upper=50.0)
        model.add_design_var('p2.y', indices=[1], lower=-50.0, upper=50.0)
        model.add_objective('comp.f_xy', index=1)
        model.add_constraint('con.c', indices=[1], upper=-15.0)

        prob.setup(check=False)
        prob.run_driver()

        # Minimum should be at (7.166667, -7.833334)
        assert_rel_error(self, prob['p1.x'], np.array([50., 7.16667, 50.]), 1e-6)
        assert_rel_error(self, prob['p2.y'], np.array([50., -7.833334, 50.]), 1e-6)

    def test_simple_paraboloid_lower(self):

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])
        model.add_subsystem('comp', Paraboloid(), promotes=['*'])
        model.add_subsystem('con', ExecComp('c = x - y'), promotes=['*'])

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        if OPTIMIZER == 'SLSQP':
            prob.driver.opt_settings['ACC'] = 1e-9
        prob.driver.options['print_results'] = False

        model.add_design_var('x', lower=-50.0, upper=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0)

        model.add_objective('f_xy')
        model.add_constraint('c', lower=15.0)

        prob.setup(check=False)
        prob.run_driver()

        # Minimum should be at (7.166667, -7.833334)
        assert_rel_error(self, prob['x'], 7.16667, 1e-6)
        assert_rel_error(self, prob['y'], -7.833334, 1e-6)

    def test_simple_paraboloid_lower_linear(self):

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])
        model.add_subsystem('comp', Paraboloid(), promotes=['*'])
        model.add_subsystem('con', ExecComp('c = x - y'), promotes=['*'])

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        if OPTIMIZER == 'SLSQP':
            prob.driver.opt_settings['ACC'] = 1e-9
        prob.driver.options['print_results'] = False

        model.add_design_var('x', lower=-50.0, upper=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0)
        model.add_objective('f_xy')
        model.add_constraint('c', lower=15.0, linear=True)

        prob.setup(check=False)
        prob.run_driver()

        # Minimum should be at (7.166667, -7.833334)
        assert_rel_error(self, prob['x'], 7.16667, 1e-6)
        assert_rel_error(self, prob['y'], -7.833334, 1e-6)

        self.assertEqual(prob.driver._quantities, ['comp.f_xy'])

    def test_simple_paraboloid_equality(self):

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])
        model.add_subsystem('comp', Paraboloid(), promotes=['*'])
        model.add_subsystem('con', ExecComp('c = - x + y'), promotes=['*'])

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        if OPTIMIZER == 'SLSQP':
            prob.driver.opt_settings['ACC'] = 1e-9
        prob.driver.options['print_results'] = False

        model.add_design_var('x', lower=-50.0, upper=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0)
        model.add_objective('f_xy')
        model.add_constraint('c', equals=-15.0)

        prob.setup(check=False)
        prob.run_driver()

        # Minimum should be at (7.166667, -7.833334)
        assert_rel_error(self, prob['x'], 7.16667, 1e-6)
        assert_rel_error(self, prob['y'], -7.833334, 1e-6)

    def test_simple_paraboloid_equality_linear(self):

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])
        model.add_subsystem('comp', Paraboloid(), promotes=['*'])
        model.add_subsystem('con', ExecComp('c = - x + y'), promotes=['*'])

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        if OPTIMIZER == 'SLSQP':
            prob.driver.opt_settings['ACC'] = 1e-9
        prob.driver.options['print_results'] = False

        model.add_design_var('x', lower=-50.0, upper=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0)
        model.add_objective('f_xy')
        model.add_constraint('c', equals=-15.0, linear=True)

        prob.setup(check=False)
        prob.run_driver()

        # Minimum should be at (7.166667, -7.833334)
        assert_rel_error(self, prob['x'], 7.16667, 1e-6)
        assert_rel_error(self, prob['y'], -7.833334, 1e-6)

    def test_simple_paraboloid_double_sided_low(self):

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])
        model.add_subsystem('comp', Paraboloid(), promotes=['*'])
        model.add_subsystem('con', ExecComp('c = - x + y'), promotes=['*'])

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        prob.driver.options['print_results'] = False

        model.add_design_var('x', lower=-50.0, upper=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0)
        model.add_objective('f_xy')
        model.add_constraint('c', lower=-11.0, upper=-10.0)

        prob.setup(check=False)
        prob.run_driver()

        # Minimum should be at (7.166667, -7.833334)
        assert_rel_error(self, prob['y'] - prob['x'], -11.0, 1e-6)

    def test_simple_paraboloid_double_sided_high(self):

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])
        model.add_subsystem('comp', Paraboloid(), promotes=['*'])
        model.add_subsystem('con', ExecComp('c = x - y'), promotes=['*'])

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        prob.driver.options['print_results'] = False

        model.add_design_var('x', lower=-50.0, upper=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0)
        model.add_objective('f_xy')
        model.add_constraint('c', lower=10.0, upper=11.0)

        prob.setup(check=False)
        prob.run_driver()

        # Minimum should be at (7.166667, -7.833334)
        assert_rel_error(self, prob['x'] - prob['y'], 11.0, 1e-6)

    def test_simple_array_comp2D(self):

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('widths', np.zeros((2, 2))), promotes=['*'])
        model.add_subsystem('comp', TestExplCompArrayDense(), promotes=['*'])
        model.add_subsystem('con', ExecComp('c = areas - 20.0', c=np.zeros((2, 2)), areas=np.zeros((2, 2))),
                            promotes=['*'])
        model.add_subsystem('obj', ExecComp('o = areas[0, 0]', areas=np.zeros((2, 2))),
                            promotes=['*'])

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        prob.driver.options['print_results'] = False

        model.add_design_var('widths', lower=-50.0, upper=50.0)
        model.add_objective('o')
        model.add_constraint('c', equals=0.0)

        prob.setup(check=False)
        prob.run_driver()

        obj = prob['o']
        assert_rel_error(self, obj, 20.0, 1e-6)

    def test_simple_array_comp2D_array_lo_hi(self):

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('widths', np.zeros((2, 2))), promotes=['*'])
        model.add_subsystem('comp', TestExplCompArrayDense(), promotes=['*'])
        model.add_subsystem('con', ExecComp('c = areas - 20.0', c=np.zeros((2, 2)), areas=np.zeros((2, 2))),
                            promotes=['*'])
        model.add_subsystem('obj', ExecComp('o = areas[0, 0]', areas=np.zeros((2, 2))),
                            promotes=['*'])

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        prob.driver.options['print_results'] = False

        model.add_design_var('widths', lower=-50.0*np.ones((2, 2)), upper=50.0*np.ones((2, 2)))
        model.add_objective('o')
        model.add_constraint('c', equals=0.0)

        prob.setup(check=False)
        prob.run_driver()

        obj = prob['o']
        assert_rel_error(self, obj, 20.0, 1e-6)

    def test_fan_out(self):
        # This tests sparse-response specification.
        # This is a slightly modified FanOut
        raise unittest.SkipTest("We don't compute sparsity for pyoptsparse just yet.")

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 1.0))
        model.add_subsystem('p2', IndepVarComp('x', 1.0))

        model.add_subsystem('comp1', ExecComp('y = 3.0*x'))
        model.add_subsystem('comp2', ExecComp('y = 5.0*x'))

        model.add_subsystem('obj', ExecComp('o = i1 + i2'))
        model.add_subsystem('con1', ExecComp('c = 15.0 - x'))
        model.add_subsystem('con2', ExecComp('c = 15.0 - x'))

        # hook up explicitly
        model.connect('p1.x', 'comp1.x')
        model.connect('p2.x', 'comp2.x')
        model.connect('comp1.y', 'obj.i1')
        model.connect('comp2.y', 'obj.i2')
        model.connect('comp1.y', 'con1.x')
        model.connect('comp2.y', 'con2.x')

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        prob.driver.options['print_results'] = False

        model.add_design_var('p1.x', lower=-50.0, upper=50.0)
        model.add_design_var('p2.x', lower=-50.0, upper=50.0)
        model.add_objective('obj.o')
        model.add_constraint('con1.c', equals=0.0)
        model.add_constraint('con2.c', equals=0.0)

        prob.setup(check=False)
        prob.run_driver()

        obj = prob['obj.o']
        assert_rel_error(self, obj, 30.0, 1e-6)

        # Verify that pyOpt has the correct wrt names
        con1 = prob.driver.pyopt_solution.constraints['con1.c']
        self.assertEqual(con1.wrt, ['p1.x'])
        con2 = prob.driver.pyopt_solution.constraints['con2.c']
        self.assertEqual(con2.wrt, ['p2.x'])

    def test_inf_as_desvar_bounds(self):

        # User may use np.inf as a bound. It is unneccessary, but the user
        # may do it anyway, so make sure SLSQP doesn't blow up with it (bug
        # reported by rfalck)

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])
        model.add_subsystem('comp', Paraboloid(), promotes=['*'])
        model.add_subsystem('con', ExecComp('c = - x + y'), promotes=['*'])

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = 'SLSQP'
        prob.driver.opt_settings['ACC'] = 1e-9
        prob.driver.options['print_results'] = False

        model.add_design_var('x', lower=-np.inf, upper=np.inf)
        model.add_design_var('y', lower=-50.0, upper=50.0)
        model.add_objective('f_xy')
        model.add_constraint('c', upper=-15.0)

        prob.setup(check=False)
        prob.run_driver()

        # Minimum should be at (7.166667, -7.833334)
        assert_rel_error(self, prob['x'], 7.16667, 1e-6)
        assert_rel_error(self, prob['y'], -7.833334, 1e-6)

    def test_pyopt_fd_solution(self):

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])

        model.add_subsystem('comp', Paraboloid(), promotes=['*'])

        model.add_subsystem('con', ExecComp('c = - x + y'), promotes=['*'])

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        prob.driver.options['gradient method'] = 'pyopt_fd'
        prob.driver.options['print_results'] = False

        model.add_design_var('x', lower=-50.0, upper=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0)
        model.add_objective('f_xy')
        model.add_constraint('c', upper=-15.0)

        prob.setup(check=False)
        prob.run_driver()

        # Minimum should be at (7.166667, -7.833334)
        assert_rel_error(self, prob['x'], 7.16667, 1e-4)
        assert_rel_error(self, prob['y'], -7.833334, 1e-4)

    def test_pyopt_fd_is_called(self):

        class ParaboloidApplyLinear(Paraboloid):
            def apply_linear(params, unknowns, resids):
                raise Exception("OpenMDAO's finite difference has been called. pyopt_fd\
                                \ option has failed.")

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])

        model.add_subsystem('comp', ParaboloidApplyLinear(), promotes=['*'])

        model.add_subsystem('con', ExecComp('c = - x + y'), promotes=['*'])

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        prob.driver.options['gradient method'] = 'pyopt_fd'
        prob.driver.options['print_results'] = False

        model.add_design_var('x', lower=-50.0, upper=50.0)
        model.add_constraint('y', lower=-50.0, upper=50.0)
        model.add_objective('f_xy')
        model.add_constraint('c', upper=-15.0)

        prob.setup(check=False)

        prob.run_driver()

    def test_snopt_fd_solution(self):

        if OPTIMIZER is not 'SNOPT':
            raise unittest.SkipTest()

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])

        model.add_subsystem('comp', Paraboloid(), promotes=['*'])

        model.add_subsystem('con', ExecComp('c = - x + y'), promotes=['*'])

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        prob.driver.options['gradient method'] = 'snopt_fd'
        prob.driver.options['print_results'] = False

        model.add_design_var('x', lower=-50.0, upper=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0)
        model.add_objective('f_xy')
        model.add_constraint('c', upper=-15.0)

        prob.setup(check=False)
        prob.run_driver()

        # Minimum should be at (7.166667, -7.833334)
        assert_rel_error(self, prob['x'], 7.16667, 1e-6)
        assert_rel_error(self, prob['y'], -7.833334, 1e-6)

    def test_snopt_fd_is_called(self):

        if OPTIMIZER is not 'SNOPT':
            raise unittest.SkipTest()

        class ParaboloidApplyLinear(Paraboloid):
            def apply_linear(params, unknowns, resids):
                raise Exception("OpenMDAO's finite difference has been called. snopt_fd\
                                \ option has failed.")

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])

        model.add_subsystem('comp', ParaboloidApplyLinear(), promotes=['*'])

        model.add_subsystem('con', ExecComp('c = - x + y'), promotes=['*'])

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        prob.driver.options['gradient method'] = 'snopt_fd'
        prob.driver.options['print_results'] = False

        model.add_design_var('x', lower=-50.0, upper=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0)
        model.add_objective('f_xy')
        model.add_constraint('c', upper=-15.0)

        prob.setup(check=False)

        prob.run_driver()

    def test_snopt_fd_option_error(self):

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])

        model.add_subsystem('comp', Paraboloid(), promotes=['*'])

        model.add_subsystem('con', ExecComp('c = - x + y'), promotes=['*'])

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = 'SLSQP'
        prob.driver.options['gradient method'] = 'snopt_fd'
        prob.driver.options['print_results'] = False

        model.add_design_var('x', lower=-50.0, upper=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0)
        model.add_objective('f_xy')
        model.add_constraint('c', upper=-15.0)

        prob.setup(check=False)

        with self.assertRaises(Exception) as raises_cm:
            prob.run_driver()

        exception = raises_cm.exception

        msg = "SNOPT's internal finite difference can only be used with SNOPT"

        self.assertEqual(exception.args[0], msg)

    def test_unsupported_multiple_obj(self):
        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])

        model.add_subsystem('comp', Paraboloid(), promotes=['*'])
        model.add_subsystem('comp2', Paraboloid())

        model.add_subsystem('con', ExecComp('c = - x + y'), promotes=['*'])

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = 'SLSQP'
        prob.driver.options['gradient method'] = 'snopt_fd'
        prob.driver.options['print_results'] = False

        model.add_design_var('x', lower=-50.0, upper=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0)
        model.add_objective('f_xy')
        model.add_objective('comp2.f_xy')
        model.add_constraint('c', upper=-15.0)

        expected = 'Multiple objectives have been added to pyOptSparseDriver' \
                   ' but the selected optimizer (SLSQP) does not support' \
                   ' multiple objectives.'

        with self.assertRaises(RuntimeError) as cm:
            prob.setup(check=False)

        self.assertEqual(str(cm.exception), expected)

    def test_simple_paraboloid_scaled_desvars_fwd(self):

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])
        model.add_subsystem('comp', Paraboloid(), promotes=['*'])
        model.add_subsystem('con', ExecComp('c = x - y'), promotes=['*'])

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        if OPTIMIZER == 'SNOPT':
            prob.driver.opt_settings['Verify level'] = 3
        prob.driver.options['print_results'] = False

        model.add_design_var('x', lower=-50.0, upper=50.0, ref=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0, ref=50.0)
        model.add_objective('f_xy')
        model.add_constraint('c', lower=10.0, upper=11.0)

        prob.setup(check=False, mode='fwd')
        prob.run_driver()

        # Minimum should be at (7.166667, -7.833334)
        assert_rel_error(self, prob['x'] - prob['y'], 11.0, 1e-6)

    def test_simple_paraboloid_scaled_desvars_fd(self):
        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])
        model.add_subsystem('comp', Paraboloid(), promotes=['*'])
        model.add_subsystem('con', ExecComp('c = x - y'), promotes=['*'])

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        if OPTIMIZER == 'SNOPT':
            prob.driver.opt_settings['Verify level'] = 3
        prob.driver.options['print_results'] = False

        model.add_design_var('x', lower=-50.0, upper=50.0, ref=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0, ref=50.0)
        model.add_objective('f_xy')
        model.add_constraint('c', lower=10.0, upper=11.0)

        model.approx_total_derivs(method='fd')

        prob.setup(check=False)
        prob.run_driver()

        # Minimum should be at (7.166667, -7.833334)
        assert_rel_error(self, prob['x'] - prob['y'], 11.0, 1e-6)

    def test_simple_paraboloid_scaled_desvars_cs(self):
        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])
        model.add_subsystem('comp', Paraboloid(), promotes=['*'])
        model.add_subsystem('con', ExecComp('c = x - y'), promotes=['*'])

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        if OPTIMIZER == 'SNOPT':
            prob.driver.opt_settings['Verify level'] = 3
        prob.driver.options['print_results'] = False

        model.add_design_var('x', lower=-50.0, upper=50.0, ref=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0, ref=50.0)
        model.add_objective('f_xy')
        model.add_constraint('c', lower=10.0, upper=11.0)

        model.approx_total_derivs(method='cs')

        prob.setup(check=False)
        prob.run_driver()

        # Minimum should be at (7.166667, -7.833334)
        assert_rel_error(self, prob['x'] - prob['y'], 11.0, 1e-6)

    def test_simple_paraboloid_scaled_desvars_rev(self):

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])
        model.add_subsystem('comp', Paraboloid(), promotes=['*'])
        model.add_subsystem('con', ExecComp('c = x - y'), promotes=['*'])

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        if OPTIMIZER == 'SNOPT':
            prob.driver.opt_settings['Verify level'] = 3
        prob.driver.options['print_results'] = False

        model.add_design_var('x', lower=-50.0, upper=50.0, ref=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0, ref=50.0)
        model.add_objective('f_xy')
        model.add_constraint('c', lower=10.0, upper=11.0)

        prob.setup(check=False, mode='rev')
        prob.run_driver()

        # Minimum should be at (7.166667, -7.833334)
        assert_rel_error(self, prob['x'] - prob['y'], 11.0, 1e-6)

    def test_simple_paraboloid_scaled_constraint_fwd(self):

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])
        model.add_subsystem('comp', Paraboloid(), promotes=['*'])
        model.add_subsystem('con', ExecComp('c = x - y'), promotes=['*'])

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        if OPTIMIZER == 'SNOPT':
            prob.driver.opt_settings['Verify level'] = 3
        prob.driver.options['print_results'] = False

        model.add_design_var('x', lower=-50.0, upper=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0)
        model.add_objective('f_xy')
        model.add_constraint('c', lower=10.0, upper=11.0, ref=10.)

        prob.setup(check=False, mode='fwd')
        prob.run_driver()

        # Minimum should be at (7.166667, -7.833334)
        assert_rel_error(self, prob['x'] - prob['y'], 11.0, 1e-6)

    def test_simple_paraboloid_scaled_constraint_fd(self):
        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])
        model.add_subsystem('comp', Paraboloid(), promotes=['*'])
        model.add_subsystem('con', ExecComp('c = x - y'), promotes=['*'])

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        if OPTIMIZER == 'SNOPT':
            prob.driver.opt_settings['Verify level'] = 3
        prob.driver.options['print_results'] = False

        model.add_design_var('x', lower=-50.0, upper=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0)
        model.add_objective('f_xy')
        model.add_constraint('c', lower=10.0, upper=11.0, ref=10.)

        model.approx_total_derivs(method='fd')

        prob.setup(check=False)
        prob.run_driver()

        # Minimum should be at (7.166667, -7.833334)
        assert_rel_error(self, prob['x'] - prob['y'], 11.0, 1e-6)

    def test_simple_paraboloid_scaled_constraint_cs(self):
        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])
        model.add_subsystem('comp', Paraboloid(), promotes=['*'])
        model.add_subsystem('con', ExecComp('c = x - y'), promotes=['*'])

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        if OPTIMIZER == 'SNOPT':
            prob.driver.opt_settings['Verify level'] = 3
        prob.driver.options['print_results'] = False

        model.add_design_var('x', lower=-50.0, upper=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0)
        model.add_objective('f_xy')
        model.add_constraint('c', lower=10.0, upper=11.0, ref=10.)

        model.approx_total_derivs(method='cs')

        prob.setup(check=False)
        prob.run_driver()

        # Minimum should be at (7.166667, -7.833334)
        assert_rel_error(self, prob['x'] - prob['y'], 11.0, 1e-6)

    def test_simple_paraboloid_scaled_constraint_rev(self):

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])
        model.add_subsystem('comp', Paraboloid(), promotes=['*'])
        model.add_subsystem('con', ExecComp('c = x - y'), promotes=['*'])

        prob.set_solver_print(level=0)

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        if OPTIMIZER == 'SNOPT':
            prob.driver.opt_settings['Verify level'] = 3
        prob.driver.options['print_results'] = False

        model.add_design_var('x', lower=-50.0, upper=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0)
        model.add_objective('f_xy')
        model.add_constraint('c', lower=10.0, upper=11.0, ref=10.)

        prob.setup(check=False, mode='rev')
        prob.run_driver()

        # Minimum should be at (7.166667, -7.833334)
        assert_rel_error(self, prob['x'] - prob['y'], 11.0, 1e-6)

    def test_simple_paraboloid_scaled_objective_fwd(self):

        prob = Problem()
        model = prob.model = Group()

        prob.set_solver_print(level=0)

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])
        model.add_subsystem('comp', Paraboloid(), promotes=['*'])
        model.add_subsystem('con', ExecComp('c = x - y'), promotes=['*'])

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        if OPTIMIZER == 'SNOPT':
            prob.driver.opt_settings['Verify level'] = 3
        prob.driver.options['print_results'] = False

        model.add_design_var('x', lower=-50.0, upper=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0)
        model.add_objective('f_xy', ref=10.)
        model.add_constraint('c', lower=10.0, upper=11.0)

        prob.setup(check=False, mode='fwd')
        prob.run_driver()

        # Minimum should be at (7.166667, -7.833334)
        assert_rel_error(self, prob['x'] - prob['y'], 11.0, 1e-6)

    def test_simple_paraboloid_scaled_objective_rev(self):

        prob = Problem()
        model = prob.model = Group()

        prob.set_solver_print(level=0)

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])
        model.add_subsystem('comp', Paraboloid(), promotes=['*'])
        model.add_subsystem('con', ExecComp('c = x - y'), promotes=['*'])

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        if OPTIMIZER == 'SNOPT':
            prob.driver.opt_settings['Verify level'] = 3
        prob.driver.options['print_results'] = False

        model.add_design_var('x', lower=-50.0, upper=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0)
        model.add_objective('f_xy', ref=10.)
        model.add_constraint('c', lower=10.0, upper=11.0)

        prob.setup(check=False, mode='rev')
        prob.run_driver()

        # Minimum should be at (7.166667, -7.833334)
        assert_rel_error(self, prob['x'] - prob['y'], 11.0, 1e-6)

    def test_sellar_mdf(self):

        prob = Problem()
        model = prob.model = SellarDerivativesGrouped()

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER
        if OPTIMIZER == 'SNOPT':
            prob.driver.opt_settings['Verify level'] = 3
        prob.driver.options['print_results'] = False

        model.add_design_var('z', lower=np.array([-10.0, 0.0]), upper=np.array([10.0, 10.0]))
        model.add_design_var('x', lower=0.0, upper=10.0)
        model.add_objective('obj')
        model.add_constraint('con1', upper=0.0)
        model.add_constraint('con2', upper=0.0)

        prob.setup(check=False, mode='rev')
        prob.run_driver()

        assert_rel_error(self, prob['z'][0], 1.9776, 1e-3)
        assert_rel_error(self, prob['z'][1], 0.0, 1e-3)
        assert_rel_error(self, prob['x'], 0.0, 1e-3)

    def test_analysis_error_objfunc(self):

        # Component raises an analysis error during some runs, and pyopt
        # attempts to recover.

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])

        model.add_subsystem('comp', ParaboloidAE(), promotes=['*'])

        model.add_subsystem('con', ExecComp('c = - x + y'), promotes=['*'])

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER

        if OPTIMIZER == 'SLSQP':
            prob.driver.opt_settings['ACC'] = 1e-9

        prob.driver.options['print_results'] = False
        model.add_design_var('x', lower=-50.0, upper=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0)

        model.add_objective('f_xy')
        model.add_constraint('c', upper=-15.0)

        prob.setup(check=False)
        prob.run_driver()

        # Minimum should be at (7.166667, -7.833334)
        assert_rel_error(self, prob['x'], 7.16667, 1e-6)
        assert_rel_error(self, prob['y'], -7.833334, 1e-6)

        # Normally it takes 9 iterations, but takes 13 here because of the
        # analysis failures. (note SLSQP takes 5 instead of 4)
        if OPTIMIZER == 'SLSQP':
            self.assertEqual(prob.driver.iter_count, 5)
        else:
            self.assertEqual(prob.driver.iter_count, 13)

    def test_raised_error_objfunc(self):

        # Component fails hard this time during execution, so we expect
        # pyoptsparse to raise.

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])

        comp = model.add_subsystem('comp', ParaboloidAE(), promotes=['*'])

        model.add_subsystem('con', ExecComp('c = - x + y'), promotes=['*'])

        prob.driver = pyOptSparseDriver()

        # SNOPT has a weird cleanup problem when this fails, so we use SLSQP. For the
        # regular failure, it doesn't matter which opt we choose since they all fail through.
        prob.driver.options['optimizer'] = 'SLSQP'
        prob.driver.opt_settings['ACC'] = 1e-9

        prob.driver.options['print_results'] = False
        model.add_design_var('x', lower=-50.0, upper=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0)

        model.add_objective('f_xy')
        model.add_constraint('c', upper=-15.0)

        comp.fail_hard = True

        prob.setup(check=False)

        with self.assertRaises(Exception) as err:
            prob.run_driver()

        # pyopt's failure message differs by platform and is not informative anyway

    def test_analysis_error_sensfunc(self):

        # Component raises an analysis error during some linearize calls, and
        # pyopt attempts to recover.

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])

        comp = model.add_subsystem('comp', ParaboloidAE(), promotes=['*'])

        model.add_subsystem('con', ExecComp('c = - x + y'), promotes=['*'])

        prob.driver = pyOptSparseDriver()
        prob.driver.options['optimizer'] = OPTIMIZER

        if OPTIMIZER == 'SLSQP':
            prob.driver.opt_settings['ACC'] = 1e-9

        prob.driver.options['print_results'] = False
        model.add_design_var('x', lower=-50.0, upper=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0)

        model.add_objective('f_xy')
        model.add_constraint('c', upper=-15.0)

        comp.grad_fail_at = 2
        comp.eval_fail_at = 100

        prob.setup(check=False)
        prob.run_driver()

        # SLSQP does a bad job recovering from gradient failures
        if OPTIMIZER == 'SLSQP':
            tol = 1e-2
        else:
            tol = 1e-6

        # Minimum should be at (7.166667, -7.833334)
        assert_rel_error(self, prob['x'], 7.16667, tol)
        assert_rel_error(self, prob['y'], -7.833334, tol)

        # Normally it takes 9 iterations, but takes 13 here because of the
        # gradfunc failures. (note SLSQP just doesn't do well)
        if OPTIMIZER == 'SNOPT':
            self.assertEqual(prob.driver.iter_count, 13)

    def test_raised_error_sensfunc(self):

        # Component fails hard this time during gradient eval, so we expect
        # pyoptsparse to raise.

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])

        comp = model.add_subsystem('comp', ParaboloidAE(), promotes=['*'])
        model.add_subsystem('con', ExecComp('c = - x + y'), promotes=['*'])

        prob.driver = pyOptSparseDriver()

        # SNOPT has a weird cleanup problem when this fails, so we use SLSQP. For the
        # regular failure, it doesn't matter which opt we choose since they all fail through.
        prob.driver.options['optimizer'] = 'SLSQP'
        prob.driver.opt_settings['ACC'] = 1e-9

        prob.driver.options['print_results'] = False
        model.add_design_var('x', lower=-50.0, upper=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0)

        model.add_objective('f_xy')
        model.add_constraint('c', upper=-15.0)

        comp.fail_hard = True
        comp.grad_fail_at = 2
        comp.eval_fail_at = 100

        prob.setup(check=False)

        with self.assertRaises(Exception) as err:
            prob.run_driver()

        # pyopt's failure message differs by platform and is not informative anyway
        del prob

if __name__ == "__main__":
    unittest.main()
