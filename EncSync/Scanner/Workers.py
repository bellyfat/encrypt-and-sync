#!/usr/bin/env python
# -*- coding: utf-8 -*-

from ..Worker import Waiter
from .Logging import logger
from ..Scannable import scan_files
from .. import Paths

class ScanWorker(Waiter):
    def __init__(self, parent, target):
        Waiter.__init__(self, parent)

        self.encsync = parent.encsync

        self.cur_target = target
        self.cur_path = None

        self.llist = parent.shared_llist
        self.rlist = parent.shared_rlist
        self.duplist = parent.shared_duplist

        self.add_event("next_node")

    def do_scan(self, task):
        raise NotImplementedError

    def get_next_task(self):
        return self.parent.get_next_task()

    def stop_condition(self):
        target = self.cur_target
        ptarget = self.parent.cur_target

        target_pending = target is None or target.status == "pending"
        ptarget_pending = ptarget is None or ptarget.status == "pending"

        return self.stopped or not target_pending or self.parent.stopped or not ptarget_pending

    def handle_task(self, task):
        try:
            handle_more = self.do_scan(task)
            self.cur_path = None

            return handle_more
        except:
            self.cur_target.change_status("failed")
            task.change_status("failed")
            logger.exception("An error occured")
            self.stop()

            return False

    def after_work(self):
        self.cur_path = None
        self.cur_target = None

class LocalScanWorker(ScanWorker):
    def get_info(self):
        if self.cur_target is None:
            return {}

        return {"operation": "local scan",
                "path": self.cur_path}

    def do_scan(self, task):
        assert(self.cur_target.type == "local")

        scannable = task.scannable

        task.change_status("pending")

        local_files = scan_files(scannable, self.encsync.allowed_paths)

        for s, n in local_files:
            self.cur_path = n["path"]

            self.emit_event("next_node", s)

            if self.stop_condition():
                task.emit_event("interrupt")
                return False

            self.llist.insert_node(n)

        task.change_status("finished")

        return False

class RemoteScanWorker(ScanWorker):
    def insert_remote_scannable(self, scannable):
        self.cur_path = scannable.path

        if self.stop_condition():
            return False

        self.rlist.insert_node(scannable.to_node())

        return True

    def get_info(self):
        if self.cur_target is None:
            return {}

        return {"operation": "remote scan",
                "path": self.cur_path}

    def do_scan(self, task):
        assert(self.cur_target.type == "remote")

        scannable = task.scannable

        task.change_status("pending")

        self.cur_path = scannable.path

        scan_result = scannable.scan()
        scan_result["d"].reverse()

        scannables = {}

        for s in scan_result["f"] + scan_result["d"]:
            self.emit_event("next_node", s)
            path = Paths.dir_denormalize(s.path)
            scannables.setdefault(path, [])
            scannables[path].append(s)

        for i in scannables.values():
            if len(i) > 1:
                task.emit_event("duplicates_found", i)
                self.cur_target.emit_event("duplicates_found", i)
                for s in i:
                    self.duplist.insert(s.type, s.enc_path)

        del scannables

        while True:
            while len(scan_result["f"]) > 0:
                s = scan_result["f"].pop(0)

                if not self.insert_remote_scannable(s):
                    task.emit_event("interrupt")
                    return False

            if len(scan_result["d"]) == 0:
                break

            s = scan_result["d"].pop()

            if not self.insert_remote_scannable(s):
                task.emit_event("interrupt")
                return False

            self.parent.add_task(s)

        task.change_status("finished")

        return True
