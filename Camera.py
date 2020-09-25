import io
from PIL import Image
import time
from threading import Thread, Event, Lock
import picamera
import cv2
from picamera.array import PiRGBArray, PiYUVArray
import traceback
import numpy as np
import os
from datetime import datetime


class Camera(object):
    def __init__(self, qs, evnts, vis):
        self.vis = vis == 'y'
        self.finish = evnts["finish"]
        self.img_q = qs["cam2motion"]
        self.motion_detected = evnts["motion"]
        self.recording = evnts["recording"]
        self.live_event = evnts["live_stream"]
        self.live_queue = qs["live_stream"]
        self.change_settings = qs["change_cam"]
        self.currently_rec = qs["currently_rec"]
        self.cam = picamera.PiCamera()
        self.cam.resolution = res = [(640, 480),
                                     (1280, 720),
                                     (1920, 1088)][1]
        # self.cam.zoom = (0.2, 0.3, 0.6, 0.6)
        # self.cam.brightness = 60
        # print(self.cam.brightness)
        # self.cam.shutter_speed = [0, 2500][0]
        self.rgb_res = [(320, 240), (1280, 720), (1920, 1088)][0]  # absolutely dies if higher
        self.cam.framerate = [24, 30, 60][0]
        # create stream that hold n number of seconds before start of recording
        self.pre_record = 10
        self.past_images = picamera.PiCameraCircularIO(self.cam,
                                                       seconds=self.pre_record)
        self.format = ["mjpeg", "h264"][1]
        self.cam.start_recording(self.past_images, format=self.format)
        # io bytes stream to hold rgb captures for analysis
        self.rgb = PiRGBArray(self.cam, size=self.rgb_res)
        # file parameters
        self.video_path = "videos"
        if not os.path.isdir(self.video_path): os.mkdir(self.video_path)
        self.video_cache = "video_cache"
        if not os.path.isdir(self.video_cache): os.mkdir(self.video_cache)
        # give time for camera stream to warm up
        time.sleep(1)

    def main_loop(self):
        # capture sequence is a loop which runs in another thread
        print("--started camera main loop--")
        self.cam.capture_sequence(self.img_capture(),
                                  format="bgr",
                                  use_video_port=True,
                                  resize=self.rgb_res)

    def cleanup(self):
        # make sure to stop save recording if interrupted
        if self.recording.is_set():
            self.stop_recording()
            self.recording.clear()
        # close streams and camera
        cv2.destroyAllWindows()
        self.cam.close()
        self.past_images.close()
        self.rgb.close()

    def start_recording(self):
        now = datetime.now()
        self.filename = f"{self.video_path}/{now.strftime('%Y_%m_%d_%H_%M_%S')}.mp4"
        print(f"--Recording at filepath: {self.filename}--")
        self.cam.split_recording(f"{self.video_cache}/after.h264")
        self.past_images.copy_to(f"{self.video_cache}/before.h264",
                                 seconds=self.pre_record)
        self.past_images.clear()
        # make sure this is empty
        while not self.currently_rec.empty():
            self.currently_rec.get()
        self.currently_rec.put(self.filename)

    def stop_recording(self):
        self.cam.split_recording(self.past_images)
        os.system(f"MP4Box -add {self.video_cache}/before.h264 -cat {self.video_cache}/after.h264 {self.filename}")
        print(f"--recorded {self.filename}--")
        while not self.currently_rec.empty():
            self.currently_rec.get()

    def stop_recording_old(self):
        self.cam.split_recording(self.past_images)
        with open(f"{self.video_cache}/after.h264", "rb") as after:
            with open(f"{self.video_cache}/before.h264", "rb") as before:
                with open(self.filename, "wb") as combined:
                    print("starting combining of videos")
                    # writing like this avoids reading bytes to memory
                    [combined.write(byte) for byte in before]
                    [combined.write(byte) for byte in after]
        print(f"--recorded {self.filename}--")
        while not self.currently_rec.empty():
            self.currently_rec.get()

    def change_cam_settings(self, exp, zoom, lr, bt):
        print(exp, zoom, lr, bt)
        self.cam.zoom = (float(lr), float(bt), float(zoom), float(zoom))
        time.sleep(0.1)
        self.cam.shutter_speed = int(exp)

    def img_capture(self):
        hz = 2
        last_loop_time = time.time()
        while not self.finish.is_set():
            # skip loop to limit fps to hz
            if (time.time() - last_loop_time) < 1 / hz:
                # limit rgb capture to reduce power consumption
                time.sleep(1 / 100)
                continue
            # reset loop
            last_loop_time = time.time()
            yield self.rgb
            img = self.rgb.array
            # recentre stream
            self.rgb.seek(0)
            self.rgb.truncate()
            # put img in motion capture
            self.img_q.put(img)
            # if live is on and queue is empty put the image in
            if self.live_queue.empty() and self.live_event.is_set(): self.live_queue.put(img)
            # change settings
            if not self.change_settings.empty():
                settings = self.change_settings.get()
                self.change_cam_settings(*settings)
            # for debugging and keyboard exit
            if self.vis:
                cv2.imshow('image', img)
                if cv2.waitKey(1) & 0xFF == ord('q'):  # or finish.set():
                    print("-q- pressed, quitting")
                    self.finish.set()
                    cv2.destroyAllWindows()
                    break

            # only start recording the first time set has been seen
            if self.motion_detected.is_set() and not self.recording.is_set():
                self.start_recording()
                self.recording.set()
            elif not self.motion_detected.is_set() and self.recording.is_set():
                self.stop_recording()
                self.recording.clear()






