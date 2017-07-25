:orphan:

.. _lsbacktracking:

Line Search and Backtracking
============================

Backtracking line searches are subsolvers that can be specified in the `line_search` attribute
of a NewtonSolver and are used to pull back to a reasonable point when a Newton step goes to far. This
can occur when a step causes output variables to exceed their specified lower and upper bounds. It can
also happen in more complicated problems where a full Newton step happens to take you well past the nonlinear solution,
even to an area where the residual norm is worse than the initial point. Specifying a line_search can
help alleviate these problems and improve robustness of your Newton solve.

There are two different backtracking line-search algorithms in OpenMDAO:

BoundsEnforceLS
  Only checks bounds and backtracks to point that satisfies them.

ArmijoGoldsteinLS
  Checks bounds and backtracks to point that satisfies them. From there, further backtracking is performed until the termination criteria are satisfied.
  The main termination criteria is the Amijo-Goldstein condition, which checks for a sufficient decrease from the initial point by measuring the
  slope. There is also an iteration maximum.

The following examples use a Newton solver on a component `ImplCompTwoStates` with an implicit output
'z' that has an upper bound of 2.5 and a lower bound of 1.5. This example shows how to specify a line search
(which in this case is the `AmijoGoldsteinLS`.):

.. embed-test::
    openmdao.solvers.linesearch.tests.test_backtracking.TestFeatureLineSearch.test_feature_boundscheck_basic

Bound Enforcement
-----------------

All of the backtracking subsolvers include the `bound_enforcement` option in the options dictionary. This option has a dual role:

1. Behavior of the the non-bounded variables when the bounded ones are capped.
2. Direction of the further backtracking.

There are three difference bounds enforcement schemes available in this option.

With "vector" bounds enforcement, the solution in the output vector is pulled back to a point where none of the
variables violate any upper or lower bounds. Further backtracking continues along this vector back towards the
initial point.

.. image:: BT1.jpg

With "scalar" bounds enforcement, only the variables that violate their bounds are pulled back to feasible values; the
remaining values are kept at the Newton-stepped point. This changes the direction of the backtracking vector so that
it still moves in the direction of the initial point.

.. image:: BT2.jpg

With "wall" bounds enforcement, only the variables that violate their bounds are pulled back to feasible values; the
remaining values are kept at the Newton-stepped point. Further backtracking only occurs in the direction of the non-violating
variables, so that it will move along the wall.

Note: when using the `BoundsEnforceLS` line search, the `scalar` and `wall` methods are exactly the same because no further
backtracking is performed.

.. image:: BT3.jpg

Here are a few examples of this option:

- bound_enforcement: vector

  The `bound_enforcement` option in the options dictionary is used to specify how the output bounds
  are enforced. When this is set to "vector", the output vector is rolled back along the computed gradient until
  it reaches a point where the earliest bound violation occurred. The backtracking continues along the original
  computed gradient.

.. embed-test::
    openmdao.solvers.linesearch.tests.test_backtracking.TestFeatureLineSearch.test_feature_boundscheck_vector

- bound_enforcement: scalar

  The `bound_enforcement` option in the options dictionary is used to specify how the output bounds
  are enforced. When this is set to "scaler", then the only indices in the output vector that are rolled back
  are the ones that violate their upper or lower bounds. The backtracking continues along the modified gradient.

.. embed-test::
    openmdao.solvers.linesearch.tests.test_backtracking.TestFeatureLineSearch.test_feature_boundscheck_scalar

- bound_enforcement: wall

  The `bound_enforcement` option in the options dictionary is used to specify how the output bounds
  are enforced. When this is set to "wall", then the only indices in the output vector that are rolled back
  are the ones that violate their upper or lower bounds. The backtracking continues along a modified gradient
  direction that follows the boundary of the violated output bounds.

.. embed-test::
    openmdao.solvers.linesearch.tests.test_backtracking.TestFeatureLineSearch.test_feature_boundscheck_wall

Control Options
---------------

- maxiter

  The "maxiter" option is a termination criteria that specifies the maximum number of backtracking steps to allow.

- alpha

  The "alpha" option is used to specify the initial length of the Newton step. Since NewtonSolver assumes a
  stepsize of 1.0, this value usually shouldn't be changed.

- rho

  The "rho" option controls how far to backtrack in each successive backtracking step. It is applied as a multiplier to
  the step, so a higher value (approaching 1.0) is a very small step, while a low value takes you close to the initial
  point. The default value is 0.5.

- c

  In the `ArmijoGoldsteinLS`, the "c" option is a multiplier on the slope check. Setting it to a smaller value means a more
  gentle slope will satisfy the condition and terminate.

- print_bound_enforce

  When the "print_bound_enforce" option is set to True, the linesearch will print the name and values of any variables
  that exceeded their lower or upper bounds and were drawn back during bounds enforcement.

.. embed-test::
    openmdao.solvers.linesearch.tests.test_backtracking.TestFeatureLineSearch.test_feature_print_bound_enforce

.. tags:: linesearch, backtracking
