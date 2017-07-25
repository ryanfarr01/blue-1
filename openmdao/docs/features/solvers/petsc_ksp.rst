:orphan:

.. _petscKSP:

Linear Solver: PetscKSP
=======================

The PetscKSP is an iterative linear solver that wraps the linear solution methods found in PETSc via Petsc4py.
The default method is "fgmres", or the Flexible Generalized Minimal RESidual method, though you choose any of
the other methods in PETSc. This linear solver is capable of handling any system topology very
effectively. It also solves all subsystems below it in the hierarchy, so assigning different solvers to
subsystems will have no effect on the solution at this level.

This solver works under MPI, so it is a good alternative to
:ref:`ScipyIterativeSolver <usr_openmdao.solvers.linear.scipy_iter_solver.py>`.
This solver is also re-entrant, so there are no problems if it is nested during preconditioning.

Here, we calculate the total derivatives across the Sellar system.

.. embed-test::
    openmdao.solvers.linear.tests.test_petsc_ksp.TestPetscKSPSolverFeature.test_specify_solver

Options
-------

- maxiter

  This lets you specify the maximum number of GMRES (or other algorithm) iterations to apply. The default maximum is 100, which
  is much higher than the other linear solvers because each multiplication by the system Jacobian is considered
  to be an iteration. You may have to decrease this value if you have a coupled system that is converging
  very slowly. (Of course, in such a case, it may be better to add a preconditioner.)  Alternatively, you
  may have to raise it if you have an extremely large number of components in your system (a 1000-component
  ring would need 1000 iterations just to make it around once.)

  This example shows what happens if you set maxiter too low (the derivatives should be nonzero, but it stops too
  soon.)

  .. embed-test::
      openmdao.solvers.linear.tests.test_petsc_ksp.TestPetscKSPSolverFeature.test_feature_maxiter

- atol

  Here, we set the absolute tolerance to a much tighter value (default is 1.0e-12) to show what happens. In
  practice, the tolerance serves a dual role in GMRES. In addition to being a termination criteria, the tolerance
  also defines what GMRES considers to be tiny. Tiny numbers are replaced by zero when the argument vector is
  normalized at the start of each new matrix-vector product. The end result here is that we iterate longer to get
  a marginally better answer.

  You may need to adjust this setting if you have abnormally large or small values in your global Jacobean.

  .. embed-test::
      openmdao.solvers.linear.tests.test_petsc_ksp.TestPetscKSPSolverFeature.test_feature_atol

- rtol

  Here, we set the absolute tolerance to a much tighter value (default is 1.0e-12) to show what happens. In
  practice, the tolerance serves a dual role in GMRES. In addition to being a termination criteria, the tolerance
  also defines what GMRES considers to be tiny. Tiny numbers are replaced by zero when the argument vector is
  normalized at the start of each new matrix-vector product. The end result here is that we iterate longer to get
  a marginally better answer.

  You may need to adjust this setting if you have abnormally large or small values in your global Jacobean.

  .. embed-test::
      openmdao.solvers.linear.tests.test_petsc_ksp.TestPetscKSPSolverFeature.test_feature_rtol

- ksp_type

  You can specify which PETSc algorithm to use in place of 'fgmres' by settng the "ksp_type" in the options
  dictionary.  Here, we use 'gmres' instead.

  .. embed-test::
      openmdao.solvers.linear.tests.test_petsc_ksp.TestPetscKSPSolverFeature.test_specify_ksp_type

Specifying a Preconditioner
---------------------------

You can specify a preconditioner to improve the convergence of the iterative linear solution by setting the `precon` attribute. The
motivation for using a preconditioner is the observation that iterative methods have better convergence
properties if the linear system has a smaller condition number, so the goal of the preconditioner is to
improve the condition number in part or all of the Jacobian.

Here, we add a Gauss Seidel preconditioner to the simple Sellar solution with Newton. Note that the number of
GMRES iterations is lower when using the preconditioner.

.. embed-test::
    openmdao.solvers.linear.tests.test_petsc_ksp.TestPetscKSPSolverFeature.test_specify_precon

While the default preconditioning "side" is right-preconditioning, you can also use left-preconditioning provided that you choose
a "ksp_type" that supports it. Here we solve the same problem with left-preconditioning using the Richardson method and a `DirectSolver`.

.. embed-test::
    openmdao.solvers.linear.tests.test_petsc_ksp.TestPetscKSPSolverFeature.test_specify_precon_left


.. tags:: Solver, LinearSolver
