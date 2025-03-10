#!/usr/bin/env python3
"""
MIT License

Copyright (c) 2025 Evgenii Sopov

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Original repository: https://github.com/sea5kg/bo

"""

import os
import sys
import time
import socket
import re
import platform
import json
import subprocess
import threading
import errno
import hashlib
from pathlib import Path
import yaml

BUF_READ_SIZE = 65536
SEND_BUFFER_SIZE = 512

VERSION = "v0.0.2"

print(
    "Welcom to bo (" + VERSION + ")!\n"
    "Utilite for sync files (like rsync) and "
    "run build on remote server (or Virtual Machine in local network)\n"
)


def fatal(error_num, msg):
    """ print error and exit """
    print("\n[ERROR] (" + str(error_num) + ") " + msg + "\n\n")
    sys.exit(-1)


CURRENT_DIR = os.path.normpath(os.path.realpath(os.getcwd()))
# init config in home dir
BO_HOME_CONFIG_DIR = os.path.join(Path.home(), ".bo-by-sea5kg")
if not os.path.isdir(BO_HOME_CONFIG_DIR):
    os.mkdir(BO_HOME_CONFIG_DIR)
    if not os.path.isdir(BO_HOME_CONFIG_DIR):
        fatal(1, "Could not create directory: '" + BO_HOME_CONFIG_DIR + "'")
BO_CONFIG_FILEPATH = os.path.join(BO_HOME_CONFIG_DIR, "config.yml")
BO_CONFIG = {
    "bo_version": VERSION,
    "workdirs": {}
}


def resave_config():
    """ resave config file """
    BO_CONFIG["bo_version"] = VERSION
    with open(BO_CONFIG_FILEPATH, 'w', encoding="utf-8") as _file:
        yaml.dump(BO_CONFIG, _file, indent=2)


def get_all_files(_startdir):
    """ recursive find all files in dir """
    _ret = []
    _rec = [_startdir]
    while len(_rec) > 0:
        _dirpath = _rec[0]
        del _rec[0]
        for _file in os.listdir(_dirpath):
            _filepath = os.path.join(_dirpath, _file)
            if _file == '.git' and os.path.isdir(_filepath):
                continue
            if os.path.isdir(_filepath):
                _rec.append(_filepath)
                continue
            if os.path.isfile(_filepath):
                _ret.append(_filepath[len(_startdir)+1:])
    return _ret


def md5_by_file(_filepath):
    """ Calculate md5 by file """
    md5 = hashlib.md5()
    with open(_filepath, 'rb') as _file:
        while True:
            data = _file.read(BUF_READ_SIZE)
            if not data:
                break
            md5.update(data)
    return md5.hexdigest()


def is_linux():
    """ current system is linux? """
    return platform.platform().lower().startswith("linux")


def is_windows():
    """ current system is windows? """
    return platform.platform().lower().startswith("windows")


class BoFilesCache:
    """ helper class for control of cache """

    def __init__(self, _cache_path):
        self.__files = {}
        self.__files_to_update = {}
        self.__cache_path = _cache_path
        self.__cache_path_to_update = _cache_path[:-4] + "_to_update.yml"
        # load
        if os.path.isfile(self.__cache_path):
            with open(self.__cache_path, encoding="utf-8") as _file:
                try:
                    self.__files = yaml.safe_load(_file)
                except yaml.YAMLError as _exc:
                    print(_exc)
                    sys.exit(_exc)
        for _file in self.__files:
            if self.__files[_file]['required_sync'] != 'NONE':
                self.__files_to_update[_file] = self.__files[_file]

    def get_cache_path(self):
        """ return cache path """
        return self.__cache_path

    def get_cache_path_to_update(self):
        """ return cache path to_update """
        return self.__cache_path_to_update

    def has(self, _file):
        """ is contains file """
        return _file in self.__files

    def add(self, _file, _fullpath):
        """ added file to cache """
        self.__files[_file] = {
            "required_sync": "UPDATE",
            "md5": md5_by_file(_fullpath),
            "size": os.path.getsize(_fullpath),
            "last_modify": os.path.getmtime(_fullpath),
            "last_modify_formatted": time.ctime(os.path.getmtime(_fullpath)),
        }
        self.__files_to_update[_file] = self.__files[_file]

    def get(self, _file):
        """ return file info """
        return self.__files[_file]

    def update(self, _file, _info):
        """ update file info """
        for _key in _info:
            self.__files[_file][_key] = _info[_key]
        if 'version' not in self.__files[_file]:
            self.__files[_file]['version'] = 0
        self.__files[_file]['version'] += 1
        if self.__files[_file]['required_sync'] == 'NONE':
            if _file in self.__files_to_update:
                del self.__files_to_update[_file]
        else:
            self.__files_to_update[_file] = self.__files[_file]

    def remove(self, _file):
        """ remove file from list """
        del self.__files[_file]
        if _file in self.__files_to_update:
            del self.__files_to_update[_file]

    def get_files(self):
        """ return all the file list """
        return self.__files

    def get_files_to_update(self):
        """ return all the file list """
        return self.__files_to_update

    def resave_cache(self):
        """ resave file """
        with open(self.__cache_path, 'w', encoding="utf-8") as _file:
            yaml.dump(self.__files, _file, indent=2)
        with open(self.__cache_path_to_update, 'w', encoding="utf-8") as _file:
            yaml.dump(self.__files_to_update, _file, indent=2)

    def rescan_files(self, _workdir):
        """ Update list of files (scan again) """
        print("Scanning files...")
        _start = time.time()
        current_files = get_all_files(_workdir)
        _changes = 0
        for _file in current_files:
            fullpath = os.path.join(_workdir, _file)
            if not self.has(_file):
                self.add(_file, fullpath)
                _changes += 1
            else:
                _fileinfo = self.__files[_file]
                if os.path.getmtime(fullpath) != _fileinfo["last_modify"]:
                    self.update(_file, {
                        "required_sync": "UPDATE",
                        "md5": md5_by_file(fullpath),
                        "size": os.path.getsize(fullpath),
                        "last_modify": os.path.getmtime(fullpath),
                        "last_modify_formatted": time.ctime(os.path.getmtime(fullpath)),
                    })
                if not os.path.isfile(fullpath):
                    self.update(_file, {"required_sync": "DELETE"})
        for _file in self.__files:
            if _file not in current_files:
                self.update(_file, {"required_sync": "DELETE"})
                _changes += 1
        _end = time.time()
        print(
            "Done. Found all files:", len(current_files), ". \n"
            "   Changes: ", _changes, ", Elapsed ", _end - _start, "sec"
        )


class BoSocketClient:
    """ Implementation for clietn protocol """
    def __init__(self, config):
        self.__config = config
        self.__hostport = self.__config['server_host'] + ":" + str(self.__config['server_port'])
        self.__sock = None

    def check_connection(self):
        """ check connection """
        try:
            print("Check connecting... " + self.__hostport)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(15)
            sock.connect((self.__config['server_host'], self.__config['server_port']))
            _ = sock.recv(1024).decode("utf-8")
            sock.close()
        except socket.timeout:
            return False
        except socket.error as serr:
            if serr.errno == errno.ECONNREFUSED:
                return False
            print(serr)
            return False
        except Exception as err:  # pylint: disable=broad-except
            fatal(112, "Exception is " + str(err))
        return True

    def __send_param(self, name, value):
        """ send command """
        name = name.strip()
        value = str(value).strip()
        command = name + " " + value
        command = command.strip()
        print(command)
        command += "\n"
        self.__sock.send(command.encode())
        resp = self.__sock.recv(1024).decode("utf-8")
        accepted = ""
        if len(resp) >= 8:
            accepted = resp[:8]
        # LATER: check value
        if accepted != "ACCEPTED":
            fatal(7, "Expected [ACCEPTED] but got [" + str(resp) + "]")
        print(resp)

    def __action_request(self):
        """ action_request """
        command = "ACTION_REQUEST"
        print(command)
        command += "\n"
        self.__sock.send(command.encode())
        resp = self.__sock.recv(1024).decode("utf-8")
        resp = resp.strip()
        print(resp)
        return resp

    def __output_request(self):
        """ OUTPUT_request """
        command = "OUTPUT_REQUEST"
        # print(command)
        command += "\n"
        self.__sock.send(command.encode())
        resp = self.__sock.recv(1024).decode("utf-8")
        if resp.startswith("OUTPUT "):
            print(resp[len("OUTPUT "):], end='', sep='')
        if resp.startswith("OUTPUT_FINISHED "):
            print(">>>> Exit status: " + resp[len("OUTPUT_FINISHED "):] + "\n\n", end='', sep='')
            return None
        if resp.startswith("OUTPUT_FAILED "):
            print(">>>> FAILED status: " + resp[len("OUTPUT_FAILED "):] + "\n\n", end='', sep='')
            return None
        # resp = resp.strip()
        # print("[" + resp + "]")
        return resp

    def __send_file(self, _filepath):
        """ send file """
        print("SEND FILE " + _filepath)
        with open(_filepath, 'rb') as _file:
            while True:
                data = _file.read(SEND_BUFFER_SIZE)
                if not data:
                    break
                self.__sock.send(data)
        self.__sock.send("".encode())
        resp = self.__sock.recv(1024).decode("utf-8")
        accepted = ""
        if len(resp) >= 8:
            accepted = resp[:8]
        if accepted != "ACCEPTED":
            fatal(8, "Expected [ACCEPTED] but got [" + str(resp) + "]")
        print(resp)

    def run_sync(self, _files: BoFilesCache):
        """ run sync """
        cache_md5 = md5_by_file(_files.get_cache_path_to_update())
        cache_size = os.path.getsize(_files.get_cache_path_to_update())
        try:
            print("Connecting... " + self.__hostport)
            self.__sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.__sock.settimeout(15)
            self.__sock.connect((self.__config['server_host'], self.__config['server_port']))
            _ = self.__sock.recv(1024).decode("utf-8")
            self.__send_param("TARGET_DIR", self.__config['target_dir'])
            self.__send_param("CACHE_MD5", cache_md5)
            self.__send_param("CACHE_SIZE", cache_size)
            self.__send_param("SEND_BUFFER_SIZE", SEND_BUFFER_SIZE)
            self.__send_param("CACHE_SEND", 1)
            print("Sending cache... ")
            self.__send_file(_files.get_cache_path_to_update())

            _action = self.__action_request()
            while _action != "ACTIONS_COMPLETED":
                if _action.startswith("ACTION_DELETED "):
                    _filename = _action[len("ACTION_DELETED "):]
                    if _files.has(_filename):
                        _files.remove(_filename)
                    _files.resave_cache()
                elif _action.startswith("ACTION_SEND_ME_FILE "):
                    _file = _action[len("ACTION_SEND_ME_FILE "):]
                    _fullpath = os.path.join(BO_WORKDIR, _file)
                    self.__send_file(_fullpath)
                    _files.update(_file, {"required_sync": "NONE"})
                else:
                    print("ERROR UNKNOWN ACTION -> ", _action)

                _action = self.__action_request()
            _files.resave_cache()

            # _ = s.recv(1024).decode("utf-8")
            # s.send(str(flag + "\n").encode())
            # _ = s.recv(1024).decode("utf-8")
            self.__sock.close()
        except socket.timeout:
            fatal(8, "Socket timeout")
        except socket.error as serr:
            if serr.errno == errno.ECONNREFUSED:
                fatal(9, "Connection refused")
            else:
                print(serr)
                fatal(10, "Socker error " + str(serr))
        except Exception as err:  # pylint: disable=broad-except
            fatal(11, "Exception is " + str(err))
            # self.__sock = None
        sys.exit(0)

    def run_command(self, _subdir, _command):
        """ Run remote command """
        try:
            print("Connecting... " + self.__hostport)
            self.__sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # self.__sock.settimeout(15)
            self.__sock.connect((self.__config['server_host'], self.__config['server_port']))
            _ = self.__sock.recv(1024).decode("utf-8")
            self.__send_param("TARGET_DIR", self.__config['target_dir'])
            self.__send_param("SUB_DIR", _subdir)
            self.__send_param("RUN_COMMAND", json.dumps(_command))
            _output = self.__output_request()
            while _output is not None:
                _output = self.__output_request()
        except socket.timeout:
            fatal(8, "Socket timeout")
        except socket.error as serr:
            if serr.errno == errno.ECONNREFUSED:
                fatal(9, "Connection refused")
            else:
                print(serr)
                fatal(10, "Socker error " + str(serr))
        except Exception as err:  # pylint: disable=broad-except
            fatal(11, "Exception is " + str(err))
            # self.__sock = None


class BoCommand:
    """ Command like SOME ...value """
    def __init__(self, buf=None):
        self.__command = None
        self.__value = None
        self.parse(buf)

    def parse(self, buf):
        """ parse command from buf """
        if buf is None or buf == "":
            self.__command = None
            self.__value = None
            return
        self.__command = re.search(r"\w*", buf).group()
        if len(buf) <= len(self.__command):
            self.__value = ""
        else:
            self.__value = buf[len(self.__command + " "):]
            self.__value = self.__value.strip()

    def get_value(self):
        """ return value from command but if not so return empty string """
        return self.__value

    def get_command(self):
        """ return command name """
        return self.__command


class BoServerSocketHandler(threading.Thread):
    """
        handler for process connection in different thread
    """
    def __init__(self, _sock, _addr, _server):
        self.__sock = _sock
        self.__addr = _addr
        self.__is_kill = False
        self.__send_buffer_size = 512
        self.__options = {}
        self.__server = _server
        self.__cache = {}
        print("Connected from " + str(self.__addr))
        threading.Thread.__init__(self)

    def __receive_file(self, filepath, file_md5, file_size):
        """ __process_command_get """
        print(
            "Receiving file... " + filepath + " (" + str(file_size) + " bytes) " +
            "per " + str(self.__send_buffer_size) + " bytes"
        )
        _received_bytes = 0
        with open(filepath, 'wb') as _file:
            while _received_bytes < file_size:
                data = self.__sock.recv(self.__send_buffer_size)
                if len(data) > 0:
                    _received_bytes += len(data)
                    _file.write(data)
                else:
                    break
        got_file_md5 = md5_by_file(filepath)
        if file_md5 != got_file_md5:
            self.__sock.send("WRONG_MD5".encode())
            print("WRONG_MD5")
            print("Expected: " + file_md5)
            print("Got: " + got_file_md5)
            return False
        print("Done")
        self.__sock.send("ACCEPTED".encode())
        return True

    def __read_command(self, command: BoCommand):
        buf = self.__sock.recv(1024).decode("utf-8").strip()
        print("buf=", buf)
        if buf == "":
            command.parse(None)
        # print(buf)
        command.parse(buf)

    def __handle_command_target_dir(self, command):
        if command.get_command() == "TARGET_DIR":
            self.__options["target_dir"] = command.get_value()
            print("target_dir: '" + self.__options["target_dir"] + "'")
            self.__sock.send(str("ACCEPTED " + self.__options["target_dir"]).encode())
        return True

    def __handle_command_sub_dir(self, command):
        if command.get_command() == "SUB_DIR":
            self.__options["sub_dir"] = command.get_value()
            print("sub_dir: '" + self.__options["sub_dir"] + "'")
            self.__sock.send(str("ACCEPTED " + self.__options["sub_dir"]).encode())
        return True

    def __handle_command_cache_md5(self, command):
        if command.get_command() == "CACHE_MD5":
            self.__options["cache_md5"] = command.get_value()
            print("cache_md5: " + self.__options["cache_md5"])
            self.__sock.send(str("ACCEPTED " + self.__options["cache_md5"]).encode())
        return True

    def __handle_command_cache_size(self, command):
        if command.get_command() == "CACHE_SIZE":
            self.__options["cache_size"] = command.get_value()
            self.__options["cache_size"] = int(self.__options["cache_size"])
            print("cache_size: " + str(self.__options["cache_size"]))
            self.__sock.send(str("ACCEPTED " + str(self.__options["cache_size"])).encode())
        return True

    def __handle_command_send_buffer_size(self, command):
        if command.get_command() == "SEND_BUFFER_SIZE":
            self.__send_buffer_size = command.get_value()
            self.__send_buffer_size = int(self.__send_buffer_size)
            print("send_buffer_size: " + str(self.__send_buffer_size))
            self.__sock.send(str("ACCEPTED " + str(self.__send_buffer_size)).encode())
        return True

    def __handle_command_cache_send(self, command):
        if command.get_command() == "CACHE_SEND":
            self.__sock.send("ACCEPTED".encode())
            self.__receive_file(
                "test", self.__options["cache_md5"],
                self.__options["cache_size"]
            )
            if os.path.isfile("test"):
                with open("test", encoding="utf-8") as _file:
                    try:
                        self.__cache = yaml.safe_load(_file)
                    except yaml.YAMLError as _exc:
                        print(_exc)
                        self.__sock.send("FAILED".encode())
                        return False
                os.remove("test")
        return True

    def __handle_command_action_request(self, command):
        if command.get_command() == "ACTION_REQUEST":
            for _file, _info in self.__cache.items():
                print(_file, _info)
                _fullpath = os.path.join(self.__options["target_dir"], _file)
                if _info['required_sync'] == 'DELETE':
                    if os.path.isfile(_fullpath):
                        os.remove(_fullpath)
                        if not os.path.isfile(_fullpath):
                            self.__sock.send(str("ACTION_DELETED " + _file).encode())
                            self.__read_command(command)
                            continue
                    else:
                        self.__sock.send(str("ACTION_DELETED " + _file).encode())
                        self.__read_command(command)
                        continue
                elif _info['required_sync'] == 'UPDATE':
                    _parent_dir = os.path.dirname(_fullpath)
                    print("_parent_dir", _parent_dir)
                    os.makedirs(_parent_dir, exist_ok=True)
                    self.__sock.send(str("ACTION_SEND_ME_FILE " + _file).encode())
                    if not self.__receive_file(_fullpath, _info["md5"], _info["size"]):
                        break
                    self.__read_command(command)
            self.__sock.send(str("ACTIONS_COMPLETED").encode())
        return True

    def __send_output_line(self, command: BoCommand, _line):
        print("_line1", _line)
        self.__sock.send(str("OUTPUT " + _line).encode())
        self.__read_command(command)

    def __handle_command_run_command(self, command: BoCommand):
        cmds = json.loads(command.get_value())
        self.__sock.send(str("ACCEPTED " + str(cmds)).encode())
        self.__read_command(command)
        if command.get_command() != "OUTPUT_REQUEST":
            self.__sock.send(str("FAILED").encode())
            return False
        if is_linux():
            cmds = ['sh', '-c'] + cmds
        if is_windows():
            cmds = ['cmd', '/c'] + cmds
        _cwd = os.path.join(self.__options["target_dir"], self.__options["sub_dir"])
        if not os.path.isdir(_cwd):
            self.__sock.send(str("OUTPUT_FAILED " + _cwd + " - not found directory").encode())
            return False
        self.__send_output_line(command, ">>>> Directory: " + _cwd + "\n")
        self.__send_output_line(command, ">>>> Command: " + str(cmds) + "\n")
        self.__send_output_line(command, ">>>> Output: " + str(cmds) + "\n")
        _proc = subprocess.Popen(  # pylint: disable=consider-using-with
            cmds,
            cwd=_cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
        )
        _returncode = _proc.poll()
        _line = _proc.stdout.readline()
        if _line:
            self.__send_output_line(command, _line.decode("utf-8"))
        while _returncode is None:
            _returncode = _proc.poll()
            _line = _proc.stdout.readline()
            if _line:
                self.__send_output_line(command, _line.decode("utf-8"))
        while _line:
            _line = _proc.stdout.readline()
            if _line:
                self.__send_output_line(command, _line.decode("utf-8"))
            else:
                break
        self.__sock.send(str("OUTPUT_FINISHED " + str(_returncode)).encode())
        return True

    def run(self):
        welcome_s = "Welcome to bo server\n"
        welcome_s += "target_dir? "
        self.__sock.send(welcome_s.encode())
        _handlers = {
            "TARGET_DIR": self.__handle_command_target_dir,
            "SUB_DIR": self.__handle_command_sub_dir,
            "CACHE_MD5": self.__handle_command_cache_md5,
            "SEND_BUFFER_SIZE": self.__handle_command_send_buffer_size,
            "CACHE_SIZE": self.__handle_command_cache_size,
            "CACHE_SEND": self.__handle_command_cache_send,
            "ACTION_REQUEST": self.__handle_command_action_request,
            "RUN_COMMAND": self.__handle_command_run_command,
        }
        command = BoCommand()
        while True:
            if self.__is_kill is True:
                break
            self.__read_command(command)
            if command.get_command() is None:
                print("command is none. break")
                break
            if command.get_command() in _handlers:
                if not _handlers[command.get_command()](command):
                    print("command is failed. break")
                    break
            else:
                resp = "\n '" + command.get_command() + "' unknown command\n\n"
                print("FAIL: unknown command '" + command.get_command() + "'")
                self.__sock.send(resp.encode())
                break
        self.__close_socket()

    def __close_socket(self):
        self.__is_kill = True
        self.__sock.close()
        self.__server.remove_thread(self)

    def kill(self):
        """ stop thread """
        if self.__is_kill is True:
            return
        self.__is_kill = True
        self.__sock.close()
        # thrs.remove(self)


class BoServer():
    """
        Server multitreading implementation
    """
    def __init__(self, host, port):
        self.__host = host
        self.__port = port
        self.__thrs = []

    def remove_thread(self, thrd):
        """ remove from threads """
        self.__thrs.remove(thrd)

    def start(self):
        """ start server """
        _srv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _srv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        _srv_sock.bind((self.__host, self.__port))
        _srv_sock.listen(10)

        print('Start service listening ' + self.__host + ':' + str(self.__port))

        try:
            while True:
                _cli_sock, addr = _srv_sock.accept()
                thr = BoServerSocketHandler(_cli_sock, addr, self)
                self.__thrs.append(thr)
                thr.start()
        except KeyboardInterrupt:
            print('Bye! Write me letters!')
            _srv_sock.close()
            for thr in self.__thrs:
                thr.kill()


if os.path.isfile(BO_CONFIG_FILEPATH):
    with open(BO_CONFIG_FILEPATH, encoding="utf-8") as _file:
        try:
            BO_CONFIG = yaml.safe_load(_file)
        except yaml.YAMLError as exc:
            print(exc)
            fatal(2, "Problem with reading config, description: " + str(exc))
else:
    resave_config()

if "workdirs" not in BO_CONFIG:
    BO_CONFIG["workdirs"] = {}
# print(BO_HOME_CONFIG_DIR)
# print(CURRENT_DIR)

RESERVED_SUBCOMMAND_0 = ["config", "sync", "server", "remote"]

SUBCOMMANDS = []
i = 1  # skip first element
while i < len(sys.argv):
    SUBCOMMANDS.append(sys.argv[i])
    i += 1
while len(SUBCOMMANDS) < 10:
    SUBCOMMANDS.append("")

if "help" in SUBCOMMANDS:
    print(
        "Usage:\n"
        "    'bo config init' - add current directory to config\n"
        "    'bo config deinit' - remove current directory from config\n"
        "    'bo config command' - Init command for current directory\n"
        "    'bo config remove-command <cmd_name>' - Init command for current directory\n"
        "    'bo config ls' - print configs\n"
        "    'bo config path' - path to config file\n"
        "    'bo sync' - partial sync to remote server\n"
        "    'bo remote run <cmd> <arg1> <arg2> ... <argN>' - call command on remote host \n"
        "    'bo server' - start server\n"
        "\n"
    )
    sys.exit(0)


def find_root_bo_work_dir(_current_dir):
    """ Find root bo workdir """
    _ret = None
    _tmp_dir = _current_dir
    _infinite_loop_protection = 0
    while len(_tmp_dir) > 0:
        _infinite_loop_protection += 1
        if _tmp_dir in BO_CONFIG["workdirs"]:
            _ret = _tmp_dir
            break
        _tmp_dir = os.path.normpath(os.path.join(_tmp_dir, '..'))
        if _tmp_dir == '/':
            break
        if _tmp_dir == 'C:\\':
            break
        if _infinite_loop_protection > 100:
            break
    return _ret


BO_WORKDIR = find_root_bo_work_dir(CURRENT_DIR)


if BO_WORKDIR is not None:
    print("Found workdir in config: ", BO_WORKDIR)

if SUBCOMMANDS[0] == "config":
    if SUBCOMMANDS[1] == "deinit":
        if BO_WORKDIR is None:
            fatal(5, "Not found initialize diretory: " + BO_WORKDIR)
        print("Removing " + BO_WORKDIR + " from config\n")
        del BO_CONFIG["workdirs"][BO_WORKDIR]
        resave_config()
        print("Done.")
    elif SUBCOMMANDS[1] == "init":
        if BO_WORKDIR is not None:
            fatal(4, "Already initialized directory: " + CURRENT_DIR)
        SERVER0 = input("Server: ")
        TARGET_DIR = input("Target dir: ")
        _cache_filename = CURRENT_DIR + "|" + TARGET_DIR + "|" + SERVER0
        CACHE_PATH = os.path.join(
            BO_HOME_CONFIG_DIR,
            hashlib.md5(_cache_filename.encode('utf-8')).hexdigest() + ".yml"
        )
        BO_CONFIG["workdirs"][CURRENT_DIR] = {
            "servers": {
                "base": {
                    "host": SERVER0,
                    "port": 4319,
                    "target_dir": TARGET_DIR,
                    "cache_path": CACHE_PATH,
                }
            },
        }
        resave_config()
        print("Done.")
        sys.exit(0)
    elif SUBCOMMANDS[1] == "command":
        if BO_WORKDIR is None:
            fatal(4, "Not initialized current directory: " + CURRENT_DIR)
        if "commands" not in BO_CONFIG["workdirs"][BO_WORKDIR]:
            BO_CONFIG["workdirs"][BO_WORKDIR]["commands"] = {}
        _cfg_cmds = BO_CONFIG["workdirs"][BO_WORKDIR]["commands"]
        COMMAND_NAME = SUBCOMMANDS[2]  # possible get from command line params
        if COMMAND_NAME == "":
            COMMAND_NAME = input("Command Name: ").strip()
        else:
            print("Command Name: " + COMMAND_NAME)
        if COMMAND_NAME == "":
            fatal(103, "Command '" + COMMAND_NAME + "' could not be empty")
        if COMMAND_NAME in _cfg_cmds:
            fatal(
                104,
                "Command '" + COMMAND_NAME + "' - alredy defined, please " +
                "try another command or remove: 'bo config remove-command " + COMMAND_NAME + "'"
            )
        if COMMAND_NAME in RESERVED_SUBCOMMAND_0:
            fatal(
                105,
                "Command '" + COMMAND_NAME + "' is reserved command name, " +
                "please try again with another name"
            )
        _cfg_cmds[COMMAND_NAME] = []
        NEW_COMMAND = "."
        while NEW_COMMAND != "":
            COMMAND = input("Command (empty string will be finish entry): ")
            COMMAND = COMMAND.strip()
            if COMMAND == "":
                break
            _cfg_cmds[COMMAND_NAME].append(COMMAND)
        BO_CONFIG["workdirs"][CURRENT_DIR]["commands"] = _cfg_cmds
        resave_config()
        print("Done.")
        sys.exit(0)
    elif SUBCOMMANDS[1] == "remove-command":
        command_name = SUBCOMMANDS[2]
        if command_name == "":
            fatal(
                110,
                "Expected name of command for remove, like " +
                "'bo config remove-command cmd_name' replace cmd_name to your existing command"
            )
        if CURRENT_DIR not in BO_CONFIG["workdirs"]:
            fatal(111, "Not initialized current directory: " + CURRENT_DIR)
        if "commands" not in BO_CONFIG["workdirs"][CURRENT_DIR]:
            BO_CONFIG["workdirs"][CURRENT_DIR]["commands"] = {}
        if command_name not in BO_CONFIG["workdirs"][CURRENT_DIR]["commands"]:
            fatal(112, "Not found registered command " + command_name)
        del BO_CONFIG["workdirs"][CURRENT_DIR]["commands"][command_name]
        resave_config()
        print("Done.")
        sys.exit(0)
    elif SUBCOMMANDS[1] == "ls":
        for _workdir in BO_CONFIG["workdirs"]:
            _item = BO_CONFIG["workdirs"][_workdir]
            print("Dir: " + _workdir)
            for _server in _item["servers"]:
                print("  -> Server '" + _server + "'")
                _server = _item["servers"][_server]
                print("     - Host: " + _server["host"])
                print("     - Target Directory: " + _server["target_dir"])
                print("     - Cache: " + _server["cache_path"])
        print("")
        sys.exit(0)
    elif SUBCOMMANDS[1] == "path":
        print("BO_CONFIG_FILEPATH: " + BO_CONFIG_FILEPATH)
    else:
        fatal(3, "Unknown sub command '" + SUBCOMMANDS[1] + "'")
    sys.exit(0)

if SUBCOMMANDS[0] == "sync":
    if BO_WORKDIR is None:
        fatal(6, "Not found config for directory '" + CURRENT_DIR + "'")
    TO_SERVER = "base"
    if SUBCOMMANDS[1] in BO_CONFIG["workdirs"][BO_WORKDIR]["servers"]:
        TO_SERVER = SUBCOMMANDS[1]
    cfg = BO_CONFIG["workdirs"][BO_WORKDIR]["servers"][TO_SERVER]
    SERVER_HOST = cfg["host"]
    SERVER_PORT = cfg["port"]
    TARGET_DIR = cfg["target_dir"]
    print(
        "Start syncing files\n    >from: " + BO_WORKDIR + " \n"
        "    >to: " + SERVER_HOST + ":" + str(SERVER_PORT)
    )
    cache_path = cfg["cache_path"]
    FILES = BoFilesCache(cache_path)

    FILES.rescan_files(BO_WORKDIR)
    start = time.time()
    print("Updating cache...")
    FILES.resave_cache()
    end = time.time()
    print("Done. Elapsed ", end - start, "sec")
    client = BoSocketClient({
        "target_dir": TARGET_DIR,
        "server_host": SERVER_HOST,
        "server_port": SERVER_PORT,
    })
    client.run_sync(FILES)

if SUBCOMMANDS[0] == "server":
    bo_server = BoServer("", 4319)
    bo_server.start()

if SUBCOMMANDS[0] == "remote":
    TO_SERVER = "base"
    if SUBCOMMANDS[2] in BO_CONFIG["workdirs"][BO_WORKDIR]["servers"]:
        TO_SERVER = SUBCOMMANDS[2]
    cfg = BO_CONFIG["workdirs"][BO_WORKDIR]["servers"][TO_SERVER]
    SERVER_HOST = cfg["host"]
    SERVER_PORT = cfg["port"]
    TARGET_DIR = cfg["target_dir"]

    if SUBCOMMANDS[1] == "run":
        print("Run command on remote host " + SERVER_HOST + ":" + str(SERVER_PORT))
        client = BoSocketClient({
            "target_dir": TARGET_DIR,
            "server_host": SERVER_HOST,
            "server_port": SERVER_PORT,
        })
        _SUB_DIR = CURRENT_DIR[len(BO_WORKDIR)+1:]
        _COMMANDS = SUBCOMMANDS[2:]
        while _COMMANDS[-1] == "":
            _COMMANDS = _COMMANDS[:-1]
        client.run_command(_SUB_DIR, _COMMANDS)
        sys.exit(0)
    # elif SUBCOMMANDS[1] == "nowait-run":
    #     sys.exit(0)
    # elif SUBCOMMANDS[1] == "kill-process":
    #     sys.exit(0)
    else:
        sys.exit("Unknown subcomannd for remote '" + SUBCOMMANDS[1] + "'")

if BO_WORKDIR is not None:
    WORKDIR_CFG = BO_CONFIG["workdirs"][BO_WORKDIR]
    if 'commands' in WORKDIR_CFG and SUBCOMMANDS[0] in WORKDIR_CFG['commands']:
        _command = SUBCOMMANDS[0]
        _commands = BO_CONFIG["workdirs"][BO_WORKDIR]['commands'][_command]
        print("Found command ", _command)
        for _cmd in _commands:
            print("TODO run> ", _cmd)
        sys.exit(0)


sys.exit("Could not understand please call 'bo help'")
