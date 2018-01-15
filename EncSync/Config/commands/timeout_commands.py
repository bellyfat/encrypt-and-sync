# -*- coding: utf-8 -*-

from ...EncScript import Command
from ...EncScript.Exceptions import EvaluationError

__all__ = ["ConnectTimeoutCommand", "ReadTimeoutCommand",
           "UploadConnectTimeoutCommand", "UploadReadTimeoutCommand"]

class ConnectTimeoutCommand(Command):
    def evaluate(self, config):
        if len(self.args) != 2:
            raise EvaluationError(self, "Expected 1 argument")

        try:
            connect_timeout = float(self.args[1])

            # Catches NaN too
            if not connect_timeout > 0.0:
                raise ValueError
        except ValueError:
            raise EvaluationError(self, "Timeout must be a positive number")

        if connect_timeout == float("inf"):
            connect_timeout = None

        if not isinstance(config.timeout, (tuple, list)):
            read_timeout = config.timeout
        else:
            read_timeout = config.timeout[1]

        config.timeout = (connect_timeout, read_timeout)

        return 0

class ReadTimeoutCommand(Command):
    def evaluate(self, config):
        if len(self.args) != 2:
            raise EvaluationError(self, "Expected 1 argument")

        try:
            read_timeout = float(self.args[1])

            # Catches NaN too
            if not read_timeout > 0.0:
                raise ValueError
        except ValueError:
            raise EvaluationError(self, "Timeout must be a positive number")

        if read_timeout == float("inf"):
            read_timeout = None

        if not isinstance(config.timeout, (tuple, list)):
            connect_timeout = config.timeout
        else:
            connect_timeout = config.timeout[0]

        config.timeout = (connect_timeout, read_timeout)

        return 0

class UploadConnectTimeoutCommand(Command):
    def evaluate(self, config):
        if len(self.args) != 2:
            raise EvaluationError(self, "Expected 1 argument")

        try:
            connect_timeout = float(self.args[1])

            # Catches NaN too
            if not connect_timeout > 0.0:
                raise ValueError
        except ValueError:
            raise EvaluationError(self, "Timeout must be a positive number")

        if connect_timeout == float("inf"):
            connect_timeout = None

        if not isinstance(config.upload_timeout, (tuple, list)):
            read_timeout = config.upload_timeout
        else:
            read_timeout = config.upload_timeout[1]

        config.upload_timeout = (connect_timeout, read_timeout)

        return 0

class UploadReadTimeoutCommand(Command):
    def evaluate(self, config):
        if len(self.args) != 2:
            raise EvaluationError(self, "Expected 1 argument")

        try:
            read_timeout = float(self.args[1])

            # Catches NaN too
            if not read_timeout > 0.0:
                raise ValueError
        except ValueError:
            raise EvaluationError(self, "Timeout must be a positive number")

        if read_timeout == float("inf"):
            read_timeout = None

        if not isinstance(config.upload_timeout, (tuple, list)):
            connect_timeout = config.upload_timeout
        else:
            connect_timeout = config.upload_timeout[0]

        config.upload_timeout = (connect_timeout, read_timeout)

        return 0
