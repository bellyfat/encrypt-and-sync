#!/usr/bin/env python
# -*- coding: utf-8 -*-

from gi.repository import Gtk as gtk
from gi.repository import GLib as glib

from .TextSelectList import TextSelectList
from . import GlobalState
import weakref
import threading

class ScanDialog(gtk.Dialog):
    def __init__(self, scan_type):
        assert(scan_type == "local" or scan_type == "remote")

        if scan_type == "local":
            title = "Scan local directories"
        else:
            title = "Scan yandex disk directories"
 

        gtk.Dialog.__init__(self, title, GlobalState.window, 0,
                            (gtk.STOCK_OK, gtk.ResponseType.OK,
                             gtk.STOCK_CANCEL, gtk.ResponseType.CANCEL))
        
        box = self.get_content_area()

        self.dir_list = TextSelectList("Directory")
        for i in GlobalState.encsync.targets:
            if scan_type == "local":
                self.dir_list.liststore.append([False, i["local"]])
            else:
                self.dir_list.liststore.append([False, i["remote"]])

        box.pack_start(self.dir_list, False, True, 0)

        self.show_all()

    def get_enabled(self):
        return (i[1] for i in self.dir_list.liststore if i[0])

class EncScanScreen(gtk.ScrolledWindow):
    def __init__(self):
        gtk.ScrolledWindow.__init__(self)

        self.vbox = gtk.VBox(spacing=5)
        self.scan_remote_button = gtk.Button(label="Scan remote disk")
        self.scan_local_button = gtk.Button(label="Scan local disk")

        self.hbox = gtk.HBox(spacing=10)

        self.scan_progress = EncScanProgress()

        self.hbox.pack_start(self.scan_remote_button, False, True, 0)
        self.hbox.pack_start(self.scan_local_button, False, True, 0)
        self.vbox.pack_start(self.hbox, False, True, 0)
        self.vbox.pack_start(self.scan_progress, True, True, 0)

        self.add(self.vbox)

        self.scan_local_button.connect("clicked", self.scan_local_button_handler)
        self.scan_remote_button.connect("clicked", self.scan_remote_button_handler)

    def scan_button_handler(self, scan_type, widget):
        dialog = ScanDialog(scan_type)

        while True:
            response = dialog.run()

            if response != gtk.ResponseType.OK:
                dialog.destroy()
                return

            if GlobalState.synchronizer.is_alive():
                msg = "Synchronizer and scanner cannot run at the same time"
                msg_dialog = gtk.MessageDialog(GlobalState.window, 0, gtk.MessageType.INFO,
                                               gtk.ButtonsType.OK, msg)
                msg_dialog.run()
                msg_dialog.destroy()
            else:
                break

        for i in dialog.get_enabled():
            GlobalState.add_scan_task(scan_type, i)

        GlobalState.scanner.start()

        dialog.destroy()

    def scan_local_button_handler(self, widget):
        self.scan_button_handler("local", widget)

    def scan_remote_button_handler(self, widget):
        self.scan_button_handler("remote", widget)

class EncScanProgress(gtk.VBox):
    def __init__(self):
        gtk.VBox.__init__(self, spacing=10)

        self.treeview = gtk.TreeView(GlobalState.scan_tasks)

        self.cell1 = gtk.CellRendererText()

        self.menu = gtk.Menu()
        self.menuitem1 = gtk.MenuItem(label="Stop")
        self.menuitem2 = gtk.MenuItem(label="Resume")
        self.menu.append(self.menuitem1)
        self.menu.append(self.menuitem2)

        self.menuitem1.connect("activate", self.stop_handler)
        self.menuitem2.connect("activate", self.resume_handler)

        self.column1 = gtk.TreeViewColumn("Status", self.cell1, text=0)

        self.column2 = gtk.TreeViewColumn("Type", self.cell1, text=1)

        self.column3 = gtk.TreeViewColumn("Path", self.cell1, text=2)

        self.treeview.append_column(self.column1)
        self.treeview.append_column(self.column2)
        self.treeview.append_column(self.column3)

        self.pack_start(self.treeview, False, True, 0)

        self.background_worker = None

        self.treeview.connect("button-press-event", self.button_press_handler)

        glib.timeout_add(1000, self.update_rows, weakref.finalize(self, lambda: None))

    def stop_handler(self, widget):
        model, treeiter = self.treeview.get_selection().get_selected()

        if treeiter is None:
            return

        row = model[treeiter]
        task = row[-1]
        if task.status is None or task.status == "pending":
            task.change_status("suspended")

    def resume_handler(self, widget):
        model, treeiter = self.treeview.get_selection().get_selected()

        if treeiter is None:
            return

        row = model[treeiter]
        task = row[-1]
        if task.status == "suspended":
            task.change_status("pending")
            if task not in GlobalState.scanner.pool:
                GlobalState.scanner.add_task(task)
            GlobalState.scanner.start()

    @staticmethod # that's not a typo
    def update_rows(weak_self):
        if not weak_self.alive:
            return False

        for row in GlobalState.scan_tasks:
            task = row[3]
            row[0] = str(task.status).capitalize()
            row[1] = task.type.capitalize()
            row[2] = task.path

        return True

    def button_press_handler(self, widget, event):
        if event.button != 3: # Catch only right click
            return

        self.menu.popup(None, None, None, None, event.button, event.time)
        self.menu.show_all()

        return True
