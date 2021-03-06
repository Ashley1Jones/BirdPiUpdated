# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'Main.ui'
#
# Created by: PyQt5 UI code generator 5.15.0
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.

from PyQt5.QtWidgets import QFileSystemModel
from PyQt5 import QtCore
import vlc
import os.path
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QInputDialog, QLineEdit
from Communications import *
from Mainui import Ui_MainWindow as UI
import cv2
from UI_Utils import *
from traceback import print_exc
#from PyQt5 import uic
#path = os.path.dirname(__file__)
#qfile_wifi = "wifi_ui.ui"
#Wifi_Dialog, _ = uic.loadUiType(os.path.join(path, qfile_wifi))


class Ui_MainWindow(QObject, UI):
    signal_terminal = QtCore.pyqtSignal(str)
    signal_dowload = QtCore.pyqtSignal(str)
    signal_update_cam = QtCore.pyqtSignal(str)
    signal_wifi = QtCore.pyqtSignal(str)

    def extra(self, MainWindow):
        # save main window widget
        self.MainWindow = MainWindow
        # create screenshots directory
        self.screenshot_dir = "screenshots"
        if not os.path.isdir(self.screenshot_dir): os.mkdir(self.screenshot_dir)

        # terminal printing activity
        self.terminal.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        font = QtGui.QFont()
        font.setPointSize(10)
        self.terminal.setFont(font)
        self.signal_terminal.connect(self.add_to_terminal)

        # connect the camera options
        self.signal_update_cam.connect(self.update_cam_selection)
        self.button_send_task.clicked.connect(self.send_task)
        self.button_dowload_files.clicked.connect(self.downlaod_files)
        self.signal_dowload.connect(self.upload_download_table)

        # connnect wifi updater
        self.signal_wifi.connect(self.update_wifi)

        # create backend sockets and give them signals
        signals = {"dl_progress": self.signal_dowload,
                   "terminal": self.signal_terminal,
                   "new_cam": self.signal_update_cam,
                   "wifi": self.signal_wifi}
        self.coms = Communications(signals)

        # create folders viewer
        self.add_folder_tree()
        self.add_vlc()  # create video player
        self.button_screenshot.clicked.connect(self.take_screenshot)

        self.live_on_off = {"STOP": "Stop Live Stream", "START": "Start Live Stream"}
        self.button_live_stream.clicked.connect(self.change_live)

        # create settings directory
        self.settings_dir = "settings"
        if not os.path.isdir(self.settings_dir):
            os.mkdir(self.settings_dir)

        # make a class which handles all the messy threads
        self.thread_handler = ThreadPoolHandler()
        # create a list of buttons to be disabled when downloading is in progress
        self.button_list = [self.button_apply_settings, self.button_live_stream, self.button_auto_settings]
        self.pushButton_scan.clicked.connect(self.coms.seek_available_ips)
        # splitting up strings into individual messages
        self.split = '/#/'
        self.split2 = '/;/'
        # to manage camera names and ip adresses
        self.CamManager = CameraManager(self.MainWindow,
                                            self.combo_select_camera,
                                            self.table_cam,
                                            self.settings_dir)

    def send_task(self):
        ip = self.CamManager.current_ip()
        if self.coms.before_send_checks(ip):
            task = self.combo_set_task.currentText()
            if task == "Night Watch" or task == "Timelapse":
                print("Do not have feature")
                self.signal_terminal.emit("Feature not implemented...")
                return
            task = task.lower().replace(" ", "_")
            if task == "add_wifi":
                self.coms.command_server.put(ip, "send_wifi_config")
                return

            self.coms.command_server.put(ip, task)
            self.signal_terminal.emit(f"Sending task {task} to '{self.CamManager.cam_name(ip)}'")

    @QtCore.pyqtSlot(str)
    def update_wifi(self, msg):
        print("ALL The way over here", msg)
        try:
            msg = msg.split(self.split)
            ip = msg.pop(0)
            msg = [np.split(self.split2) for np in msg if len(np.split(self.split2)) == 2]
            print("formateed", msg)
            results = WifiDialog(msg).results
            if results is None:
                return
            command = "add_wifi_config"
            results.insert(0, command)
            print("New config", results)
            self.coms.command_server.put(ip, results)
        except:
            traceback.print_exc()

    def downlaod_files(self):
        ip = self.CamManager.current_ip()
        if self.coms.before_send_checks(ip):
            self.coms.command_server.put(ip, "send_files")
            self.coms.download_server.get_files(ip)

    @QtCore.pyqtSlot(str)
    def upload_download_table(self, msg):
        print("download just got : ", msg)
        split = msg.split("-")
        ip, perc, eta = split
        self.CamManager.update_download(ip, perc)
        if not perc.isnumeric():
            msg = QtWidgets.QMessageBox()
            msg.setWindowTitle("INFO")
            msg.setText(f"'{self.CamManager.cam_name(ip)}' Download Complete")
            msg.setIcon(QtWidgets.QMessageBox.Information)
            msg.exec_()

    @QtCore.pyqtSlot(str)
    def update_cam_selection(self, msg):
        try:
            self._update_cam_selection(msg)
        except:
            print_exc()

    def _update_cam_selection(self, msg):
        # print(f"emitted {msg}")
        if "--" in msg:
            print("broken")
            return
        split = msg.split("/#/")
        key = split.pop(0)
        ip = split.pop(0)
        name = self.CamManager.cam_name(ip)
        if key == "a":
            self.CamManager.add_cam(ip)
            self.signal_terminal.emit(f"'{name}' added to available cameras")
        elif key == "d":
            self.CamManager.delete_cam(ip)
            self.signal_terminal.emit(f"'{name}' removed from available cameras")
        elif key == "e":
            self.CamManager.edit_table(ip, *split[:3])
        elif key == "wifi":
            print("Adding this to wifi", split)
            self.wifi_config.put(split)

    def reset_cam_settings(self, settings=None):
        if settings is None:
            self.slider_updown.setSliderPosition(100)
            self.slider_leftright.setSliderPosition(0)
            self.slider_zoom.setSliderPosition(0)
            self.slider_exposure.setSliderPosition(50)
        else:
            self.slider_updown.setSliderPosition(settings[3])
            self.slider_leftright.setSliderPosition(settings[2])
            self.slider_zoom.setSliderPosition(settings[1])
            self.slider_exposure.setSliderPosition(settings[0])
        ip = self.CamManager.current_ip()
        if self.coms.before_send_checks(ip):
            self.send_cam_settings()

    def send_cam_settings(self):
        sliders = (self.slider_exposure.sliderPosition(),
                   self.slider_zoom.sliderPosition(),
                   self.slider_leftright.sliderPosition(),
                   self.slider_updown.sliderPosition())
        # first save changes in text file
        with open("settings.txt", "w+") as s:
            for slider in sliders:
                s.write(f"{slider}\n")
        self.coms.change_cam_settings(*sliders)

    @QtCore.pyqtSlot(str)
    def add_to_terminal(self, text):
        self.terminal.append(text)

    def change_live(self):
        ip = self.CamManager.current_ip()
        if self.coms.before_send_checks(ip):
            if self.button_live_stream.text() == self.live_on_off["START"]:
                self.button_live_stream.setText(self.live_on_off["STOP"])
                self.coms.command_server.put(ip, "start_live_stream")
                self.coms.stream_server.start_stream(ip, self.live_image)
            elif self.button_live_stream.text() == self.live_on_off["STOP"]:
                self.button_live_stream.setText(self.live_on_off["START"])
                self.coms.command_server.put(ip, "stop_live_stream")
                self.coms.stream_server.end_stream()

    def add_vlc(self):
        self.opened_file = None
        self.instance = vlc.Instance()
        self.mediaplayer = self.instance.media_player_new()
        self.button_play_pause.clicked.connect(self.playpause)
        self.timer = QTimer(self.MainWindow)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.updateUI)
        self.positionslider = self.horizontalSlider
        self.positionslider.setToolTip("Position")
        self.positionslider.setMaximum(1000)
        self.positionslider.sliderMoved.connect(self.setPosition)

    def Stop(self):
        """Stop player
        """
        self.mediaplayer.stop()
        self.button_play_pause.setText("Play")
        self.opened_file = None

    def updateUI(self):
        """updates the user interface"""
        # setting the slider to the desired position
        self.positionslider.setValue(self.mediaplayer.get_position() * 1000)

        if not self.mediaplayer.is_playing():
            # no need to call this function if nothing is played
            self.timer.stop()
            if not self.isPaused:
                # after the video finished, the play button stills shows
                # "Pause", not the desired behavior of a media player
                # this will fix it
                self.Stop()

    def open_video(self, filename=None):
        """Open a media file in a MediaPlayer
        """
        self.media = self.instance.media_new(filename)
        # put the media in the media player
        self.mediaplayer.set_media(self.media)
        # parse the metadata of the file
        self.media.parse()
        if sys.platform.startswith('linux'):  # for Linux using the X Server
            self.mediaplayer.set_xwindow(self.main_video_frame.winId())
        elif sys.platform == "win32":  # for Windows
            self.mediaplayer.set_hwnd(self.main_video_frame.winId())
        elif sys.platform == "darwin":  # for MacOS
            self.mediaplayer.set_nsobject(int(self.main_video_frame.winId()))
        self.playpause()

    def take_screenshot(self):
        if not self.mediaplayer.play() == -1:
            name = f"{self.screenshot_dir}/{len(os.listdir(self.screenshot_dir))}.jpg"
            self.mediaplayer.video_take_snapshot(0, name,
                                                 i_width=self.mediaplayer.video_get_width(),
                                                 i_height=self.mediaplayer.video_get_height())
            self.mediaplayer.pause()
        else:
            self.signal_terminal.emit("Video needs to be played before taking screenshot")

    def playpause(self):
        """Toggle play/pause status
        """
        print("HERE", self.mediaplayer.is_playing())
        if self.mediaplayer.is_playing():
            self.mediaplayer.pause()
            self.button_play_pause.setText("Play")
            self.isPaused = True
        else:
            if self.mediaplayer.play() == -1:
                print("no video selected")
                # self.OpenFile()
                return
            self.mediaplayer \
                .play()
            self.button_play_pause.setText("Pause")
            self.timer.start()
            self.isPaused = False

    def setPosition(self, position):
        """Set the position
        """
        self.mediaplayer.set_position(position / 1000.0)

    def cleanup(self):
        self.coms.cleanup()
        self.CamManager.save()
        self.thread_handler.kill()

    def add_folder_tree(self):
        self.load_project_structure(self.file_viewer)
        self.file_viewer.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.file_viewer.customContextMenuRequested.connect(self.context_menu)
        # FileViewer(self.treeView)

    def load_project_structure(self, tree):
        font = QtGui.QFont()
        font.setPointSize(8)
        tree.setFont(font)
        self.menu_model = QFileSystemModel()
        self.menu_model.setRootPath(os.getcwd())
        # model.setRootPath(QDir)
        tree.setModel(self.menu_model)
        tree.setRootIndex(self.menu_model.index(os.getcwd()))

    def context_menu(self):
        menu = QtWidgets.QMenu()
        open = menu.addAction("Open")
        rename = menu.addAction("Rename")
        dowscale = menu.addAction("Downscale .MP4")
        # convert = menu.addAction("Convert to .MP4")
        delete = menu.addAction("Delete")
        open.triggered.connect(self.open_file)
        rename.triggered.connect(self.rename_file)
        dowscale.triggered.connect(self.dowscale_mp4)
        # convert.triggered.connect(self.convert2mp4)
        delete.triggered.connect(self.delete_file)
        cursor = QtGui.QCursor()
        menu.exec_(cursor.pos())

    def convert2mp4(self):
        conversion = self.thread_handler.add(Thread(target=self._convert2mp4))

    def _convert2mp4(self):
        file_name = self.get_file_from_menu()
        self.add_to_terminal(f"Converting {file_name}")
        self.check_if_playing(file_name)
        convert2mp4(file_name)
        self.add_to_terminal(f"Finished converting {file_name}")

    def dowscale_mp4(self):
        width, ok = QInputDialog.getText(self.MainWindow, "Get Text", "Width of video to downscale: ", QLineEdit.Normal,
                                         "")
        if ok and width != "":
            if not (width.isnumeric() and int(width) < 1280):
                self.add_to_terminal("Enter a valid number")
                return
            downscaling = self.thread_handler.add(Thread(target=self._downscale_mp4,
                                                         args=(width,)))

    def _downscale_mp4(self, width):
        file_name = self.get_file_from_menu()
        self.add_to_terminal(f"Downscaling {file_name}")
        if file_name == self.opened_file:
            self.Stop()
            time.sleep(0.5)
        cap = cv2.VideoCapture(file_name)
        # fourcc = cv2.VideoWriter_fourcc(*"MP4V")
        fourcc = cv2.VideoWriter_fourcc("M", "P", "4", "V")
        ret, img = cap.read()
        width = int(width)
        height = int((9 / 16) * width)
        img = cv2.resize(img, (width, height))
        new_name = file_name.split(".")[0] + "_downscaled" + ".mp4"
        out = cv2.VideoWriter(new_name, fourcc, 24, (img.shape[1], img.shape[0]))
        while True:
            out.write(img)
            ret, img = cap.read()
            if ret:
                img = cv2.resize(img, (width, height))
            else:
                break
        self.add_to_terminal(f"Finished downscaling {file_name}")
        out.release()
        cap.release()

    def rename_file(self):
        file_name = self.get_file_from_menu()
        self.check_if_playing(file_name)
        text, ok = QInputDialog.getText(self.MainWindow, "Get Text", "Rename to: ", QLineEdit.Normal, "")
        if ok and text != "":
            split = file_name.split('.')
            if len(split) == 0:
                self.signal_terminal.emit("not a file")
            else:
                self.check_if_playing(file_name)
                file_type = split[-1]
                dir = os.path.dirname(file_name)
                new_path = f"{dir}/{text}.{file_type}"
                os.rename(file_name, new_path)

    def open_file(self):
        file_name = self.get_file_from_menu()
        if file_name.split(".")[-1] in ["h264", "mp4"]:
            self.open_video(file_name)
        else:
            os.startfile(file_name)
        self.opened_file = file_name

    def check_if_playing(self, file_name):
        if self.opened_file == file_name:
            self.Stop()
            self.opened_file = None
            time.sleep(0.5)

    def get_file_from_menu(self):
        index = self.file_viewer.currentIndex()
        return self.menu_model.filePath(index)

    def delete_file(self):
        file_name = self.get_file_from_menu()
        self.check_if_playing(file_name)
        os.remove(file_name)


if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()
    ui = Ui_MainWindow()
    ui.setupUi(MainWindow)
    ui.extra(MainWindow)
    MainWindow.show()
    print(f"App exited with code {app.exec_()}")
    ui.cleanup()
    print("coms cleaned up")
    # sys.exit(app.exec_())
    sys.exit()
