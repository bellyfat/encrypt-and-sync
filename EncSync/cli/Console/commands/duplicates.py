#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse

from .... import Paths
from ...show_duplicates import show_duplicates
from ...common import recognize_path
from ...Environment import Environment
from ....EncScript import Command

__all__ = ["DuplicatesCommand"]

class DuplicatesCommand(Command):
    def evaluate(self, console):
        parser = argparse.ArgumentParser(description="Show duplicates",
                                         prog=self.args[0])
        parser.add_argument("dirs", nargs="+",
                            help="List of paths to show duplicates for")

        ns = parser.parse_args(self.args[1:])

        paths = []

        for path in ns.dirs:
            path, path_type = recognize_path(path, console.cur_storage.name)

            if path_type == console.cur_storage.name:
                path = path_type + "://" + Paths.join_properly(console.cwd, path)
            else:
                path = path_type + "://" + path

            paths.append(path)

        env = Environment(console.env)

        return show_duplicates(env, paths)
