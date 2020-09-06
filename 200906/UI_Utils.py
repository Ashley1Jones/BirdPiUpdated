from PyQt5 import QtWidgets
from wifi_ui import Ui_Dialog as Wifi_Dialog
from PyQt5.QtCore import QTimer
import os
from Utils import get_dict_key
from traceback import print_exc


class WifiDialog(QtWidgets.QDialog, Wifi_Dialog):
    def __init__(self, wifi_config):
        super().__init__()
        self.setupUi(self)
        self.results = self.getResults(wifi_config)

    def getResults(self, config):
        n_rows = self.tableWidget.rowCount()
        # set the table to the current config
        for i, line in enumerate(config):
            for j, np in enumerate(line):
                self.tableWidget.setItem(i, j, QtWidgets.QTableWidgetItem(np))

        # get the edited table
        if self.exec_() == self.Accepted:
            result = []
            for i in range(n_rows):
                if self.tableWidget.item(i, 0) is None or self.tableWidget.item(i, 1) is None:
                    break
                elif len(self.tableWidget.item(i, 0).text()) < 1 or len(self.tableWidget.item(i, 1).text()) < 1:
                    continue
                result.append(f"{self.tableWidget.item(i, 0).text()}/;/{self.tableWidget.item(i, 1).text()}")
            return result
        else:
            return None


def get_column_values(tbl, col):
    column = []
    for i in range(tbl.rowCount()):
        item = tbl.item(i, col)
        if item is None:
            column.append(None)
        elif len(item.text()) < 1:
            column.append(None)
        else:
            column.append(item.text())
    return column


class CameraManager(object):
    def __init__(self, MainWindow, combo, table, settings_dir):
        self.combo = combo
        self.table = table
        # setup timer to keep track of names and ips. store ips in dict
        self.table_timer = QTimer(MainWindow)
        self.table_timer.setInterval(500)
        self.table_timer.timeout.connect(self.update_names)
        self.table_timer.start()
        self.name_ip_key = {}
        self.name_settings_file = f"{settings_dir}/name_settings.txt"
        self._load()

    def _load(self):
        if os.path.isfile(self.name_settings_file):
            with open(self.name_settings_file, "r") as f:
                lines = f.read().split("\n")
                for line in lines:
                    if len(line) < 2:
                        continue
                    ip, name = line.split(";")
                    self.name_ip_key[ip] = name

    def edit_table(self, ip, task, n_files, total_size):
        row = self._get_table_index(ip)
        [self._set_table_text(row, col, text) for col, text in ((2, task), (3, n_files),
                                                               (4, total_size))]

    def _set_table_text(self, row, col, text):
        self.table.setItem(row, col, QtWidgets.QTableWidgetItem(text))

    def save(self):
        if len(self.name_ip_key) > 0:
            with open(self.name_settings_file, "w") as f:
                for ip, name in self.name_ip_key.items():
                    f.write(f"{ip};{name}\n")

    def _get_table_index(self, ip):
        rows = self.table.rowCount()
        column_text = [self.table.item(row, 1).text() if self.table.item(row, 1) else None
                       for row in range(rows)]
        return column_text.index(None) if ip not in column_text else column_text.index(ip)

    def update_download(self, ip, perc):
        row = self._get_table_index(ip)
        self._set_table_text(row, 5, perc)

    def add_cam(self, ip):
        try:
            self._add_cam(ip)
        except:
            print_exc()

    def cam_name(self, ip):
        return self.name_ip_key[ip]if ip in self.name_ip_key.keys() else ip

    def delete_cam(self, ip):
        # remove from combo box
        name = self.cam_name(ip)
        index = self.combo.findText(name)
        self.combo.removeItem(index)
        # display on table
        idx = self._get_table_index(ip)
        self.table.setItem(idx, 2, QtWidgets.QTableWidgetItem("Disconnected"))

    def _add_cam(self, ip):
        idx = self._get_table_index(ip)
        # first add to table
        self.table.setItem(idx, 1, QtWidgets.QTableWidgetItem(ip))
        self.table.setItem(idx, 2, QtWidgets.QTableWidgetItem("Waiting"))

        # then check if names are assigned to ip
        name = self.name_ip_key[ip] if ip in self.name_ip_key.keys() else f"cam{len(self.name_ip_key)}"
        self.table.setItem(idx, 0, QtWidgets.QTableWidgetItem(name))

        rows = self.table.rowCount()
        if idx + 1 == rows:
            self.table.setRowCount(rows + 1)
        self.combo.addItem(name)
        return name

    def current_ip(self):
        if self.combo.count() == 0:
            msg = QtWidgets.QMessageBox()
            msg.setWindowTitle("INFO")
            msg.setText(f"No Camera(s) Connected")
            msg.setIcon(QtWidgets.QMessageBox.Information)
            msg.exec_()
        else:
            return get_dict_key(self.name_ip_key, self.combo.currentText())

    def update_names(self):
        for i in range(self.table.rowCount()):
            if self.table.item(i, 0) is not None:
                ip = self.table.item(i, 1).text()

                if len(self.table.item(i, 0).text()) > 1:
                    name = self.table.item(i, 0).text()
                else:
                    name = f"cam{len(self.name_ip_key)}"
                    self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(name))

                old_name = self.name_ip_key[ip] if ip in self.name_ip_key.keys() else ip
                self.name_ip_key[ip] = name
                idx = self.combo.findText(old_name)
                self.combo.setItemText(idx, name)


#class OpencvVideoPlayer(object):

