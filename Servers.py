from Utils import *
import cv2
from PyQt5 import QtGui, QtWidgets
import math
from multiprocessing import Queue, Event
import io
import struct
from PIL import Image
import numpy as np
import zlib


def create_server(port, n=10):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((get_host_ip(), port))
    s.listen(n)
    return s


def create_client(ip, port, timeout=None):
    start = time.time()
    while True:
        if timeout:
            if time.time() - start > timeout:
                return None
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect((ip, port))
            break
        except ConnectionRefusedError:
            s.close()
            time.sleep(1)
            continue
        except socket.timeout:
            s.close()
            raise socket.error
    return s


def format_msg(msg):
    code = '/#/'
    if type(msg) is str:
        msg += f"{code}none{code}END{code}"
    elif type(msg) is list:
        new_msg = ""
        msg.append("END")
        for m in msg:
            new_msg += f"{m}{code}"
        msg = new_msg
    else:
        raise TypeError
    return msg


class SocketOptionsMethods(object):
    def __init__(self, signal_terminal=None, signal_update=None):
        self.signal_terminal = signal_terminal
        self.signal_update = signal_update
        self.headersize = 40
        self.split = '/#/'
        self.main_port = 9000
        self.downlaod_port = self.main_port + 1
        self.stream_port = self.main_port + 2
        self.closed = Event()

    def close(self):
        self.closed.set()

    def _add_to_terminal(self, text):
        if self.signal_terminal:
            self.signal_terminal.emit(text)

    def _update_cam(self, text):
        if self.signal_update:
            self.signal_update.emit(text)


class CommandWorker(Thread, SocketOptionsMethods):
    def __init__(self, ip, connection, signal_terminal, signal_new_cam, signal_wifi):
        Thread.__init__(self)
        SocketOptionsMethods.__init__(self, signal_terminal, signal_new_cam)
        self.signal_wifi = signal_wifi
        self.ip = ip
        self.connection = connection
        self.closed = Event()
        self.queue = Queue()
        self.check_hz = 1
        self.start()

    def put(self, msg):
        self.queue.put(msg)

    def close(self):
        self.closed.set()
        try:
            while not self.queue.empty():
                self.queue.get(timeout=1)
            self.queue.close()
        except BrokenPipeError:
            pass
        except:
            traceback.print_exc()

    def run(self):
        last_checked = time.time()
        while not self.closed.is_set():
            if not self.queue.empty():
                msg = self.queue.get()
                print("sent to queue ", msg)
                ip, msg = msg
                self._send(msg)
            elif time.time() - last_checked > 1 / self.check_hz:
                self._send(format_msg(['check', 'none']))
                last_checked = time.time()
            else:
                time.sleep(1 / 100)

    def _send(self, msg):
        try:
            msg = byteHeader(msg, self.headersize)
            self.connection.send(msg)
            time.sleep(1 / 100)
            msg = self.connection.recv(self.headersize).decode()
            # if the message is a standard short reply, just remove spaces
            if msg[-1] == " ":
                msg = msg.replace(' ', '')
                self.signal_update.emit(format_msg(['e', self.ip, msg]))
            else:
                # otherwise, buffer until the end of message is found
                while True:
                    msg += self.connection.recv(self.headersize).decode()
                    if "END" in msg:
                        msg.replace(' ', '')
                        break
                self.signal_wifi.emit(format_msg([self.ip, msg]))
        except socket.timeout:
            # traceback.print_exc()
            print(f"{self.ip} didn't reply in time... closing")
            self._update_cam(format_msg(['d', self.ip, 'Disconnected']))
            self.close()
        except:
            traceback.print_exc()
            print(f"{self.ip} had an error in communication... closing")
            self._update_cam(format_msg(['d', self.ip, 'Disconnected']))
            self.close()


class CommandServer(SocketOptionsMethods):
    def __init__(self, signal_terminal, signal_update, signal_wifi):
        super().__init__(signal_terminal, signal_update)
        self.connections = {}
        self.signal_wifi = signal_wifi
        self.timeout = 10

    def add_ip(self, ip, rpi):
        rpi.settimeout(self.timeout)
        self.connections[ip] = CommandWorker(ip, rpi,
                                             self.signal_wifi,
                                             self.signal_update,
                                             self.signal_wifi)

        self._update_cam(format_msg(['a', ip, 'Waiting']))

    def put(self, ip, msg):
        msg = format_msg(msg)
        self.connections[ip].put((ip, msg))

    def sendall(self, msg):
        msg = format_msg(msg)
        for ip, connection in self.connections.items():
            connection.put((ip, msg))

    def close(self):
        for connection in self.connections.values():
            if not connection.closed.is_set():
                connection.close()


class LiveStreamServer(SocketOptionsMethods):
    def __init__(self, signal_terminal):
        super().__init__(signal_terminal=signal_terminal)
        self.stream_yn = Event()

    def start_stream(self, ip, pixmap):
        self.stream_thread = Thread(target=self._start_stream, args=(ip, pixmap))
        self.stream_thread.start()

    def end_stream(self):
        self.stream_yn.set()

    def _start_stream(self, ip, pixmap):
        self._add_to_terminal("Starting live stream")
        skt = create_client(ip, self.stream_port)
        skt.settimeout(10)
        connection = skt.makefile("rb")
        width, height = pixmap.geometry().height(), pixmap.geometry().width()
        try:
            while True:
                image_len = struct.unpack("<L", connection.read(struct.calcsize("<L")))[0]
                if image_len == 0 and self.stream_yn.is_set():
                    break
                stream = io.BytesIO()
                data = connection.read(image_len)
                stream.write(data)
                stream.seek(0)
                try:
                    image = Image.open(stream).convert("RGB")
                except:
                    traceback.print_exc()
                    skt.send(b"OK")
                    continue
                image.verify()
                image = np.array(image)#, dtype=np.uint8)
                width, height = pixmap.geometry().height(), pixmap.geometry().width()
                image = cv2.resize(image, (height-1, width-1))
                qim = QtGui.QImage(image.data, image.shape[1], image.shape[0], image.strides[0],
                                   QtGui.QImage.Format_RGB888)#.rgbSwapped()
                pixmap.setPixmap(QtGui.QPixmap(qim))
                #print("SNEDING?")
                skt.send(b"OK")
        except socket.timeout:
            traceback.print_exc()
        finally:
            connection.close()
            skt.close()
            self.stream_yn.clear()
            image = np.zeros((height, width), dtype=np.uint8)
            qim = QtGui.QImage(image.data, image.shape[1], image.shape[0], image.strides[0],
                               QtGui.QImage.Format_RGB888).rgbSwapped()
            pixmap.setPixmap(QtGui.QPixmap(qim))
            self._add_to_terminal("Ending live stream")


class DownloadServer(SocketOptionsMethods):
    def __init__(self, dir, signal_download=None, signal_terminal=None):
        super().__init__(signal_terminal=signal_terminal)
        self.signal_download = signal_download
        self.video_dir = create_and_return_file(dir)
        self.buffer = 8 * 1024
        # keep track of how much downloaded
        self.downloaded = 0
        self.downloading = 0
        self.t_handler = {}

    def _update_progress(self, text):
        if self.signal_download:
            self.signal_download.emit(text)

    def get_files(self, ip):
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
        info_printer("Connecting to files server", "Get Files")
        skt = create_client(ip, self.downlaod_port, 10)
        if skt is None:
            info_printer("Failed Connect", "Get Files")
            return
        info_printer("Connected", "Get Files")
        # get info on downloads
        info = skt.recv(self.headersize).decode().split("-")
        n_files, self.downloading = int(info[0]), float(info[1])
        if n_files == 0:
            self._add_to_terminal("No files to retrieve")
            self._update_progress(f"{ip}-N/a-N/a")
            skt.close()
            return
        self._add_to_terminal(f"Downloading {n_files} with size {int(self.downloading / 1e6)}Mb")
        self._update_progress(f"{ip}-0-...")
        time.sleep(1)
        self.downloaded = 0
        self._get_videos(skt, ip)
        self._finish(skt, ip)

    def _finish(self, skt, ip):
        print("finished downloading")
        self._update_progress(f"{ip}-Done-N/a")
        skt.close()

    def _get_videos(self, skt, ip):
        # first loop to collect all files
        while not self.closed.is_set():
            msg = skt.recv(self.headersize)
            # if message is close, then close socket
            if b"ENDALL" in msg or b"CLOSE" in msg:
                info_printer("End of videos", "Get Videos")
                break
            # gather message bytes length and name of file
            msg = msg.decode().split("-")
            msg_len, msg_name = int(msg[0]), msg[1]
            print(f"    new message size: {msg_len / (1e6)}Mb "
                  f"with name {msg_name}")
            self._buffer_recv(skt, msg_name, msg_len, ip)
            self._update_progress(f"{ip}-{math.ceil(100 * self.downloaded / self.downloading)}-Blah")
            print(f"    {msg_name} saved")

    def _buffer_recv(self, skt, msg_name, msg_len, ip):
        fname = f"{self.video_dir}/{msg_name}"
        recv_msg_len = 0
        n_buffers = 0
        print_time = time.time()
        start = time.time()
        with open(fname, "ab") as v:
            while not self.closed.is_set():
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
        info_printer(f"That took {time.time() - start}", "download performance")


class ignore4now(object):
    def _f_bytes(self, b):
        return b.decode().replace(" ", "")

    def _get_lapses(self, skt, ip):
        connection = skt.makefile("rb")
        out = None

        try:
            while not self.closed.is_set():
                name = connection.read(self.headersize)
                print(f"Downloading name {name}")
                name = self._f_bytes(name)
                if "ENDALL" in name:
                    info_printer("End of Lapses", "Get Lapses")
                    break
                name, fps = name.split("-")
                fps = int(fps)

                out = None

                while not self.closed.is_set():
                    size = connection.read(self.headersize)
                    print(f"Downloading image of size {size}")
                    size = self._f_bytes(size)
                    if "END" in size:
                        break
                    size = int(size)
                    self.downloaded += size
                    self._update_progress(f"{ip}-{math.ceil(100 * self.downloaded / self.downloading)}-BLAH")
                    img = connection.read(size)
                    img = self._jpg2RGB(img)
                    if out:
                        pass
                    else:
                        out = cv2.VideoWriter(os.path.join(self.video_dir, f"{name}.mp4"),
                                              cv2.VideoWriter_fourcc("m", "p", "4", "v"), fps,
                                              (img.shape[1], img.shape[0]))
                    out.write(img)
                out.release()
                skt.send(b"OK")
        finally:
            connection.close()
            if out: out.release()

    def _jpg2RGB(self, img):
        stream = io.BytesIO()
        stream.write(img)
        stream.seek(0)
        image = Image.open(stream).convert("RGB")
        image.verify()
        return np.array(image)




