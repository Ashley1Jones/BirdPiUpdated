from threading import Thread, Event, Lock
from multiprocessing import Process
import traceback
import time
import sys
import threading
import ctypes
import logging
import os
from PyQt5.QtCore import *
import cv2
import socket


def append_ifabsent(fname, txt):
    if not os.path.isfile(fname):
        with open(fname, "w"):
            pass
    with open(fname, "r") as f:
        lines = f.readlines()
    with open(fname, "a") as f:
        if f"{txt}\n" not in lines:
            print(f"New line appending {txt}")
            f.write(f"{txt}\n")
        else:
            print("already got it")


def create_and_return_file(fname):
    if not os.path.isdir(fname):
        os.mkdir(fname)
    return fname


def get_host_ip():
    return [l for l in ([ip for ip in socket.gethostbyname_ex(socket.gethostname())[2]
                         if not ip.startswith("127.")][:1], [[(s.connect(('8.8.8.8', 53)),
                                                               s.getsockname()[0], s.close()) for s in
                                                              [socket.socket(socket.AF_INET,
                                                                             socket.SOCK_DGRAM)]][0][1]]) if l][0][0]


def indent(text, num_indents):
    return f"{text:>{4*num_indents}}"


def byteHeader(header, size):
    return bytes(f"{header:<{size}}", "utf-8")


class TimeOut:
    """
    used for timeouting blocks of code
    https://www.jujens.eu/posts/en/2018/Jun/02/python-timeout-function/
    """
    def __init__(self, timeout):
        self.start_time = time.time()
        self.timeout = timeout
        self.deactivated = Event()

    def __enter__(self):
        """
        enter by making the thread and starting
        """
        self.thread = Thread(target=self.timer, args=())
        self.thread.start()
        return self

    def __exit__(self, type, value, traceback):
        self.deactivated.set()

    def timer(self):
        """
        loop until either timeout is exceeded or deactivate is set
        """
        while time.time() - self.start_time < self.timeout and not self.deactivated.is_set():
            time.sleep(1e-3)
        # raise error if deactivate was not set
        if not self.deactivated.is_set():
            self.raise_error()

    def deactivate(self):
        self.deactivated.set()

    def raise_error(self):
        print("exiting")
        sys.exit()

def convert2mp4(file_name):
    cap = cv2.VideoCapture(file_name)
    fourcc = cv2.VideoWriter_fourcc(*"MP4V")
    ret, img = cap.read()
    if not ret:
        return
    new_name = file_name.split(".")[0]+".mp4"
    out = cv2.VideoWriter(new_name, fourcc, 24, (img.shape[1], img.shape[0]))
    broken = False
    try:
        while ret:
            out.write(img)
            ret, img = cap.read()
    except:
        broken = True
    finally:
        out.release()
        cap.release()
        if not broken: os.remove(file_name)



class ThreadPoolHandler(object):
    def __init__(self):
        self.pool = []
        self.lock = Lock()

    def add(self, t):
        t.start()
        with self.lock:
            self.pool.append(t)
            self.pool = [t for t in self.pool if t.isAlive()]
            print(f"currently {len(self.pool)} active")
        return t

    def kill(self):
        with self.lock:
            print(f"Killing remaining {len(self.pool)} threads in pool")
            [kill_thread(t) for t in self.pool]


def SubProcessClass(target, finish, args, method="thread"):
    """
    :param target: class to be targeted to be subprocess
    :param finish: finish event used to break loop
    :return: class object which overrides the process class
    """
    if method == "thread":
        Method = Thread
    elif method == "process":
        Method = Process
    else:
        raise ValueError

    class Override(Method):
        def __init__(self, target, finish, args):
            """
            overrides the Process class to create a seperate process containing this class only-
            input and output can be found in the subprocess and main process-
            """
            Method.__init__(self)
            self.finish = finish
            self.target = target
            self.args = args

        def run(self):
            """
            initialise used instead of init self because...
            memory from init self does not transfer to new class.

            Class requires three main methods;
                -init
                -main_loop
                -cleanup
            """
            try:
                # init target class
                self.target = self.target(*self.args)
            except Exception:
                traceback.print_exc()
                if not self.finish.is_set():
                    self.finish.set()
                return

            try:
                # loop targets main loop, while checking finish status
                while not self.finish.is_set():
                    # returns none, unless a break is called from within the class
                    if self.target.main_loop() == "break":
                        break
            # if exception occurs, raise error and print
            except Exception as e:
                traceback.print_exc()
            finally:
                # if code breaks, and finish has not been called, set the event
                if not self.finish.is_set():
                    self.finish.set()
                # call class cleanup code
                self.target.cleanup()

    return Override(target, finish, args)


def get_thread_id(t):
    # returns id of the respective thread
    if hasattr(t, '_thread_id'):
        return t._thread_id
    for id, thread in threading._active.items():
        if thread is t:
            return id

def kill_thread(t):
    thread_id = get_thread_id(t)
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id,
                                                     ctypes.py_object(SystemExit))
    if res > 1:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, 0)
        print('Thread exception raise failure')


def create_log(name, lvl):
    log = logging.getLogger(name)
    log.setLevel(lvl)
    # formatter = logging.Formatter("%(levelname)s:%(name)s:%(message)s")
    if lvl == logging.ERROR:
        lvl = "error"
    elif lvl == logging.INFO:
        lvl = "info"
    else:
        raise ValueError("incorrect logging level")
    file_handler = logging.FileHandler(f"log/{name}_{lvl}.log")
    file_handler.setFormatter(logging.Formatter("%(asctime)s:%(name)s:%(message)s"))
    log.addHandler(file_handler)
    return log


def ParrallelClass(target, finish, args, Method, logName):
    """
    :param target: class to be targeted to be subprocess
    :param finish: finish event used to break loop
    :return: class object which overrides the process class
    """

    class Override(Method):
        def __init__(self, target, finish, args, logName):
            """
            overrides the Process class to create a seperate process containing this class only-
            input and output can be found in the subprocess and main process-
            """
            Method.__init__(self)
            self.finish = finish
            self.target = target
            self.args = args
            # create logging
            self.log_dir = f"log/{logName}.log"
            if not os.path.isdir("log"): os.mkdir("log")
            self.error_logger = create_log(name=target.__name__, lvl=logging.ERROR)
            # start thread or process with init
            self.start()

        def save_and_print_error(self, err):
            self.finish.set()
            traceback.print_exc()
            err = traceback.format_exc()
            self.error_logger.error(err)

        def run(self):
            """
            initialise used instead of init self because...
            memory from init self does not transfer to new class.

            Class requires three main methods;
                -init
                -main_loop
                -cleanup
            """
            try:
                if not (hasattr(target, "main_loop") and hasattr(target, "cleanup")):
                    raise AttributeError
            except Exception as e:
                self.save_and_print_error(e)
                return

            try:
                # init target class
                self.target = self.target(*self.args)
                while not self.finish.is_set():
                    self.target.main_loop()
            # if exception occurs, raise error and print
            except Exception as e:
                self.save_and_print_error(e)
            finally:
                # call class cleanup code
                try:
                    self.target.cleanup()
                except Exception as e:
                    self.save_and_print_error(e)

    return Override(target, finish, args, logName)


class Worker(QRunnable):
    '''
    Worker thread

    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.

    :param callback: The function callback to run on this worker thread. Supplied args and
                     kwargs will be passed through to the runner.
    :type callback: function
    :param args: Arguments to pass to the callback function
    :param kwargs: Keywords to pass to the callback function

    '''

    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()

        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        '''
        Initialise the runner function with passed args, kwargs.
        '''

        # Retrieve args/kwargs here; and fire processing using them
        try:
            result = self.fn(*self.args, **self.kwargs)
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
            print("ERROR - ", exctype, value, traceback.format_exc())
        else:
            self.signals.result.emit(result)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done


class WorkerSignals(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(tuple)
    result = pyqtSignal(object)
    progress = pyqtSignal(int)