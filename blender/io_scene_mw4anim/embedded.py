"""Line-wrapped binary payloads avoid Blender's quadratic long-line insertion."""
import base64


def encode(data):
    return base64.encodebytes(data).decode('ascii')


def decode(text):
    # Accept legacy one-line payloads and new CR/LF-wrapped payloads, retaining
    # strict validation of all other characters.
    return base64.b64decode(text.replace('\r', '').replace('\n', ''), validate=True)
