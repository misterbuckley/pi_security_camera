# TODO
# - find a better way to detect motion
# - open streaming server when motion is detected
# - alert users when motion is detected just like a ring does
# - find a way to only care about motion on part of the video, a la ring


import datetime
import io
import picamera
import subprocess
import numpy as np
from PIL import Image, ImageChops


# -------------------- SETTINGS --------------------

VIDEO_RESOLUTION = '640x480'
VIDEO_FRAMERATE = 24

# attempt to detect motion every this many seconds
MOTION_DETECTION_INTERVAL = 1

# record for at least this many seconds after first detecting motion
RECORD_DURATION = 5

OUTPUT_DIRECTORY = 'captures'
OUTPUT_FILENAME_FORMAT = "capture-%Y-%m-%d@%H:%M:%S"

# --------------------------------------------------


def main():
    with picamera.PiCamera(resolution=VIDEO_RESOLUTION,
                           framerate=VIDEO_FRAMERATE) as camera:

        stream = picamera.PiCameraCircularIO(camera, seconds=10)

        camera.start_recording(stream, format='h264')

        try:
            while True:
                camera.wait_recording(MOTION_DETECTION_INTERVAL)

                if detect_motion(camera):
                    now = datetime.datetime.now()
                    formatted = now.strftime(OUTPUT_FILENAME_FORMAT)
                    output_filename = f"{OUTPUT_DIRECTORY}/{formatted}"

                    camera.split_recording(f"{output_filename}.h264")

                    while detect_motion(camera):
                        camera.wait_recording(RECORD_DURATION)

                    camera.split_recording(stream)

                    # convert the h264 output file to mp4 and then remove the h264
                    subprocess.call(f"ffmpeg -framerate 24 -i {output_filename}.h264 -c copy {output_filename}.mp4",
                                    shell=True)
                    subprocess.call(f"rm {output_filename}.h264", shell=True)

        finally:
            camera.stop_recording()


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


if __name__ == '__main__':
    main()
