#
# Copyright (c) 2021 The GPflux Contributors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
""" A kernel's features and coefficients using Random Fourier Features (RFF). """

from typing import Mapping, Optional

import numpy as np
import tensorflow as tf

import gpflow
from gpflow.base import DType, TensorType

from gpflux.layers.basis_functions.fourier_features.utils import (
    RFF_SUPPORTED_KERNELS,
    _mapping_concat,
    _mapping_cosine,
    _matern_number,
    _sample_students_t,
)
from gpflux.types import ShapeType


class RandomFourierFeaturesBase(tf.keras.layers.Layer):
    def __init__(self, kernel: gpflow.kernels.Kernel, n_components: int, **kwargs: Mapping):
        """
        :param kernel: kernel to approximate using a set of random features.
        :param output_dim: total number of basis functions used to approximate
            the kernel.
        """
        super().__init__(**kwargs)

        assert isinstance(kernel, RFF_SUPPORTED_KERNELS), "Unsupported Kernel"
        self.kernel = kernel
        self.n_components = n_components  # M: number of Monte Carlo samples
        if kwargs.get("input_dim", None):
            self._input_dim = kwargs["input_dim"]
            self.build(tf.TensorShape([self._input_dim]))
        else:
            self._input_dim = None

    def build(self, input_shape: ShapeType) -> None:
        """
        Creates the variables of the layer.
        See `tf.keras.layers.Layer.build()
        <https://www.tensorflow.org/api_docs/python/tf/keras/layers/Layer#build>`_.
        """
        input_dim = input_shape[-1]
        self._weights_build(input_dim, n_components=self.n_components)
        super().build(input_shape)

    def _weights_build(self, input_dim: int, n_components: int) -> None:
        shape = (n_components, input_dim)
        self.W = self.add_weight(
            name="weights",
            trainable=False,
            shape=shape,
            dtype=self.dtype,
            initializer=self._weights_init,
        )

    def _weights_init(self, shape: TensorType, dtype: Optional[DType] = None) -> TensorType:
        if isinstance(self.kernel, gpflow.kernels.SquaredExponential):
            return tf.random.normal(shape, dtype=dtype)
        else:
            p = _matern_number(self.kernel)
            nu = 2.0 * p + 1.0  # degrees of freedom
            return _sample_students_t(nu, shape, dtype)

    def compute_output_shape(self, input_shape: ShapeType) -> tf.TensorShape:
        """
        Computes the output shape of the layer.
        See `tf.keras.layers.Layer.compute_output_shape()
        <https://www.tensorflow.org/api_docs/python/tf/keras/layers/Layer#compute_output_shape>`_.
        """
        # TODO: Keras docs say "If the layer has not been built, this method
        # will call `build` on the layer." -- do we need to do so?
        tensor_shape = tf.TensorShape(input_shape).with_rank(2)
        output_dim = self.n_components
        return tensor_shape[:-1].concatenate(output_dim)

    def get_config(self) -> Mapping:
        """
        Returns the config of the layer.
        See `tf.keras.layers.Layer.get_config()
        <https://www.tensorflow.org/api_docs/python/tf/keras/layers/Layer#get_config>`_.
        """
        config = super().get_config()
        config.update(
            {"kernel": self.kernel, "n_components": self.n_components, "input_dim": self._input_dim}
        )

        return config


class RandomFourierFeatures(RandomFourierFeaturesBase):
    r"""
    Random Fourier features (RFF) is a method for approximating kernels. The essential
    element of the RFF approach :cite:p:`rahimi2007random` is the realization that Bochner's theorem
    for stationary kernels can be approximated by a Monte Carlo sum.

    We will approximate the kernel :math:`k(\mathbf{x}, \mathbf{x}')`
    by :math:`\Phi(\mathbf{x})^\top \Phi(\mathbf{x}')`
    where :math:`\Phi: \mathbb{R}^{D} \to \mathbb{R}^{M}` is a finite-dimensional feature map.

    The feature map is defined as:

    .. math::

      \Phi(\mathbf{x}) = \sqrt{\frac{2 \sigma^2}{\ell}}
        \begin{bmatrix}
          \cos(\boldsymbol{\theta}_1^\top \mathbf{x}) \\
          \sin(\boldsymbol{\theta}_1^\top \mathbf{x}) \\
          \vdots \\
          \cos(\boldsymbol{\theta}_{\frac{M}{2}}^\top \mathbf{x}) \\
          \sin(\boldsymbol{\theta}_{\frac{M}{2}}^\top \mathbf{x})
        \end{bmatrix}

    where :math:`\sigma^2` is the kernel variance.
    The features are parameterised by random weights:

    - :math:`\boldsymbol{\theta} \sim p(\boldsymbol{\theta})`
      where :math:`p(\boldsymbol{\theta})` is the spectral density of the kernel.

    At least for the squared exponential kernel, this variant of the feature
    mapping has more desirable theoretical properties than its cosine-based
    counterpart :class:`RandomFourierFeaturesCosine` :cite:p:`sutherland2015error`.
    """

    def compute_output_shape(self, input_shape: ShapeType) -> tf.TensorShape:
        """
        Computes the output shape of the layer.
        See `tf.keras.layers.Layer.compute_output_shape()
        <https://www.tensorflow.org/api_docs/python/tf/keras/layers/Layer#compute_output_shape>`_.
        """
        # TODO: Keras docs say "If the layer has not been built, this method
        # will call `build` on the layer." -- do we need to do so?
        tensor_shape = tf.TensorShape(input_shape).with_rank(2)
        output_dim = 2 * self.n_components
        return tensor_shape[:-1].concatenate(output_dim)

    def call(self, inputs: TensorType) -> tf.Tensor:
        """
        Evaluate the basis functions at ``inputs``.

        :param inputs: The evaluation points, a tensor with the shape ``[N, D]``.

        :return: A tensor with the shape ``[N, 2M]``.
        """
        constant = tf.sqrt(2.0 * self.kernel.variance / self.n_components)
        bases = _mapping_concat(inputs, self.W, lengthscales=self.kernel.lengthscales)
        output = constant * bases
        tf.ensure_shape(output, self.compute_output_shape(inputs.shape))
        return output


class RandomFourierFeaturesCosine(RandomFourierFeaturesBase):
    r"""
    Random Fourier Features (RFF) is a method for approximating kernels. The essential
    element of the RFF approach :cite:p:`rahimi2007random` is the realization that Bochner's theorem
    for stationary kernels can be approximated by a Monte Carlo sum.

    We will approximate the kernel :math:`k(\mathbf{x}, \mathbf{x}')`
    by :math:`\Phi(\mathbf{x})^\top \Phi(\mathbf{x}')` where
    :math:`\Phi: \mathbb{R}^{D} \to \mathbb{R}^{M}` is a finite-dimensional feature map.

    The feature map is defined as:

    .. math::
      \Phi(\mathbf{x}) = \sqrt{\frac{2 \sigma^2}{\ell}}
        \begin{bmatrix}
          \cos(\boldsymbol{\theta}_1^\top \mathbf{x} + \tau) \\
          \vdots \\
          \cos(\boldsymbol{\theta}_M^\top \mathbf{x} + \tau)
        \end{bmatrix}

    where :math:`\sigma^2` is the kernel variance.
    The features are parameterised by random weights:

    - :math:`\boldsymbol{\theta} \sim p(\boldsymbol{\theta})`
      where :math:`p(\boldsymbol{\theta})` is the spectral density of the kernel
    - :math:`\tau \sim \mathcal{U}(0, 2\pi)`

    Equivalent to :class:`RandomFourierFeatures` by elementary trignometric identities.
    """

    def build(self, input_shape: ShapeType) -> None:
        """
        Creates the variables of the layer.
        See `tf.keras.layers.Layer.build()
        <https://www.tensorflow.org/api_docs/python/tf/keras/layers/Layer#build>`_.
        """
        input_dim = input_shape[-1]
        self._bias_build(n_components=self.output_dim)
        super().build(input_shape)

    def _bias_build(self, n_components: int) -> None:
        shape = (1, n_components)
        self.b = self.add_weight(
            name="bias",
            trainable=False,
            shape=shape,
            dtype=self.dtype,
            initializer=self._bias_init,
        )

    def _bias_init(self, shape: TensorType, dtype: Optional[DType] = None) -> TensorType:
        return tf.random.uniform(shape=shape, maxval=2.0 * np.pi, dtype=dtype)

    def call(self, inputs: TensorType) -> tf.Tensor:
        """
        Evaluate the basis functions at ``inputs``.

        :param inputs: The evaluation points, a tensor with the shape ``[N, D]``.

        :return: A tensor with the shape ``[N, M]``.
        """
        constant = tf.sqrt(2.0 * self.kernel.variance / self.n_components)
        bases = _mapping_cosine(inputs, self.W, lengthscales=self.kernel.lengthscales)
        output = constant * bases
        tf.ensure_shape(output, self.compute_output_shape(inputs.shape))
        return output
