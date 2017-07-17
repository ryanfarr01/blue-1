"""Define the LinearRunOnce class."""
from openmdao.solvers.linear.linear_block_gs import LinearBlockGS
from openmdao.recorders.recording_iteration_stack import Recording


class LinearRunOnce(LinearBlockGS):
    """
    Simple linear solver that performs a single iteration of Guass-Seidel.

    This is done without iteration or norm calculation.
    """

    SOLVER = 'LN: RUNONCE'

    def solve(self, vec_names, mode):
        """
        Run the solver.

        Parameters
        ----------
        vec_names : [str, ...]
            List of names of the right-hand-side vectors.
        mode : str
            'fwd' or 'rev'.

        Returns
        -------
        float
            Initial error.
        float
            Error at the first iteration.
        """
        self._vec_names = vec_names
        self._mode = mode
        system = self._system

        # Pre-processing
        self._rhs_vecs = {}
        if self._mode == 'fwd':
            b_vecs = system._vectors['residual']
        else:  # rev
            b_vecs = system._vectors['output']

        for vec_name in self._vec_names:
            self._rhs_vecs[vec_name] = b_vecs[vec_name]._clone()

        with Recording('LinearRunOnce', 0, self) as rec:
            # Single iteration of GS
            self._iter_execute()

            rec.abs = 0.0
            rec.rel = 0.0

        return False, 0.0, 0.0
