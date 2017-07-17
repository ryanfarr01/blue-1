"""
Test objects for the sellar two discipline problem.

From Sellar's analytic problem.

    Sellar, R. S., Batill, S. M., and Renaud, J. E., "Response Surface Based, Concurrent Subspace
    Optimization for Multidisciplinary System Design," Proceedings References 79 of the 34th AIAA
    Aerospace Sciences Meeting and Exhibit, Reno, NV, January 1996.
"""

import numpy as np

from openmdao.api import Group, ExplicitComponent, ExecComp, IndepVarComp, \
                         NonlinearBlockGS, ScipyIterativeSolver


class SellarDis1(ExplicitComponent):
    """
    Component containing Discipline 1 -- no derivatives version.
    """

    def setup(self):

        # Global Design Variable
        self.add_input('z', val=np.zeros(2))

        # Local Design Variable
        self.add_input('x', val=0.)

        # Coupling parameter
        self.add_input('y2', val=1.0)

        # Coupling output
        self.add_output('y1', val=1.0)

        # Finite difference all partials.
        self.approx_partials('*', '*')

    def compute(self, inputs, outputs):
        """
        Evaluates the equation
        y1 = z1**2 + z2 + x1 - 0.2*y2
        """
        z1 = inputs['z'][0]
        z2 = inputs['z'][1]
        x1 = inputs['x']
        y2 = inputs['y2']

        outputs['y1'] = z1**2 + z2 + x1 - 0.2*y2


class SellarDis2(ExplicitComponent):
    """
    Component containing Discipline 2 -- no derivatives version.
    """

    def setup(self):
        # Global Design Variable
        self.add_input('z', val=np.zeros(2))

        # Coupling parameter
        self.add_input('y1', val=1.0)

        # Coupling output
        self.add_output('y2', val=1.0)

        # Finite difference all partials.
        self.approx_partials('*', '*')

    def compute(self, inputs, outputs):
        """
        Evaluates the equation
        y2 = y1**(.5) + z1 + z2
        """

        z1 = inputs['z'][0]
        z2 = inputs['z'][1]
        y1 = inputs['y1']

        # Note: this may cause some issues. However, y1 is constrained to be
        # above 3.16, so lets just let it converge, and the optimizer will
        # throw it out
        if y1.real < 0.0:
            y1 *= -1

        outputs['y2'] = y1**.5 + z1 + z2


class SellarNoDerivatives(Group):
    """
    Group containing the Sellar MDA. This version uses the disciplines without derivatives.
    """

    def setup(self):
        self.add_subsystem('px', IndepVarComp('x', 1.0), promotes=['x'])
        self.add_subsystem('pz', IndepVarComp('z', np.array([5.0, 2.0])), promotes=['z'])

        cycle = self.add_subsystem('cycle', Group(), promotes=['x', 'z', 'y1', 'y2'])
        d1 = cycle.add_subsystem('d1', SellarDis1(), promotes=['x', 'z', 'y1', 'y2'])
        d2 = cycle.add_subsystem('d2', SellarDis2(), promotes=['z', 'y1', 'y2'])

        self.add_subsystem('obj_cmp', ExecComp('obj = x**2 + z[1] + y1 + exp(-y2)',
                           z=np.array([0.0, 0.0]), x=0.0),
                           promotes=['x', 'z', 'y1', 'y2', 'obj'])

        self.add_subsystem('con_cmp1', ExecComp('con1 = 3.16 - y1'), promotes=['con1', 'y1'])
        self.add_subsystem('con_cmp2', ExecComp('con2 = y2 - 24.0'), promotes=['con2', 'y2'])

        self.nonlinear_solver = NonlinearBlockGS()
        self.linear_solver = ScipyIterativeSolver()


class SellarDis1CS(ExplicitComponent):
    """
    Component containing Discipline 1 -- no derivatives version.
    Uses Complex Step
    """

    def setup(self):

        # Global Design Variable
        self.add_input('z', val=np.zeros(2))

        # Local Design Variable
        self.add_input('x', val=0.)

        # Coupling parameter
        self.add_input('y2', val=1.0)

        # Coupling output
        self.add_output('y1', val=1.0)

        # Finite difference all partials.
        self.approx_partials('*', '*', method='cs')

    def compute(self, inputs, outputs):
        """
        Evaluates the equation
        y1 = z1**2 + z2 + x1 - 0.2*y2
        """
        z1 = inputs['z'][0]
        z2 = inputs['z'][1]
        x1 = inputs['x']
        y2 = inputs['y2']

        outputs['y1'] = z1**2 + z2 + x1 - 0.2*y2


class SellarDis2CS(ExplicitComponent):
    """
    Component containing Discipline 2 -- no derivatives version.
    Uses Complex Step
    """

    def setup(self):
        # Global Design Variable
        self.add_input('z', val=np.zeros(2))

        # Coupling parameter
        self.add_input('y1', val=1.0)

        # Coupling output
        self.add_output('y2', val=1.0)

        # Finite difference all partials.
        self.approx_partials('*', '*', method='cs')

    def compute(self, inputs, outputs):
        """
        Evaluates the equation
        y2 = y1**(.5) + z1 + z2
        """

        z1 = inputs['z'][0]
        z2 = inputs['z'][1]
        y1 = inputs['y1']

        # Note: this may cause some issues. However, y1 is constrained to be
        # above 3.16, so lets just let it converge, and the optimizer will
        # throw it out
        if y1.real < 0.0:
            y1 *= -1

        outputs['y2'] = y1**.5 + z1 + z2


class SellarNoDerivativesCS(Group):
    """
    Group containing the Sellar MDA. This version uses the disciplines without derivatives.
    """

    def setup(self):
        self.add_subsystem('px', IndepVarComp('x', 1.0), promotes=['x'])
        self.add_subsystem('pz', IndepVarComp('z', np.array([5.0, 2.0])), promotes=['z'])

        cycle = self.add_subsystem('cycle', Group(), promotes=['x', 'z', 'y1', 'y2'])
        d1 = cycle.add_subsystem('d1', SellarDis1CS(), promotes=['x', 'z', 'y1', 'y2'])
        d2 = cycle.add_subsystem('d2', SellarDis2CS(), promotes=['z', 'y1', 'y2'])

        self.add_subsystem('obj_cmp', ExecComp('obj = x**2 + z[1] + y1 + exp(-y2)',
                           z=np.array([0.0, 0.0]), x=0.0),
                           promotes=['x', 'z', 'y1', 'y2', 'obj'])

        self.add_subsystem('con_cmp1', ExecComp('con1 = 3.16 - y1'), promotes=['con1', 'y1'])
        self.add_subsystem('con_cmp2', ExecComp('con2 = y2 - 24.0'), promotes=['con2', 'y2'])

        self.nonlinear_solver = NonlinearBlockGS()
        self.linear_solver = ScipyIterativeSolver()