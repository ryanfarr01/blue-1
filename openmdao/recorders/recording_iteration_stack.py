"""Management of iteration stack for recording."""

recording_iteration_stack = []


def print_recording_iteration_stack():
    """
    Print the record iteration stack.

    Used for debugging.
    """
    print()
    for name, iter_count in reversed(recording_iteration_stack):
        print('^^^', name, iter_count)
    print(60 * '^')


def get_formatted_iteration_coordinate():
    """
    Format the iteration coordinate into human-readable form.

    'rank0:pyoptsparsedriver|6|root._solve_nonlinear|6|mda._solve_nonlinear|6|mda.d1._solve_nonlinear|45'
    """
    separator = '|'
    iteration_coord_list = []

    for name, iter_count in recording_iteration_stack:
        iteration_coord_list.append('{}{}{}'.format(name, separator, iter_count))

    rank = 0  # TODO_PARALLEL needs to be updated when we go parallel
    formatted_iteration_coordinate = ':'.join(["rank%d" % rank,
                                               separator.join(iteration_coord_list)])
    return formatted_iteration_coordinate


class Recording(object):
    """
    A class that acts as a context manager.

    But with properly-timed values for abs and rel,
    where solvers are concerned.
    """

    def __init__(self, name, iter_count, object_requesting_recording):
        """
        Initialize Recording.

        Parameters
        ----------
        name : str
            Name of object getting recorded.
        iter_count : int
            Current counter of iterations completed.
        object_requesting_recording : object
            The object that wants to be recorded.

        Attributes
        ----------
        name : str
            Name of object getting recorded.
        iter_count : int
            Current counter of iterations completed.
        object_requesting_recording : object
            The object that wants to be recorded.
        abs : float
            Absolute error.
        rel : float
            Relative error.
        method : str
            Current method.
        _is_solver : bool
            True if object_requesting_recording is a Solver.
        """
        self.name = name
        self.iter_count = iter_count
        self.object_requesting_recording = object_requesting_recording
        self.abs = 0
        self.rel = 0
        self.method = ''

        from openmdao.solvers.solver import Solver
        self._is_solver = isinstance(self.object_requesting_recording, Solver)

    def __enter__(self):
        """
        Do things before the code inside the 'with Recording' block.
        """
        recording_iteration_stack.append((self.name, self.iter_count))
        return self

    def __exit__(self, *args):
        """
        Do things after the code inside the 'with Recording' block.
        """
        # Determine if recording is justified.
        do_recording = True
        for stack_item in recording_iteration_stack:
            if stack_item[0] in ('_iter_get_norm', '_compute_total_derivs'):
                do_recording = False
                break

        if do_recording:
            if self._is_solver:
                self.object_requesting_recording.record_iteration(abs=self.abs, rel=self.rel)
            else:
                self.object_requesting_recording.record_iteration()

        # Enable the following line for stack debugging.
        # print_recording_iteration_stack()

        recording_iteration_stack.pop()
