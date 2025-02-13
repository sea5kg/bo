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
import errno
import hashlib
from pathlib import Path
import yaml

BUF_READ_SIZE = 65536
SEND_BUFFER_SIZE = 512

VERSION = "v0.0.1"

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


class BoFilesCache:
    """ helper class for control of cache """

    def __init__(self, _cache_path):
        self.__files = {}
        self.__cache_path = _cache_path
        # load
        if os.path.isfile(self.__cache_path):
            with open(self.__cache_path, encoding="utf-8") as _file:
                try:
                    self.__files = yaml.safe_load(_file)
                except yaml.YAMLError as _exc:
                    print(_exc)
                    sys.exit(_exc)

    def resave_cache(self):
        """ resave file """
        with open(self.__cache_path, 'w', encoding="utf-8") as _file:
            yaml.dump(self.__files, _file, indent=2)

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

    def remove(self, _file):
        """ remove file from list """
        del self.__files[_file]

    def get_files(self):
        """ return all the file list """
        return self.__files


class BoSocketClient:
    """ Implementation for clietn protocol """
    def __init__(self, config, files):
        self.__config = config
        self.__hostport = self.__config['server_host'] + ":" + str(self.__config['server_port'])
        self.__files = files
        self.__sock = None

    def check_connection(self):
        """ check connection """
        try:
            print("Check connecting... " + self.__hostport)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
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

    def run_sync(self):
        """ run sync """
        cache_md5 = md5_by_file(self.__config['cache_path'])
        cache_size = os.path.getsize(self.__config['cache_path'])
        try:
            print("Connecting... " + self.__hostport)
            self.__sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.__sock.settimeout(1)
            self.__sock.connect((self.__config['server_host'], self.__config['server_port']))
            _ = self.__sock.recv(1024).decode("utf-8")
            self.__send_param("TARGET_DIR", self.__config['target_dir'])
            self.__send_param("CACHE_MD5", cache_md5)
            self.__send_param("CACHE_SIZE", cache_size)
            self.__send_param("SEND_BUFFER_SIZE", SEND_BUFFER_SIZE)
            self.__send_param("CACHE_SEND", 1)
            print("Sending cache... ")
            self.__send_file(self.__config['cache_path'])

            _action = self.__action_request()
            while _action != "ACTIONS_COMPLETED":
                if _action.startswith("ACTION_DELETED "):
                    _filename = _action[len("ACTION_DELETED "):]
                    if self.__files.has(_filename):
                        self.__files.remove(_filename)
                    self.__files.resave_cache()
                elif _action.startswith("ACTION_SEND_ME_FILE "):
                    _file = _action[len("ACTION_SEND_ME_FILE "):]
                    _fullpath = os.path.join(CURRENT_DIR, _file)
                    self.__send_file(_fullpath)
                    self.__files.update(_file, {"required_sync": "NONE"})
                else:
                    print("ERROR UNKNOWN ACTION -> ", _action)

                _action = self.__action_request()
            self.__files.resave_cache()

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
        "    'bo config ls' - print configs\n"
        "    'bo config path' - path to config file\n"
        "    'bo sync' - partial sync to remote server\n"
        "\n"
    )
    sys.exit(0)

if SUBCOMMANDS[0] == "config":
    if SUBCOMMANDS[1] == "deinit":
        if CURRENT_DIR not in BO_CONFIG["workdirs"]:
            fatal(5, "Not found initialize diretory: " + CURRENT_DIR)
        print("Removing " + CURRENT_DIR + " from config\n")
        del BO_CONFIG["workdirs"][CURRENT_DIR]
        resave_config()
        print("Done.")
    elif SUBCOMMANDS[1] == "init":
        if CURRENT_DIR in BO_CONFIG["workdirs"]:
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
        if CURRENT_DIR not in BO_CONFIG["workdirs"]:
            fatal(4, "Not initialized current directory: " + CURRENT_DIR)
        if "commands" not in BO_CONFIG["workdirs"][CURRENT_DIR]:
            BO_CONFIG["workdirs"][CURRENT_DIR]["commands"] = {}
        _cfg_cmds = BO_CONFIG["workdirs"][CURRENT_DIR]["commands"]
        COMMAND_NAME = input("Command Name: ")
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

if SUBCOMMANDS[0] == "sync":
    if CURRENT_DIR not in BO_CONFIG["workdirs"]:
        fatal(6, "Not found config for directory '" + CURRENT_DIR + "'")
    TO_SERVER = "base"
    if SUBCOMMANDS[1] in BO_CONFIG["workdirs"][CURRENT_DIR]["servers"]:
        TO_SERVER = SUBCOMMANDS[1]
    cfg = BO_CONFIG["workdirs"][CURRENT_DIR]["servers"][TO_SERVER]
    SERVER_HOST = cfg["host"]
    SERVER_PORT = cfg["port"]
    TARGET_DIR = cfg["target_dir"]
    print(
        "Start syncing files\n    >from: " + CURRENT_DIR + " \n"
        "    >to: " + SERVER_HOST + ":" + str(SERVER_PORT)
    )
    cache_path = cfg["cache_path"]
    FILES = BoFilesCache(cache_path)

    print("Scanning files...")
    start = time.time()
    current_files = get_all_files(CURRENT_DIR)
    _CHANGES = 0
    for _file in current_files:
        fullpath = os.path.join(CURRENT_DIR, _file)
        if not FILES.has(_file):
            FILES.add(_file, fullpath)
            _CHANGES += 1
        else:
            _fileinfo = FILES.get(_file)
            if os.path.getmtime(fullpath) != _fileinfo["last_modify"]:
                FILES.update(_file, {
                    "required_sync": "UPDATE",
                    "md5": md5_by_file(fullpath),
                    "size": os.path.getsize(fullpath),
                    "last_modify": os.path.getmtime(fullpath),
                    "last_modify_formatted": time.ctime(os.path.getmtime(fullpath)),
                })
            if not os.path.isfile(fullpath):
                FILES.update(_file, {"required_sync": "DELETE"})
    for _file in FILES.get_files():
        if _file not in current_files:
            FILES.update(_file, {"required_sync": "DELETE"})
            _CHANGES += 1
    end = time.time()
    print(
        "Done. Found all files:", len(current_files), ". \n"
        "   Changes: ", _CHANGES, ", Elapsed ", end - start, "sec"
    )
    start = time.time()
    print("Updating cache...")
    FILES.resave_cache()
    end = time.time()
    print("Done. Elapsed ", end - start, "sec")
    client = BoSocketClient({
        "cache_path": cache_path,
        "target_dir": TARGET_DIR,
        "server_host": SERVER_HOST,
        "server_port": SERVER_PORT,
    }, FILES)
    client.run_sync()
