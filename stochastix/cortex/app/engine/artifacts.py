"""
Safe loading of the trained artefacts in the models folder.

Each currency has two files, written by trainer.py:

  EUR_XXX.keras          Keras archive (config.json + model.weights.h5)
  EUR_XXX_scaler.joblib  MinMaxScaler written with joblib.dump

Neither file is trusted. Model files travel by hand (scp, tar archives,
copies between folders), so a tampered file must not be able to run code.

Scalers. joblib.load is pickle, and pickle can call any Python function
while loading. load_scaler() reads the same file format with its own
unpickler, which resolves only the handful of names a fitted MinMaxScaler
needs and refuses everything else. joblib reads object-dtype arrays with
the unrestricted pickle module, so arrays must have a plain numeric dtype.
Compressed and legacy joblib formats are refused because the trainer never
writes them. The fitted values are checked before the scaler is used.

Models. The API never deserialises the model config. It builds the known
architecture from model.py and loads only the weights from the archive,
so config.json (the part of a .keras file that names classes and
functions) is never read.
"""
import io
import logging
import math
import os
import pickle  # nosec B403 - only the restricted _ScalerUnpickler below reads pickles
import zipfile

import numpy as np
from sklearn.preprocessing import MinMaxScaler

from cortex.app.engine.model import build_model

logger = logging.getLogger("cortex.artifacts")

MAX_SCALER_BYTES = 1024 * 1024
MAX_MODEL_BYTES = 64 * 1024 * 1024
MAX_MODEL_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_ARRAY_ELEMENTS = 64

_KERAS_MEMBERS = {"metadata.json", "config.json", "model.weights.h5"}
_DTYPE_CODES = {"f8", "f4", "i8", "i4", "u8", "u4", "b1", "<f8", "<f4", "<i8", "<i4"}
_SCALER_ATTRIBUTES = {
    "feature_range", "copy", "clip", "n_features_in_", "n_samples_seen_",
    "scale_", "min_", "data_min_", "data_max_", "data_range_",
}
_FITTED_ARRAYS = ("scale_", "min_", "data_min_", "data_max_", "data_range_")


class ArtifactError(Exception):
    """A model or scaler file was refused."""


class _NdarrayMarker:
    """Stands in for numpy.ndarray inside the pickle; it cannot be called."""


_NDARRAY = _NdarrayMarker()


def _dtype_from_pickle(spec, align=False, copy=True):
    if not isinstance(spec, str) or spec not in _DTYPE_CODES:
        raise ArtifactError(f"Refusing dtype {spec!r} in a scaler file")
    return np.dtype(spec)


class _ArrayPlaceholder:
    """Takes the place of joblib's NumpyArrayWrapper while unpickling."""

    _FIELDS = {"subclass", "shape", "order", "dtype", "allow_mmap", "numpy_array_alignment_bytes"}

    def __new__(cls, *args):
        if args:
            raise ArtifactError("Unexpected arguments for an array wrapper")
        return super().__new__(cls)

    def __setstate__(self, state):
        if not isinstance(state, dict) or not set(state) <= self._FIELDS:
            raise ArtifactError("Unexpected array wrapper state in a scaler file")
        self.state = state


_PERMITTED_GLOBALS = {
    ("sklearn.preprocessing._data", "MinMaxScaler"): MinMaxScaler,
    ("joblib.numpy_pickle", "NumpyArrayWrapper"): _ArrayPlaceholder,
    ("numpy", "ndarray"): _NDARRAY,
    ("numpy", "dtype"): _dtype_from_pickle,
}


class _ScalerUnpickler(pickle._Unpickler):
    """Reads joblib's uncompressed format, restricted to a fitted MinMaxScaler.

    joblib writes each numpy array as a NumpyArrayWrapper object followed by
    the raw array bytes outside the pickle stream. When the wrapper's BUILD
    opcode is reached, the bytes are read from the file and the wrapper is
    replaced on the stack by the array, as joblib's own unpickler does.
    """

    dispatch = pickle._Unpickler.dispatch.copy()

    def __init__(self, raw: io.BytesIO):
        super().__init__(raw)
        self._raw = raw

    def find_class(self, module, name):
        try:
            return _PERMITTED_GLOBALS[(module, name)]
        except KeyError:
            raise ArtifactError(f"Refusing to load {module}.{name} from a scaler file") from None

    def persistent_load(self, pid):
        raise ArtifactError("Refusing persistent references in a scaler file")

    def load_build(self):
        stack = self.stack
        if len(stack) < 2:
            raise ArtifactError("Malformed scaler file")
        target = stack[-2]
        if isinstance(target, _ArrayPlaceholder):
            state = stack.pop()
            target.__setstate__(state)
            stack[-1] = self._read_array(target.state)
            return
        # BUILD sets an object's state. Only instances of the two expected
        # types may receive it; applied to a class or function it would
        # change that object for the whole process.
        if not (type(target) is MinMaxScaler or isinstance(target, np.dtype)):
            raise ArtifactError(f"Refusing to set state on {type(target).__name__} in a scaler file")
        super().load_build()

    dispatch[pickle.BUILD[0]] = load_build

    def _read_array(self, state):
        if state.get("subclass") is not _NDARRAY:
            raise ArtifactError("Refusing an ndarray subclass in a scaler file")
        dtype = state.get("dtype")
        if not isinstance(dtype, np.dtype) or dtype.hasobject or dtype.kind not in "fiub" or dtype.itemsize > 8:
            raise ArtifactError(f"Refusing array dtype {dtype!r} in a scaler file")
        shape = state.get("shape")
        if (not isinstance(shape, tuple) or len(shape) > 2
                or not all(isinstance(n, int) and not isinstance(n, bool) and 0 <= n <= MAX_ARRAY_ELEMENTS for n in shape)):
            raise ArtifactError(f"Refusing array shape {shape!r} in a scaler file")
        count = math.prod(shape) if shape else 1
        if count > MAX_ARRAY_ELEMENTS:
            raise ArtifactError("Refusing an oversized array in a scaler file")
        order = state.get("order", "C")
        if order not in ("C", "F"):
            raise ArtifactError("Refusing array order in a scaler file")

        if state.get("numpy_array_alignment_bytes") is not None:
            padding = self._raw.read(1)
            if len(padding) != 1:
                raise ArtifactError("Truncated scaler file")
            skip = padding[0]
            if skip and len(self._raw.read(skip)) != skip:
                raise ArtifactError("Truncated scaler file")

        size = count * dtype.itemsize
        data = self._raw.read(size)
        if len(data) != size:
            raise ArtifactError("Truncated scaler file")
        array = np.frombuffer(data, dtype=dtype, count=count).copy()
        if order == "F":
            array.shape = shape[::-1]
            array = array.transpose()
        else:
            array.shape = shape
        if dtype.byteorder not in ("=", "|") and dtype.byteorder != np.dtype(dtype.char).byteorder:
            array = array.byteswap().view(dtype.newbyteorder("="))
        return array


def _check_scaler(obj) -> MinMaxScaler:
    if type(obj) is not MinMaxScaler:
        raise ArtifactError(f"Scaler file holds {type(obj).__name__}, expected MinMaxScaler")
    attrs = obj.__dict__
    unexpected = set(attrs) - _SCALER_ATTRIBUTES
    missing = _SCALER_ATTRIBUTES - set(attrs)
    if unexpected or missing:
        raise ArtifactError(f"Scaler attributes differ from a fitted MinMaxScaler (unexpected {sorted(unexpected)}, missing {sorted(missing)})")
    feature_range = attrs["feature_range"]
    if (not isinstance(feature_range, tuple) or len(feature_range) != 2
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in feature_range)):
        raise ArtifactError("Scaler feature_range is malformed")
    if not isinstance(attrs["copy"], bool) or not isinstance(attrs["clip"], bool):
        raise ArtifactError("Scaler flags are malformed")
    if attrs["n_features_in_"] != 1 or isinstance(attrs["n_features_in_"], bool):
        raise ArtifactError("Scaler must have exactly one feature")
    seen = attrs["n_samples_seen_"]
    if isinstance(seen, bool) or not isinstance(seen, (int, np.integer)) or seen < 1:
        raise ArtifactError("Scaler n_samples_seen_ is malformed")
    for name in _FITTED_ARRAYS:
        value = attrs[name]
        if (not isinstance(value, np.ndarray) or value.shape != (1,) or value.dtype != np.float64
                or not np.all(np.isfinite(value))):
            raise ArtifactError(f"Scaler {name} is malformed")
    if not np.all(attrs["scale_"] != 0):
        raise ArtifactError("Scaler scale_ is zero")
    return obj


def load_scaler(path: str) -> MinMaxScaler:
    """Loads a scaler written by trainer.py, refusing anything else."""
    size = os.path.getsize(path)
    if size > MAX_SCALER_BYTES:
        raise ArtifactError(f"Scaler file is {size} bytes, over the {MAX_SCALER_BYTES} byte limit")
    with open(path, "rb") as handle:
        data = handle.read(MAX_SCALER_BYTES + 1)
    # joblib.dump without compression writes a pickle that starts with the
    # PROTO opcode. Compressed files start with zlib, gzip, bz2, xz or lz4
    # magic bytes and joblib releases before 0.10 used other layouts; the
    # trainer writes neither, so both are refused.
    if len(data) < 2 or data[0] != 0x80 or data[1] not in (2, 3, 4, 5):
        raise ArtifactError("Scaler file is not an uncompressed joblib pickle")
    try:
        obj = _ScalerUnpickler(io.BytesIO(data)).load()
    except ArtifactError:
        raise
    except Exception as exc:
        raise ArtifactError(f"Scaler file could not be read safely ({type(exc).__name__})") from exc
    return _check_scaler(obj)


def load_inference_model(path: str, input_shape: tuple):
    """Builds the forecasting network and loads only its weights from path."""
    size = os.path.getsize(path)
    if size > MAX_MODEL_BYTES:
        raise ArtifactError(f"Model file is {size} bytes, over the {MAX_MODEL_BYTES} byte limit")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
    except zipfile.BadZipFile as exc:
        raise ArtifactError("Model file is not a Keras archive") from exc
    names = [info.filename for info in infos]
    if len(names) != len(set(names)) or not set(names) <= _KERAS_MEMBERS or "model.weights.h5" not in names:
        raise ArtifactError(f"Model archive has unexpected members: {sorted(names)}")
    if sum(info.file_size for info in infos) > MAX_MODEL_UNCOMPRESSED_BYTES:
        raise ArtifactError("Model archive expands beyond the size limit")

    model = build_model(input_shape, mc_dropout=False, compile_model=False)
    model.load_weights(path)
    return model
