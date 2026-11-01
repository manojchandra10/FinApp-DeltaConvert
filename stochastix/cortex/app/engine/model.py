import logging
import keras
from keras import layers, models, callbacks

logger = logging.getLogger("cortex.model")

WINDOW_SIZE = 180


def build_model(input_shape: tuple, mc_dropout: bool = False) -> keras.Model:
    """
    LSTM model for one-step-ahead return prediction.

    Dropout is active during training (standard Keras behaviour) and inactive
    during inference. The previous version hard-wired training=True into each
    Dropout call, which was intended as Monte Carlo dropout; in practice
    model.predict() overrides that flag in Keras 3, so inference was already
    deterministic and the flag only created version-dependent ambiguity.
    It has been removed. If Monte Carlo sampling is wanted later, pass
    mc_dropout=True and call the model directly (model(x)) N times.
    """
    inputs = layers.Input(shape=input_shape, name="rate_input")

    if mc_dropout:
        x = layers.LSTM(64, return_sequences=True)(inputs)
        x = layers.Dropout(0.3)(x, training=True)
        x = layers.LSTM(64, return_sequences=True)(x)
        x = layers.Dropout(0.3)(x, training=True)
        x = layers.LSTM(32, return_sequences=False)(x)
        x = layers.Dropout(0.3)(x, training=True)
    else:
        x = layers.LSTM(64, return_sequences=True)(inputs)
        x = layers.Dropout(0.3)(x)
        x = layers.LSTM(64, return_sequences=True)(x)
        x = layers.Dropout(0.3)(x)
        x = layers.LSTM(32, return_sequences=False)(x)
        x = layers.Dropout(0.3)(x)

    x = layers.Dense(16, activation="relu")(x)
    outputs = layers.Dense(1)(x)

    model = models.Model(inputs, outputs)
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=0.001),
        loss="mean_squared_error",
    )

    logger.info("Model architecture built.")
    return model


def make_inference_model(trained: keras.Model, input_shape: tuple) -> keras.Model:
    """
    Rebuilds the architecture without any training-time flags and copies the
    weights across. Older .keras files on disk were saved with training=True
    baked into the graph; loading them and transferring weights into a clean
    twin makes inference behaviour explicit and independent of the installed
    Keras version. Falls back to the loaded model if the transfer fails.
    """
    try:
        clean = build_model(input_shape, mc_dropout=False)
        clean.set_weights(trained.get_weights())
        return clean
    except Exception as e:
        logger.warning(f"Weight transfer into inference model failed, using loaded model: {e}")
        return trained


def get_training_callbacks() -> list:
    """Returns standard training callbacks."""
    return [
        callbacks.EarlyStopping(
            monitor="val_loss",
            patience=5,
            restore_best_weights=True,
            verbose=1,
        ),
        callbacks.ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.5,
            patience=3,
            min_lr=1e-6,
            verbose=1,
        ),
    ]


def train_model(
    model: keras.Model,
    X,
    y,
    epochs: int = 50,
    batch_size: int = 32,
    validation_split: float = 0.15,
) -> keras.Model:
    """Trains the model with early stopping and LR scheduling."""
    logger.info(f"Training on {len(X)} samples (val_split={validation_split})...")

    model.fit(
        X,
        y,
        epochs=epochs,
        batch_size=batch_size,
        validation_split=validation_split,
        callbacks=get_training_callbacks(),
        verbose=1,
    )

    logger.info("Training complete.")
    return model
