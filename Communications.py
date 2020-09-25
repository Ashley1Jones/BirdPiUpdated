from Servers import *
from threading import Lock
import sys


class Communications(object):
    def __init__(self, signals, vid_dir, dir):
        self.vid_dir = vid_dir
        # this will be used to store all threads branching from this class
        self.thread_handler = ThreadPoolHandler()
        self.command_port = SocketOptionsMethods().main_port
        self.headersize = 40

        self.add_to_terminal = signals["terminal"]
        self.update_download_progress = signals["dl_progress"]
        self.new_cam_update = signals["new_cam"]
        self.update_wifi = signals["wifi"]

        self.finish = Event()
        self.lock = Lock()
        # create all the servers
        self.s = {}
        self.start_servers()
        self.seek_available_ips()
        # file where connected pi's are
        self.connected_dir = os.path.join(dir, "connected_pis.txt")

    def before_send_checks(self, ip):
        return ip in self.command_server.connections

    def start_servers(self):
        self.command_server = CommandServer(signal_terminal=self.add_to_terminal,
                                            signal_update=self.new_cam_update,
                                            signal_wifi=self.update_wifi)
        self.download_server = DownloadServer(signal_download=self.update_download_progress,
                                              signal_terminal=self.add_to_terminal,
                                              dir=self.vid_dir)
        self.stream_server = LiveStreamServer(signal_terminal=self.add_to_terminal)
        self.server_list = [self.command_server, self.download_server, self.stream_server]

    def seek_available_ips(self):
        # when instance is created, first try and find all coms on port 9003
        self.thread_handler.add(target=self._seek_available_ips, args=(self.command_port, ))

    def _seek_available_ips(self, port):
        ip_list = list(os.popen("arp -a"))
        own = ip_list[1].split(" ")[1].split(".")[2]

        system = sys.platform
        #if system == 'win32' and not ext:

        #    ip_list = [line.split(" ") for line in ip_list[3:]]
        #    ip_list = [ip[2] for ip in ip_list if ip[-4] == 'dynamic']
        #elif not ext:
        #    ip_list = [ip.split('(')[1].split(')')[0] for ip in ip_list]
        #else:
        #    ip_list = [f"192.168.{own}.{i}" for i in range(255)]
        ip_list = [f"192.168.{own}.{i}" for i in range(255)]
        # read ips connected in the past and append them to list of connections
        #with open(self.connected_dir, "r") as f:
        #    exist_ips = f.read().split("\n")

        #[ip_list.append(ip) for ip in exist_ips if ip not in ip_list]
        #print(ip_list)

        #self.add_to_terminal.emit(f"Scanning {len(ip_list)} devices for camera on port {port}")
        self.add_to_terminal.emit(f"Scanning searching on port: {port}")
        ips = []
        lock = Lock()
        n_cams = 0
        def connect(ip, attempts):
            for i in range(attempts):
                if self.finish.is_set():
                    return
                rpi = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    rpi.connect((ip, port))
                    rpi.settimeout(None)
                    print(f"--found a pie with ip {ip}--")
                    with lock:
                        ips.append((ip, rpi))
                        append_ifabsent(self.connected_dir, ip)
                        self.command_server.add_ip(ip, rpi)
                        #n_cams += 1
                    return
                #except (ConnectionRefusedError, socket.timeout, TimeoutError):
                #    rpi.close()
                except Exception as e:
                    # print(f"IP {ip} failed with {e}")
                    #traceback.print_exc()
                    rpi.close()
                    return

        n_cams = 0
        pool = []
        for ip in ip_list:
            if ip in self.command_server.connections:
                if not self.command_server.connections[ip].closed.is_set():
                    print("already connected to that")
                    continue
            if len(ip) < 2:
                continue
            attempts = 1
            #attempts = 1 if ip not in exist_ips else 5 # attempt more times with known connections
            t = Thread(target=connect, args=(ip, attempts))
            t.start()
            pool.append(t)
            # only allow n threads
            while len(pool) > 500:
                pool = [t for t in pool if t.is_alive()]
                time.sleep(1 / 20)

            #print(f"Attempting with '{ip}' on port {port}")
        [t.join(timeout=30) for t in pool]

        self.add_to_terminal.emit(f"Finished camera search")

    def change_cam_settings(self, ip, exp, zoom, lr, bt):
        if not self.before_send_checks(ip):
            return
        # change exposure to something the camera can read
        if exp == 50:
            exp = 0
        else:
            exp = int((exp/100)*(10000-500)+500)
        if zoom == 0:
            lr = 0
            bt = 0
        else:
            lr /= 100
            bt = (100 - bt) / 100
        zoom = (100-zoom)/100
        msg = ["CHANGECAM", exp, zoom, lr, bt]
        self.command_server.put(ip, msg)

    def cleanup(self):
        for server in self.server_list:
            if server:
                server.close()
        self.finish.set()
        self.thread_handler.kill_all()
