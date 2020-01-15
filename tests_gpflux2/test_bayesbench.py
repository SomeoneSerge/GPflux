import os
import numpy as np
import importlib.util
import pytest

def import_module_from_path(path, module_name):
    if os.path.isdir(path):
        path = os.path.join(path, f"{module_name}.py")
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def this_dir():
    return os.path.dirname(__file__)

@pytest.fixture
def bayesbench_deepgp():
    path = os.path.join(this_dir(), '../experiments/bayesian_benchmarks')
    return import_module_from_path(path, 'bayesbench_deepgp')

def get_snelson_X_and_Y():
    data = np.load(os.path.join(this_dir(), 'snelson1d.npz'))
    return data['X'], data['Y']

def test_bayesbench_deepgp_snelson(bayesbench_deepgp):
    X, Y = get_snelson_X_and_Y()
    bench = bayesbench_deepgp.BayesBench_DeepGP()
    bench.Config.MAXITER = 3000
    bench.fit(X, Y)
    elbo = bench.log_pdf(X, Y)
    expected_elbo = - 55.9003  # from log marginal likelihood of GPR with SquaredExponential kernel
    assert np.allclose(elbo, expected_elbo, rtol=0.001)
