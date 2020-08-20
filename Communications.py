from Servers import *


class Communications(object):
    def __init__(self, signals):
        # this will be used to store all threads branching from this class
        self.thread_handler = ThreadPoolHandler()
        self.command_port = 9000
        self.headersize = 40

        self.add_to_terminal = signals["terminal"]
        self.update_download_progress = signals["dl_progress"]
        self.new_cam_update = signals["new_cam"]

        self.finish = Event()
        self.lock = Lock()
        # create all the servers
        self.s = {}
        self.start_servers()
        # when instance is created, first try and find all coms on port 9003
        self.thread_handler.add(Thread(target=self.seek_available_ips, args=(self.command_port+3,)))
        self.before_send_checks = self.command_server.before_send_checks

    def start_servers(self):
        self.command_server = CommandServer(self.command_port,
                                            signal_terminal=self.add_to_terminal,
                                            signal_new_cam=self.new_cam_update)
        self.download_server = DownloadServer(self.command_port+1,
                                              signal_download=self.update_download_progress,
                                              signal_terminal=self.add_to_terminal)
        self.stream_server = LiveStreamServer(self.command_port+2,
                                              signal_terminal=self.add_to_terminal)
        self.server_list = [self.command_server, self.download_server, self.stream_server]

    def seek_available_ips(self, port):
        own_ip = get_host_ip()
        end_ip = own_ip.split(".")[-1]
        net_ip = own_ip.replace(end_ip, "")
        print("--seeking ips--")
        for i in range(256):
            server_ip = f"{net_ip}{i}"
            try:
                client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client.settimeout(1 / 10)
                client.connect((server_ip, port))
                client.settimeout(None)
                print("--found a pie--")
                append_ifabsent("connected_pis.txt", server_ip)
                time.sleep(1 / 10)
                client.close()
            except:
                time.sleep(1 / 1000)

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
