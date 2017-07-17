"""
Define the NonLinearRunOnce class.

This is a simple nonlinear solver that just runs the system once.
"""
from openmdao.solvers.solver import NonlinearSolver
from openmdao.recorders.recording_iteration_stack import Recording


class NonLinearRunOnce(NonlinearSolver):
    """
    Simple solver that runs the containing system once.

    This is done without iteration or norm calculation.
    """

    SOLVER = 'NL: RUNONCE'

    def solve(self):
        """
        Run the solver.

        Returns
        -------
        boolean
            Failure flag; True if failed to converge, False is successful.
        float
            absolute error.
        float
            relative error.
        """
        system = self._system

        with Recording('NLRunOnce', 0, self) as rec:
            # If this is a parallel group, transfer all at once then run each subsystem.
            if len(system._subsystems_myproc) != len(system._subsystems_allprocs):
                system._transfer('nonlinear', 'fwd')
                for subsys in system._subsystems_myproc:
                    subsys._solve_nonlinear()
                system._check_reconf_update()
            # If this is not a parallel group, transfer for each subsystem just prior to running it.
            else:
                for isub, subsys in enumerate(system._subsystems_myproc):
                    system._transfer('nonlinear', 'fwd', isub)
                    subsys._solve_nonlinear()
                    system._check_reconf_update()
            rec.abs = 0.0
            rec.rel = 0.0

        return False, 0.0, 0.0
