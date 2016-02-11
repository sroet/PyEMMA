# This file is part of PyEMMA.
#
# Copyright (c) 2015, 2014 Computational Molecular Biology Group, Freie Universitaet Berlin (GER)
#
# PyEMMA is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''
Created on 19.01.2015

@author: marscher
'''

from __future__ import absolute_import

from math import ceil, log

from pyemma._base.model import Model
from pyemma.util.annotators import doc_inherit, deprecated
from pyemma.util.linalg import eig_corr
from pyemma.util.reflection import get_default_args

import numpy as np
from pyemma.coordinates.estimators.covar.running_moments import running_covar

from .transformer import StreamingTransformer

__all__ = ['TICA']


class TICAModel(Model):
    pass


class TICA(StreamingTransformer):
    r""" Time-lagged independent component analysis (TICA)"""

    def __init__(self, lag, dim=-1, var_cutoff=0.95, kinetic_map=True, epsilon=1e-6,
                 mean=None, stride=1):
        r""" Time-lagged independent component analysis (TICA) [1]_, [2]_, [3]_.

        Parameters
        ----------
        lag : int
            lag time
        dim : int, optional, default -1
            Maximum number of significant independent components to use to reduce dimension of input data. -1 means
            all numerically available dimensions (see epsilon) will be used unless reduced by var_cutoff.
            Setting dim to a positive value is exclusive with var_cutoff.
        var_cutoff : float in the range [0,1], optional, default 0.95
            Determines the number of output dimensions by including dimensions until their cumulative kinetic variance
            exceeds the fraction subspace_variance. var_cutoff=1.0 means all numerically available dimensions
            (see epsilon) will be used, unless set by dim. Setting var_cutoff smaller than 1.0 is exclusive with dim
        kinetic_map : bool, optional, default True
            Eigenvectors will be scaled by eigenvalues. As a result, Euclidean distances in the transformed data
            approximate kinetic distances [4]_. This is a good choice when the data is further processed by clustering.
        epsilon : float
            eigenvalue norm cutoff. Eigenvalues of C0 with norms <= epsilon will be
            cut off. The remaining number of eigenvalues define the size
            of the output.
        mean : ndarray, optional, default None
            Optionally pass pre-calculated means to avoid their re-computation.
            The shape has to match the input dimension.

        Notes
        -----
        Given a sequence of multivariate data :math:`X_t`, computes the mean-free
        covariance and time-lagged covariance matrix:

        .. math::

            C_0 &=      (X_t - \mu)^T (X_t - \mu) \\
            C_{\tau} &= (X_t - \mu)^T (X_{t + \tau} - \mu)

        and solves the eigenvalue problem

        .. math:: C_{\tau} r_i = C_0 \lambda_i(tau) r_i,

        where :math:`r_i` are the independent components and :math:`\lambda_i(tau)` are
        their respective normalized time-autocorrelations. The eigenvalues are
        related to the relaxation timescale by

        .. math:: t_i(tau) = -\tau / \ln |\lambda_i|.

        When used as a dimension reduction method, the input data is projected
        onto the dominant independent components.

        References
        ----------
        .. [1] Perez-Hernandez G, F Paul, T Giorgino, G De Fabritiis and F Noe. 2013.
           Identification of slow molecular order parameters for Markov model construction
           J. Chem. Phys. 139, 015102. doi:10.1063/1.4811489
        .. [2] Schwantes C, V S Pande. 2013.
           Improvements in Markov State Model Construction Reveal Many Non-Native Interactions in the Folding of NTL9
           J. Chem. Theory. Comput. 9, 2000-2009. doi:10.1021/ct300878a
        .. [3] L. Molgedey and H. G. Schuster. 1994.
           Separation of a mixture of independent signals using time delayed correlations
           Phys. Rev. Lett. 72, 3634.
        .. [4] Noe, F. and C. Clementi. 2015.
            Kinetic distance and kinetic maps from molecular dynamics simulation
            http://arxiv.org/abs/1506.06259

        """
        default_var_cutoff = get_default_args(self.__init__)['var_cutoff']
        if dim != -1 and var_cutoff != default_var_cutoff:
            raise ValueError('Trying to set both the number of dimension and the subspace variance. Use either or.')

        super(TICA, self).__init__()

        if dim > -1:
            var_cutoff = 1.0

        # empty dummy model instance
        self._model = TICAModel()
        self.set_params(lag=lag, dim=dim, var_cutoff=var_cutoff, kinetic_map=kinetic_map,
                        epsilon=epsilon, mean=mean, stride=stride)

        # skipped trajectories
        self._skipped_trajs = []

    @property
    def lag(self):
        """ lag time of correlation matrix :math:`C_{\tau}` """
        return self._lag

    @lag.setter
    def lag(self, new_tau):
        self._lag = new_tau

    @doc_inherit
    def describe(self):
        dim = self.dim
        try:
            dim = self.dimension()
        except:
            pass
        return "[TICA, lag = %i; max. output dim. = %i]" % (self._lag, dim)

    def dimension(self):
        """ output dimension """
        if self.dim > -1:
            return self.dim
        d = None
        if self.dim != -1 and not self._estimated:  # fixed parametrization
            d = self.dim
        elif self._estimated:  # parametrization finished. Dimension is known
            dim = len(self.eigenvalues)
            if self.var_cutoff < 1.0:  # if subspace_variance, reduce the output dimension if needed
                dim = min(dim, np.searchsorted(self.cumvar, self.var_cutoff) + 1)
            d = dim
        elif self.var_cutoff == 1.0:  # We only know that all dimensions are wanted, so return input dim
            d = self.data_producer.dimension()
        else:  # We know nothing. Give up
            raise RuntimeError('Requested dimension, but the dimension depends on the cumulative variance and the '
                               'transformer has not yet been estimated. Call estimate() before.')
        return d

    @property
    def mean(self):
        """ mean of input features """
        return self._model.mean

    @property
    @deprecated('please use the "mean" property')
    def mu(self):
        return self.mean

    @mean.setter
    def mean(self, value):
        self._model.mean = value

    @property
    def cov(self):
        return self._model.cov

    @cov.setter
    def cov(self, value):
        self._model.cov = value

    @property
    def cov_tau(self):
        return self._model.cov_tau

    @cov_tau.setter
    def cov_tau(self, value):
        self._model.cov_tau = value

    @cov.setter
    def cov(self, value):
        self._model.cov = value

    def _estimate(self, iterable, **kw):
        r"""
        Chunk-based parameterization of TICA. Iterates over all data and estimates
        the mean, covariance and time lagged covariance. Finally, the
        generalized eigenvalue problem is solved to determine
        the independent components.
        """
        indim = iterable.dimension()
        assert indim > 0, "zero dimension from data source!"
        assert self.dim <= indim, ("requested more output dimensions (%i) than dimension"
                                   " of input data (%i)" % (self.dim, indim))

        self._logger.debug("Running TICA with tau=%i; Estimating two covariance matrices"
                           " with dimension (%i, %i)" % (self._lag, indim, indim))
        if not any(iterable.trajectory_lengths(self.stride) > self.lag):
            raise ValueError("None single dataset [longest=%i] is longer than"
                             " lag time [%i]." % (max(iterable.trajectory_lengths(self.stride)), self.lag))

        self._skipped_trajs = np.fromiter((i for i in range(self._ntraj) if
                                           iterable.trajectory_length(i) < self.lag),
                                          dtype=int)
        with iterable.iterator(lag=self.lag, return_trajindex=False) as it:
            # register progress
            n_chunks = it._n_chunks
            self._progress_register(n_chunks, "calculate mean+cov", 0)
            nsave = int(max(log(ceil(n_chunks), 2), 2))
            self._logger.debug("using %s moments for %i chunks" % (nsave, n_chunks))
            covar = running_covar(xx=True, xy=True, yy=False,
                                  remove_mean=True, symmetrize=True, nsave=nsave)

            for X, Y in it:
                covar.add(X, Y)
                # counting chunks and log of eta
                self._progress_update(1, stage=0)

        cov, cov_tau = covar.cov_XX(), covar.cov_XY()

        # diagonalize with low rank approximation
        self._logger.debug("diagonalize Cov and Cov_tau.")
        eigenvalues, eigenvectors = \
            eig_corr(cov, cov_tau, self.epsilon)
        self._logger.debug("finished diagonalisation.")

        # compute cumulative variance
        cumvar = np.cumsum(eigenvalues ** 2)
        cumvar /= cumvar[-1]

        if len(self._skipped_trajs) >= 1:
            self._skipped_trajs = self._skipped_trajs
            self._logger.warning("Had to skip %u trajectories for being too short. "
                                 "Their indexes are in self._skipped_trajs."
                                 % len(self._skipped_trajs))

        self._model.update_model_params(mean=covar.mean_X(),
                                        cov=cov,
                                        cov_tau=cov_tau,
                                        cumvar=cumvar,
                                        eigenvalues=eigenvalues,
                                        eigenvectors=eigenvectors)
        return self._model

    def _transform_array(self, X):
        r"""Projects the data onto the dominant independent components.

        Parameters
        ----------
        X : ndarray(n, m)
            the input data

        Returns
        -------
        Y : ndarray(n,)
            the projected data
        """
        X_meanfree = X - self.mean
        Y = np.dot(X_meanfree, self.eigenvectors[:, 0:self.dimension()])
        if self.kinetic_map:  # scale by eigenvalues
            Y *= self.eigenvalues[0:self.dimension()]
        return Y

    @property
    def feature_TIC_correlation(self):
        r"""Instantaneous correlation matrix between input features and TICs

        Denoting the input features as :math:`X_i` and the TICs as :math:`\theta_j`, the instantaneous, linear correlation
        between them can be written as

        .. math::

            \mathbf{Corr}(X_i, \mathbf{\theta}_j) = \frac{1}{\sigma_{X_i}}\sum_l \sigma_{X_iX_l} \mathbf{U}_{li}

        The matrix :math:`\mathbf{U}` is the matrix containing, as column vectors, the eigenvectors of the TICA
        generalized eigenvalue problem .

        Returns
        -------
        feature_TIC_correlation : ndarray(n,m)
            correlation matrix between input features and TICs. There is a row for each feature and a column
            for each TIC.
        """
        feature_sigma = np.sqrt(np.diag(self.cov))
        return np.dot(self.cov, self.eigenvectors[:, : self.dimension()]) / feature_sigma[:, np.newaxis]

    @property
    def timescales(self):
        r"""Implied timescales of the TICA transformation

        For each :math:`i`-th eigenvalue, this returns

        .. math::

            t_i = -\frac{\tau}{\log(|\lambda_i|)}

        where :math:`\tau` is the :py:obj:`lag` of the TICA object and :math:`\lambda_i` is the `i`-th
        :py:obj:`eigenvalue <eigenvalues>` of the TICA object.

        Returns
        -------
        timescales: 1D np.array
            numpy array with the implied timescales. In principle, one should expect as many timescales as
            input coordinates were available. However, less eigenvalues will be returned if the TICA matrices
            were not full rank or :py:obj:`var_cutoff` was parsed
        """
        if self._estimated:
            return -self.lag / np.log(np.abs(self.eigenvalues))
        else:
            self._logger.info("TICA not yet parametrized")

    @property
    def eigenvalues(self):
        r"""Eigenvalues of the TICA problem (usually denoted :math:`\lambda`

        Returns
        -------
        eigenvalues: 1D np.array
        """
        return self._model.eigenvalues

    @property
    def eigenvectors(self):
        r"""Eigenvectors of the TICA problem, columnwise

        Returns
        -------
        eigenvectors: (N,M) ndarray
        """
        return self._model.eigenvectors

    @property
    def cumvar(self):
        r"""Cumulative sum of the the TICA eigenvalues

        Returns
        -------
        cumvar: 1D np.array
        """
        return self._model.cumvar
