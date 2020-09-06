from Servers import *
from threading import Lock

class Communications(object):
    def __init__(self, signals, vid_dir):
        self.vid_dir = vid_dir
        # this will be used to store all threads branching from this class
        self.thread_handler = ThreadPoolHandler()
        self.command_port = 9000
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
        self.before_send_checks = self.command_server.before_send_checks
        self.seek_available_ips()

    def seek_available_ips(self):
        # when instance is created, first try and find all coms on port 9003
        self.thread_handler.add(Thread(target=self._seek_available_ips, args=(self.command_port,)))

    def start_servers(self):
        self.command_server = CommandServer(self.command_port,
                                            signal_terminal=self.add_to_terminal,
                                            signal_new_cam=self.new_cam_update,
                                            signal_wifi=self.update_wifi)
        self.download_server = DownloadServer(self.command_port+1,
                                              signal_download=self.update_download_progress,
                                              signal_terminal=self.add_to_terminal,
                                              dir=self.vid_dir)
        self.stream_server = LiveStreamServer(self.command_port+2,
                                              signal_terminal=self.add_to_terminal)
        self.server_list = [self.command_server, self.download_server, self.stream_server]

    def _seek_available_ips_old(self, port):
        found = False
        ip_list = list(os.popen("arp -a"))[3:]
        ip_list = [line.split(" ") for line in ip_list]
        ip_list = [ip[2] for ip in ip_list if ip[-4] == 'dynamic']
        self.add_to_terminal.emit(f"Scanning {len(ip_list)} devices for camera on port {port}")

        for ip in ip_list:
            ip = "192.168.1.108"
            print(self.command_server.coms.keys())
            if ip in self.command_server.coms:
                print("already connected to that")
                continue
            print(f"Attempting with {ip}")
            rpi = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            rpi.settimeout(5)
            try:
                rpi.connect((ip, port))
            except:
                traceback.print_exc()
                rpi.close()
                time.sleep(1 / 1000)
                continue
            rpi.settimeout(None)
            print(f"--found a pie with ip {ip}--")
            append_ifabsent("connected_pis.txt", ip)
            self.command_server.add_ip(ip, rpi)
            found = True
        if not found:
            self.add_to_terminal.emit("No cameras found")

    def _seek_available_ips(self, port):
        found = False
        ip_list = list(os.popen("arp -a"))[3:]
        ip_list = [line.split(" ") for line in ip_list]
        ip_list = [ip[2] for ip in ip_list if ip[-4] == 'dynamic']
        self.add_to_terminal.emit(f"Scanning {len(ip_list)} devices for camera on port {port}")
        ips = []
        lock = Lock()

        def connect(ip):
            rpi = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            rpi.settimeout(5)
            try:
                rpi.connect((ip, port))
                rpi.settimeout(None)
                print(f"--found a pie with ip {ip}--")
                with lock:
                    ips.append((ip, rpi))
            except (ConnectionRefusedError, socket.timeout):
                rpi.close()
            except:
                traceback.print_exc()
                rpi.close()

        pool = []
        for ip in ip_list:
            if ip in self.command_server.coms:
                print("already connected to that")
                continue
            t = Thread(target=connect, args=(ip,))
            t.start()
            pool.append(t)
            print(f"Attempting with {ip}")
        [t.join(timeout=30) for t in pool]

        for ip, rpi in ips:
            append_ifabsent("connected_pis.txt", ip)
            self.command_server.add_ip(ip, rpi)
            found = True
        if not found:
            self.add_to_terminal.emit("No cameras found")

    def change_cam_settings(self, ip, exp, zoom, lr, bt):
        if not self.command_server.before_send_checks(ip):
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
        # first tell cameras to close
        print("server closed and sending close command to cameras")
        self.command_server.sendall("CLOSE")
        for server in self.server_list:
            if server:
                server.close()
        print("sent end")
        self.finish.set()
        print("waiting for server to close")
        self.thread_handler.kill()

    def restart(self):
        self.cleanup()
        self.finish.clear()
        self.start_servers()
        print("restarted server")
        self.add_to_terminal.emit("Successfully restarted server")
