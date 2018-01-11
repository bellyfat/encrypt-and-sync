#!/usr/bin/env python
# -*- coding: utf-8 -*-

import threading

from .Logging import logger
from .Target import DownloadTarget
from ..Worker import Worker
from ..LogReceiver import LogReceiver
from ..EncryptedStorage import EncryptedStorage

__all__ = ["Downloader"]

class Downloader(Worker):
    def __init__(self, encsync, directory, n_workers=2):
        Worker.__init__(self)

        self.encsync = encsync
        self.targets = []
        self.n_workers = n_workers
        self.directory = directory

        self.targets_lock = threading.Lock()
        self.speed_limit = float("inf") # Bytes per second

        self.cur_target = None

        self.add_event("next_target")
        self.add_event("next_task")
        self.add_event("error")

        self.add_receiver(LogReceiver(logger))

    def change_status(self, status):
        for i in self.get_targets() + [self.cur_target]:
            if i is not None:
                i.status = status

    def get_targets(self):
        with self.targets_lock:
            return list(self.targets)

    def make_target(self, src_storage_name, src_path, dst_storage_name, dst_path):
        encsync_target, dir_type = self.encsync.identify_target(src_storage_name,
                                                                src_path)

        if encsync_target is None:
            raise ValueError("%r doesn't belong to any targets" % (src_path,))

        src = EncryptedStorage(self.encsync, src_storage_name, self.directory)
        dst = EncryptedStorage(self.encsync, dst_storage_name, self.directory)

        target = DownloadTarget(self)
        target.name = encsync_target["name"]
        target.src = src
        target.dst = dst
        target.src_path = src_path
        target.dst_path = dst_path

        return target

    def add_download(self, name, src_path, dst_storage_name, dst_path):
        target = self.make_target(name, src_path, dst_storage_name, dst_path)

        self.add_target(target)

        return target

    def add_target(self, target):
        with self.targets_lock:
            self.targets.append(target)

        return target

    def set_speed_limit(self, limit):
        self.speed_limit = limit / float(self.n_workers)

        for worker in self.get_worker_list():
            worker.speed_limit = self.speed_limit

    def stop(self):
        Worker.stop(self)

        # Intentional assignment for thread safety
        target = self.cur_target

        if target is not None:
            target.stop()

    def work(self):
        while not self.stopped:
            try:
                with self.targets_lock:
                    try:
                        self.cur_target = self.targets.pop(0)
                    except IndexError:
                        break

                self.emit_event("next_target", self.cur_target)
                self.cur_target.complete(self)
            except Exception as e:
                self.emit_event("error", e)
                if self.cur_target is not None:
                    self.cur_target.status = "failed"
            finally:
                self.cur_target = None
