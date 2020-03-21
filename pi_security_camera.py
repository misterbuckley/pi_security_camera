# TODO
# - find a better way to detect motion
# - open streaming server when motion is detected
# - alert users when motion is detected just like a ring does
# - find a way to only care about motion on part of the video, a la ring
# - continuously upload captures to server
# - continuously delete captures that have been uploaded to server
# - log output to file
# - threads
#   - check for and delete old captures on another thread
#   - archive log files on another thread
#   - convert .h264 ti .mp4 on another thread
# - read in settings from an easily configured file at OS root level
# - create OUTPUT_FILE_LOCATION and LOG_FILE_LOCATION directories if not present
# - docstrings
# - use original image to check for motion, else small (slow) movements will not trigger motion detect
#   - reset original image against which differences are counted as "motion" every minute or 2
# - use classes and shit and get rid of global variables


import os
import time
import sys
import socket
import datetime
import io
import picamera
import subprocess
import numpy as np
import shutil
import smtplib
import ssl
from PIL import Image, ImageChops


# -------------------- SETTINGS --------------------

DEFAULT_RESOLUTION = "640x480"
DEFAULT_FRAMERATE = 24
MOTION_DETECTION_INTERVAL = 1                        # attempt to detect motion every this many seconds
RECORD_RESOLUTION = "1920x1080"                      # switch to this resolution when motion is detected
RECORD_DURATION = 5                                  # record for at least this many seconds after first detecting motion
KEEP_VIDEOS_FOR = 60 * 60 * 24 * 7                   # time to keep videos for in seconds (default: 61 * 60 * 24 * 7 = 1 week)
TIMESTAMP_FORMAT = "%Y-%m-%d@%H:%M:%S"               # format for time stamps, as used in output file names
OUTPUT_FILE_LOCATION = "captures"                    # save files to this directory
OUTPUT_FILE_FORMAT = f"capture-{TIMESTAMP_FORMAT}"   # format for filename output
LOG_FILE_LOCATION = "logs"                           # where to save log files
LOG_FILE_FORMAT = "log"                              # format for log files
LOG_FILE_SIZE_LIMIT = 1024 * 1024 * 512              # 512 MB max log file size

# --------------------------------------------------


update_prior_image_every = 60 # seconds
prior_image = None
prior_image_taken_at = None


def main():
    with picamera.PiCamera(resolution=DEFAULT_RESOLUTION,
                           framerate=DEFAULT_FRAMERATE) as camera:

        stream = picamera.PiCameraCircularIO(camera, seconds=10)

        log_message("start recording")
        log_message(f"resolution: {DEFAULT_RESOLUTION}")
        log_message(f"framerate: {DEFAULT_FRAMERATE}")

        camera.start_recording(stream, format="h264")

        try:
            while True:
                camera.wait_recording(MOTION_DETECTION_INTERVAL)

                if detect_motion(camera):
                    now = datetime.datetime.now()
                    formatted_time = now.strftime(OUTPUT_FILE_FORMAT)
                    output_filename = f"{OUTPUT_FILE_LOCATION}/{formatted_time}"

                    camera.stop_recording()
                    # TODO move this stuff to a change_resolution() method
                    log_message(f"setting resolution to {RECORD_RESOLUTION}")
                    camera.resolution = RECORD_RESOLUTION
                    camera.start_recording(f"{output_filename}.h264", format="h264")

                    while detect_motion(camera):
                        log_message(f"recording for {RECORD_DURATION} seconds")
                        camera.wait_recording(RECORD_DURATION)

                    log_message(f"Motion stopped, saving to file {output_filename}.mp4")

                    camera.stop_recording()
                    # TODO move this stuff to a change_resolution() method
                    log_message("converting .h264 raw output file to .mp4")
                    # convert the h264 output file to mp4 and then remove the h264
                    subprocess.call(f"ffmpeg -framerate 24 -i {output_filename}.h264 -c copy {output_filename}.mp4",
                                    shell=True)
                    subprocess.call(f"rm {output_filename}.h264", shell=True)

                    log_message(f"setting resolution to {DEFAULT_RESOLUTION}")
                    camera.resolution = DEFAULT_RESOLUTION
                    camera.start_recording(stream, format="h264")

                delete_files_older_than(KEEP_VIDEOS_FOR)

                notify_if_disk_getting_full()

        finally:
            log_message("stop recording")

            camera.stop_recording()


def image_entropy(img):
    w, h = img.size
    a = np.array(img.convert("RGB")).reshape((w*h, 3))
    h, e = np.histogramdd(a, bins=(16,)*3, range=((0, 256),)*3)
    prob = h/np.sum(h)  # normalize
    prob = prob[prob > 0]  # remove zeros
    return -np.sum(prob*np.log2(prob))


def detect_motion(camera):
    global prior_image
    global prior_image_taken_at

    stream = io.BytesIO()

    camera.capture(stream, format="jpeg", use_video_port=True)
    stream.seek(0)
    current_image = Image.open(stream)

    now = time.time()

    if prior_image is None:
        log_message("no prior image, skipping motion check")

        prior_image = current_image
        prior_image_taken_at = now

        return False

    else:
        log_message("checking for motion")

        diff = ImageChops.difference(prior_image, current_image)
        entropy = image_entropy(diff)
        log_message(f"entropy of diff: {entropy}")

        was_motion_detected = entropy >= 2
        if was_motion_detected: log_message("motion detected!")

        if now - prior_image_taken_at > update_prior_image_every:
            log_message(f"it has been {update_prior_image_every} seconds, updating prior image")

            prior_image = current_image
            prior_image_taken_at = now

        return was_motion_detected


def delete_files_older_than(age_limit=KEEP_VIDEOS_FOR):
    log_message(f"checking for captures older than {KEEP_VIDEOS_FOR / 24 / 60 / 60} days")

    path = OUTPUT_FILE_LOCATION
    now = time.time()

    for f in os.listdir(path):
        f = os.path.join(path, f)

        if os.path.isfile(f) and os.stat(f).st_mtime < now - age_limit:
            log_message(f"old file found, removing: {f}")

            os.remove(f)


def notify_if_disk_getting_full():
    total, used, free = shutil.disk_usage('/')

    log_message(f"Disk usage: {used} / {total}  free space: {free}")

    if free <= 1024 * 1024 * 1024:  # <= 1 GB left
        context = ssl.create_default_context()
        hostname = socket.gethostname()

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            sender_address = f"pi@{hostname}"
            receiver_address = "iammikebuckley+securitycamera@gmail.com"
            password = os.getenv('GMAIL_PASS')
            server.login(receiver_address, password)

            email_content = f"""
            Subject: {hostname} is running out of space

            Disk usage: {used / 1024 / 1024 / 1024} of {total / 1024 / 1024 / 1024} GB
            Free space: {free / 1024 / 1024 / 1024}
            """

            server.sendmail(sender_address, receiver_address, email_content)


def log_message(message):
    now = datetime.datetime.now()
    formatted_time = now.strftime(TIMESTAMP_FORMAT)
    log_message = f"{formatted_time} {message}"
    log_filename = f"{LOG_FILE_LOCATION}/{LOG_FILE_FORMAT}"

    print(log_message)

    log_file_size = os.path.getsize(log_filename)
    if log_file_size > LOG_FILE_SIZE_LIMIT:
        print("log file has reached size limit, archiving")
        archive_log_file(log_filename)

    with open(log_filename, "a+") as log_file:
        log_file.write(log_message + "\n")


def archive_log_file(log_filename):
    now = datetime.datetime.now()
    formatted_time = now.strftime(TIMESTAMP_FORMAT)
    os.rename(log_filename, f"{log_filename}-{formatted_time}.log")


if __name__ == "__main__":
    # TODO
    # read_settings()

    main()
