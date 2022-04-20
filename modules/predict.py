#! python

import io
from os.path import exists

import numpy as np
import requests
import tensorflow as tf
import tensorflow_hub as hub
from PIL import Image

IMAGE_DIM = 224  # required/default image dimensionality


def load_images(uri, image_size):
    loaded_images = []
    loaded_image_paths = []

    try:
        response = requests.get(uri)
        with io.BytesIO(response.content) as img_bytes:
            image = Image.open(img_bytes)
            image = image.resize(image_size, Image.NEAREST)
        image = tf.keras.preprocessing.image.img_to_array(image)

        image /= 255
        loaded_images.append(image)
        loaded_image_paths.append(uri)
    except Exception as ex:
        print("Image Load Failure: ", uri, ex)

    return np.asarray(loaded_images), loaded_image_paths


def load_model(model_path):
    if model_path is None or not exists(model_path):
        raise ValueError("saved_model_path must be the valid \
            directory of a saved model to load.")

    return tf.keras.models.load_model(model_path, custom_objects={
        'KerasLayer': hub.KerasLayer})


def classify(uri, image_dim=IMAGE_DIM):
    images, image_paths = load_images(uri, (image_dim, image_dim))
    return classify_nd(images)


def is_nsfw(uri):
    prob = classify(uri)
    # print(prob)
    if prob['hentai'] >= 0.60 or prob['porn'] >= 0.60:
        return True
    return False


def classify_nd(nd_images):
    model_preds = model.predict(nd_images)
    # preds = np.argsort(model_preds, axis = 1).tolist()

    categories = ['drawings', 'hentai', 'neutral', 'porn', 'sexy']

    for single_preds in model_preds:
        return {
            categories[j]: float(pred) for j, pred in enumerate(single_preds)}


model = load_model('./mobilenet_v2_140_224/saved_model.h5')
