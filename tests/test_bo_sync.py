#!/usr/bin/env python3
"""
Simple end-to-end test for bo.py:
  - starts 'bo.py server' in a subprocess
  - creates a temp workdir and a temp target dir
  - registers workdir in an isolated BO_HOME/config.yml
  - runs 'bo.py sync' and verifies file trees match
  - modifies files, re-syncs, verifies again
  - stops server, cleans up

Run:
    python3 test_bo_sync.py
"""

import os
import sys
import shutil
import socket
import subprocess
import time
import hashlib

import yaml

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BO_PY = os.path.normpath(os.path.join(THIS_DIR, "..", "bo.py"))

TMP_TEST_BO_SYNC = os.path.join(THIS_DIR, "tmp_test_bo_sync")

SERVER_PORT = 4319
SERVER_HOST = "127.0.0.1"


def md5_of_file(path):
    """Return md5 hex digest of a file."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def list_files(root):
    """Return dict {relative_path: md5} for all files under root, skipping .git."""
    result = {}
    for dirpath, dirnames, filenames in os.walk(root):
        # skip .git
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            result[rel] = md5_of_file(full)
    return result


def wait_port(host, port, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def write_file(path, content):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "wt", encoding="utf-8") as _file:
        _file.write(content)


def run_sync(workdir, env):
    """Run 'bo.py sync' from workdir with isolated BO_HOME."""
    proc = subprocess.run(
        [sys.executable, BO_PY, "sync"],
        cwd=workdir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )
    out = proc.stdout.decode(errors="replace")
    print(out)
    if proc.returncode != 0:
        raise RuntimeError("bo sync failed with code " + str(proc.returncode))


def main():
    print("=== bo end-to-end test ===")

    if not os.path.isfile(BO_PY):
        print("ERROR: bo.py not found at", BO_PY)
        sys.exit(1)

    if os.path.isdir(TMP_TEST_BO_SYNC):
        shutil.rmtree(TMP_TEST_BO_SYNC, ignore_errors=True)
    os.makedirs(TMP_TEST_BO_SYNC)

    workdir = os.path.join(TMP_TEST_BO_SYNC, "work")
    target_dir = os.path.join(TMP_TEST_BO_SYNC, "target")
    bo_home = os.path.join(TMP_TEST_BO_SYNC, "bo_home")
    os.makedirs(workdir, exist_ok=True)
    os.makedirs(target_dir, exist_ok=True)
    os.makedirs(bo_home, exist_ok=True)
    print("workdir   :", workdir)
    print("target_dir:", target_dir)
    print("bo_home   :", bo_home)

    # env for all bo.py subprocesses
    child_env = os.environ.copy()
    child_env["BO_HOME"] = bo_home

    server_proc = None
    exit_code = 0

    try:
        # ---- prepare initial files in workdir
        write_file(os.path.join(workdir, "hello.txt"), "hello world\n")
        write_file(os.path.join(workdir, "sub", "nested.txt"), "nested content\n")
        write_file(os.path.join(workdir, "sub", "deep", "deep.txt"), "deep content\n")
        write_file(os.path.join(workdir, "empty.txt"), "")

        # ---- write test config inside isolated BO_HOME
        cache_filename = workdir + "|" + target_dir + "|" + SERVER_HOST
        cache_path = os.path.join(
            bo_home,
            hashlib.md5(cache_filename.encode()).hexdigest() + ".sqlite"
        )

        cfg = {
            "bo_version": "test",
            "workdirs": {
                workdir: {
                    "servers": {
                        "base": {
                            "host": SERVER_HOST,
                            "port": SERVER_PORT,
                            "target_dir": target_dir,
                            "cache_path": cache_path,
                        }
                    }
                }
            },
        }
        config_path = os.path.join(bo_home, "config.yml")
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, indent=2)
        print("Wrote test config:", config_path)

        # ---- start server (with BO_HOME)
        print("Starting bo server ...")
        server_proc = subprocess.Popen(
            [sys.executable, BO_PY, "server"],
            cwd=TMP_TEST_BO_SYNC,
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if not wait_port(SERVER_HOST, SERVER_PORT, timeout=5.0):
            print("ERROR: server did not start on", SERVER_HOST, SERVER_PORT)
            if server_proc.poll() is not None:
                print(server_proc.stdout.read().decode(errors="replace"))
            exit_code = 2
            return
        print("Server is up on", SERVER_HOST, SERVER_PORT)

        # ---- first sync
        print("\n--- first sync ---")
        run_sync(workdir, child_env)

        expected = list_files(workdir)
        actual = list_files(target_dir)
        if expected != actual:
            print("MISMATCH after first sync!")
            print("expected:", expected)
            print("actual  :", actual)
            exit_code = 3
            return
        print("OK: trees match after first sync")

        # ---- modify files and re-sync
        print("\n--- modify and re-sync ---")
        time.sleep(1.1)
        write_file(os.path.join(workdir, "hello.txt"), "hello world v2\n")
        write_file(os.path.join(workdir, "new.txt"), "brand new file\n")
        os.remove(os.path.join(workdir, "empty.txt"))
        write_file(os.path.join(workdir, "sub", "nested.txt"), "nested v2\n")
        run_sync(workdir, child_env)

        expected = list_files(workdir)
        actual = list_files(target_dir)
        if expected != actual:
            print("MISMATCH after second sync!")
            print("expected:", expected)
            print("actual  :", actual)
            exit_code = 4
            return
        print("OK: trees match after second sync")

        # ---- delete files and re-sync
        print("\n--- delete and re-sync ---")
        time.sleep(1.1)
        os.remove(os.path.join(workdir, "new.txt"))
        shutil.rmtree(os.path.join(workdir, "sub", "deep"))
        run_sync(workdir, child_env)

        expected = list_files(workdir)
        actual = list_files(target_dir)
        if expected != actual:
            print("MISMATCH after third sync!")
            print("expected:", expected)
            print("actual  :", actual)
            exit_code = 5
            return
        print("OK: trees match after third sync")

        print("\n=== ALL TESTS PASSED ===")

    finally:
        if server_proc is not None and server_proc.poll() is None:
            print("\nStopping server ...")
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_proc.kill()
                server_proc.wait(timeout=5)
            print("Server stopped")

        shutil.rmtree(TMP_TEST_BO_SYNC, ignore_errors=True)
        print("Cleaned up", TMP_TEST_BO_SYNC)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()