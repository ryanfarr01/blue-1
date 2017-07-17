"""Define the base Vector and Transfer classes."""
from __future__ import division, print_function
import numpy as np

from six.moves import range
from six import iteritems

from openmdao.utils.general_utils import ensure_compatible
from openmdao.utils.name_maps import name2abs_name


class VectorInfo(object):
    """
    Communal object for storing some global information in the vectors.

    Attributes
    ----------
    _under_complex_step : bool
        When this is True, the vectors operate with complex numbers.
    """

    def __init__(self):
        """
        Initialize.
        """
        self._under_complex_step = False


class Vector(object):
    """
    Base Vector class.

    This class is instantiated for inputs, outputs, and residuals.
    It provides a dictionary interface and an arithmetic operations interface.
    Implementations:

    - <DefaultVector>
    - <PETScVector>

    Attributes
    ----------
    _name : str
        The name of the vector: 'nonlinear', 'linear', or right-hand side name.
    _typ : str
        Type: 'input' for input vectors; 'output' for output/residual vectors.
    _system : System
        Pointer to the owning system.
    _iproc : int
        Global processor index.
    _views : dict
        Dictionary mapping absolute variable names to the ndarray views.
    _views_flat : dict
        Dictionary mapping absolute variable names to the flattened ndarray views.
    _idxs : dict
        Either 0 or slice(None), used so that 1-sized vectors are made floats.
    _names : set([str, ...])
        Set of variables that are relevant in the current context.
    _root_vector : Vector
        Pointer to the vector owned by the root system.
    _alloc_complex : Bool
        If True, then space for the imaginary part is also allocated.
    _data : {}
        Dict of the actual allocated data (depends on implementation), keyed
        by varset name.
    _indices : list
        List of indices mapping the varset-grouped data to the global vector.
    _vector_info : <VectorInfo>
        Object to store some global info, such as complex step state.
    _imag_views : dict
        Dictionary mapping absolute variable names to the ndarray views for the imaginary part.
    _imag_views_flat : dict
        Dictionary mapping absolute variable names to the flattened ndarray views for the imaginary
        part.
    _imag_data : {}
        Dict of the actual allocated data (depends on implementation) for the imaginary part, keyed
        by varset name.
    _complex_view_cache : {}
        Temporary storage of complex views used by in-place numpy operations.
    """

    _vector_info = VectorInfo()

    def __init__(self, name, typ, system, root_vector=None, resize=False, alloc_complex=False):
        """
        Initialize all attributes.

        Parameters
        ----------
        name : str
            The name of the vector: 'nonlinear', 'linear', or right-hand side name.
        typ : str
            Type: 'input' for input vectors; 'output' for output/residual vectors.
        system : <System>
            Pointer to the owning system.
        root_vector : <Vector>
            Pointer to the vector owned by the root system.
        resize : bool
            If true, resize the root vector.
        alloc_complex : bool
            Whether to allocate any imaginary storage to perform complex step. Default is False.
        """
        self._name = name
        self._typ = typ

        self._system = system

        self._iproc = system.comm.rank
        self._views = {}
        self._views_flat = {}

        # self._names will either be equivalent to self._views or to the
        # set of variables relevant to the current matvec product.
        self._names = self._views

        self._root_vector = None
        self._data = {}
        self._indices = {}

        # Support for Complex Step
        self._imag_data = {}
        self._imag_views = {}
        self._complex_view_cache = {}
        self._imag_views_flat = {}
        self._alloc_complex = alloc_complex

        if root_vector is None:
            self._root_vector = self
        else:
            self._root_vector = root_vector

        if resize:
            if root_vector is None:
                raise RuntimeError(
                    'Cannot resize the vector because the root vector has not yet '
                    + ' been created in system %s' % system.pathname)
            self._update_root_data()

        self._initialize_data(root_vector)
        self._initialize_views()

    def _create_subvector(self, system):
        """
        Return a smaller vector for a subsystem.

        Parameters
        ----------
        system : <System>
            system for the subvector that is a subsystem of self._system.

        Returns
        -------
        <Vector>
            subvector instance.
        """
        return self.__class__(self._name, self._typ, system,
                              self._root_vector)

    def _clone(self, initialize_views=False):
        """
        Return a copy that optionally provides view access to its data.

        Parameters
        ----------
        initialize_views : bool
            Whether to initialize the views into the clone.

        Returns
        -------
        <Vector>
            instance of the clone; the data is copied.
        """
        vec = self.__class__(self._name, self._typ, self._system, self._root_vector,
                             alloc_complex=self._alloc_complex)
        vec._clone_data()
        if initialize_views:
            vec._initialize_views()
        return vec

    def get_data(self, new_array=None):
        """
        Get the array combining the data of all the varsets.

        Parameters
        ----------
        new_array : ndarray or None
            Array to fill in with the values; otherwise new array created.

        Returns
        -------
        ndarray
            Array combining the data of all the varsets.
        """
        if new_array is None:
            total_size = np.sum(self._system._var_sizes[self._typ][self._iproc, :])
            new_array = np.zeros(total_size)

        for set_name, data in iteritems(self._data):
            new_array[self._indices[set_name]] = data

        return new_array

    def set_data(self, array):
        """
        Set the incoming array combining the data of all the varsets.

        Parameters
        ----------
        array : ndarray
            Array to set to the data for all the varsets.
        """
        for set_name, data in iteritems(self._data):
            data[:] = array[self._indices[set_name]]

    def iadd_data(self, array):
        """
        In-place add the incoming combined array.

        Parameters
        ----------
        array : ndarray
            Array to set to the data for all the varsets.
        """
        for set_name, data in iteritems(self._data):
            data += array[self._indices[set_name]]

    def _contains_abs(self, abs_name):
        """
        Check if the variable is involved in the current mat-vec product.

        Parameters
        ----------
        abs_name : str
            Absolute variable name in the owning system's namespace.

        Returns
        -------
        boolean
            True or False.
        """
        return abs_name in self._names

    def __iter__(self):
        """
        Yield an iterator over variables involved in the current mat-vec product (relative names).

        Returns
        -------
        listiterator
            iterator over the variable names.
        """
        system = self._system
        type_ = self._typ
        idx = len(system.pathname) + 1 if system.pathname else 0

        iter_list = []
        for abs_name in system._var_abs_names[type_]:
            if abs_name in self._names:
                rel_name = abs_name[idx:]
                iter_list.append(rel_name)
        return iter(iter_list)

    def __contains__(self, name):
        """
        Check if the variable is involved in the current mat-vec product.

        Parameters
        ----------
        name : str
            Promoted or relative variable name in the owning system's namespace.

        Returns
        -------
        boolean
            True or False.
        """
        abs_name = name2abs_name(self._system, name, self._names, self._typ)
        return abs_name is not None

    def __getitem__(self, name):
        """
        Get the unscaled variable value in true units.

        Parameters
        ----------
        name : str
            Promoted or relative variable name in the owning system's namespace.

        Returns
        -------
        float or ndarray
            variable value (not scaled, not dimensionless).
        """
        abs_name = name2abs_name(self._system, name, self._names, self._typ)
        if abs_name is not None:
            if self._vector_info._under_complex_step:
                if self._typ == 'input':
                    return self._views[abs_name] + 1j * self._imag_views[abs_name]
                else:
                    if abs_name not in self._complex_view_cache:
                        self._complex_view_cache[abs_name] = self._views[abs_name] + \
                            1j * self._imag_views[abs_name]
                    return self._complex_view_cache[abs_name]

            return self._views[abs_name]
        else:
            msg = 'Variable name "{}" not found.'
            raise KeyError(msg.format(name))

    def __setitem__(self, name, value):
        """
        Set the unscaled variable value in true units.

        Parameters
        ----------
        name : str
            Promoted or relative variable name in the owning system's namespace.
        value : float or list or tuple or ndarray
            variable value to set (not scaled, not dimensionless)
        """
        abs_name = name2abs_name(self._system, name, self._names, self._typ)
        if abs_name is not None:
            value, shape = ensure_compatible(name, value, self._views[abs_name].shape)
            if self._vector_info._under_complex_step:

                # setitem overwrites anything you may have done with numpy indexing
                try:
                    del self._complex_view_cache[abs_name]
                except KeyError:
                    pass

                self._views[abs_name][:] = value.real
                self._imag_views[abs_name][:] = value.imag
            else:
                self._views[abs_name][:] = value
        else:
            msg = 'Variable name "{}" not found.'
            raise KeyError(msg.format(name))

    def _initialize_data(self, root_vector):
        """
        Internally allocate vectors.

        Must be implemented by the subclass.

        Sets the following attributes:

        - _data

        Parameters
        ----------
        root_vector : <Vector> or None
            the root's vector instance or None, if we are at the root.
        """
        pass

    def _initialize_views(self):
        """
        Internally assemble views onto the vectors.

        Must be implemented by the subclass.

        Sets the following attributes:

        - _views
        - _views_flat
        - _idxs

        """
        pass

    def _clone_data(self):
        """
        For each item in _data, replace it with a copy of the data.

        Must be implemented by the subclass.
        """
        pass

    def __iadd__(self, vec):
        """
        Perform in-place vector addition.

        Must be implemented by the subclass.

        Parameters
        ----------
        vec : <Vector>
            vector to add to self.
        """
        pass

    def __isub__(self, vec):
        """
        Perform in-place vector substraction.

        Must be implemented by the subclass.

        Parameters
        ----------
        vec : <Vector>
            vector to subtract from self.
        """
        pass

    def __imul__(self, val):
        """
        Perform in-place scalar multiplication.

        Must be implemented by the subclass.

        Parameters
        ----------
        val : int or float
            scalar to multiply self.
        """
        pass

    def add_scal_vec(self, val, vec):
        """
        Perform in-place addition of a vector times a scalar.

        Must be implemented by the subclass.

        Parameters
        ----------
        val : int or float
            scalar.
        vec : <Vector>
            this vector times val is added to self.
        """
        pass

    def set_vec(self, vec):
        """
        Set the value of this vector to that of the incoming vector.

        Must be implemented by the subclass.

        Parameters
        ----------
        vec : <Vector>
            the vector whose values self is set to.
        """
        pass

    def set_const(self, val):
        """
        Set the value of this vector to a constant scalar value.

        Must be implemented by the subclass.

        Parameters
        ----------
        val : int or float
            scalar to set self to.
        """
        pass

    def get_norm(self):
        """
        Return the norm of this vector.

        Must be implemented by the subclass.

        Returns
        -------
        float
            norm of this vector.
        """
        pass

    def change_scaling_state(self, c0, c1):
        """
        Change the scaling state.

        Parameters
        ----------
        c0 : int ndarray[nvar_myproc]
            0th order coefficients for scaling/unscaling.
        c1 : int ndarray[nvar_myproc]
            1st order coefficients for scaling/unscaling.
        """
        pass

    def _enforce_bounds_vector(self, du, alpha, lower_bounds, upper_bounds):
        """
        Enforce lower/upper bounds, backtracking the entire vector together.

        This method modifies both self (u) and step (du) in-place.

        Parameters
        ----------
        du : <Vector>
            Newton step; the backtracking is applied to this vector in-place.
        alpha : float
            step size.
        lower_bounds : <Vector>
            Lower bounds vector.
        upper_bounds : <Vector>
            Upper bounds vector.
        """
        pass

    def _enforce_bounds_scalar(self, du, alpha, lower_bounds, upper_bounds):
        """
        Enforce lower/upper bounds on each scalar separately, then backtrack as a vector.

        This method modifies both self (u) and step (du) in-place.

        Parameters
        ----------
        du : <Vector>
            Newton step; the backtracking is applied to this vector in-place.
        alpha : float
            step size.
        lower_bounds : <Vector>
            Lower bounds vector.
        upper_bounds : <Vector>
            Upper bounds vector.
        """
        pass

    def _enforce_bounds_wall(self, du, alpha, lower_bounds, upper_bounds):
        """
        Enforce lower/upper bounds on each scalar separately, then backtrack along the wall.

        This method modifies both self (u) and step (du) in-place.

        Parameters
        ----------
        du : <Vector>
            Newton step; the backtracking is applied to this vector in-place.
        alpha : float
            step size.
        lower_bounds : <Vector>
            Lower bounds vector.
        upper_bounds : <Vector>
            Upper bounds vector.
        """
        pass

    def _remove_complex_views(self):
        """
        Remove temporary complex view and migrate its values into real and imaginary views.
        """
        for abs_name, value in iteritems(self._complex_view_cache):
            self._views[abs_name][:] = value.real
            self._imag_views[abs_name][:] = value.imag
        self._complex_view_cache = {}

    def print_variables(self):
        """
        Print the names and values of all variables in this vector, one per line.
        """
        abs2prom = self._system._var_abs2prom[self._typ]
        print('-' * 35)
        print('   Vector %s, type %s' % (self._name, self._typ))
        for abs_name, view in iteritems(self._views):
            prom_name = abs2prom[abs_name]
            print(' ' * 3, prom_name, view)
        print('-' * 35)
        print()


class Transfer(object):
    """
    Base Transfer class.

    Implementations:

    - <DefaultTransfer>
    - <PETScTransfer>

    Attributes
    ----------
    _in_vec : Vector
        pointer to the input vector.
    _out_vec : Vector
        pointer to the output vector.
    _in_inds : int ndarray
        input indices for the transfer.
    _out_inds : int ndarray
        output indices for the transfer.
    _comm : MPI.Comm or FakeComm
        communicator of the system that owns this transfer.
    """

    def __init__(self, in_vec, out_vec, in_inds, out_inds, comm):
        """
        Initialize all attributes.

        Parameters
        ----------
        in_vec : <Vector>
            pointer to the input vector.
        out_vec : <Vector>
            pointer to the output vector.
        in_inds : int ndarray
            input indices for the transfer.
        out_inds : int ndarray
            output indices for the transfer.
        comm : MPI.Comm or <FakeComm>
            communicator of the system that owns this transfer.
        """
        self._in_vec = in_vec
        self._out_vec = out_vec
        self._in_inds = in_inds
        self._out_inds = out_inds
        self._comm = comm

        self._initialize_transfer()

    def _initialize_transfer(self):
        """
        Set up the transfer; do any necessary pre-computation.

        Optionally implemented by the subclass.
        """
        pass

    def __call__(self, in_vec, out_vec, mode='fwd'):
        """
        Perform transfer.

        Must be implemented by the subclass.

        Parameters
        ----------
        in_vec : <Vector>
            pointer to the input vector.
        out_vec : <Vector>
            pointer to the output vector.
        mode : str
            'fwd' or 'rev'.
        """
        pass
