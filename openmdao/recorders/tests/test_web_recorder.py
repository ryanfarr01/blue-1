""" Unit test for the OpenMDAOServerRecorder. """
import errno
import os
import time
import unittest
import numpy as np
import requests_mock
import json
import base64

from shutil import rmtree
from six import iteritems, PY2, PY3
from tempfile import mkdtemp

from openmdao.api import BoundsEnforceLS, NonlinearBlockGS, ArmijoGoldsteinLS, NonlinearBlockJac,\
            NewtonSolver, NonLinearRunOnce, WebRecorder, Group, IndepVarComp, ExecComp, \
            DirectSolver, ScipyIterativeSolver, PetscKSP, LinearBlockGS, LinearRunOnce, \
            LinearBlockJac

from openmdao.core.problem import Problem
from openmdao.devtools.testutil import assert_rel_error
from openmdao.utils.record_util import format_iteration_coordinate
from openmdao.utils.general_utils import set_pyoptsparse_opt
from openmdao.recorders.web_recorder import format_version
from openmdao.test_suite.components.sellar import SellarDis1withDerivatives, \
    SellarDis2withDerivatives
from openmdao.test_suite.components.paraboloid import Paraboloid

if PY2:
    import cPickle as pickle
if PY3:
    import pickle


# check that pyoptsparse is installed
# if it is, try to use SNOPT but fall back to SLSQP
OPT, OPTIMIZER = set_pyoptsparse_opt('SLSQP')
if OPTIMIZER:
    from openmdao.drivers.pyoptsparse_driver import pyOptSparseDriver
    optimizers = {'pyoptsparse': pyOptSparseDriver}


def run_driver(problem):
    t0 = time.time()
    problem.run_driver()
    t1 = time.time()

    return t0, t1

@requests_mock.Mocker()
class TestServerRecorder(unittest.TestCase):
    _endpoint_base = 'http://www.openmdao.org/visualization/case'
    _default_case_id = '123456'
    _accepted_token = 'test'
    recorded_metadata = False
    recorded_driver_iteration = False
    recorded_global_iteration = False
    recorded_system_metadata = False
    recorded_system_iteration = False
    recorded_solver_metadata = False
    recorded_solver_iterations = False
    driver_data = None
    driver_iteration_data = None
    gloabl_iteration_data = None
    system_metadata = None
    system_iterations = None
    solver_metadata = None
    solver_iterations = None

    def setUp(self):
        super(TestServerRecorder, self).setUp()

    def assert_array_close(self, test_val, comp_set):
        values_arr = [t for t in comp_set if t['name'] == test_val['name']]
        if len(values_arr) != 1:
            self.assertTrue(False, 'Expected to find a value with a unique name in the comp_set,\
             but found 0 or more than 1 instead')
            return
        np.testing.assert_almost_equal(test_val['values'], values_arr[0]['values'], decimal=5)

    def setup_sellar_model(self):
        self.prob = Problem()

        model = self.prob.model = Group()
        model.add_subsystem('px', IndepVarComp('x', 1.0), promotes=['x'])
        model.add_subsystem('pz', IndepVarComp('z', np.array([5.0, 2.0])), promotes=['z'])
        model.add_subsystem('d1', SellarDis1withDerivatives(), promotes=['x', 'z', 'y1', 'y2'])
        model.add_subsystem('d2', SellarDis2withDerivatives(), promotes=['z', 'y1', 'y2'])
        model.add_subsystem('obj_cmp', ExecComp('obj = x**2 + z[1] + y1 + exp(-y2)',
                                                z=np.array([0.0, 0.0]), x=0.0),
                                                promotes=['obj', 'x', 'z', 'y1', 'y2'])

        model.add_subsystem('con_cmp1', ExecComp('con1 = 3.16 - y1'), promotes=['con1', 'y1'])
        model.add_subsystem('con_cmp2', ExecComp('con2 = y2 - 24.0'), promotes=['con2', 'y2'])
        self.prob.model.nonlinear_solver = NonlinearBlockGS()

        self.prob.model.add_design_var('x', lower=-100, upper=100)
        self.prob.model.add_design_var('z', lower=-100, upper=100)
        self.prob.model.add_objective('obj')
        self.prob.model.add_constraint('con1')
        self.prob.model.add_constraint('con2')

    def setup_sellar_grouped_model(self):
        self.prob = Problem()

        model = self.prob.model = Group()

        model.add_subsystem('px', IndepVarComp('x', 1.0), promotes=['x'])
        model.add_subsystem('pz', IndepVarComp('z', np.array([5.0, 2.0])), promotes=['z'])

        mda = model.add_subsystem('mda', Group(), promotes=['x', 'z', 'y1', 'y2'])
        mda.linear_solver = ScipyIterativeSolver()
        mda.add_subsystem('d1', SellarDis1withDerivatives(), promotes=['x', 'z', 'y1', 'y2'])
        mda.add_subsystem('d2', SellarDis2withDerivatives(), promotes=['z', 'y1', 'y2'])

        model.add_subsystem('obj_cmp', ExecComp('obj = x**2 + z[1] + y1 + exp(-y2)',
                                                z=np.array([0.0, 0.0]), x=0.0, y1=0.0,
                                                y2=0.0),
                            promotes=['obj', 'x', 'z', 'y1', 'y2'])

        model.add_subsystem('con_cmp1', ExecComp('con1 = 3.16 - y1'), promotes=['con1', 'y1'])
        model.add_subsystem('con_cmp2', ExecComp('con2 = y2 - 24.0'), promotes=['con2', 'y2'])

        mda.nonlinear_solver = NonlinearBlockGS()
        model.linear_solver = ScipyIterativeSolver()

        model.add_design_var('z', lower=np.array([-10.0, 0.0]), upper=np.array([10.0, 10.0]))
        model.add_design_var('x', lower=0.0, upper=10.0)
        model.add_objective('obj')
        model.add_constraint('con1', upper=0.0)
        model.add_constraint('con2', upper=0.0)

    def setup_endpoints(self, m):
        m.post(self._endpoint_base, json=self.check_header, status_code=200)
        m.post(self._endpoint_base + '/' + self._default_case_id + '/global_iterations',
               json=self.check_global_iteration)
        m.post(self._endpoint_base + '/' + self._default_case_id + '/driver_metadata',
               json=self.check_driver)
        m.post(self._endpoint_base + '/' + self._default_case_id + '/driver_iterations',
               json=self.check_driver_iteration)
        m.post(self._endpoint_base + '/' + self._default_case_id + '/system_metadata',
               json=self.check_system_metadata)
        m.post(self._endpoint_base + '/' + self._default_case_id + '/system_iterations',
               json=self.check_system_iteration)
        m.post(self._endpoint_base + '/' + self._default_case_id + '/solver_metadata',
               json=self.check_solver_metadata)
        m.post(self._endpoint_base + '/' + self._default_case_id + '/solver_iterations',
               json=self.check_solver_iterations)

    def check_header(self, request, context):
        if request.headers['token'] == self._accepted_token:
            return {
                'case_id': self._default_case_id,
                'status': 'Success'
            }
        else:
            return {
                'case_id': '-1',
                'status': 'Failed',
                'reasoning': 'Bad token'
            }

    def check_driver(self, request, context):
        self.recorded_metadata = True
        self.driver_data = request.body
        return {'status': 'Success'}

    def check_driver_iteration(self, request, context):
        self.recorded_driver_iteration = True
        self.driver_iteration_data = request.body
        return {'status': 'Success'}

    def check_global_iteration(self, request, context):
        self.recorded_global_iteration = True
        self.global_iteration_data = request.body
        return {'status': 'Success'}

    def check_system_metadata(self, request, context):
        self.recorded_system_metadata = True
        self.system_metadata = request.body

    def check_system_iteration(self, request, context):
        self.recorded_system_iteration = True
        self.system_iterations = request.body

    def check_solver_metadata(self, request, context):
        self.recorded_solver_metadata = True
        self.solver_metadata = request.body

    def check_solver_iterations(self, request, context):
        self.recorded_solver_iterations = True
        self.solver_iterations = request.body

    def test_get_case_success(self, m):
        self.setup_endpoints(m)
        recorder = WebRecorder(self._accepted_token, suppress_output=True)
        self.assertEqual(recorder._case_id, self._default_case_id)

    def test_get_case_fail(self, m):
        self.setup_endpoints(m)
        recorder = WebRecorder('', suppress_output=True)
        self.assertEqual(recorder._case_id, '-1')

    def test_driver_records_metadata(self, m):
        self.setup_endpoints(m)
        recorder = WebRecorder(self._accepted_token, suppress_output=True)

        self.setup_sellar_model()

        recorder.options['includes'] = ["p1.x"]
        recorder.options['record_metadata'] = True
        self.prob.driver.add_recorder(recorder)
        self.prob.setup(check=False)

        # Need this since we aren't running the model.
        self.prob.final_setup()

        self.prob.cleanup()
        self.assertTrue(self.recorded_metadata)
        self.recorded_metadata = False

        driv_data = json.loads(self.driver_data)
        self.driver_data = None

        driv_id = driv_data['id']
        model_data = json.loads(driv_data['model_viewer_data'])
        connections = model_data['connections_list']
        self.assertEqual(driv_id, 'Driver')
        self.assertEqual(len(connections), 11)

    def test_driver_doesnt_record_metadata(self, m):
        self.setup_endpoints(m)

        self.setup_sellar_model()

        recorder = WebRecorder(self._accepted_token, suppress_output=True)
        recorder.options['record_metadata'] = False
        self.prob.driver.add_recorder(recorder)
        self.prob.setup(check=False)

        self.prob.cleanup()

        self.assertFalse(self.recorded_metadata)
        self.assertEqual(self.driver_data, None)

    def test_only_desvars_recorded(self, m):
        self.setup_endpoints(m)

        recorder = WebRecorder(self._accepted_token, suppress_output=True)

        self.setup_sellar_model()

        recorder.options['record_desvars'] = True
        recorder.options['record_responses'] = False
        recorder.options['record_objectives'] = False
        recorder.options['record_constraints'] = False
        self.prob.driver.add_recorder(recorder)

        self.prob.setup(check=False)

        t0, t1 = run_driver(self.prob)

        self.prob.cleanup()

        driver_iteration_data = json.loads(self.driver_iteration_data)
        self.driver_iteration_data = None
        self.assertTrue({'name': 'px.x', 'values': [1.0]} in driver_iteration_data['desvars'])
        self.assertTrue({'name': 'pz.z', 'values': [5.0, 2.0]} in driver_iteration_data['desvars'])
        self.assertEqual(driver_iteration_data['responses'], [])
        self.assertEqual(driver_iteration_data['objectives'], [])
        self.assertEqual(driver_iteration_data['constraints'], [])

    def test_only_objectives_recorded(self, m):
        self.setup_endpoints(m)
        recorder = WebRecorder(self._accepted_token, suppress_output=True)

        self.setup_sellar_model()

        recorder.options['record_desvars'] = False
        recorder.options['record_responses'] = False
        recorder.options['record_objectives'] = True
        recorder.options['record_constraints'] = False
        self.prob.driver.add_recorder(recorder)
        self.prob.setup(check=False)

        t0, t1 = run_driver(self.prob)

        self.prob.cleanup()

        driver_iteration_data = json.loads(self.driver_iteration_data)
        self.assertAlmostEqual(driver_iteration_data['objectives'][0]['values'][0], 28.5883082)
        self.assertEqual(driver_iteration_data['objectives'][0]['name'], 'obj_cmp.obj')
        self.assertEqual(driver_iteration_data['desvars'], [])
        self.assertEqual(driver_iteration_data['responses'], [])
        self.assertEqual(driver_iteration_data['constraints'], [])

    def test_only_constraints_recorded(self, m):
        self.setup_endpoints(m)
        recorder = WebRecorder(self._accepted_token, suppress_output=True)

        self.setup_sellar_model()

        recorder.options['record_desvars'] = False
        recorder.options['record_responses'] = False
        recorder.options['record_objectives'] = False
        recorder.options['record_constraints'] = True
        self.prob.driver.add_recorder(recorder)
        self.prob.setup(check=False)

        t0, t1 = run_driver(self.prob)

        self.prob.cleanup()

        driver_iteration_data = json.loads(self.driver_iteration_data)
        if driver_iteration_data['constraints'][0]['name'] == 'con_cmp1.con1':
            self.assertAlmostEqual(driver_iteration_data['constraints'][0]['values'][0],
                                   -22.42830237)
            self.assertAlmostEqual(driver_iteration_data['constraints'][1]['values'][0],
                                   -11.94151185)
            self.assertEqual(driver_iteration_data['constraints'][1]['name'], 'con_cmp2.con2')
            self.assertEqual(driver_iteration_data['constraints'][0]['name'], 'con_cmp1.con1')
        elif driver_iteration_data['constraints'][0]['name'] == 'con_cmp2.con2':
            self.assertAlmostEqual(driver_iteration_data['constraints'][1]['values'][0],
                                   -22.42830237)
            self.assertAlmostEqual(driver_iteration_data['constraints'][0]['values'][0],
                                   -11.94151185)
            self.assertEqual(driver_iteration_data['constraints'][0]['name'], 'con_cmp2.con2')
            self.assertEqual(driver_iteration_data['constraints'][1]['name'], 'con_cmp1.con1')
        else:
            self.assertTrue(False, 'Driver iteration data did not contain\
             the expected names for constraints')

        self.assertEqual(driver_iteration_data['desvars'], [])
        self.assertEqual(driver_iteration_data['objectives'], [])
        self.assertEqual(driver_iteration_data['responses'], [])

    def test_record_system(self, m):
        self.setup_endpoints(m)
        recorder = WebRecorder(self._accepted_token, suppress_output=True)

        self.setup_sellar_model()

        recorder.options['record_inputs'] = True
        recorder.options['record_outputs'] = True
        recorder.options['record_residuals'] = True
        recorder.options['record_metadata'] = True

        self.prob.model.add_recorder(recorder)

        d1 = self.prob.model.get_subsystem('d1')  # instance of SellarDis1withDerivatives, a Group
        d1.add_recorder(recorder)

        obj_cmp = self.prob.model.get_subsystem('obj_cmp')  # an ExecComp
        obj_cmp.add_recorder(recorder)

        self.prob.setup(check=False)

        t0, t1 = run_driver(self.prob)

        self.prob.cleanup()

        system_metadata = json.loads(self.system_metadata)
        system_iterations = json.loads(self.system_iterations)
        scaling_facts_raw = system_metadata['scaling_factors']
        scaling_facts_ascii = scaling_facts_raw.encode('ascii')
        scaling_facts_base64 = base64.b64decode(scaling_facts_ascii)
        scaling_facts = pickle.loads(scaling_facts_base64)
        system_metadata['scaling_factors'] = scaling_facts

        inputs = [
            {'name': 'd1.z', 'values': [5.0, 2.0]},
            {'name': 'd1.x', 'values': [1.0]},
            {'name': 'd2.z', 'values': [5.0, 2.0]},
            {'name': 'd1.y2', 'values': [12.05848815]}
        ]

        outputs = [
            {'name': 'd1.y1', 'values': [25.58830237]}
        ]

        residuals = [
            {'name': 'd1.y1', 'values': [0.0]}
        ]

        for i in inputs:
            self.assert_array_close(i, system_iterations['inputs'])
        for o in outputs:
            self.assert_array_close(o, system_iterations['outputs'])
        for r in residuals:
            self.assert_array_close(r, system_iterations['residuals'])

        inputs = [
            {'name': 'con_cmp2.y2', 'values': [12.058488150624356]},
            {'name': 'obj_cmp.y1', 'values': [25.58830237000701]},
            {'name': 'obj_cmp.x', 'values': [1.0]},
            {'name': 'obj_cmp.z', 'values': [5.0, 2.0]}
        ]

        outputs = [
            {'name': 'obj_cmp.obj', 'values': [28.58830816]}
        ]

        residuals = [
            {'name': 'obj_cmp.obj', 'values': [0.0]}
        ]

        for i in inputs:
            self.assert_array_close(i, system_iterations['inputs'])
        for o in outputs:
            self.assert_array_close(o, system_iterations['outputs'])
        for r in residuals:
            self.assert_array_close(r, system_iterations['residuals'])

    def test_simple_driver_recording(self, m):
        self.setup_endpoints(m)
        recorder = WebRecorder(self._accepted_token, suppress_output=True)

        if OPT is None:
            raise unittest.SkipTest("pyoptsparse is not installed")

        if OPTIMIZER is None:
            raise unittest.SkipTest("pyoptsparse is not providing SNOPT or SLSQP")

        prob = Problem()
        model = prob.model = Group()

        model.add_subsystem('p1', IndepVarComp('x', 50.0), promotes=['*'])
        model.add_subsystem('p2', IndepVarComp('y', 50.0), promotes=['*'])
        model.add_subsystem('comp', Paraboloid(), promotes=['*'])
        model.add_subsystem('con', ExecComp('c = - x + y'), promotes=['*'])

        model.suppress_solver_output = True

        prob.driver = pyOptSparseDriver()

        prob.driver.add_recorder(recorder)
        recorder.options['record_desvars'] = True
        recorder.options['record_responses'] = True
        recorder.options['record_objectives'] = True
        recorder.options['record_constraints'] = True

        prob.driver.options['optimizer'] = OPTIMIZER
        if OPTIMIZER == 'SLSQP':
            prob.driver.opt_settings['ACC'] = 1e-9

        model.add_design_var('x', lower=-50.0, upper=50.0)
        model.add_design_var('y', lower=-50.0, upper=50.0)
        model.add_objective('f_xy')
        model.add_constraint('c', upper=-15.0)
        prob.setup(check=False)

        t0, t1 = run_driver(prob)

        prob.cleanup()

        driver_iteration_data = json.loads(self.driver_iteration_data)

        expected_desvars = [
            {'name': 'p1.x', 'values': [7.1666666]},
            {'name': 'p2.y', 'values': [-7.8333333]}
        ]

        expected_objectives = [
            {'name': 'comp.f_xy', 'values': [-27.083333]}
        ]

        expected_constraints = [
            {'name': 'con.c', 'values': [-15.0]}
        ]

        for d in expected_desvars:
            self.assert_array_close(d, driver_iteration_data['desvars'])

        for o in expected_objectives:
            self.assert_array_close(o, driver_iteration_data['objectives'])

        for c in expected_constraints:
            self.assert_array_close(c, driver_iteration_data['constraints'])

    def test_array_input(self, m):
        self.setup_endpoints(m)
        recorder = WebRecorder(self._accepted_token, suppress_output=True)

        if OPT is None:
            raise unittest.SkipTest("pyoptsparse is not installed")

        if OPTIMIZER is None:
            raise unittest.SkipTest("pyoptsparse is not providing SNOPT or SLSQP")

        prob = Problem(model=Group())
        prob.model.add_subsystem('indep', IndepVarComp('x', np.arange(12).reshape((4,3))))
        prob.model.add_subsystem('C1', ExecComp('y=numpy.sum(x)*2.0', x=np.zeros((2,2))))

        # connect C1.x to entries (0,0), (-1,1), (2,1), (1,1) of indep.x
        prob.model.connect('indep.x', 'C1.x',
                           src_indices=[[(0,0), (-1,1)],
                                        [(2,1), (1,1)]])

        prob.driver.add_recorder(recorder)
        recorder.options['record_desvars'] = True
        recorder.options['record_responses'] = True
        recorder.options['record_objectives'] = True
        recorder.options['record_constraints'] = True
        recorder.options['record_inputs'] = True

        prob.setup(check=False)

        t0, t1 = run_driver(prob)

        prob.cleanup()

        driver_iteration_data = json.loads(self.driver_iteration_data)

        expected_desvars = [
            {'name': 'p1.x', 'values': [7.1666666]},
            {'name': 'p2.y', 'values': [-7.8333333]}
        ]

        expected_objectives = [
            {'name': 'comp.f_xy', 'values': [-27.083333]}
        ]

        expected_constraints = [
            {'name': 'con.c', 'values': [-15.0]}
        ]

        print("Desvars: " + str(driver_iteration_data['desvars']))
        print(" ")
        print("Objectives: " + str(driver_iteration_data['objectives']))
        print(" ")
        print("Constraints: " + str(driver_iteration_data['constraints']))

        # for d in expected_desvars:
        #     self.assert_array_close(d, driver_iteration_data['desvars'])

        # for o in expected_objectives:
        #     self.assert_array_close(o, driver_iteration_data['objectives'])

        # for c in expected_constraints:
        #     self.assert_array_close(c, driver_iteration_data['constraints'])

    def test_record_solver(self, m):
        self.setup_endpoints(m)
        recorder = WebRecorder(self._accepted_token, suppress_output=True)

        self.setup_sellar_model()

        recorder.options['record_abs_error'] = True
        recorder.options['record_rel_error'] = True
        recorder.options['record_solver_output'] = True
        recorder.options['record_solver_residuals'] = True
        self.prob.model._nonlinear_solver.add_recorder(recorder)

        self.prob.setup(check=False)

        t0, t1 = run_driver(self.prob)

        self.prob.cleanup()

        expected_solver_output = [
            {'name': 'con_cmp1.con1', 'values': [-22.42830237000701]},
            {'name': 'd1.y1', 'values': [25.58830237000701]},
            {'name': 'con_cmp2.con2', 'values': [-11.941511849375644]},
            {'name': 'pz.z', 'values': [5.0, 2.0]},
            {'name': 'obj_cmp.obj', 'values': [28.588308165163074]},
            {'name': 'd2.y2', 'values': [12.058488150624356]},
            {'name': 'px.x', 'values': [1.0]}
        ]

        expected_solver_residuals = [
            {'name': 'con_cmp1.con1', 'values': [0.0]},
            {'name': 'd1.y1', 'values': [1.318802844707534e-10]},
            {'name': 'con_cmp2.con2', 'values': [0.0]},
            {'name': 'pz.z', 'values': [0.0, 0.0]},
            {'name': 'obj_cmp.obj', 'values': [0.0]},
            {'name': 'd2.y2', 'values': [0.0]},
            {'name': 'px.x', 'values': [0.0]}
        ]

        solver_iteration = json.loads(self.solver_iterations)

        self.assertAlmostEqual(solver_iteration['abs_err'], 1.31880284470753394998e-10)
        self.assertAlmostEqual(solver_iteration['rel_err'], 3.6299074030587596e-12)

        for o in expected_solver_output:
            self.assert_array_close(o, solver_iteration['solver_output'])

        for r in expected_solver_residuals:
            self.assert_array_close(r, solver_iteration['solver_residuals'])

    def test_record_line_search_armijo_goldstein(self, m):
        self.setup_endpoints(m)
        recorder = WebRecorder(self._accepted_token, suppress_output=True)
        self.setup_sellar_model()

        model = self.prob.model
        model.nonlinear_solver = NewtonSolver()
        model.linear_solver = ScipyIterativeSolver()

        model._nonlinear_solver.options['solve_subsystems'] = True
        model._nonlinear_solver.options['max_sub_solves'] = 4
        ls = model._nonlinear_solver.linesearch = ArmijoGoldsteinLS(bound_enforcement='vector')

        # This is pretty bogus, but it ensures that we get a few LS iterations.
        ls.options['c'] = 100.0
        ls.add_recorder(recorder)

        self.prob.setup(check=False)

        t0, t1 = run_driver(self.prob)

        self.prob.cleanup()

        expected_abs_error = model._residuals.get_norm()
        expected_rel_error = expected_abs_error / 2.9086436370499857e-08

        solver_iteration = json.loads(self.solver_iterations)

        self.assertAlmostEqual(solver_iteration['abs_err'], expected_abs_error)
        self.assertAlmostEqual(solver_iteration['rel_err'], expected_rel_error)
        self.assertEqual(solver_iteration['solver_output'], [])
        self.assertEqual(solver_iteration['solver_residuals'], [])

    def test_record_line_search_bounds_enforce(self, m):
        self.setup_endpoints(m)
        recorder = WebRecorder(self._accepted_token, suppress_output=True)
        self.setup_sellar_model()

        model = self.prob.model
        model.nonlinear_solver = NewtonSolver()
        model.linear_solver = ScipyIterativeSolver()

        model.nonlinear_solver.options['solve_subsystems'] = True
        model.nonlinear_solver.options['max_sub_solves'] = 4
        ls = model.nonlinear_solver.linesearch = BoundsEnforceLS(bound_enforcement='vector')

        ls.add_recorder(recorder)

        self.prob.setup(check=False)

        t0, t1 = run_driver(self.prob)

        self.prob.cleanup()

        expected_abs_error = 7.02783609310096e-10
        expected_rel_error = 8.078674883382422e-07

        solver_iteration = json.loads(self.solver_iterations)
        self.assertAlmostEqual(solver_iteration['abs_err'], expected_abs_error)
        self.assertAlmostEqual(solver_iteration['rel_err'], expected_rel_error)
        self.assertEqual(solver_iteration['solver_output'], [])
        self.assertEqual(solver_iteration['solver_residuals'], [])

    def test_record_solver_nonlinear_block_gs(self, m):
        self.setup_endpoints(m)
        recorder = WebRecorder(self._accepted_token, suppress_output=True)
        self.setup_sellar_model()

        self.prob.model.nonlinear_solver = NonlinearBlockGS()
        self.prob.model.nonlinear_solver.add_recorder(recorder)

        recorder.options['record_solver_output'] = True
        recorder.options['record_solver_residuals'] = True

        self.prob.setup(check=False)

        t0, t1 = run_driver(self.prob)

        self.prob.cleanup()

        coordinate = [0, 'Driver', (0,), 'root._solve_nonlinear', (0,), 'NonlinearBlockGS', (6, )]
        expected_abs_error = 1.31880284470753394998e-10
        expected_rel_error = 3.6299074030587596e-12

        expected_solver_output = [
            {'name': 'px.x', 'values': [1.0]},
            {'name': 'pz.z', 'values': [5., 2.]},
            {'name': 'd1.y1', 'values': [25.58830237]},
            {'name': 'd2.y2', 'values': [12.05848815]},
            {'name': 'obj_cmp.obj', 'values': [28.58830817]},
            {'name': 'con_cmp1.con1', 'values': [-22.42830237]},
            {'name': 'con_cmp2.con2', 'values': [-11.94151185]}
        ]

        expected_solver_residuals = [
            {'name': 'px.x', 'values': [-0]},
            {'name': 'pz.z', 'values': [-0., -0.]},
            {'name': 'd1.y1', 'values': [1.31880284e-10]},
            {'name': 'd2.y2', 'values': [0.]},
            {'name': 'obj_cmp.obj', 'values': [0.]},
            {'name': 'con_cmp1.con1', 'values': [0.]},
            {'name': 'con_cmp2.con2', 'values': [0.]},
        ]

        solver_iteration = json.loads(self.solver_iterations)

        self.assertAlmostEqual(solver_iteration['abs_err'], expected_abs_error)
        self.assertAlmostEqual(solver_iteration['rel_err'], expected_rel_error)

        for o in expected_solver_output:
            self.assert_array_close(o, solver_iteration['solver_output'])

        for r in expected_solver_residuals:
            self.assert_array_close(r, solver_iteration['solver_residuals'])

    def test_record_solver_nonlinear_block_jac(self, m):
        self.setup_endpoints(m)
        recorder = WebRecorder(self._accepted_token, suppress_output=True)
        self.setup_sellar_model()

        self.prob.model.nonlinear_solver = NonlinearBlockJac()
        self.prob.model.nonlinear_solver.add_recorder(recorder)

        self.prob.setup(check=False)

        t0, t1 = run_driver(self.prob)

        self.prob.cleanup()

        solver_iteration = json.loads(self.solver_iterations)

        expected_abs_error = 7.234027587097439e-07
        expected_rel_error = 1.991112651729199e-08
        self.assertAlmostEqual(expected_abs_error, solver_iteration['abs_err'])
        self.assertAlmostEqual(expected_rel_error, solver_iteration['rel_err'])
        self.assertEqual(solver_iteration['solver_residuals'], [])
        self.assertEqual(solver_iteration['solver_output'], [])

    def test_record_solver_nonlinear_newton(self, m):
        self.setup_endpoints(m)
        recorder = WebRecorder(self._accepted_token, suppress_output=True)
        self.setup_sellar_model()

        self.prob.model.nonlinear_solver = NewtonSolver()
        self.prob.model.nonlinear_solver.add_recorder(recorder)

        self.prob.setup(check=False)

        t0, t1 = run_driver(self.prob)

        self.prob.cleanup()

        solver_iteration = json.loads(self.solver_iterations)

        expected_abs_error = 5.041402548755789e-06
        expected_rel_error = 1.3876088080160474e-07
        self.assertAlmostEqual(expected_abs_error, solver_iteration['abs_err'])
        self.assertAlmostEqual(expected_rel_error, solver_iteration['rel_err'])
        self.assertEqual(solver_iteration['solver_residuals'], [])
        self.assertEqual(solver_iteration['solver_output'], [])

    def test_record_solver_nonlinear_nonlinear_run_once(self, m):
        self.setup_endpoints(m)
        recorder = WebRecorder(self._accepted_token, suppress_output=True)
        self.setup_sellar_model()

        self.prob.model.nonlinear_solver = NonLinearRunOnce()
        self.prob.model.nonlinear_solver.add_recorder(recorder)

        self.prob.setup(check=False)

        t0, t1 = run_driver(self.prob)

        self.prob.cleanup()

        # No norms so no expected norms
        expected_abs_error = 0.0
        expected_rel_error = 0.0
        expected_solver_residuals = None
        expected_solver_output = None

        solver_iteration = json.loads(self.solver_iterations)

        self.assertEqual(expected_abs_error, solver_iteration['abs_err'])
        self.assertEqual(expected_rel_error, solver_iteration['rel_err'])
        self.assertEqual(solver_iteration['solver_residuals'], [])
        self.assertEqual(solver_iteration['solver_output'], [])

    def test_record_solver_linear_direct_solver(self, m):
        self.setup_endpoints(m)
        recorder = WebRecorder(self._accepted_token, suppress_output=True)
        self.setup_sellar_model()

        self.prob.model.nonlinear_solver = NewtonSolver()
        # used for analytic derivatives
        self.prob.model.nonlinear_solver.linear_solver = DirectSolver()

        recorder.options['record_abs_error'] = True
        recorder.options['record_rel_error'] = True
        recorder.options['record_solver_output'] = True
        recorder.options['record_solver_residuals'] = True
        self.prob.model.nonlinear_solver.linear_solver.add_recorder(recorder)

        self.prob.setup(check=False)
        t0, t1 = run_driver(self.prob)

        expected_solver_output = [
            {'name': 'px.x', 'values': [0.0]},
            {'name': 'pz.z', 'values': [0.0, 0.0]},
            {'name': 'd1.y1', 'values': [0.00045069]},
            {'name': 'd2.y2', 'values': [-0.00225346]},
            {'name': 'obj_cmp.obj', 'values': [0.00045646]},
            {'name': 'con_cmp1.con1', 'values': [-0.00045069]},
            {'name': 'con_cmp2.con2', 'values': [-0.00225346]},
        ]

        expected_solver_residuals = [
            {'name': 'px.x', 'values': [0.0]},
            {'name': 'pz.z', 'values': [-0., -0.]},
            {'name': 'd1.y1', 'values': [0.0]},
            {'name': 'd2.y2', 'values': [-0.00229801]},
            {'name': 'obj_cmp.obj', 'values': [5.75455956e-06]},
            {'name': 'con_cmp1.con1', 'values': [-0.]},
            {'name': 'con_cmp2.con2', 'values': [-0.]},
        ]

        solver_iteration = json.loads(self.solver_iterations)

        self.assertAlmostEqual(0.0, solver_iteration['abs_err'])
        self.assertAlmostEqual(0.0, solver_iteration['rel_err'])

        for o in expected_solver_output:
            self.assert_array_close(o, solver_iteration['solver_output'])

        for r in expected_solver_residuals:
            self.assert_array_close(r, solver_iteration['solver_residuals'])

    def test_record_solver_linear_scipy_iterative_solver(self, m):
        self.setup_endpoints(m)
        recorder = WebRecorder(self._accepted_token, suppress_output=True)
        self.setup_sellar_model()

        self.prob.model.nonlinear_solver = NewtonSolver()
        # used for analytic derivatives
        self.prob.model.nonlinear_solver.linear_solver = ScipyIterativeSolver()

        recorder.options['record_abs_error'] = True
        recorder.options['record_rel_error'] = True
        recorder.options['record_solver_output'] = True
        recorder.options['record_solver_residuals'] = True
        self.prob.model.nonlinear_solver.linear_solver.add_recorder(recorder)

        self.prob.setup(check=False)
        t0, t1 = run_driver(self.prob)

        expected_abs_error = 0.0
        expected_rel_error = 0.0

        expected_solver_output = [
            {'name': 'px.x', 'values': [0.0]},
            {'name': 'pz.z', 'values': [0.0, 0.0]},
        ]

        solver_iteration = json.loads(self.solver_iterations)

        self.assertAlmostEqual(0.0, solver_iteration['abs_err'])
        self.assertAlmostEqual(0.0, solver_iteration['rel_err'])

        for o in expected_solver_output:
            self.assert_array_close(o, solver_iteration['solver_output'])

    def test_record_solver_linear_block_gs(self, m):
        self.setup_endpoints(m)
        recorder = WebRecorder(self._accepted_token, suppress_output=True)
        self.setup_sellar_model()

        self.prob.model.nonlinear_solver = NewtonSolver()
        # used for analytic derivatives
        self.prob.model.nonlinear_solver.linear_solver = LinearBlockGS()

        recorder.options['record_abs_error'] = True
        recorder.options['record_rel_error'] = True
        recorder.options['record_solver_output'] = True
        recorder.options['record_solver_residuals'] = True
        self.prob.model.nonlinear_solver.linear_solver.add_recorder(recorder)

        self.prob.setup(check=False)
        t0, t1 = run_driver(self.prob)

        solver_iteration = json.loads(self.solver_iterations)
        expected_abs_error = 9.109083208861876e-11
        expected_rel_error = 9.114367543620551e-12

        expected_solver_output = [
            {'name': 'px.x', 'values': [0.0]},
            {'name': 'pz.z', 'values': [0.0, 0.0]},
            {'name': 'd1.y1', 'values': [0.00045069]},
            {'name': 'd2.y2', 'values': [-0.00225346]},
            {'name': 'obj_cmp.obj', 'values': [0.00045646]},
            {'name': 'con_cmp1.con1', 'values': [-0.00045069]},
            {'name': 'con_cmp2.con2', 'values': [-0.00225346]},
        ]

        self.assertAlmostEqual(expected_abs_error, solver_iteration['abs_err'])
        self.assertAlmostEqual(expected_rel_error, solver_iteration['rel_err'])

        for o in expected_solver_output:
            self.assert_array_close(o, solver_iteration['solver_output'])

    def test_record_solver_linear_linear_run_once(self, m):
        self.setup_endpoints(m)
        recorder = WebRecorder(self._accepted_token, suppress_output=True)
        # raise unittest.SkipTest("Linear Solver recording not working yet")
        self.setup_sellar_model()

        self.prob.model.nonlinear_solver = NewtonSolver()
        # used for analytic derivatives
        self.prob.model.nonlinear_solver.linear_solver = LinearRunOnce()

        recorder.options['record_abs_error'] = True
        recorder.options['record_rel_error'] = True
        recorder.options['record_solver_output'] = True
        recorder.options['record_solver_residuals'] = True
        self.prob.model.nonlinear_solver.linear_solver.add_recorder(recorder)

        self.prob.setup(check=False)
        t0, t1 = run_driver(self.prob)

        solver_iteration = json.loads(self.solver_iterations)
        expected_abs_error = 0.0
        expected_rel_error = 0.0

        expected_solver_output = [
            {'name': 'px.x', 'values': [0.0]},
            {'name': 'pz.z', 'values': [0.0, 0.0]},
            {'name': 'd1.y1', 'values': [-4.15366975e-05]},
            {'name': 'd2.y2', 'values': [-4.10568454e-06]},
            {'name': 'obj_cmp.obj', 'values': [-4.15366737e-05]},
            {'name': 'con_cmp1.con1', 'values': [4.15366975e-05]},
            {'name': 'con_cmp2.con2', 'values': [-4.10568454e-06]},
        ]

        self.assertAlmostEqual(expected_abs_error, solver_iteration['abs_err'])
        self.assertAlmostEqual(expected_rel_error, solver_iteration['rel_err'])

        for o in expected_solver_output:
            self.assert_array_close(o, solver_iteration['solver_output'])

    def test_record_solver_linear_block_jac(self, m):
        self.setup_endpoints(m)
        recorder = WebRecorder(self._accepted_token, suppress_output=True)
        self.setup_sellar_model()

        self.prob.model.nonlinear_solver = NewtonSolver()
        # used for analytic derivatives
        self.prob.model.nonlinear_solver.linear_solver = LinearBlockJac()

        recorder.options['record_abs_error'] = True
        recorder.options['record_rel_error'] = True
        recorder.options['record_solver_output'] = True
        recorder.options['record_solver_residuals'] = True
        self.prob.model.nonlinear_solver.linear_solver.add_recorder(recorder)

        self.prob.setup(check=False)
        t0, t1 = run_driver(self.prob)

        solver_iteration = json.loads(self.solver_iterations)
        expected_abs_error = 9.947388408259769e-11
        expected_rel_error = 4.330301334141486e-08

        expected_solver_output = [
            {'name': 'px.x', 'values': [0.0]},
            {'name': 'pz.z', 'values': [0.0, 0.0]},
            {'name': 'd1.y1', 'values': [4.55485639e-09]},
            {'name': 'd2.y2', 'values': [-2.27783334e-08]},
            {'name': 'obj_cmp.obj', 'values': [-2.28447051e-07]},
            {'name': 'con_cmp1.con1', 'values': [2.28461863e-07]},
            {'name': 'con_cmp2.con2', 'values': [-2.27742837e-08]},
        ]

        self.assertAlmostEqual(expected_abs_error, solver_iteration['abs_err'])
        self.assertAlmostEqual(expected_rel_error, solver_iteration['rel_err'])

        for o in expected_solver_output:
            self.assert_array_close(o, solver_iteration['solver_output'])

    def test_record_driver_system_solver(self, m):
        # Test what happens when all three types are recorded:
        #    Driver, System, and Solver
        self.setup_endpoints(m)
        recorder = WebRecorder(self._accepted_token, suppress_output=True)
        if OPT is None:
            raise unittest.SkipTest("pyoptsparse is not installed")

        if OPTIMIZER is None:
            raise unittest.SkipTest("pyoptsparse is not providing SNOPT or SLSQP")

        self.setup_sellar_grouped_model()

        self.prob.driver = pyOptSparseDriver()
        self.prob.driver.options['optimizer'] = OPTIMIZER
        self.prob.driver.opt_settings['ACC'] = 1e-9

        recorder.options['record_metadata'] = True

        # Add recorders
        # Driver
        self.prob.driver.add_recorder(recorder)
        # System
        pz = self.prob.model.get_subsystem('pz')  # IndepVarComp which is an ExplicitComponent
        pz.add_recorder(recorder)
        # Solver
        mda = self.prob.model.get_subsystem('mda')
        mda.nonlinear_solver.add_recorder(recorder)

        # Driver
        recorder.options['record_desvars'] = True
        recorder.options['record_responses'] = True
        recorder.options['record_objectives'] = True
        recorder.options['record_constraints'] = True

        # System
        recorder.options['record_inputs'] = True
        recorder.options['record_outputs'] = True
        recorder.options['record_residuals'] = True

        # Solver
        recorder.options['record_abs_error'] = True
        recorder.options['record_rel_error'] = True
        recorder.options['record_solver_output'] = True
        recorder.options['record_solver_residuals'] = True

        self.prob.setup(check=False, mode='rev')
        t0, t1 = run_driver(self.prob)
        self.prob.cleanup()

        # Driver recording test
        coordinate = [0, 'SLSQP', (7, )]

        expected_desvars = [
            {'name': 'pz.z', 'values': self.prob['pz.z']},
            {'name': 'px.x', 'values': self.prob['px.x']}
        ]

        expected_objectives = [
            {'name': 'obj_cmp.obj', 'values': self.prob['obj_cmp.obj']}
        ]

        expected_constraints = [
            {'name': 'con_cmp1.con1', 'values': self.prob['con_cmp1.con1']},
            {'name': 'con_cmp2.con2', 'values': self.prob['con_cmp2.con2']}
        ]

        driver_iteration_data = json.loads(self.driver_iteration_data)

        for d in expected_desvars:
            self.assert_array_close(d, driver_iteration_data['desvars'])

        for o in expected_objectives:
            self.assert_array_close(o, driver_iteration_data['objectives'])

        for c in expected_constraints:
            self.assert_array_close(c, driver_iteration_data['constraints'])

        # System recording test
        expected_inputs = []
        expected_outputs = [{'name': 'pz.z', 'values': [1.97764, -1.13287e-15]}]
        expected_residuals = [{'name': 'pz.z', 'values': [0.0, 0.0]}]

        system_iteration = json.loads(self.system_iterations)

        self.assertEqual(expected_inputs, system_iteration['inputs'])

        for o in expected_outputs:
            self.assert_array_close(o, system_iteration['outputs'])

        for r in expected_residuals:
            self.assert_array_close(r, system_iteration['residuals'])

        # Solver recording test
        expected_abs_error = 3.90598e-11
        expected_rel_error = 1.037105199e-6

        expected_solver_output = [
            {'name': 'mda.d2.y2', 'values': [3.75527777]},
            {'name': 'mda.d1.y1', 'values': [3.16]}
        ]

        expected_solver_residuals = [
            {'name': 'mda.d2.y2', 'values': [0.0]},
            {'name': 'mda.d1.y1', 'values': [0.0]}
        ]

        solver_iteration = json.loads(self.solver_iterations)

        self.assertAlmostEqual(expected_abs_error, solver_iteration['abs_err'])
        self.assertAlmostEqual(expected_rel_error, solver_iteration['rel_err'])

        for o in expected_solver_output:
            self.assert_array_close(o, solver_iteration['solver_output'])

        for r in expected_solver_residuals:
            self.assert_array_close(r, solver_iteration['solver_residuals'])

    def test_implicit_component(self, m):
        self.setup_endpoints(m)
        recorder = WebRecorder(self._accepted_token, suppress_output=True)
        from openmdao.core.tests.test_impl_comp import QuadraticLinearize, QuadraticJacVec
        group = Group()
        group.add_subsystem('comp1', IndepVarComp([('a', 1.0), ('b', 1.0), ('c', 1.0)]))
        group.add_subsystem('comp2', QuadraticLinearize())
        group.add_subsystem('comp3', QuadraticJacVec())
        group.connect('comp1.a', 'comp2.a')
        group.connect('comp1.b', 'comp2.b')
        group.connect('comp1.c', 'comp2.c')
        group.connect('comp1.a', 'comp3.a')
        group.connect('comp1.b', 'comp3.b')
        group.connect('comp1.c', 'comp3.c')

        prob = Problem(model=group)
        prob.setup(check=False)

        prob['comp1.a'] = 1.
        prob['comp1.b'] = -4.
        prob['comp1.c'] = 3.

        comp2 = prob.model.get_subsystem('comp2')  # ImplicitComponent
        comp2.add_recorder(recorder)

        t0, t1 = run_driver(prob)
        prob.cleanup()

        expected_inputs = [
            {'name': 'comp2.a', 'values': [1.0]},
            {'name': 'comp2.b', 'values': [-4.0]},
            {'name': 'comp2.c', 'values': [3.0]}
        ]
        expected_outputs = [{'name': 'comp2.x', 'values': [3.0]}]
        expected_residuals = [{'name': 'comp2.x', 'values': [0.0]}]

        system_iteration = json.loads(self.system_iterations)

        for i in expected_inputs:
            self.assert_array_close(i, system_iteration['inputs'])

        for r in expected_residuals:
            self.assert_array_close(r, system_iteration['residuals'])

        for o in expected_outputs:
            self.assert_array_close(o, system_iteration['outputs'])

if __name__ == "__main__":
    unittest.main()
