#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time

from ..Scanner import Scanner
from ..Event.EventHandler import EventHandler
from ..FileList import LocalFileList, RemoteFileList, DuplicateList
from .. import Paths

from . import common

def get_path_with_schema(target):
    if target.type == "remote":
        return Paths.join("disk://", target.path)

    return target.path

def print_target_totals(target):
    n_files = n_dirs = 0

    assert(target.type in ("local", "remote"))

    if target.type == "local":
        filelist = LocalFileList()
    elif target.type == "remote":
        filelist = RemoteFileList()

    children = filelist.find_node_children(target.path)

    for i in children:
        if i["type"] == "f":
            n_files += 1
        elif i["type"] == "d":
            n_dirs += 1

    filelist.close()

    path = get_path_with_schema(target)

    print("[%s]: %d files" % (path, n_files))
    print("[%s]: %d directories" % (path, n_dirs))

    if target.type != "remote":
        return

    duplist = DuplicateList()

    children = duplist.find_children(target.path)
    n_duplicates = sum(1 for i in children)

    duplist.close()

    print("[%s]: %d duplicates" % (path, n_duplicates))

class ScannerReceiver(EventHandler):
    def __init__(self, scanner):
        EventHandler.__init__(self)

        self.worker_receiver = WorkerReceiver()

        self.add_emitter_callback(scanner, "started", self.on_started)
        self.add_emitter_callback(scanner, "finished", self.on_finished)
        self.add_emitter_callback(scanner, "next_target", self.on_next_target)
        self.add_emitter_callback(scanner, "worker_started", self.on_worker_started)

    def on_started(self, event):
        print("Scanner: started")

    def on_finished(self, event):
        print("Scanner: finished")

    def on_next_target(self, event, target):
        path = get_path_with_schema(target)
        print("Next %s target: [%s]" % (target.type, path))

    def on_worker_started(self, event, worker):
        worker.add_receiver(self.worker_receiver)

class TargetReceiver(EventHandler):
    def __init__(self):
        EventHandler.__init__(self)

        self.add_callback("status_changed", self.on_status_changed)
        self.add_callback("duplicates_found", self.on_duplicates_found)

    def on_status_changed(self, event):
        target = event["emitter"]

        if target.status in ("finished", "failed", "suspended"):
            path = get_path_with_schema(target)
            print("[%s]: %s" % (path, target.status))

        if target.status == "finished":
            print_target_totals(target)

    def on_duplicates_found(self, event, duplicates):
        print("Found %d duplicates of %s" % (len(duplicates) - 1, duplicates[0].path))

class WorkerReceiver(EventHandler):
    def __init__(self):
        EventHandler.__init__(self)

        self.add_callback("next_node", self.on_next_node)

        self.last_print = 0

    def on_next_node(self, event, scannable):
        if time.time() - self.last_print < 0.5:
            return

        self.last_print = time.time()

        print(scannable.path)

def do_scan(env, paths, n_workers):
    encsync, ret = common.make_encsync(env)
    if encsync is None:
        return ret

    scanner = Scanner(env["encsync"], n_workers)

    targets = []

    target_receiver = TargetReceiver()

    for path in paths:
        path, scan_type = common.recognize_path(path)
        if scan_type == "local":
            path = os.path.realpath(os.path.expanduser(path))
        else:
            path = common.prepare_remote_path(path)

        target = scanner.add_dir(scan_type, path)
        target.add_receiver(target_receiver)
        targets.append(target)

    scanner_receiver = ScannerReceiver(scanner)

    scanner.add_receiver(scanner_receiver)

    scanner.start()
    scanner.join()

    if any(i.status != "finished" for i in targets):
        return 1

    return 0
