from Utils import *
import cv2
from PyQt5 import QtGui, QtWidgets
import math
from multiprocessing import Queue, Event
import io
import struct
from PIL import Image
import numpy as np


def create_server(port, n=10):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((get_host_ip(), port))
    s.listen(n)
    return s

#Highmac1953
class CreateServerClass(object):
    def __init__(self, port, signal_terminal=None, signal_new_cam=None, n=5):
        self.signal_terminal = signal_terminal
        self.port = port
        self.finish = Event()
        self.lock = Lock()
        self.headersize = 40
        self.signal_new_cam = signal_new_cam
        try:
            self.s = create_server(self.port, n)
        except:
            if signal_new_cam:
                self._add_to_terminal("ERROR: Not network connection")
                return
        self.s.settimeout(10)
        self.coms = {}
        self.accept_thread = Thread(target=self._accept_coms)
        self.accept_thread.start()

    def _accept_coms(self):
        """
        this functions launches the server socket
        each time client connects to the server, it is stored in a dictionary with the name sent from the client
        """
        while not self.finish.is_set():
            try:
                print(f"accepting on port {self.port}")
                clientsocket, address = self.s.accept()
            except:
                time.sleep(1 / 10)
                continue
            print(f"--connection from address {address} has been established--")
            address = address[0]
            with self.lock:
                if address in self.coms:
                    self.coms[address].close()
                    print("--already got that camera--")
                clientsocket.settimeout(10)
                self.coms[address] = clientsocket
                self._emit(f"{address}-Waiting-a")

    def before_send_checks(self, ip):
        if len(self.coms) == 0:
            self._add_to_terminal("No camera(s) connected")
            return False
        elif ip not in self.coms:
            self._add_to_terminal(f"{ip} not in list of connections")
            return False
        else:
            return True

    def _add_to_terminal(self, text):
        if self.signal_terminal:
            self.signal_terminal.emit(text)

    def _format_message(self, msg):
        if type(msg) is str:
            msg += "-none-"
        elif type(msg) is list:
            new_msg = ""
            for m in msg:
                new_msg += f"{m}-"
            msg = new_msg
        else:
            self._add_to_terminal(f"{msg} not appropriate message type")
            return "None"
        return msg

    def _remove_ip(self, ip):
        self.coms[ip].close()
        self.coms.pop(ip)

    def _emit(self, msg):
        if self.signal_new_cam:
            self.signal_new_cam.emit(msg)

    def close(self):
        self.finish.set()
        self.s.close()


class CommandServer(CreateServerClass):
    def __init__(self, port, signal_terminal, signal_new_cam):
        super().__init__(port,
                         signal_terminal=signal_terminal,
                         signal_new_cam=signal_new_cam)
        self.queue = Queue()
        self.command_thread = Thread(target=self._command_sender)
        self.command_thread.start()

    def _command_sender(self):
        """
        check if there are commands to be sent
        if not, check if 5 seconds have passed since last cameras coms have been checked
        if so, send message and recv with timeout
        if no reponse, close client and pop from dictionary
        :return:
        """
        last_checked = time.time()
        while not self.finish.is_set():
            if not self.queue.empty():
                msg = self.queue.get()
                print("sent to queue ", msg)
                ip, msg = msg
                self._send(ip, msg)
            elif time.time() - last_checked > 1:
                self._check_on_all()
                last_checked = time.time()
            else:
                time.sleep(1 / 100)

    def put(self, ip, msg):
        msg = self._format_message(msg)
        self.queue.put((ip, msg))

    def sendall(self, msg):
        msg = self._format_message(msg)
        for ip in self.coms.keys():
            self.queue.put((ip, msg))

    def _check_on_all(self):
        try:
            for ip, com in self.coms.items():
                self._send(ip, "check-none-")
        except:
            traceback.print_exc()

    def _send(self, ip, msg):
        with self.lock:
            try:
                if ip in self.coms:
                    print(f"{msg} before bye header")
                    msg = byteHeader(msg, self.headersize)
                    print(f"sending {msg}")
                    self.coms[ip].send(msg)
                    time.sleep(1 / 100)
                    msg = self.coms[ip].recv(self.headersize).decode().replace(' ', '')
                    self._emit(f"{ip}-{msg}-e")
                else:
                    print(f"{ip} not in coms of port {self.port}")
            except:
                print(f"{ip} didn't reply in time... closing")
                self.signal_new_cam.emit(f"{ip}-Disconnected-d")
                self._remove_ip(ip)


class LiveStreamServer(CreateServerClass):
    def __init__(self, port, signal_terminal):
        super().__init__(port, signal_terminal=signal_terminal)
        self.stream_yn = Event()

    def start_stream(self, ip, pixmap):
        self.stream_thread = Thread(target=self._start_stream, args=(ip, pixmap))
        self.stream_thread.start()

    def end_stream(self):
        self.stream_yn.set()

    def _start_stream(self, ip, pixmap):
        self._add_to_terminal("INFO: Starting live stream")
        started = time.time()
        while not ip in self.coms:
            time.sleep(1/10)
            if time.time()-started > 5:
                print("Stream timed out")
                return
        skt = self.coms[ip]
        skt.settimeout(10)
        connection = skt.makefile("rb")
        skipped = 0
        # stream = io.BytesIO()
        width, height = pixmap.geometry().height(), pixmap.geometry().width()
        try:
            while True:
                image_len = struct.unpack("<L", connection.read(struct.calcsize("<L")))[0]
                if image_len == 0 and self.stream_yn.is_set():
                    break
                stream = io.BytesIO()
                stream.write(connection.read(image_len))
                stream.seek(0)
                # img_bytes = connection.read(image_len)
                #image = Image.open(img_bytes)
                try:
                    image = Image.open(stream).convert("RGB")
                except:
                    continue
                image.verify()
                image = np.array(image)#, dtype=np.uint8)
                width, height = pixmap.geometry().height(), pixmap.geometry().width()
                image = cv2.resize(image, (height-1, width-1))
                qim = QtGui.QImage(image.data, image.shape[1], image.shape[0], image.strides[0],
                                   QtGui.QImage.Format_RGB888)#.rgbSwapped()
                pixmap.setPixmap(QtGui.QPixmap(qim))
        finally:
            connection.close()
            skt.close()
            self.coms.pop(ip)
            self.stream_yn.clear()
            image = np.zeros((height, width), dtype=np.uint8)
            qim = QtGui.QImage(image.data, image.shape[1], image.shape[0], image.strides[0],
                               QtGui.QImage.Format_RGB888).rgbSwapped()
            pixmap.setPixmap(QtGui.QPixmap(qim))


class DownloadServer(CreateServerClass):
    def __init__(self, port, signal_download, signal_terminal):
        super().__init__(port, signal_terminal=signal_terminal)
        self.signal_download = signal_download
        self.video_dir = create_and_return_file("videos")
        self.buffer = 8 * 1024
        # keep track of how much downloaded
        self.downloaded = 0
        self.downloading = 0
        self.t_handler = {}

    def _update_progress(self, text):
        self.signal_download.emit(text)

    def get_files(self, ip):
        if self.before_send_checks(ip):
            if ip in self.t_handler:
                if not self.t_handler[ip].is_alive():
                    self.t_handler[ip] = Thread(target=self._get_files, args=(ip,))
                    self.t_handler[ip].start()
                else:
                    self._add_to_terminal(f"{ip} already downloading")
            else:
                self.t_handler[ip] = Thread(target=self._get_files, args=(ip,))
                self.t_handler[ip].start()

    def _get_files(self, ip):
        """
        This function needs to be threaded.  Retrieves file size and name in header.
        Then loop to receive the whole file
        :param skt: individual client socket
        :param buffer: byte size of each buffer
        :return:
        """
        skt = self.coms[ip]
        print("start downloading")
        info = skt.recv(self.headersize).decode().split("-")
        n_files, self.downloading = int(info[0]), float(info[1])
        if n_files == 0:
            self._add_to_terminal("No files to retrieve")
            # clear close from pipeline that otherwise be taken later
            skt.recv(self.headersize)
            self._update_progress(f"{ip}-N/a-N/a")
            return
        self._add_to_terminal(f"Downloading {n_files} with size {int(self.downloading / 1e6)}Mb")
        self._update_progress(f"{ip}-0-...")
        time.sleep(1)
        # first loop to collect all files
        while not self.finish.is_set():
            msg_string = b""
            msg = skt.recv(self.headersize)
            # if message is close, then close socket
            if msg[:5] == b"CLOSE":
                print("--end of messages--")
                break
            # gather message bytes length and name of file
            msg = msg.decode().split("-")
            msg_len, msg_name = int(msg[0]), msg[1]
            print(f"    new message size: {msg_len / (1e6)}Mb "
                  f"with name {msg_name}")
            self._buffer_recv(skt, msg_name, msg_len, ip)
            self._update_progress(f"{ip}-{math.ceil(100 * self.downloaded / self.downloading)}-Blah")
            print(f"    {msg_name} saved")
        print("finished downloading")
        self._update_progress(f"{ip}-Done-N/a")
        self.downloaded = 0

    def _buffer_recv(self, skt, msg_name, msg_len, ip):
        fname = f"{self.video_dir}/{msg_name}"
        recv_msg_len = 0
        n_buffers = 0
        print_time = time.time()
        with open(fname, "ab") as v:
            while not self.finish.is_set():
                msg = skt.recv(self.buffer)
                recv_msg_len += len(msg)
                self.downloaded += len(msg)
                v.write(msg)
                # if length of message is matched then break
                if recv_msg_len >= msg_len:
                    print(f"    {msg_name} received and sending feedback")
                    skt.send(bytes("video received", "utf-8"))
                    time.sleep(1/100)
                    break
                n_buffers += 1
                # only print every n seconds
                if time.time() - print_time > 1:
                    print_time = time.time()
                    print(f"    another {n_buffers} received, current message length {len(msg)}")
                    speed = self.buffer * n_buffers
                    # eta = round((downloading - downloaded) / speed, 2)
                    self._update_progress(f"{ip}-{math.ceil(100 * self.downloaded / self.downloading)}-BLAH")
                    n_buffers = 0
