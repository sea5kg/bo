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
import hashlib
from pathlib import Path
import yaml

BUF_READ_SIZE = 65536

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
    with open(BO_CONFIG_FILEPATH, 'w') as _file:
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
                _ret.append(_filepath)
    return _ret


if os.path.isfile(BO_CONFIG_FILEPATH):
    with open(BO_CONFIG_FILEPATH) as _file:
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
                    "target_dir": TARGET_DIR,
                    "cache_path": CACHE_PATH,
                }
            },
        }
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
    print("Start syncing files\n    >from: " + CURRENT_DIR + " \n    >to: " + cfg["host"])
    cache_path = cfg["cache_path"]
    FILES = {}
    if os.path.isfile(cache_path):
        with open(cache_path) as _file:
            try:
                FILES = yaml.safe_load(_file)
            except yaml.YAMLError as exc:
                print(exc)
                sys.exit(exc)

    print("Scanning files...")
    start = time.time()
    current_files = get_all_files(CURRENT_DIR)
    _CHANGES = 0
    for filepath in current_files:
        if filepath not in FILES:
            md5 = hashlib.md5()
            with open(filepath, 'rb') as _file:
                while True:
                    data = _file.read(BUF_READ_SIZE)
                    if not data:
                        break
                    md5.update(data)
            FILES[filepath] = {
                "todo_sync": True,
                "operation_sync": "UPDATE",
                "md5": md5.hexdigest(),
                "last_modify": os.path.getmtime(filepath),
                "last_modify_formatted": time.ctime(os.path.getmtime(filepath)),
            }
            _CHANGES += 1
        else:
            _fileinfo = FILES[filepath]
            if os.path.getmtime(filepath) != _fileinfo["last_modify"]:
                FILES[filepath]["todo_sync"] = True
                FILES[filepath]["operation_sync"] = "UPDATE"
    for filepath in FILES:
        if filepath not in current_files:
            FILES[filepath]["todo_sync"] = True
            FILES[filepath]["operation_sync"] = "DELETE"
            _CHANGES += 1
    end = time.time()
    print(
        "Done. Found all files:", len(current_files), ". \n"
        "   Changes: ", _CHANGES, ", Elapsed ", end - start, "sec"
    )
    start = time.time()
    print("Updating cache...")
    with open(cache_path, 'w') as _file:
        yaml.dump(FILES, _file, indent=2)
    print("Done.")
    sys.exit(0)
