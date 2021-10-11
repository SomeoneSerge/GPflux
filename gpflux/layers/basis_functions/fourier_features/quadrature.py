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
""" A kernel's features and coefficients using quadrature Fourier features (QFF). """

from typing import Mapping

import tensorflow as tf

import gpflow
from gpflow.base import TensorType
from gpflow.quadrature.gauss_hermite import ndgh_points_and_weights

from gpflux.layers.basis_functions.fourier_features.base import FourierFeaturesBase
from gpflux.layers.basis_functions.fourier_features.utils import (
    QFF_SUPPORTED_KERNELS,
    _bases_concat,
)
from gpflux.types import ShapeType


class QuadratureFourierFeatures(FourierFeaturesBase):
    def __init__(self, kernel: gpflow.kernels.Kernel, n_components: int, **kwargs: Mapping):
        assert isinstance(kernel, QFF_SUPPORTED_KERNELS), "Unsupported Kernel"
        super(QuadratureFourierFeatures, self).__init__(kernel, n_components, **kwargs)

    def build(self, input_shape: ShapeType) -> None:
        """
        Creates the variables of the layer.
        See `tf.keras.layers.Layer.build()
        <https://www.tensorflow.org/api_docs/python/tf/keras/layers/Layer#build>`_.
        """
        input_dim = input_shape[-1]
        abscissa_value, weights_value = ndgh_points_and_weights(
            dim=input_dim, n_gh=self.n_components
        )

        # Quadrature node points
        self.abscissa = tf.Variable(initial_value=abscissa_value, trainable=False)
        # Gauss-Hermite weights (not to be confused with random Fourier feature
        # weights or NN weights)
        self.weights = tf.Variable(initial_value=weights_value, trainable=False)
        super().build(input_shape)

    def _compute_output_dim(self, input_shape: ShapeType) -> int:
        input_dim = input_shape[-1]
        return 2 * self.n_components ** input_dim

    def _compute_constant(self) -> tf.Tensor:
        return tf.tile(tf.sqrt(self.kernel.variance * self.weights), multiples=[2])

    def _compute_bases(self, inputs: TensorType) -> tf.Tensor:
        return _bases_concat(inputs, self.abscissa, lengthscales=self.kernel.lengthscales)
