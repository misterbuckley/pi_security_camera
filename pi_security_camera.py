# TODO
# - find a better way to detect motion
# - open streaming server when motion is detected
# - alert users when motion is detected just like a ring does
# - find a way to only care about motion on part of the video, a la ring
# - continuously upload captures to server
# - continuously delete captures that have been uploaded to server


import os
import time
import sys
#  import _thread
import datetime
import io
import picamera
import subprocess
import numpy as np
from PIL import Image, ImageChops


# -------------------- SETTINGS --------------------

# default resolution and framerate
DEFAULT_RESOLUTION = '640x480'
DEFAULT_FRAMERATE = 24

# attempt to detect motion every this many seconds
MOTION_DETECTION_INTERVAL = 1

# switch to this resolution when motion is detected
RECORD_RESOLUTION = '1920x1080'

# record for at least this many seconds after first detecting motion
RECORD_DURATION = 5

OUTPUT_DIRECTORY = 'captures'
OUTPUT_FILENAME_FORMAT = "capture-%Y-%m-%d@%H:%M:%S"

# time to keep videos for in seconds (default: 60 * 60 * 24 * 7 = 1 week)
KEEP_VIDEOS_FOR = 60 * 60 * 24 * 7

# 0 = mute, 1 = verbose, 2 = very verbose
DEBUG_MODE = 2

# --------------------------------------------------


prior_image = None


def main():
    with picamera.PiCamera(resolution=DEFAULT_RESOLUTION,
                           framerate=DEFAULT_FRAMERATE) as camera:

        stream = picamera.PiCameraCircularIO(camera, seconds=10)

        if DEBUG_MODE >= 1: print("Start recording")

        camera.start_recording(stream, format='h264')

        try:
            while True:
                camera.wait_recording(MOTION_DETECTION_INTERVAL)

                if detect_motion(camera):
                    if DEBUG_MODE >= 1: print("Motion detected!")

                    now = datetime.datetime.now()
                    formatted = now.strftime(OUTPUT_FILENAME_FORMAT)
                    output_filename = f"{OUTPUT_DIRECTORY}/{formatted}"

                    camera.stop_recording()
                    camera.resolution = RECORD_RESOLUTION
                    #  camera.split_recording(f"{output_filename}.h264")
                    camera.start_recording(f"{output_filename}.h264", format='h264')

                    while detect_motion(camera):
                        if DEBUG_MODE >= 1: print("Motion detected, recording " + str(RECORD_DURATION) + " seconds")

                        camera.wait_recording(RECORD_DURATION)

                    if DEBUG_MODE >= 1: print("Motion stopped, saving to file {output_filename}.mp4")

                    camera.stop_recording()
                    camera.resolution = RECORD_RESOLUTION
                    #  camera.split_recording(stream)
                    camera.start_recording(stream, format='h264')

                    # convert the h264 output file to mp4 and then remove the h264
                    subprocess.call(f"ffmpeg -framerate 24 -i {output_filename}.h264 -c copy {output_filename}.mp4",
                                    shell=True)
                    subprocess.call(f"rm {output_filename}.h264", shell=True)

        finally:
            if DEBUG_MODE >= 1: print("Stop recording")

            camera.stop_recording()


def image_entropy(img):
    w, h = img.size
    a = np.array(img.convert('RGB')).reshape((w*h, 3))
    h, e = np.histogramdd(a, bins=(16,)*3, range=((0, 256),)*3)
    prob = h/np.sum(h)  # normalize
    prob = prob[prob > 0]  # remove zeros
    return -np.sum(prob*np.log2(prob))


def detect_motion(camera):
    if DEBUG_MODE >= 1: print("Looking for motion")

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

        if DEBUG_MODE >= 2: print("Image entropy: " + str(entropy))

        prior_image = current_image
        return entropy >= 2


def delete_files_older_than(age_limit):
    while True:
        if DEBUG_MODE >= 2: print("Checking for old files")

        path = OUTPUT_DIRECTORY
        now = time.time()

        for f in os.listdir(path):
            f = os.path.join(path, f)

            if os.path.isfile(f) and os.stat(f).st_mtime < now - age_limit:
                if DEBUG_MODE >= 2: print(f"Old file found: {f}")

                os.remove(f)

        time.sleep(10)


if __name__ == '__main__':
    # TODO threads
    #  _thread.start_new_thread(delete_files_older_than, (KEEP_VIDEOS_FOR,))
    #  _thread.start_new_thread(main, ())

    main()
