"""H-01: model and scaler files must not be able to run code when loaded."""
import io
import os
import pickle
import zipfile

import joblib
import numpy as np
import pytest
from sklearn.preprocessing import MinMaxScaler

from conftest import MODELS_DIR
from cortex.app.engine.artifacts import ArtifactError, load_inference_model, load_scaler
from cortex.app.engine.model import WINDOW_SIZE


class _Payload:
    def __init__(self, marker):
        self.marker = marker

    def __reduce__(self):
        return (os.system, (f"echo ran >> {self.marker}",))


def _fitted():
    return MinMaxScaler(feature_range=(0, 1)).fit(np.array([[-0.01], [0.02]]))


@pytest.mark.parametrize("code", ["GBP", "CHF"])
def test_shipped_scalers_load_exactly_as_joblib(code):
    path = MODELS_DIR / f"EUR_{code}_scaler.joblib"
    ours, reference = load_scaler(str(path)), joblib.load(path)
    assert sorted(vars(ours)) == sorted(vars(reference))
    for name, value in vars(reference).items():
        if isinstance(value, np.ndarray):
            assert np.array_equal(vars(ours)[name], value) and vars(ours)[name].dtype == value.dtype
        else:
            assert vars(ours)[name] == value
    sample = np.array([[0.0012], [-0.0031]])
    assert np.array_equal(ours.transform(sample), reference.transform(sample))


def test_payload_in_object_state_is_refused(tmp_path):
    marker = tmp_path / "ran"
    scaler = _fitted()
    scaler.__dict__["note"] = _Payload(marker)
    path = tmp_path / "evil.joblib"
    joblib.dump(scaler, path)
    with pytest.raises(ArtifactError, match="Refusing to load"):
        load_scaler(str(path))
    assert not marker.exists()


def test_payload_hidden_in_object_array_is_refused(tmp_path):
    # joblib reads object arrays with the unrestricted pickle module, so a
    # loader that only restricted class names would still run this one.
    marker = tmp_path / "ran"
    scaler = _fitted()
    scaler.scale_ = np.array([_Payload(marker)], dtype=object)
    path = tmp_path / "evil.joblib"
    joblib.dump(scaler, path)
    with pytest.raises(ArtifactError):
        load_scaler(str(path))
    assert not marker.exists()


def test_state_on_a_class_is_refused(tmp_path):
    # BUILD applied to the MinMaxScaler class itself would change it for the
    # whole process; only instances may receive state.
    stream = (
        b"\x80\x04"
        + b"\x8c\x1bsklearn.preprocessing._data\x94\x8c\x0cMinMaxScaler\x94\x93\x94"
        + b"}\x94\x8c\ttransform\x94K\x01sb."
    )
    path = tmp_path / "class-state.joblib"
    path.write_bytes(stream)
    with pytest.raises(ArtifactError, match="Refusing to set state"):
        load_scaler(str(path))
    assert callable(MinMaxScaler.transform)


def test_compressed_and_oversized_files_are_refused(tmp_path):
    compressed = tmp_path / "compressed.joblib"
    joblib.dump(_fitted(), compressed, compress=3)
    with pytest.raises(ArtifactError, match="not an uncompressed"):
        load_scaler(str(compressed))

    big = tmp_path / "big.joblib"
    big.write_bytes(b"\x80\x04" + b"\x00" * (1024 * 1024 + 10))
    with pytest.raises(ArtifactError, match="over the"):
        load_scaler(str(big))


def test_wrong_object_type_is_refused(tmp_path):
    path = tmp_path / "dict.joblib"
    path.write_bytes(pickle.dumps({"scale_": 1.0}, protocol=4))
    with pytest.raises(ArtifactError, match="expected MinMaxScaler"):
        load_scaler(str(path))


def test_model_weights_load_without_reading_the_config(tmp_path):
    source = MODELS_DIR / "EUR_GBP.keras"
    broken = tmp_path / "EUR_GBP.keras"
    with zipfile.ZipFile(source) as archive, zipfile.ZipFile(broken, "w") as out:
        for info in archive.infolist():
            data = archive.read(info.filename)
            if info.filename == "config.json":
                data = b'{"module": "os", "class_name": "system", not even json'
            out.writestr(info, data)
    reference = load_inference_model(str(source), (WINDOW_SIZE, 1))
    model = load_inference_model(str(broken), (WINDOW_SIZE, 1))
    x = np.random.default_rng(3).random((1, WINDOW_SIZE, 1)).astype("float32")
    assert np.array_equal(model.predict(x, verbose=0), reference.predict(x, verbose=0))


def test_model_archive_with_extra_members_is_refused(tmp_path):
    source = MODELS_DIR / "EUR_GBP.keras"
    extra = tmp_path / "EUR_GBP.keras"
    with zipfile.ZipFile(source) as archive, zipfile.ZipFile(extra, "w") as out:
        for info in archive.infolist():
            out.writestr(info, archive.read(info.filename))
        out.writestr("../../evil.py", b"print('x')")
    with pytest.raises(ArtifactError, match="unexpected members"):
        load_inference_model(str(extra), (WINDOW_SIZE, 1))
