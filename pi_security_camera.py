import io
import picamera
import subprocess
import numpy as np
from PIL import Image, ImageChops


MOTION_DETECTION_INTERVAL = 1  # attempt to detect motion 1x/sec
RECORD_INTERVAL = 10  # after motion is detected, record at least 10 seconds
OUTPUT_DIRECTORY = 'images'


prior_image = None


def image_entropy(img):
    w, h = img.size
    a = np.array(img.convert('RGB')).reshape((w*h, 3))
    h, e = np.histogramdd(a, bins=(16,)*3, range=((0, 256),)*3)
    prob = h/np.sum(h)  # normalize
    prob = prob[prob > 0]  # remove zeros
    return -np.sum(prob*np.log2(prob))


def detect_motion(camera):
    global prior_image
    stream = io.BytesIO()

    camera.capture(stream, format='jpeg', use_video_port=True)
    stream.seek(0)

    if prior_image is None:
        prior_image = Image.open(stream)
        return False
    else:
        current_image = Image.open(stream)

        diff = ImageChops.difference(prior_image, current_image)
        entropy = image_entropy(diff)
        print("entropy: " + str(entropy))

        prior_image = current_image
        return entropy >= 2


def write_video(stream):
    with io.open('before.h264', 'wb') as output:
        for frame in stream.frames:
            if frame.frame_type == picamera.PiVideoFrameType.sps_header:
                stream.seek(frame.position)
                break
        while True:
            buf = stream.read1()
            if not buf:
                break
            output.write(buf)

    stream.seek(0)
    stream.truncate()


with picamera.PiCamera() as camera:
    camera.resolution = (1280, 720)
    stream = picamera.PiCameraCircularIO(camera, seconds=10)

    camera.start_recording(stream, format='h264')

    try:
        while True:
            camera.wait_recording(MOTION_DETECTION_INTERVAL)

            if detect_motion(camera):
                camera.split_recording('after.h264')

                write_video(stream)

                while detect_motion(camera):
                    camera.wait_recording(RECORD_INTERVAL)

                #  subprocess.call("ffmpeg -framerate 24 -i input.h264 -c copy output.mp4")
                print('Motion stopped!')
                camera.split_recording(stream)

    finally:
        camera.stop_recording()

