Sparse Partial Derivatives
==========================

When a partial derivative is sparse (few non-zero entries compared to the total size of the matrix),
it may be advantageous to utilize a format that stores only the non-zero entries. To use sparse
partial derivatives, they must first be declared with the sparsity pattern in
:code:`setup` using the :code:`declare_partials` method.

Usage
-----

1. To specify the sparsity pattern in the AIJ format (alternatively known as COO format), use the :code:`rows` and :code:`cols` arguments
to :code:`declare_partials`. For example, to declare a sparsity pattern of non-zero
entries in the (0, 0), (1, 1), (1, 2), and (1,3) positions, one would use
:code:`rows=[0, 1, 1, 1], cols=[0, 1, 2, 3]`. When using :code:`compute_partials`, you do not
need to pass the sparsity pattern again. Instead, you simply give the values for the entries in the
same order as given in :code:`declare_partials`.

.. embed-test::
    openmdao.jacobians.tests.test_jacobian_features.TestJacobianForDocs.test_sparse_jacobian

2. If only some of your jacobian entries change across iterations or if you wish to avoid creating intermediate arrays, you may update the entries in-place.

.. embed-test::
    openmdao.jacobians.tests.test_jacobian_features.TestJacobianForDocs.test_sparse_jacobian_in_place

3. If your partial derivative is constant and sparse, or if you simply wish to provide an initial value for the derivative, you can pass in the values using the :code:`val` argument. If you are using the AIJ format, :code:`val` should receive the non-zero entries in the same order as given for :code:`rows` and :code:`cols`. Alternatively, you may provide a Scipy sparse matrix, from which the sparsity pattern is deduced.

.. embed-test::
    openmdao.jacobians.tests.test_jacobian_features.TestJacobianForDocs.test_sparse_jacobian_const
